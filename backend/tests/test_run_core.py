from collections.abc import Callable

import pytest

from app.domain.runs import (
    ActivePin,
    BaseEdge,
    ConnectEdge,
    MaskSnapshot,
    NodeSnapshot,
    Op,
    VersionPin,
    VersionSnapshot,
)
from app.services.operation_routing import OperationRoutingError, resolve_op
from app.services.prompt_builder import PRESERVATION_PREAMBLE, build_prompt
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
    ("has_base", "has_mask", "connect_count", "expected"),
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
    has_base: bool,
    has_mask: bool,
    connect_count: int,
    expected: Op,
) -> None:
    assert (
        resolve_op(
            has_base=has_base,
            has_mask=has_mask,
            connect_count=connect_count,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("has_base", "has_mask", "connect_count"),
    [(False, True, 0), (False, True, 1), (True, False, -1), (True, False, 3)],
)
def test_resolve_op_rejects_invalid_states(
    has_base: bool,
    has_mask: bool,
    connect_count: int,
) -> None:
    with pytest.raises(OperationRoutingError):
        resolve_op(
            has_base=has_base,
            has_mask=has_mask,
            connect_count=connect_count,
        )


def test_base_pin_uses_pinned_version_while_connect_follows_active() -> None:
    target = NodeSnapshot(id="target", prompt="Combine them")
    base_node = NodeSnapshot(
        id="base-node",
        prompt="ancestor prompt must stay hidden",
        active_version_id="base-new",
    )
    connect_node = NodeSnapshot(
        id="connect-node",
        prompt="another hidden ancestor prompt",
        active_version_id="connect-new",
    )
    versions = {
        candidate.id: candidate
        for candidate in (
            version("base-old", "base-node", seed=11),
            version("base-new", "base-node", seed=12),
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
        BaseEdge(
            id="base-edge",
            source_node_id="base-node",
            target_node_id="target",
            pin=VersionPin(version_id="base-old"),
        ),
    )

    resolved = resolve_inputs(
        target=target,
        inbound_edges=edges,
        nodes={
            target.id: target,
            base_node.id: base_node,
            connect_node.id: connect_node,
        },
        versions=versions,
        random_seed=fixed_seed(),
    )

    assert resolved.base == versions["base-old"]
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


def test_resolution_rejects_second_base_edge() -> None:
    target = NodeSnapshot(id="target", prompt="Edit")
    versions = {"v1": version("v1", "a"), "v2": version("v2", "b")}
    edges = (
        BaseEdge("e1", "a", "target", VersionPin(version_id="v1")),
        BaseEdge("e2", "b", "target", VersionPin(version_id="v2")),
    )

    with pytest.raises(RunResolutionError, match="at most one base"):
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
        mask=MaskSnapshot("1 2 3", 512, 512, base_version_id="older"),
    )
    base = version("current", "source")

    with pytest.raises(RunResolutionError, match="mask is stale"):
        resolve_inputs(
            target=target,
            inbound_edges=(
                BaseEdge(
                    "edge",
                    "source",
                    "target",
                    VersionPin(version_id="current"),
                ),
            ),
            nodes={target.id: target},
            versions={base.id: base},
            random_seed=fixed_seed(),
        )


def test_seed_precedence_is_override_then_base_then_random() -> None:
    base = version("base", "source", seed=22)
    edge = BaseEdge("edge", "source", "target", VersionPin(version_id="base"))
    target_override = NodeSnapshot(id="target", prompt="Edit", seed=33)
    target_inherit = NodeSnapshot(id="target", prompt="Edit")
    target_generate = NodeSnapshot(id="generate", prompt="Create")

    overridden = resolve_inputs(
        target=target_override,
        inbound_edges=(edge,),
        nodes={},
        versions={base.id: base},
        random_seed=fixed_seed(44),
    )
    inherited = resolve_inputs(
        target=target_inherit,
        inbound_edges=(edge,),
        nodes={},
        versions={base.id: base},
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


def test_generate_prompt_is_trimmed_without_edit_preservation_claims() -> None:
    assert build_prompt(user_prompt="  a navy shoe  ", op=Op.GENERATE) == (
        "a navy shoe"
    )


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
            BaseEdge("edge", "source", "target", VersionPin(version_id="old")),
        ),
        nodes={source.id: source, target.id: target},
        versions={old.id: old, new.id: new},
        random_seed=fixed_seed(),
    )

    assert request.op is Op.EDIT_INSTRUCT
    assert request.base == old
    assert request.input_snapshot.base_version_id == "old"
    assert request.input_snapshot.connect_version_ids == ()
    assert request.input_snapshot.mask_hash is None
    assert request.seed == 91
    assert request.edit_depth == 5
    assert "make it navy" in request.prompt_at_runtime
    assert source.prompt not in request.prompt_at_runtime


def test_valid_mask_is_hashed_into_frozen_provenance() -> None:
    mask = MaskSnapshot("encoded-rle", 128, 96, base_version_id="base")
    target = NodeSnapshot(id="target", prompt="replace the mark", mask=mask)
    base = version("base", "source")

    request = freeze_run_request(
        target=target,
        inbound_edges=(
            BaseEdge("edge", "source", "target", VersionPin(version_id="base")),
        ),
        nodes={target.id: target},
        versions={base.id: base},
        random_seed=fixed_seed(),
    )

    assert request.op is Op.EDIT_INPAINT
    assert request.input_snapshot.mask_hash is not None
    assert len(request.input_snapshot.mask_hash) == 64
