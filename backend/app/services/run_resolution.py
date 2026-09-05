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
        raise RunResolutionError("A node accepts one input image.")
    if len(connect_edges) > 2:
        raise RunResolutionError("Two references maximum. Remove one first.")

    subject = _resolve_subject(subject_edges[0], versions) if subject_edges else None
    connects = _resolve_connects(connect_edges, nodes, versions)

    mask = target.mask
    if mask is not None:
        if subject is None:
            raise RunResolutionError("Select an input image before selecting an area.")
        if target.mask.subject_version_id != subject.id:
            raise RunResolutionError(
                "Area selection belongs to a different image. Select "
                "it again or remove it."
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
        raise RunResolutionError("Input image is unavailable. Choose an input image.")
    if version.node_id != edge.source_node_id:
        raise RunResolutionError("The input image belongs to another node.")
    return version


def _resolve_connects(
    edges: Sequence[ConnectEdge],
    nodes: Mapping[str, NodeSnapshot],
    versions: Mapping[str, VersionSnapshot],
) -> tuple[VersionSnapshot, ...]:
    orders = [edge.order for edge in edges]
    if any(order < 0 for order in orders) or len(orders) != len(set(orders)):
        raise RunResolutionError(
            "Reference positions must be unique non-negative values"
        )
    if sorted(orders) != list(range(len(orders))):
        raise RunResolutionError("Reference positions must be contiguous from zero")

    resolved: list[VersionSnapshot] = []
    for edge in sorted(edges, key=lambda candidate: candidate.order):
        source = nodes.get(edge.source_node_id)
        if source is None:
            raise RunResolutionError(
                "Source deleted — remove or replace this reference."
            )
        if source.active_version_id is None:
            raise RunResolutionError("Reference has no image — run its source first.")
        version = versions.get(source.active_version_id)
        if version is None:
            raise RunResolutionError(
                "Reference image is unavailable. Remove or replace this reference."
            )
        if version.node_id != source.id:
            raise RunResolutionError("The reference image belongs to another node.")
        resolved.append(version)

    return tuple(resolved)
