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


def test_atomic_chips_order_active_following_broken_refs_and_conflicts(
    client: TestClient,
) -> None:
    project = create_project(client)
    a = create_node(client, project, prompt="A lamp")
    b = create_node(client, project, prompt="A logo")
    target = create_node(client, project, prompt="")
    queue, provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, av = submit_and_execute(client, project, str(a["id"]), queue, provider)
    _, bv = submit_and_execute(client, project, str(b["id"]), queue, provider)
    prefix = f"/api/projects/{project}/nodes/{target['id']}"
    a_chip = {
        "type": "connect",
        "edge_id": str(uuid.uuid4()),
        "source_node_id": a["id"],
    }
    b_chip = {
        "type": "connect",
        "edge_id": str(uuid.uuid4()),
        "source_node_id": b["id"],
    }
    document = [
        {"type": "text", "text": "Put the logo from "},
        b_chip,
        {"type": "text", "text": " on "},
        a_chip,
    ]
    saved = client.put(
        prefix + "/prompt", json={"document": document, "expected_revision": 0}
    )
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["edges"]) == 2
    assert (
        client.put(
            prefix + "/prompt", json={"document": [], "expected_revision": 0}
        ).status_code
        == 409
    )
    submitted = client.post(prefix + "/runs", json={"idempotency_key": "first"})
    assert submitted.status_code == 202, submitted.text
    with TestingSessionLocal() as db:
        frozen = db.get(RunJob, uuid.UUID(submitted.json()["id"])).frozen_request
        assert frozen["input_snapshot"]["connect_version_ids"] == [str(bv), str(av)]
        assert frozen["prompt_at_runtime"].startswith(
            "Put the logo from image 1 on image 2"
        )
        assert "A lamp" not in frozen["prompt_at_runtime"]
    _, new_av = submit_and_execute(client, project, str(a["id"]), queue, provider)
    assert (
        client.put(
            prefix + "/subject", json={"source_node_id": a["id"], "version_id": str(av)}
        ).status_code
        == 200
    )
    reordered = [a_chip, {"type": "text", "text": " with "}, b_chip]
    assert (
        client.put(
            prefix + "/prompt", json={"document": reordered, "expected_revision": 1}
        ).status_code
        == 200
    )
    submitted = client.post(prefix + "/runs", json={"idempotency_key": "second"})
    with TestingSessionLocal() as db:
        frozen = db.get(RunJob, uuid.UUID(submitted.json()["id"])).frozen_request
        assert frozen["input_snapshot"]["subject_version_id"] == str(av)
        assert frozen["input_snapshot"]["connect_version_ids"] == [str(new_av), str(bv)]
        assert "image 2 with image 3" in frozen["prompt_at_runtime"]
    assert client.delete(f"/api/projects/{project}/nodes/{b['id']}").status_code == 204
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert next(node for node in graph["nodes"] if node["id"] == b["id"])["deleted"]
    broken = client.post(prefix + "/runs", json={"idempotency_key": "broken"})
    assert broken.status_code == 422 and "missing node" in broken.text
    assert (
        client.put(
            prefix + "/prompt", json={"document": [a_chip], "expected_revision": 2}
        ).status_code
        == 200
    )
    assert len(client.get(f"/api/projects/{project}/graph").json()["edges"]) == 2


def test_duplicate_self_empty_and_plain_at_text(client: TestClient) -> None:
    project = create_project(client)
    source = create_node(client, project, prompt="empty")
    target = create_node(client, project, prompt="")
    prefix = f"/api/projects/{project}/nodes/{target['id']}"
    chip = {
        "type": "connect",
        "source_node_id": source["id"],
        "edge_id": str(uuid.uuid4()),
    }
    for document in (
        [chip, chip],
        [{**chip, "source_node_id": target["id"]}],
        [chip, {**chip, "edge_id": str(uuid.uuid4())}],
    ):
        assert (
            client.put(
                prefix + "/prompt", json={"document": document, "expected_revision": 0}
            ).status_code
            == 422
        )
    assert (
        client.put(
            prefix + "/prompt", json={"document": [chip], "expected_revision": 0}
        ).status_code
        == 200
    )
    assert (
        client.post(prefix + "/runs", json={"idempotency_key": "empty"}).status_code
        == 422
    )
    graph = client.put(
        prefix + "/prompt",
        json={
            "document": [{"type": "text", "text": "literal @text"}],
            "expected_revision": 1,
        },
    ).json()
    assert graph["edges"] == []
