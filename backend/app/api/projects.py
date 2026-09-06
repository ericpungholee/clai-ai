import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc(), Project.id)
        )
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
) -> Project:
    project = Project(name=project_data.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def rename_project(
    project_id: uuid.UUID, data: ProjectCreate, db: Session = Depends(get_db)
) -> Project:
    project = get_project(project_id, db)
    project.name = data.name
    project.updated_at = datetime.now(UTC)
    db.commit()
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    project = db.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    if project is None:
        raise HTTPException(404, "Project not found")
    project.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
