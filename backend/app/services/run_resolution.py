from collections.abc import Callable, Mapping, Sequence

from app.domain.runs import (
    ConnectEdge,
    NodeSnapshot,
    ResolvedInputs,
    RunEdge,
    SubjectEdge,
    VersionSnapshot,
)
from app.services.masks import validate_mask


class RunResolutionError(ValueError):
    pass


def resolve_inputs(
    *,
    target: NodeSnapshot,
    inbound_edges: Sequence[RunEdge],
    nodes: Mapping[str, NodeSnapshot],
    versions: Mapping[str, VersionSnapshot],
    random_seed: Callable[[], int],
) -> ResolvedInputs:
    if any(edge.target_node_id != target.id for edge in inbound_edges):
        raise RunResolutionError("Every supplied edge must target the run node")

    subject_edges = [edge for edge in inbound_edges if isinstance(edge, SubjectEdge)]
    connect_edges = [edge for edge in inbound_edges if isinstance(edge, ConnectEdge)]

    if len(subject_edges) > 1:
        raise RunResolutionError("A node accepts at most one subject edge")
    if len(connect_edges) > 2:
        raise RunResolutionError("A node accepts at most two connect edges")

    subject = _resolve_subject(subject_edges[0], versions) if subject_edges else None
    connects = _resolve_connects(connect_edges, nodes, versions)

    mask = target.mask
    if mask is not None:
        if subject is None:
            raise RunResolutionError("A mask requires a resolved subject version")
        if target.mask.subject_version_id != subject.id:
            raise RunResolutionError(
                "The mask is stale for the resolved subject version"
            )
        if validate_mask(mask):
            mask = None

    seed = target.seed
    if seed is None and subject is not None:
        seed = subject.seed
    if seed is None:
        seed = random_seed()

    return ResolvedInputs(
        node=target,
        subject=subject,
        connects=connects,
        mask=mask,
        seed=seed,
    )


def _resolve_subject(
    edge: SubjectEdge,
    versions: Mapping[str, VersionSnapshot],
) -> VersionSnapshot:
    version = versions.get(edge.pin.version_id)
    if version is None:
        raise RunResolutionError("The subject edge points to a missing version")
    if version.node_id != edge.source_node_id:
        raise RunResolutionError("The pinned subject version belongs to another node")
    return version


def _resolve_connects(
    edges: Sequence[ConnectEdge],
    nodes: Mapping[str, NodeSnapshot],
    versions: Mapping[str, VersionSnapshot],
) -> tuple[VersionSnapshot, ...]:
    orders = [edge.order for edge in edges]
    if any(order < 0 for order in orders) or len(orders) != len(set(orders)):
        raise RunResolutionError("Connect orders must be unique non-negative values")
    if sorted(orders) != list(range(len(orders))):
        raise RunResolutionError("Connect orders must be contiguous from zero")

    resolved: list[VersionSnapshot] = []
    for edge in sorted(edges, key=lambda candidate: candidate.order):
        source = nodes.get(edge.source_node_id)
        if source is None:
            raise RunResolutionError("A connect edge points to a missing node")
        if source.active_version_id is None:
            raise RunResolutionError("A connect source has no active version")
        version = versions.get(source.active_version_id)
        if version is None:
            raise RunResolutionError("A connect source has a missing active version")
        if version.node_id != source.id:
            raise RunResolutionError("The active version belongs to another node")
        resolved.append(version)

    return tuple(resolved)
