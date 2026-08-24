from fastapi.testclient import TestClient

from app.main import app
from app.workers.celery_app import celery_app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_task_is_registered() -> None:
    assert "clai.ping" in celery_app.tasks
