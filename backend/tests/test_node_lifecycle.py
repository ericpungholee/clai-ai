import uuid

import pytest
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt", "Change it"),
        ("settings", {"whiteBackground": False}),
        ("seed", 42),
        ("subject", None),
        ("mask", None),
    ],
)
def test_result_rejects_draft_patch(client: TestClient, field: str, value: object):
    project = create_project(client)
    node = create_node(client, project, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    submit_and_execute(client, project, node["id"], queue, FakeProvider())
    url = f"/api/projects/{project}/nodes/{node['id']}"
    response = client.patch(url, json={field: value})
    assert response.status_code == 409
    assert "frozen" in response.json()["detail"]
    assert (
        client.patch(
            url, json={"title": "New name", "position": {"x": 1, "y": 2}}
        ).status_code
        == 200
    )
    assert (
        client.post(url + "/runs", json={"idempotency_key": "second"}).status_code
        == 409
    )
    assert client.put(url + "/mask", json=None).status_code == 409
    assert client.delete(url + "/subject").status_code == 409
    assert (
        client.put(
            url + "/subject",
            json={"source_node_id": node["id"], "version_id": str(uuid.uuid4())},
        ).status_code
        == 409
    )
    assert (
        client.put(
            url + "/prompt", json={"document": [], "expected_revision": 0}
        ).status_code
        == 409
    )
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert len(graph["nodes"][0]["versions"]) == 1
    assert graph["nodes"][0]["prompt"] == "A lamp"


def test_failed_run_unlocks_draft_and_retry_freezes_it(client: TestClient):
    project = create_project(client)
    node = create_node(client, project, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    url = f"/api/projects/{project}/nodes/{node['id']}"
    run = client.post(url + "/runs", json={"idempotency_key": "failed"}).json()
    assert client.patch(url, json={"prompt": "While running"}).status_code == 409
    with TestingSessionLocal.begin() as db:
        db.get(RunJob, uuid.UUID(run["id"])).status = "failed"
    assert (
        client.patch(
            url,
            json={
                "prompt": "A copper lamp",
                "settings": {"whiteBackground": False},
                "seed": 9,
            },
        ).status_code
        == 200
    )
    assert client.put(url + "/mask", json=None).status_code == 200
    submit_and_execute(client, project, node["id"], queue, FakeProvider())
    assert client.patch(url, json={"prompt": "Another change"}).status_code == 409


def test_try_another_copies_inputs_and_persists_a_fresh_seed(client: TestClient):
    project = create_project(client)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    source = create_node(client, project, prompt="A lamp")
    _, image = submit_and_execute(client, project, source["id"], queue, FakeProvider())
    edited = client.post(
        f"/api/projects/{project}/versions/{image}/branches",
        json={"prompt": "Make it copper", "position": {"x": 380, "y": 0}},
    ).json()["node"]
    submit_and_execute(client, project, edited["id"], queue, FakeProvider())
    url = f"/api/projects/{project}/nodes/{edited['id']}/duplicate"
    revised = client.post(url, json={"position": {"x": 380, "y": 850}}).json()
    another = client.post(
        url, json={"fresh_seed": True, "position": {"x": 380, "y": 1700}}
    ).json()
    assert revised["seed"] == edited["seed"]
    assert isinstance(another["seed"], int)
    assert another["seed"] != revised["seed"]
    for node in [revised, another]:
        assert node["prompt"] == edited["prompt"]
        assert node["settings"] == edited["settings"]
        assert node["versions"] == [] and node["run"] is None
    graph = client.get(f"/api/projects/{project}/graph").json()
    for node in [edited, revised, another]:
        edge = next(
            edge for edge in graph["edges"] if edge["target_node_id"] == node["id"]
        )
        assert edge["pin"]["version_id"] == str(image)
    provider = FakeProvider()
    submit_and_execute(client, project, another["id"], queue, provider)
    assert provider.requests[-1].seed == another["seed"]


def test_legacy_selection_keeps_images_and_new_drafts_resolve_the_selection(
    client: TestClient,
):
    from app.models.graph import GraphNode, Version

    project = create_project(client)
    source = create_node(client, project, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, first = submit_and_execute(client, project, source["id"], queue, FakeProvider())
    # Seed an older multi-image node directly; new API submissions cannot do this.
    with TestingSessionLocal.begin() as db:
        original = db.get(Version, first)
        job = RunJob(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project),
            node_id=uuid.UUID(source["id"]),
            idempotency_key="legacy",
            status="complete",
            frozen_request={"op": "generate"},
        )
        db.add(job)
        db.flush()
        second = uuid.uuid4()
        attributes = {
            column.name: getattr(original, column.name)
            for column in Version.__table__.columns
            if column.name not in {"id", "run_job_id"}
        }
        db.add(Version(**attributes, id=second, run_job_id=job.id))
        db.flush()
        db.get(GraphNode, uuid.UUID(source["id"])).active_version_id = second
    url = f"/api/projects/{project}/nodes/{source['id']}"
    assert client.patch(url, json={"active_version_id": str(first)}).status_code == 200
    target = create_node(client, project, prompt="")
    client.put(
        f"/api/projects/{project}/nodes/{target['id']}/prompt",
        json={
            "expected_revision": 0,
            "document": [
                {
                    "type": "connect",
                    "edge_id": str(uuid.uuid4()),
                    "source_node_id": source["id"],
                }
            ],
        },
    )
    provider = FakeProvider()
    submit_and_execute(client, project, target["id"], queue, provider)
    assert provider.requests[-1].connects[0].id == str(first)
    assert client.patch(url, json={"active_version_id": str(second)}).status_code == 200
    assert (
        client.post(url + "/runs", json={"idempotency_key": "forbidden"}).status_code
        == 409
    )
    graph = client.get(f"/api/projects/{project}/graph").json()
    legacy = next(node for node in graph["nodes"] if node["id"] == source["id"])
    frozen = next(node for node in graph["nodes"] if node["id"] == target["id"])
    assert len(legacy["versions"]) == 2
    assert frozen["versions"][0]["input_snapshot"]["connect_version_ids"] == [
        str(first)
    ]


def test_migration_restores_a_hidden_image_without_splitting_nodes(client: TestClient):
    import runpy
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect, text

    from app.models.graph import GraphNode, Version

    project = create_project(client)
    source = create_node(client, project, prompt="A retained lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, image = submit_and_execute(client, project, source["id"], queue, FakeProvider())
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/c9512e4a731b_single_image_nodes.py"
    )
    with TestingSessionLocal.begin() as db:
        node = db.get(GraphNode, uuid.UUID(source["id"]))
        node.active_version_id = None
        db.flush()
        db.execute(
            text("CREATE TABLE version_visibility (version_id VARCHAR PRIMARY KEY)")
        )
        with Operations.context(MigrationContext.configure(db.connection())):
            runpy.run_path(str(migration))["upgrade"]()
        db.refresh(node)
        assert node.active_version_id == image
        assert db.get(Version, image) is not None
        assert "version_visibility" not in inspect(db.connection()).get_table_names()
    graph = client.get(f"/api/projects/{project}/graph").json()
    assert len(graph["nodes"]) == 1
    assert len(graph["nodes"][0]["versions"]) == 1
