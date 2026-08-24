import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_create_list_and_get_project(client: TestClient) -> None:
    create_response = client.post(
        "/api/projects",
        json={"name": "  Desk Lamp Exploration  "},
    )

    assert create_response.status_code == 201
    created_project = create_response.json()
    assert created_project["name"] == "Desk Lamp Exploration"
    assert created_project["thumbnail_url"] is None

    list_response = client.get("/api/projects")
    assert list_response.status_code == 200
    assert list_response.json() == [created_project]

    get_response = client.get(f"/api/projects/{created_project['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == created_project


def test_project_name_is_required(client: TestClient) -> None:
    response = client.post("/api/projects", json={"name": "   "})

    assert response.status_code == 422


def test_missing_project_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/api/projects/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_invalid_project_id_returns_validation_error(client: TestClient) -> None:
    response = client.get("/api/projects/not-a-project-id")

    assert response.status_code == 422
