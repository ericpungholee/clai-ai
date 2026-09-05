import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.graph import Version
from app.models.project import Project
from app.services.run_queue import get_run_enqueuer
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)


def test_worker_configuration_failure_cannot_leave_a_run_stuck(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.workers import celery_app as worker

    project = create_project(client)
    node = create_node(client, project, prompt="Lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    response = client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "broken-worker"},
    )
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)

    def broken_reader(_settings: object) -> None:
        raise OSError("fixture storage unavailable")

    monkeypatch.setattr(worker, "create_artifact_reader", broken_reader)
    with pytest.raises(OSError, match="fixture"):
        worker.run_job.run(response.json()["id"])
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert graph["nodes"][0]["run"]["status"] == "failed"
    assert graph["nodes"][0]["run"]["attempts"] == 0


def test_home_activity_thumbnail_rename_and_delete_retain_images(
    client: TestClient,
) -> None:
    first = create_project(client, "First")
    second = create_project(client, "Second")
    node = create_node(client, first, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version = submit_and_execute(
        client, first, str(node["id"]), queue, FakeProvider()
    )
    projects = client.get("/api/projects").json()
    assert projects[0]["id"] == first and projects[0]["thumbnail_url"]
    assert (
        client.patch(f"/api/projects/{second}", json={"name": "Renamed"}).status_code
        == 200
    )
    assert client.get("/api/projects").json()[0]["name"] == "Renamed"
    assert client.delete(f"/api/projects/{first}").status_code == 204
    assert len(client.get("/api/projects").json()) == 1
    assert client.get(f"/api/projects/{first}/graph").status_code == 404
    with TestingSessionLocal() as db:
        assert db.get(Project, uuid.UUID(first)).deleted_at is not None
        assert db.get(Version, version).artifact_url


def test_duplicate_keeps_draft_wiring_but_not_someone_elses_versions(
    client: TestClient,
) -> None:
    project = create_project(client)
    source = create_node(client, project, prompt="A lamp")
    target = create_node(client, project, prompt="Use this reference")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version = submit_and_execute(
        client, project, str(source["id"]), queue, FakeProvider()
    )
    prefix = f"/api/projects/{project}/nodes/{target['id']}"
    client.put(
        prefix + "/subject",
        json={"source_node_id": source["id"], "version_id": str(version)},
    )
    document = [
        {"type": "text", "text": "Take the finish from "},
        {
            "type": "connect",
            "source_node_id": source["id"],
            "edge_id": str(uuid.uuid4()),
        },
    ]
    client.put(prefix + "/prompt", json={"document": document, "expected_revision": 0})
    duplicate = client.post(
        prefix + "/duplicate", json={"position": {"x": 500, "y": 500}}
    )
    assert duplicate.status_code == 201, duplicate.text
    copied = duplicate.json()
    assert copied["versions"] == [] and copied["active_version_id"] is None
    assert copied["document"][0] == document[0]
    assert copied["document"][1]["source_node_id"] == source["id"]
    assert copied["document"][1]["edge_id"] != document[1]["edge_id"]
    graph = client.get(f"/api/projects/{project}/graph").json()
    edges = [edge for edge in graph["edges"] if edge["target_node_id"] == copied["id"]]
    assert len(edges) == 2
    assert next(edge for edge in edges if edge["role"] == "subject")["pin"][
        "version_id"
    ] == str(version)


def test_graph_rehydrates_durable_run_and_completion_never_overwrites_draft(
    client: TestClient,
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="First frozen instruction")
    queue, provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/nodes/{node['id']}"
    submitted = client.post(prefix + "/runs", json={"idempotency_key": "one"}).json()
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert graph["nodes"][0]["run"]["id"] == submitted["id"]
    assert graph["nodes"][0]["run"]["status"] == "queued"
    client.patch(
        prefix, json={"prompt": "New draft while running", "expected_revision": 0}
    )
    from app.services.run_execution import execute_run_job
    from tests.test_graph import FakeDinoV2Scorer, FakeIngestor

    execute_run_job(
        job_id=uuid.UUID(submitted["id"]),
        session_factory=TestingSessionLocal,
        provider=provider,
        ingestor=FakeIngestor(),
        scorer=FakeDinoV2Scorer(),
    )
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert graph["nodes"][0]["prompt"] == "New draft while running"
    assert graph["nodes"][0]["run"]["status"] == "complete"
    assert graph["nodes"][0]["versions"][0]["prompt_at_runtime"].startswith(
        "First frozen instruction"
    )
