import uuid

from fastapi.testclient import TestClient


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
