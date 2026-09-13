import base64
import binascii
import uuid
from io import BytesIO
from typing import Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.graph import get_project_or_404
from app.core.config import settings
from app.core.database import get_db
from app.domain.image_views import mesh_view_urls
from app.models.graph import GraphNode, Version, VersionMesh
from app.providers.trellis import TRELLIS_MULTI_ENDPOINT
from app.schemas.mesh_logo import LogoPreservation, MeshDecal
from app.storage.artifacts import ArtifactStore
from app.storage.factory import create_artifact_store

router = APIRouter(
    prefix="/api/projects/{project_id}/versions/{version_id}/mesh", tags=["mesh"]
)


class MeshCreate(BaseModel):
    attempt_id: uuid.UUID
    texture: Literal["no", "standard"] = "standard"
    regenerate: bool = False
    model: Literal["trellis"] = "trellis"


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
    model: str
    logo_preservation: LogoPreservation | None = None
    source_views: dict[str, str] = Field(default_factory=dict)


class LogoUpdate(BaseModel):
    attempt_id: uuid.UUID
    decal: MeshDecal | None


def get_logo_store() -> ArtifactStore:
    return create_artifact_store(settings)


class MeshEnqueuer(Protocol):
    def enqueue(self, version_id: uuid.UUID, attempt_id: uuid.UUID) -> None: ...


class CeleryMeshEnqueuer:
    def enqueue(self, version_id: uuid.UUID, attempt_id: uuid.UUID) -> None:
        from app.workers.celery_app import mesh_job

        mesh_job.delay(str(version_id), str(attempt_id))


def get_mesh_enqueuer() -> MeshEnqueuer:
    return CeleryMeshEnqueuer()


def mesh_data(mesh: VersionMesh) -> MeshData:
    data = MeshData.model_validate(mesh, from_attributes=True)
    data.source_views = mesh.provider_response_metadata.get("source_views", {})
    logo = mesh.provider_response_metadata.get("logo_preservation")
    if logo is not None:
        data.logo_preservation = LogoPreservation.model_validate(logo)
    return data


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
    get_project_or_404(project_id, db, lock=False)
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
        regenerate = mesh.status == "complete" and data.regenerate
        if mesh.attempt_id == data.attempt_id or (
            mesh.status != "failed" and not upgrade_texture and not regenerate
        ):
            return mesh_data(mesh)
    version = db.get(Version, version_id)
    try:
        views = mesh_view_urls(
            front_url=source_url, metadata=version.provider_response_metadata
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if mesh is None:
        mesh = VersionMesh(
            version_id=version_id, provider="fal", model=TRELLIS_MULTI_ENDPOINT
        )
        db.add(mesh)
    mesh.provider = "fal"
    mesh.model = TRELLIS_MULTI_ENDPOINT
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
    mesh.provider_response_metadata = {
        "source_views": views,
        "input_policy": "stored_five_views",
    }
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


@router.put("/logo", response_model=LogoPreservation)
def update_logo(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: LogoUpdate,
    db: Session = Depends(get_db),
    store: ArtifactStore = Depends(get_logo_store),
) -> LogoPreservation:
    get_project_or_404(project_id, db)
    source_url = source_image(project_id, version_id, db)
    mesh = db.scalar(
        select(VersionMesh)
        .where(VersionMesh.version_id == version_id)
        .with_for_update()
    )
    if mesh is None:
        raise HTTPException(404, "Mesh not found")
    if mesh.status != "complete" or mesh.attempt_id != data.attempt_id:
        raise HTTPException(409, "This mesh generation has changed. Reopen the viewer.")
    decal = data.decal
    if decal is not None:
        if decal.source.url != (mesh.source_artifact_url or source_url):
            raise HTTPException(422, "The logo must use this mesh's original image")
        current = mesh_data(mesh).logo_preservation
        previous_crop = current.decal.crop if current and current.decal else None
        if decal.crop.dataUrl.startswith("data:image/png;base64,"):
            try:
                content = base64.b64decode(
                    decal.crop.dataUrl.split(",", 1)[1], validate=True
                )
                with Image.open(BytesIO(content)) as png:
                    if png.format != "PNG" or png.size != (
                        decal.crop.width,
                        decal.crop.height,
                    ):
                        raise ValueError("Invalid crop dimensions")
                    png.verify()
            except (
                ValueError,
                binascii.Error,
                OSError,
                UnidentifiedImageError,
            ) as error:
                raise HTTPException(422, "Invalid logo PNG") from error
            stored = store.put(
                key=f"meshes/{mesh.attempt_id}/logo.png",
                content=content,
                content_type="image/png",
            )
            decal.crop.dataUrl = stored.artifact_url
        elif previous_crop is None or decal.crop != previous_crop:
            # Never fetch a client-supplied URL or persist expiring external crops.
            raise HTTPException(422, "Use the saved crop or upload a PNG selection")
    logo = LogoPreservation(status="ready" if decal else "removed", decal=decal)
    # Assign a new object: the existing JSON column is not a MutableDict.
    mesh.provider_response_metadata = {
        **mesh.provider_response_metadata,
        "logo_preservation": logo.model_dump(mode="json"),
    }
    db.commit()
    return logo
