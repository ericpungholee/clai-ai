from collections.abc import Callable

import pytest

from app.domain.runs import (
    ActivePin,
    ConnectEdge,
    MaskSnapshot,
    NodeSnapshot,
    Op,
    SubjectEdge,
    VersionPin,
    VersionSnapshot,
)
from app.services.frozen_request_codec import (
    decode_frozen_request,
    encode_frozen_request,
)
from app.services.operation_routing import OperationRoutingError, resolve_op
from app.services.prompt_builder import (
    PRESERVATION_PREAMBLE,
    WHITE_BACKGROUND_CLAUSE,
    build_prompt,
)
from app.services.run_freezing import freeze_run_request
from app.services.run_resolution import RunResolutionError, resolve_inputs


def version(
    version_id: str,
    node_id: str,
    *,
    seed: int = 7,
    edit_depth: int = 0,
) -> VersionSnapshot:
    return VersionSnapshot(
        id=version_id,
        node_id=node_id,
        artifact_url=f"https://artifacts.test/{version_id}.png",
        seed=seed,
        edit_depth=edit_depth,
    )


def fixed_seed(value: int = 314) -> Callable[[], int]:
    return lambda: value


@pytest.mark.parametrize(
    ("has_subject", "has_mask", "connect_count", "expected"),
    [
        (False, False, 0, Op.GENERATE),
        (False, False, 1, Op.GENERATE_REF),
        (True, False, 0, Op.EDIT_INSTRUCT),
        (True, True, 0, Op.EDIT_INPAINT),
        (True, True, 1, Op.EDIT_COMPOSITE),
        (True, False, 1, Op.EDIT_REF_GUIDED),
    ],
)
def test_resolve_op_covers_every_routing_row(
    has_subject: bool,
    has_mask: bool,
    connect_count: int,
    expected: Op,
) -> None:
    assert (
        resolve_op(
            has_subject=has_subject,
            has_mask=has_mask,
            connect_count=connect_count,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("has_subject", "has_mask", "connect_count"),
    [(False, True, 0), (False, True, 1), (True, False, -1), (True, False, 3)],
)
def test_resolve_op_rejects_invalid_states(
    has_subject: bool,
    has_mask: bool,
    connect_count: int,
) -> None:
    with pytest.raises(OperationRoutingError):
        resolve_op(
            has_subject=has_subject,
            has_mask=has_mask,
            connect_count=connect_count,
        )


def test_subject_pin_uses_pinned_version_while_connect_follows_active() -> None:
    target = NodeSnapshot(id="target", prompt="Combine them")
    subject_node = NodeSnapshot(
        id="subject-node",
        prompt="ancestor prompt must stay hidden",
        active_version_id="subject-new",
    )
    connect_node = NodeSnapshot(
        id="connect-node",
        prompt="another hidden ancestor prompt",
        active_version_id="connect-new",
    )
    versions = {
        candidate.id: candidate
        for candidate in (
            version("subject-old", "subject-node", seed=11),
            version("subject-new", "subject-node", seed=12),
            version("connect-old", "connect-node", seed=21),
            version("connect-new", "connect-node", seed=22),
        )
    }
    edges = (
        ConnectEdge(
            id="connect-edge",
            source_node_id="connect-node",
            target_node_id="target",
            pin=ActivePin(),
            order=0,
        ),
        SubjectEdge(
            id="subject-edge",
            source_node_id="subject-node",
            target_node_id="target",
            pin=VersionPin(version_id="subject-old"),
        ),
    )

    resolved = resolve_inputs(
        target=target,
        inbound_edges=edges,
        nodes={
            target.id: target,
            subject_node.id: subject_node,
            connect_node.id: connect_node,
        },
        versions=versions,
        random_seed=fixed_seed(),
    )

    assert resolved.subject == versions["subject-old"]
    assert resolved.connects == (versions["connect-new"],)
    assert resolved.seed == 11


def test_connects_are_resolved_in_contiguous_order() -> None:
    target = NodeSnapshot(id="target", prompt="Combine")
    first = NodeSnapshot(id="first", prompt="hidden", active_version_id="v1")
    second = NodeSnapshot(id="second", prompt="hidden", active_version_id="v2")
    versions = {"v1": version("v1", "first"), "v2": version("v2", "second")}

    resolved = resolve_inputs(
        target=target,
        inbound_edges=(
            ConnectEdge("e2", "second", "target", ActivePin(), order=1),
            ConnectEdge("e1", "first", "target", ActivePin(), order=0),
        ),
        nodes={node.id: node for node in (target, first, second)},
        versions=versions,
        random_seed=fixed_seed(),
    )

    assert resolved.connects == (versions["v1"], versions["v2"])


def test_resolution_rejects_second_subject_edge() -> None:
    target = NodeSnapshot(id="target", prompt="Edit")
    versions = {"v1": version("v1", "a"), "v2": version("v2", "b")}
    edges = (
        SubjectEdge("e1", "a", "target", VersionPin(version_id="v1")),
        SubjectEdge("e2", "b", "target", VersionPin(version_id="v2")),
    )

    with pytest.raises(RunResolutionError, match="at most one subject"):
        resolve_inputs(
            target=target,
            inbound_edges=edges,
            nodes={target.id: target},
            versions=versions,
            random_seed=fixed_seed(),
        )


def test_resolution_rejects_third_connect_edge() -> None:
    target = NodeSnapshot(id="target", prompt="Combine")
    sources = [
        NodeSnapshot(id=f"n{index}", prompt="hidden", active_version_id=f"v{index}")
        for index in range(3)
    ]
    versions = {f"v{index}": version(f"v{index}", f"n{index}") for index in range(3)}
    edges = tuple(
        ConnectEdge(
            f"e{index}",
            f"n{index}",
            "target",
            ActivePin(),
            order=index,
        )
        for index in range(3)
    )

    with pytest.raises(RunResolutionError, match="at most two connect"):
        resolve_inputs(
            target=target,
            inbound_edges=edges,
            nodes={node.id: node for node in (target, *sources)},
            versions=versions,
            random_seed=fixed_seed(),
        )


def test_resolution_rejects_stale_mask() -> None:
    target = NodeSnapshot(
        id="target",
        prompt="Replace the logo",
        mask=MaskSnapshot("1 2 3", 512, 512, subject_version_id="older"),
    )
    subject = version("current", "source")

    with pytest.raises(RunResolutionError, match="mask is stale"):
        resolve_inputs(
            target=target,
            inbound_edges=(
                SubjectEdge(
                    "edge",
                    "source",
                    "target",
                    VersionPin(version_id="current"),
                ),
            ),
            nodes={target.id: target},
            versions={subject.id: subject},
            random_seed=fixed_seed(),
        )


def test_seed_precedence_is_override_then_subject_then_random() -> None:
    subject = version("subject", "source", seed=22)
    edge = SubjectEdge("edge", "source", "target", VersionPin(version_id="subject"))
    target_override = NodeSnapshot(id="target", prompt="Edit", seed=33)
    target_inherit = NodeSnapshot(id="target", prompt="Edit")
    target_generate = NodeSnapshot(id="generate", prompt="Create")

    overridden = resolve_inputs(
        target=target_override,
        inbound_edges=(edge,),
        nodes={},
        versions={subject.id: subject},
        random_seed=fixed_seed(44),
    )
    inherited = resolve_inputs(
        target=target_inherit,
        inbound_edges=(edge,),
        nodes={},
        versions={subject.id: subject},
        random_seed=fixed_seed(44),
    )
    generated = resolve_inputs(
        target=target_generate,
        inbound_edges=(),
        nodes={},
        versions={},
        random_seed=fixed_seed(44),
    )

    assert overridden.seed == 33
    assert inherited.seed == 22
    assert generated.seed == 44


def test_edit_prompt_uses_the_accepted_preamble_exactly() -> None:
    assert build_prompt(user_prompt="  make it navy  ", op=Op.EDIT_INSTRUCT) == (
        "Preserve exactly every unmentioned attribute, including geometry,\n"
        "proportions, silhouette, camera angle, framing, lighting direction,\n"
        "and background.\n"
        "Change only: make it navy\n"
        "Do not restyle or reinterpret any other element."
    )
    assert "{resolved_user_prompt}" in PRESERVATION_PREAMBLE


@pytest.mark.parametrize("op", [Op.GENERATE, Op.GENERATE_REF])
def test_generate_prompt_appends_white_background_clause(op: Op) -> None:
    assert build_prompt(user_prompt="  a navy shoe  ", op=op) == (
        "a navy shoe\n\nPlace the object on a clean white background."
    )
    assert WHITE_BACKGROUND_CLAUSE == "Place the object on a clean white background."


@pytest.mark.parametrize("op", [Op.GENERATE, Op.GENERATE_REF])
def test_generate_prompt_omits_white_background_clause_when_disabled(op: Op) -> None:
    assert (
        build_prompt(user_prompt="  a navy shoe  ", op=op, white_background=False)
        == "a navy shoe"
    )


@pytest.mark.parametrize(
    "op", [Op.EDIT_INSTRUCT, Op.EDIT_INPAINT, Op.EDIT_COMPOSITE, Op.EDIT_REF_GUIDED]
)
def test_edit_prompt_never_receives_white_background_clause(op: Op) -> None:
    prompt = build_prompt(
        user_prompt="make it navy",
        op=op,
        white_background=True,
    )
    assert WHITE_BACKGROUND_CLAUSE not in prompt


def test_frozen_request_contains_only_resolved_artifacts_and_target_prompt() -> None:
    target = NodeSnapshot(id="target", prompt="make it navy")
    source = NodeSnapshot(
        id="source",
        prompt="make it a completely different red boot",
        active_version_id="new",
    )
    old = version("old", "source", seed=91, edit_depth=4)
    new = version("new", "source", seed=92, edit_depth=5)

    request = freeze_run_request(
        target=target,
        inbound_edges=(
            SubjectEdge("edge", "source", "target", VersionPin(version_id="old")),
        ),
        nodes={source.id: source, target.id: target},
        versions={old.id: old, new.id: new},
        random_seed=fixed_seed(),
    )

    assert request.op is Op.EDIT_INSTRUCT
    assert request.subject == old
    assert request.input_snapshot.subject_version_id == "old"
    assert request.input_snapshot.connect_version_ids == ()
    assert request.input_snapshot.mask_hash is None
    assert request.seed == 91
    assert request.edit_depth == 5
    assert "make it navy" in request.prompt_at_runtime
    assert source.prompt not in request.prompt_at_runtime


def test_frozen_request_codec_rejects_legacy_base_vocabulary() -> None:
    request = freeze_run_request(
        target=NodeSnapshot(id="target", prompt="make it navy"),
        inbound_edges=(
            SubjectEdge("edge", "source", "target", VersionPin(version_id="subject")),
        ),
        nodes={},
        versions={"subject": version("subject", "source")},
        random_seed=fixed_seed(),
    )

    old_subject_key = encode_frozen_request(request)
    old_subject_key["base"] = old_subject_key.pop("subject")
    with pytest.raises(ValueError, match="subject vocabulary"):
        decode_frozen_request(old_subject_key)

    old_snapshot_key = encode_frozen_request(request)
    snapshot = old_snapshot_key["input_snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["base_version_id"] = snapshot.pop("subject_version_id")
    with pytest.raises(ValueError, match="subject vocabulary"):
        decode_frozen_request(old_snapshot_key)

    old_mask_key = encode_frozen_request(request)
    old_mask_key["mask"] = {
        "rle": "encoded",
        "width": 1,
        "height": 1,
        "base_version_id": "subject",
    }
    with pytest.raises(ValueError, match="subject vocabulary"):
        decode_frozen_request(old_mask_key)


def test_valid_mask_is_hashed_into_frozen_provenance() -> None:
    mask = MaskSnapshot("encoded-rle", 128, 96, subject_version_id="subject")
    target = NodeSnapshot(id="target", prompt="replace the mark", mask=mask)
    subject = version("subject", "source")

    request = freeze_run_request(
        target=target,
        inbound_edges=(
            SubjectEdge("edge", "source", "target", VersionPin(version_id="subject")),
        ),
        nodes={target.id: target},
        versions={subject.id: subject},
        random_seed=fixed_seed(),
    )

    assert request.op is Op.EDIT_INPAINT
    assert request.input_snapshot.mask_hash is not None
    assert len(request.input_snapshot.mask_hash) == 64
