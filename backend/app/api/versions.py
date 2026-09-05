import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.graph import get_project_or_404
from app.core.database import get_db
from app.models.graph import GraphNode, RunJob, Version, VersionVisibility

router = APIRouter(prefix="/api/projects/{project_id}/versions", tags=["versions"])


class VisibilityUpdate(BaseModel):
    hidden: bool


class CollapseReady(BaseModel):
    status: Literal["ready"] = "ready"
    root_version_id: uuid.UUID
    instruction: str
    steps: int


class CollapseUnavailable(BaseModel):
    status: Literal["unavailable"] = "unavailable"
    reason: str


def project_version(
    project_id: uuid.UUID, version_id: uuid.UUID, db: Session
) -> Version:
    version = db.scalar(
        select(Version)
        .join(GraphNode, GraphNode.id == Version.node_id)
        .where(Version.id == version_id, GraphNode.project_id == project_id)
    )
    if version is None:
        raise HTTPException(404, "Version not found")
    return version


@router.put("/{version_id}/visibility", status_code=204)
def update_visibility(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: VisibilityUpdate,
    db: Session = Depends(get_db),
) -> Response:
    project = get_project_or_404(project_id, db)
    version = project_version(project_id, version_id, db)
    visibility = db.get(VersionVisibility, version_id)
    if data.hidden and visibility is None:
        db.add(VersionVisibility(version_id=version_id))
    elif not data.hidden and visibility is not None:
        db.delete(visibility)
    db.flush()
    node = db.get(GraphNode, version.node_id)
    if data.hidden and node.active_version_id == version_id:
        node.active_version_id = db.scalar(
            select(Version.id)
            .where(
                Version.node_id == node.id,
                ~Version.id.in_(select(VersionVisibility.version_id)),
            )
            .order_by(Version.created_at.desc(), Version.id.desc())
            .limit(1)
        )
        node.revision += 1
    project.updated_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.get(
    "/{version_id}/collapse-preview", response_model=CollapseReady | CollapseUnavailable
)
def preview_collapse(
    project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db)
) -> CollapseReady | CollapseUnavailable:
    get_project_or_404(project_id, db)
    current = project_version(project_id, version_id, db)
    instructions: list[str] = []
    visited: set[uuid.UUID] = set()
    # This explicit preview is the only consumer of historical instructions.
    # It creates no run: the user sees/edits a new draft before ordinary dispatch.
    while current.op.startswith("edit_"):
        if current.id in visited:
            return CollapseUnavailable(reason="This historical chain contains a cycle.")
        visited.add(current.id)
        if current.op != "edit_instruct":
            return CollapseUnavailable(
                reason=(
                    "This chain includes a mask or connect reference. Its regions "
                    "and image positions cannot be safely reapplied to the root. "
                    "Branch from an earlier version instead."
                )
            )
        job = db.get(RunJob, current.run_job_id)
        instruction = job.frozen_request.get("user_prompt") if job else None
        if not isinstance(instruction, str) or not instruction.strip():
            # Pre-document runs lack user_prompt; parse only their exact legacy
            # envelope, never reinterpret or rewrite the immutable stored text.
            prefix = (
                "Preserve exactly every unmentioned attribute, including geometry,\n"
                "proportions, silhouette, camera angle, framing, lighting direction,\n"
                "and background.\nChange only: "
            )
            suffix = "\nDo not restyle or reinterpret any other element."
            runtime = current.prompt_at_runtime
            if not runtime.startswith(prefix) or not runtime.endswith(suffix):
                return CollapseUnavailable(
                    reason=(
                        "The original instruction is unavailable for an older run. "
                        "Its stored prompt has not been changed."
                    )
                )
            instruction = runtime[len(prefix) : -len(suffix)]
        instructions.append(instruction.strip())
        subject_id = current.input_snapshot.get("subject_version_id")
        if not isinstance(subject_id, str):
            return CollapseUnavailable(
                reason="This historical edit has no recorded subject."
            )
        current = project_version(project_id, uuid.UUID(subject_id), db)
    if len(instructions) < 2:
        return CollapseUnavailable(
            reason="There is no multi-edit chain to collapse yet."
        )
    instruction = (
        "Apply these changes in order; later changes take precedence:\n"
        + "\n".join(
            f"{index}. {text}" for index, text in enumerate(reversed(instructions), 1)
        )
    )
    if len(instruction) > 8000:
        return CollapseUnavailable(
            reason=(
                "The accumulated instructions exceed the prompt limit. "
                "Branch from an earlier version instead."
            )
        )
    return CollapseReady(
        root_version_id=current.id, instruction=instruction, steps=len(instructions)
    )
