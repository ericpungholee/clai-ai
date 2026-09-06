import uuid
from typing import Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.graph import get_project_or_404
from app.core.database import get_db
from app.models.graph import GraphNode, Version, VersionMesh
from app.providers.tripo import TRIPO_ENDPOINT

router = APIRouter(
    prefix="/api/projects/{project_id}/versions/{version_id}/mesh", tags=["mesh"]
)


class MeshCreate(BaseModel):
    attempt_id: uuid.UUID
    texture: Literal["no", "standard"] = "standard"


class MeshData(BaseModel):
    version_id: uuid.UUID
    attempt_id: uuid.UUID
    status: Literal[
        "queued", "dispatching", "provider_pending", "ingesting", "complete", "failed"
    ]
    texture: Literal["no", "standard"]
    artifact_url: str | None
    preview_url: str | None
    error: str | None
    elapsed_seconds: float | None


class MeshEnqueuer(Protocol):
    def enqueue(self, version_id: uuid.UUID, attempt_id: uuid.UUID) -> None: ...


class CeleryMeshEnqueuer:
    def enqueue(self, version_id: uuid.UUID, attempt_id: uuid.UUID) -> None:
        from app.workers.celery_app import mesh_job

        mesh_job.delay(str(version_id), str(attempt_id))


def get_mesh_enqueuer() -> MeshEnqueuer:
    return CeleryMeshEnqueuer()


def mesh_data(mesh: VersionMesh) -> MeshData:
    return MeshData.model_validate(mesh, from_attributes=True)


def source_image(project_id: uuid.UUID, version_id: uuid.UUID, db: Session) -> str:
    url = db.scalar(
        select(Version.artifact_url)
        .join(GraphNode, GraphNode.id == Version.node_id)
        .where(Version.id == version_id, GraphNode.project_id == project_id)
    )
    if url is None:
        raise HTTPException(404, "Image not found")
    return url


@router.get("", response_model=MeshData | None)
def get_mesh(
    project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db)
) -> MeshData | None:
    get_project_or_404(project_id, db)
    source_image(project_id, version_id, db)
    mesh = db.get(VersionMesh, version_id)
    return mesh_data(mesh) if mesh else None


@router.post("", response_model=MeshData, status_code=202)
def create_mesh(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: MeshCreate,
    db: Session = Depends(get_db),
    enqueuer: MeshEnqueuer = Depends(get_mesh_enqueuer),
) -> MeshData:
    get_project_or_404(project_id, db)
    source_url = source_image(project_id, version_id, db)
    # Serialize creation and upgrades even before this version has a cache row.
    db.execute(select(Version.id).where(Version.id == version_id).with_for_update())
    mesh = db.get(VersionMesh, version_id)
    if mesh:
        upgrade_texture = (
            mesh.status == "complete"
            and mesh.texture == "no"
            and data.texture == "standard"
        )
        if mesh.attempt_id == data.attempt_id or (
            mesh.status != "failed" and not upgrade_texture
        ):
            return mesh_data(mesh)
    if mesh is None:
        mesh = VersionMesh(version_id=version_id, provider="fal", model=TRIPO_ENDPOINT)
        db.add(mesh)
    mesh.attempt_id = data.attempt_id
    mesh.texture = data.texture
    mesh.status = "queued"
    mesh.source_artifact_url = source_url
    mesh.artifact_url = None
    mesh.preview_url = None
    mesh.error = None
    mesh.elapsed_seconds = None
    mesh.started_at = None
    mesh.provider_request_id = None
    mesh.provider_response_metadata = {}
    mesh.request_payload = {}
    db.commit()
    try:
        enqueuer.enqueue(version_id, data.attempt_id)
    except Exception as error:
        mesh = db.scalar(
            select(VersionMesh)
            .where(VersionMesh.version_id == version_id)
            .with_for_update()
        )
        if mesh.status != "queued" or mesh.attempt_id != data.attempt_id:
            return mesh_data(mesh)
        mesh.status = "failed"
        mesh.error = "The 3D job could not be queued. Your image is unchanged."
        db.commit()
        raise HTTPException(503, mesh.error) from error
    return mesh_data(mesh)
