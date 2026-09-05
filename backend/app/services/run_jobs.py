import secrets
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.prompts import compile_document
from app.domain.runs import (
    ActivePin,
    ConnectEdge,
    FrozenRunRequest,
    MaskSnapshot,
    NodeSettings,
    NodeSnapshot,
    SubjectEdge,
    VersionPin,
    VersionSnapshot,
)
from app.models.graph import GraphEdge, GraphNode, RunJob, Version
from app.models.project import Project
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
    reroll: bool = False,
) -> tuple[RunJob, bool]:
    target_row = _lock_target(project_id, node_id, db)
    existing = db.scalar(
        select(RunJob).where(
            RunJob.node_id == node_id,
            RunJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    # A response can be lost after enqueue, or another tab can still show Run.
    # Reuse the in-flight job instead of charging for a duplicate generation.
    running = db.scalar(
        select(RunJob)
        .where(
            RunJob.node_id == node_id,
            RunJob.status.in_(
                ("queued", "dispatching", "provider_pending", "ingesting")
            ),
        )
        .order_by(RunJob.created_at.desc(), RunJob.id.desc())
        .limit(1)
    )
    if running is not None:
        return running, False

    frozen = _freeze_node_run(
        target_row, db, random_seed or (lambda: secrets.randbits(32))
    )
    if reroll:
        # A deliberate re-roll changes only this submission's resolved seed.
        # Explicit draft settings and their signature remain unchanged.
        frozen = replace(frozen, seed=(random_seed or (lambda: secrets.randbits(32)))())
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


def preview_run(
    *, project_id: uuid.UUID, node_id: uuid.UUID, db: Session
) -> FrozenRunRequest:
    target = _lock_target(project_id, node_id, db)
    return _freeze_node_run(target, db, lambda: 0)


def _lock_target(project_id: uuid.UUID, node_id: uuid.UUID, db: Session) -> GraphNode:
    # A project-sized mutation lock gives all graph reads one coherent snapshot
    # and avoids opposing node-lock orders when two nodes reference each other.
    db.scalar(select(Project).where(Project.id == project_id).with_for_update())
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

    return target_row


def _freeze_node_run(
    target_row: GraphNode, db: Session, random_seed: Callable[[], int]
) -> FrozenRunRequest:
    node_id = target_row.id

    edge_rows = list(
        db.scalars(
            select(GraphEdge)
            .where(GraphEdge.target_node_id == node_id)
            .order_by(GraphEdge.role, GraphEdge.connect_order, GraphEdge.id)
        )
    )
    source_ids = {edge.source_node_id for edge in edge_rows}
    node_rows = list(
        db.execute(
            select(GraphNode.id, GraphNode.active_version_id, GraphNode.deleted_at)
            .where(GraphNode.id.in_({node_id, *source_ids}))
            .with_for_update()
        )
    )
    nodes = {
        str(node.id): NodeSnapshot(
            id=str(node.id),
            prompt="",
            active_version_id=str(node.active_version_id)
            if node.active_version_id
            else None,
        )
        for node in node_rows
        if node.deleted_at is None
    }
    chips = [part for part in target_row.prompt if part["type"] == "connect"]
    connects = sorted(
        (edge for edge in edge_rows if edge.role == "connect"),
        key=lambda edge: edge.connect_order,
    )
    if [(part["edge_id"], part["source_node_id"]) for part in chips] != [
        (str(edge.id), str(edge.source_node_id)) for edge in connects
    ]:
        raise RunSubmissionError(
            "The prompt and connect wires do not match. Reconnect the broken chip."
        )
    target = replace(
        _node_snapshot(target_row),
        prompt=compile_document(
            target_row.prompt,
            has_subject=any(edge.role == "subject" for edge in edge_rows),
        ),
    )

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
        list(
            db.execute(
                select(
                    Version.id,
                    Version.node_id,
                    Version.artifact_url,
                    Version.seed,
                    Version.edit_depth,
                ).where(Version.id.in_(required_version_ids))
            )
        )
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
        random_seed=random_seed,
    )
    if frozen.mask is not None and frozen.connects:
        raise RunSubmissionError(
            "FLUX Fill cannot use connect images. Remove the connect chips "
            "or clear the mask before running."
        )
    return frozen


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
        prompt="",
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
