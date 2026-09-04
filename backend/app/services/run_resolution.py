from collections.abc import Callable, Mapping, Sequence

from app.domain.runs import (
    BaseEdge,
    ConnectEdge,
    NodeSnapshot,
    ResolvedInputs,
    RunEdge,
    VersionSnapshot,
)


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

    base_edges = [edge for edge in inbound_edges if isinstance(edge, BaseEdge)]
    connect_edges = [edge for edge in inbound_edges if isinstance(edge, ConnectEdge)]

    if len(base_edges) > 1:
        raise RunResolutionError("A node accepts at most one base edge")
    if len(connect_edges) > 2:
        raise RunResolutionError("A node accepts at most two connect edges")

    base = _resolve_base(base_edges[0], versions) if base_edges else None
    connects = _resolve_connects(connect_edges, nodes, versions)

    if target.mask is not None:
        if base is None:
            raise RunResolutionError("A mask requires a resolved base version")
        if target.mask.base_version_id != base.id:
            raise RunResolutionError("The mask is stale for the resolved base version")

    seed = target.seed
    if seed is None and base is not None:
        seed = base.seed
    if seed is None:
        seed = random_seed()

    return ResolvedInputs(
        node=target,
        base=base,
        connects=connects,
        mask=target.mask,
        seed=seed,
    )


def _resolve_base(
    edge: BaseEdge,
    versions: Mapping[str, VersionSnapshot],
) -> VersionSnapshot:
    version = versions.get(edge.pin.version_id)
    if version is None:
        raise RunResolutionError("The base edge points to a missing version")
    if version.node_id != edge.source_node_id:
        raise RunResolutionError("The pinned base version belongs to another node")
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
