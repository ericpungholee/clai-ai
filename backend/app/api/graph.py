import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.graph import GraphEdge, GraphNode, RunJob, Version
from app.models.project import Project
from app.schemas.graph import (
    BranchCreate,
    BranchData,
    GraphDocument,
    GraphEdgeData,
    GraphNodeData,
    NodeCreate,
    NodeDuplicate,
    NodeSettingsData,
    NodeUpdate,
    PromptUpdate,
    RunJobData,
    RunPreviewData,
    RunSubmit,
    SubjectEdgeReplace,
)
from app.services.graph_service import (
    GraphConflictError,
    GraphMutationError,
    assert_draft_editable,
    create_branch,
    create_node,
    read_graph_document,
    replace_subject_edge,
    serialize_edge,
    serialize_node,
    update_node,
    update_prompt,
)
from app.services.run_jobs import (
    ResultRunError,
    RunSubmissionError,
    preview_run,
    submit_run,
)
from app.services.run_queue import RunEnqueuer, get_run_enqueuer

router = APIRouter(prefix="/api/projects", tags=["graph"])


def get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


@router.get("/{project_id}/graph", response_model=GraphDocument)
def get_graph(project_id: uuid.UUID, db: Session = Depends(get_db)) -> GraphDocument:
    get_project_or_404(project_id, db)
    return read_graph_document(project_id, db)


@router.post(
    "/{project_id}/nodes",
    response_model=GraphNodeData,
    status_code=status.HTTP_201_CREATED,
)
def post_node(
    project_id: uuid.UUID,
    data: NodeCreate,
    db: Session = Depends(get_db),
) -> GraphNodeData:
    project = get_project_or_404(project_id, db)
    try:
        node = create_node(project_id, data, db)
        project.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(node)
        return serialize_node(node, [])
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Node already exists") from error


@router.patch("/{project_id}/nodes/{node_id}", response_model=GraphNodeData)
def patch_node(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    data: NodeUpdate,
    db: Session = Depends(get_db),
) -> GraphNodeData:
    project = get_project_or_404(project_id, db)
    node = db.scalar(
        select(GraphNode)
        .where(
            GraphNode.id == node_id,
            GraphNode.project_id == project_id,
            GraphNode.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    try:
        update_node(node, data, db)
        project.updated_at = datetime.now(UTC)
        versions = list(
            db.scalars(
                select(Version)
                .where(Version.node_id == node.id)
                .order_by(Version.created_at, Version.id)
            )
        )
        db.commit()
        return serialize_node(node, versions)
    except GraphConflictError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except GraphMutationError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put(
    "/{project_id}/nodes/{target_node_id}/subject", response_model=GraphEdgeData
)
def put_subject_edge(
    project_id: uuid.UUID,
    target_node_id: uuid.UUID,
    data: SubjectEdgeReplace,
    db: Session = Depends(get_db),
) -> GraphEdgeData:
    project = get_project_or_404(project_id, db)
    try:
        edge = replace_subject_edge(
            project_id=project_id,
            target_node_id=target_node_id,
            data=data,
            db=db,
        )
        project.updated_at = datetime.now(UTC)
        db.commit()
        return serialize_edge(edge)
    except GraphConflictError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except GraphMutationError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid input image") from error


@router.delete(
    "/{project_id}/nodes/{target_node_id}/subject",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_subject_edge(
    project_id: uuid.UUID,
    target_node_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    project = get_project_or_404(project_id, db)
    node = db.get(GraphNode, target_node_id)
    if node is None or node.project_id != project_id:
        raise HTTPException(404, "Node not found")
    try:
        assert_draft_editable(node, db)
    except GraphConflictError as error:
        raise HTTPException(409, str(error)) from error
    db.execute(
        delete(GraphEdge).where(
            GraphEdge.project_id == project_id,
            GraphEdge.target_node_id == target_node_id,
            GraphEdge.role == "subject",
        )
    )
    project.updated_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{project_id}/nodes/{node_id}/prompt", response_model=GraphDocument)
def put_prompt(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    data: PromptUpdate,
    db: Session = Depends(get_db),
) -> GraphDocument:
    project = get_project_or_404(project_id, db)
    try:
        update_prompt(project_id, node_id, data, db)
        project.updated_at = datetime.now(UTC)
        db.commit()
        return read_graph_document(project_id, db)
    except GraphConflictError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except GraphMutationError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(422, "The reference wire is invalid") from error


@router.post(
    "/{project_id}/versions/{version_id}/branches",
    response_model=BranchData,
    status_code=status.HTTP_201_CREATED,
)
def post_branch(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: BranchCreate,
    db: Session = Depends(get_db),
) -> BranchData:
    project = get_project_or_404(project_id, db)
    try:
        branch = create_branch(
            project_id=project_id,
            source_version_id=version_id,
            data=data,
            db=db,
        )
        project.updated_at = datetime.now(UTC)
        db.commit()
        return branch
    except GraphConflictError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except GraphMutationError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{project_id}/nodes/{node_id}/run-preview", response_model=RunPreviewData)
def get_run_preview(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RunPreviewData:
    get_project_or_404(project_id, db)
    try:
        preview = preview_run(project_id=project_id, node_id=node_id, db=db)
        return RunPreviewData(op=preview.op)
    except ResultRunError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except (RunSubmissionError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/{project_id}/nodes/{node_id}/runs",
    response_model=RunJobData,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_run(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    data: RunSubmit,
    db: Session = Depends(get_db),
    enqueuer: RunEnqueuer = Depends(get_run_enqueuer),
) -> RunJobData:
    get_project_or_404(project_id, db)
    try:
        job, created = submit_run(
            project_id=project_id,
            node_id=node_id,
            idempotency_key=data.idempotency_key,
            db=db,
        )
        job_id = job.id
        db.commit()
        if created:
            try:
                enqueuer.enqueue(job_id)
            except Exception as error:
                failed_job = db.scalar(
                    select(RunJob).where(RunJob.id == job_id).with_for_update()
                )
                if failed_job is not None and failed_job.status != "queued":
                    return serialize_run_job(job_id, db)
                if failed_job is not None:
                    failed_job.status = "failed"
                    failed_job.error = f"QueueError: {error}"[:8000]
                    failed_job.completed_at = datetime.now(UTC)
                    db.commit()
                raise HTTPException(
                    status_code=503, detail="Run persisted but could not be enqueued"
                ) from error
        return serialize_run_job(job_id, db)
    except ResultRunError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except (RunSubmissionError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError as error:
        db.rollback()
        existing = db.scalar(
            select(RunJob).where(
                RunJob.node_id == node_id,
                RunJob.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            return serialize_run_job(existing.id, db)
        raise HTTPException(
            status_code=409, detail="Run submission conflicted"
        ) from error


@router.get("/{project_id}/runs/{job_id}", response_model=RunJobData)
def get_run(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RunJobData:
    get_project_or_404(project_id, db)
    job = db.scalar(
        select(RunJob.id).where(RunJob.id == job_id, RunJob.project_id == project_id)
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return serialize_run_job(job_id, db)


def serialize_run_job(job_id: uuid.UUID, db: Session) -> RunJobData:
    job = db.get(RunJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Run not found")
    version_id = db.scalar(select(Version.id).where(Version.run_job_id == job.id))
    return RunJobData(
        id=job.id,
        node_id=job.node_id,
        status=job.status,
        op=str(job.frozen_request["op"]),
        attempts=job.attempts,
        error=job.error,
        version_id=version_id,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.delete("/{project_id}/nodes/{node_id}", status_code=204)
def delete_node(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    project = get_project_or_404(project_id, db)
    node = db.scalar(
        select(GraphNode)
        .where(GraphNode.id == node_id, GraphNode.project_id == project_id)
        .with_for_update()
    )
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    dependents = db.scalar(
        select(GraphEdge.id).where(GraphEdge.source_node_id == node.id).limit(1)
    )
    has_history = db.scalar(select(RunJob.id).where(RunJob.node_id == node.id).limit(1))
    if dependents is not None or has_history is not None:
        node.deleted_at = datetime.now(UTC)
    else:
        db.delete(node)
    project.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Node cannot be deleted") from error
    return Response(status_code=204)


@router.post(
    "/{project_id}/nodes/{node_id}/duplicate",
    response_model=GraphNodeData,
    status_code=201,
)
def duplicate_node(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    data: NodeDuplicate,
    db: Session = Depends(get_db),
) -> GraphNodeData:
    project = get_project_or_404(project_id, db)
    source = db.scalar(
        select(GraphNode).where(
            GraphNode.id == node_id,
            GraphNode.project_id == project_id,
            GraphNode.deleted_at.is_(None),
        )
    )
    if source is None:
        raise HTTPException(404, "Node not found")
    data.settings = NodeSettingsData.model_validate(
        {
            **source.settings,
            "whiteBackground": source.settings.get("whiteBackground", True),
        }
    )
    data.seed = secrets.randbits(32) if data.fresh_seed else source.seed
    node = create_node(project_id, data, db)
    # Copy the draft and wiring, not historical versions or the source's active pointer.
    node.prompt = [
        {**part, "edge_id": str(uuid.uuid4())}
        if part["type"] == "connect"
        else dict(part)
        for part in source.prompt
    ]
    source_edges = list(
        db.scalars(select(GraphEdge).where(GraphEdge.target_node_id == source.id))
    )
    chip_ids = {
        part["source_node_id"]: uuid.UUID(part["edge_id"])
        for part in node.prompt
        if part["type"] == "connect"
    }
    for edge in source_edges:
        db.add(
            GraphEdge(
                id=chip_ids[str(edge.source_node_id)]
                if edge.role == "connect"
                else uuid.uuid4(),
                project_id=project_id,
                source_node_id=edge.source_node_id,
                target_node_id=node.id,
                role=edge.role,
                pin_mode=edge.pin_mode,
                pinned_version_id=edge.pinned_version_id,
                connect_order=edge.connect_order,
            )
        )
    node.mask_rle, node.mask_width, node.mask_height, node.mask_subject_version_id = (
        source.mask_rle,
        source.mask_width,
        source.mask_height,
        source.mask_subject_version_id,
    )
    project.updated_at = datetime.now(UTC)
    db.commit()
    return serialize_node(node, [])
