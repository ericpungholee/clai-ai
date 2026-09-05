from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256

from app.domain.runs import (
    FrozenRunRequest,
    InputSnapshot,
    MaskSnapshot,
    NodeSnapshot,
    Op,
    RunEdge,
    VersionSnapshot,
)
from app.services.operation_routing import resolve_op
from app.services.prompt_builder import EDIT_OPS, build_prompt
from app.services.run_resolution import resolve_inputs


def calculate_edit_depth(*, op: Op, subject: VersionSnapshot | None) -> int:
    if op not in EDIT_OPS:
        return 0
    if subject is None:
        raise ValueError("An edit operation requires a subject version")
    return subject.edit_depth + 1


def hash_mask(mask: MaskSnapshot | None) -> str | None:
    if mask is None:
        return None
    canonical = (
        f"{mask.width}:{mask.height}:{mask.subject_version_id}:{mask.rle}"
    ).encode()
    return sha256(canonical).hexdigest()


def freeze_run_request(
    *,
    target: NodeSnapshot,
    inbound_edges: Sequence[RunEdge],
    nodes: Mapping[str, NodeSnapshot],
    versions: Mapping[str, VersionSnapshot],
    random_seed: Callable[[], int],
) -> FrozenRunRequest:
    resolved = resolve_inputs(
        target=target,
        inbound_edges=inbound_edges,
        nodes=nodes,
        versions=versions,
        random_seed=random_seed,
    )
    op = resolve_op(
        has_subject=resolved.subject is not None,
        has_mask=resolved.mask is not None,
        connect_count=len(resolved.connects),
    )

    return FrozenRunRequest(
        node_id=target.id,
        user_prompt=target.prompt,
        op=op,
        prompt_at_runtime=build_prompt(
            user_prompt=target.prompt,
            op=op,
            white_background=target.settings.white_background,
        ),
        seed=resolved.seed,
        settings=target.settings,
        subject=resolved.subject,
        connects=resolved.connects,
        mask=resolved.mask,
        input_snapshot=InputSnapshot(
            subject_version_id=resolved.subject.id if resolved.subject else None,
            connect_version_ids=tuple(version.id for version in resolved.connects),
            mask_hash=hash_mask(resolved.mask),
        ),
        edit_depth=calculate_edit_depth(op=op, subject=resolved.subject),
    )
