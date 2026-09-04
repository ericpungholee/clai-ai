import uuid
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.domain.runs import MaskSnapshot
from app.models.graph import GraphEdge, GraphNode, Version
from app.providers.fal_transport import FalSdkTransport
from app.providers.sam import SamSelector
from app.schemas.graph import MaskData
from app.services.masks import validate_mask
from app.storage.factory import create_artifact_reader

router = APIRouter(prefix="/api/projects/{project_id}", tags=["masks"])


class Point(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    label: Literal[0, 1]


class Selection(BaseModel):
    text: str = Field(default="", max_length=240)
    points: list[Point] = Field(default_factory=list, max_length=32)


def get_sam_selector() -> SamSelector:
    if settings.fal_api_key is None:
        raise HTTPException(503, "Image selection is unavailable: configure FAL_KEY")
    return SamSelector(FalSdkTransport(settings.fal_api_key))


@router.put("/nodes/{node_id}/mask", response_model=MaskData | None)
def put_mask(
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    data: MaskData | None = None,
    db: Session = Depends(get_db),
) -> MaskData | None:
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
        raise HTTPException(404, "Node not found")
    if data is None:
        node.mask_rle = node.mask_width = node.mask_height = (
            node.mask_subject_version_id
        ) = None
    else:
        edge = db.scalar(
            select(GraphEdge).where(
                GraphEdge.target_node_id == node_id, GraphEdge.role == "subject"
            )
        )
        if edge is None or edge.pinned_version_id != data.subject_version_id:
            raise HTTPException(
                409,
                "The subject changed. Reopen the mask editor for its current version.",
            )
        version = db.get(Version, data.subject_version_id)
        if version is None:
            raise HTTPException(404, "Subject version not found")
        try:
            validate_mask(
                MaskSnapshot(
                    data.rle, data.width, data.height, str(data.subject_version_id)
                )
            )
            image = create_artifact_reader(settings).read(version.artifact_url)
            if Image.open(BytesIO(image.content)).size != (data.width, data.height):
                raise ValueError("Mask dimensions must match the subject image")
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        node.mask_rle, node.mask_width, node.mask_height = (
            data.rle,
            data.width,
            data.height,
        )
        node.mask_subject_version_id = data.subject_version_id
    db.commit()
    return data


@router.post("/versions/{version_id}/selection", response_model=MaskData | None)
def select_region(
    project_id: uuid.UUID,
    version_id: uuid.UUID,
    data: Selection,
    db: Session = Depends(get_db),
    selector: SamSelector = Depends(get_sam_selector),
) -> MaskData | None:
    version = db.scalar(
        select(Version)
        .join(GraphNode, GraphNode.id == Version.node_id)
        .where(Version.id == version_id, GraphNode.project_id == project_id)
    )
    if version is None:
        raise HTTPException(404, "Version not found")
    if not data.text.strip() and not data.points:
        raise HTTPException(422, "Click the image or describe an area to select")
    artifact = create_artifact_reader(settings).read(version.artifact_url)
    width, height = Image.open(BytesIO(artifact.content)).size
    if any(point.x >= width or point.y >= height for point in data.points):
        raise HTTPException(422, "Selection points must be inside the image")
    try:
        mask = selector.select(
            image=artifact,
            version_id=str(version_id),
            width=width,
            height=height,
            text=data.text.strip(),
            points=[point.model_dump() for point in data.points],
        )
    except Exception as error:
        raise HTTPException(
            502, "Selection failed. Your existing mask is unchanged."
        ) from error
    if mask is None:
        return None
    return MaskData(
        rle=mask.rle, width=width, height=height, subject_version_id=version_id
    )
