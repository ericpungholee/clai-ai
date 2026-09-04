import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.runs import (
    ActivePin,
    ConnectEdge,
    MaskSnapshot,
    NodeSettings,
    NodeSnapshot,
    SubjectEdge,
    VersionPin,
    VersionSnapshot,
)
from app.models.graph import GraphEdge, GraphNode, RunJob, Version
from app.services.frozen_request_codec import encode_frozen_request
from app.services.run_freezing import freeze_run_request


class RunSubmissionError(ValueError):
    pass


def submit_run(
    *,
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    idempotency_key: str,
    db: Session,
    random_seed: Callable[[], int] | None = None,
) -> tuple[RunJob, bool]:
    target_row = db.scalar(
        select(GraphNode)
        .where(
            GraphNode.id == node_id,
            GraphNode.project_id == project_id,
            GraphNode.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if target_row is None:
        raise RunSubmissionError("Node not found")

    existing = db.scalar(
        select(RunJob).where(
            RunJob.node_id == node_id,
            RunJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    edge_rows = list(
        db.scalars(
            select(GraphEdge)
            .where(GraphEdge.target_node_id == node_id)
            .order_by(GraphEdge.role, GraphEdge.connect_order, GraphEdge.id)
        )
    )
    source_ids = {edge.source_node_id for edge in edge_rows}
    node_rows = list(
        db.scalars(
            select(GraphNode)
            .where(GraphNode.id.in_({node_id, *source_ids}))
            .with_for_update()
        )
    )
    nodes = {str(node.id): _node_snapshot(node) for node in node_rows}
    target = nodes[str(node_id)]

    required_version_ids = {
        edge.pinned_version_id
        for edge in edge_rows
        if edge.pinned_version_id is not None
    }
    required_version_ids.update(
        node.active_version_id
        for node in node_rows
        if node.id in source_ids and node.active_version_id is not None
    )
    version_rows = (
        list(db.scalars(select(Version).where(Version.id.in_(required_version_ids))))
        if required_version_ids
        else []
    )
    versions = {
        str(version.id): VersionSnapshot(
            id=str(version.id),
            node_id=str(version.node_id),
            artifact_url=version.artifact_url,
            seed=version.seed,
            edit_depth=version.edit_depth,
        )
        for version in version_rows
    }
    frozen = freeze_run_request(
        target=target,
        inbound_edges=tuple(_edge_snapshot(edge) for edge in edge_rows),
        nodes=nodes,
        versions=versions,
        random_seed=random_seed or (lambda: secrets.randbits(32)),
    )
    job = RunJob(
        id=uuid.uuid4(),
        project_id=project_id,
        node_id=node_id,
        idempotency_key=idempotency_key,
        status="queued",
        frozen_request=encode_frozen_request(frozen),
        attempts=0,
        queued_at=datetime.now(UTC),
    )
    db.add(job)
    db.flush()
    return job, True


def preview_run(*, project_id: uuid.UUID, node_id: uuid.UUID, db: Session) -> str:
    job, created = submit_run(
        project_id=project_id,
        node_id=node_id,
        idempotency_key=f"preview:{uuid.uuid4()}",
        db=db,
        random_seed=lambda: 0,
    )
    op = str(job.frozen_request["op"])
    if created:
        db.expunge(job)
    db.rollback()
    return op


def _node_snapshot(node: GraphNode) -> NodeSnapshot:
    settings = node.settings
    mask = None
    if node.mask_rle is not None:
        if (
            node.mask_width is None
            or node.mask_height is None
            or node.mask_subject_version_id is None
        ):
            raise RunSubmissionError("Node mask is incomplete")
        mask = MaskSnapshot(
            rle=node.mask_rle,
            width=node.mask_width,
            height=node.mask_height,
            subject_version_id=str(node.mask_subject_version_id),
        )
    return NodeSnapshot(
        id=str(node.id),
        prompt=node.prompt,
        settings=NodeSettings(
            aspect_ratio=_setting_string(settings, "aspect_ratio"),
            width=_setting_integer(settings, "width"),
            height=_setting_integer(settings, "height"),
            white_background=_setting_boolean(
                settings, "whiteBackground", default=False
            ),
        ),
        seed=node.seed,
        mask=mask,
        active_version_id=(
            str(node.active_version_id) if node.active_version_id else None
        ),
    )


def _edge_snapshot(edge: GraphEdge) -> SubjectEdge | ConnectEdge:
    if edge.role == "subject":
        if edge.pinned_version_id is None:
            raise RunSubmissionError("Subject edge has no pinned version")
        return SubjectEdge(
            id=str(edge.id),
            source_node_id=str(edge.source_node_id),
            target_node_id=str(edge.target_node_id),
            pin=VersionPin(version_id=str(edge.pinned_version_id)),
        )
    if edge.connect_order is None:
        raise RunSubmissionError("Connect edge has no order")
    return ConnectEdge(
        id=str(edge.id),
        source_node_id=str(edge.source_node_id),
        target_node_id=str(edge.target_node_id),
        pin=ActivePin(),
        order=edge.connect_order,
    )


def _setting_string(settings: dict[str, object], key: str) -> str:
    value = settings.get(key)
    if not isinstance(value, str):
        raise RunSubmissionError(f"Node setting {key} must be a string")
    return value


def _setting_integer(settings: dict[str, object], key: str) -> int:
    value = settings.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RunSubmissionError(f"Node setting {key} must be an integer")
    return value


def _setting_boolean(
    settings: dict[str, object], key: str, *, default: bool | None = None
) -> bool:
    value = settings.get(key, default)
    if not isinstance(value, bool):
        raise RunSubmissionError(f"Node setting {key} must be a boolean")
    return value
