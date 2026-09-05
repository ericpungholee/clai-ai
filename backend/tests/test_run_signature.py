import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models.graph import RunJob
from app.services.run_queue import get_run_enqueuer
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)


def test_preview_signature_tracks_draft_and_active_reference_not_position(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    provider = FakeProvider()
    source = create_node(client, project_id, prompt="A lamp")
    _, first = submit_and_execute(
        client, project_id, str(source["id"]), queue, provider
    )
    _, second = submit_and_execute(
        client, project_id, str(source["id"]), queue, provider
    )
    target = create_node(client, project_id, prompt="Change the shade")
    url = f"/api/projects/{project_id}/nodes/{target['id']}"

    def signature():
        response = client.get(f"{url}/run-preview")
        assert response.status_code == 200, response.text
        return response.json()["run_signature"]

    original = signature()
    assert client.patch(url, json={"position": {"x": 900, "y": 100}}).status_code == 200
    assert client.patch(url, json={"title": "Renamed"}).status_code == 200
    assert signature() == original
    assert client.patch(url, json={"prompt": "Change the base"}).status_code == 200
    changed_prompt = signature()
    assert changed_prompt != original
    assert (
        client.patch(
            url, json={"settings": {**target["settings"], "whiteBackground": False}}
        ).status_code
        == 200
    )
    changed_background = signature()
    assert changed_background != changed_prompt
    assert (
        client.put(
            f"{url}/subject",
            json={"source_node_id": source["id"], "version_id": str(first)},
        ).status_code
        == 200
    )
    first_subject = signature()
    assert (
        client.put(
            f"{url}/subject",
            json={"source_node_id": source["id"], "version_id": str(second)},
        ).status_code
        == 200
    )
    assert signature() != first_subject
    graph = client.get(f"/api/projects/{project_id}/graph").json()
    revision = next(
        node["revision"] for node in graph["nodes"] if node["id"] == target["id"]
    )
    assert (
        client.put(
            f"{url}/prompt",
            json={
                "expected_revision": revision,
                "document": [
                    {
                        "type": "connect",
                        "edge_id": str(uuid.uuid4()),
                        "source_node_id": source["id"],
                    },
                    {"type": "text", "text": " proportions"},
                ],
            },
        ).status_code
        == 200
    )
    reference = signature()
    assert (
        client.patch(
            f"/api/projects/{project_id}/nodes/{source['id']}",
            json={"active_version_id": str(first)},
        ).status_code
        == 200
    )
    assert signature() != reference


def test_reroll_changes_only_submission_seed_and_preserves_deduplication(
    client: TestClient, monkeypatch
) -> None:
    project_id = create_project(client)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    source = create_node(client, project_id, prompt="A lamp")
    url = f"/api/projects/{project_id}/nodes/{source['id']}"
    assert client.patch(url, json={"seed": 42}).status_code == 200
    _, version_id = submit_and_execute(
        client, project_id, str(source["id"]), queue, FakeProvider()
    )
    preview = client.get(f"{url}/run-preview").json()
    graph = client.get(f"/api/projects/{project_id}/graph").json()
    active = graph["nodes"][0]["versions"][0]
    assert active["id"] == str(version_id)
    assert active["run_signature"] == preview["run_signature"]
    assert active["seed"] == 42

    monkeypatch.setattr("app.services.run_jobs.secrets.randbits", lambda _: 1234)
    reroll = client.post(
        f"{url}/runs", json={"idempotency_key": "reroll", "reroll": True}
    )
    assert reroll.status_code == 202
    job_id = uuid.UUID(reroll.json()["id"])
    with TestingSessionLocal() as db:
        frozen = db.get(RunJob, job_id).frozen_request
        assert frozen["seed"] == 1234
        assert frozen["run_signature"] == active["run_signature"]
    for key in ("reroll", "another-tab"):
        duplicate = client.post(
            f"{url}/runs", json={"idempotency_key": key, "reroll": True}
        )
        assert duplicate.json()["id"] == str(job_id)
    assert queue.job_ids.count(job_id) == 1
    assert client.get(f"{url}/run-preview").json() == preview
    assert (
        client.get(f"/api/projects/{project_id}/graph").json()["nodes"][0]["seed"] == 42
    )
