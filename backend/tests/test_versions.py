import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.graph import GraphNode, RunJob, Version
from app.services.run_queue import get_run_enqueuer
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)


def test_collapse_is_an_explicit_draft_and_deletion_never_erases_history(
    client: TestClient,
) -> None:
    project = create_project(client)
    root = create_node(client, project, prompt="ROOT PROMPT NEVER INHERITED")
    queue, provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, root_version = submit_and_execute(
        client, project, str(root["id"]), queue, provider
    )
    version = root_version
    for index in range(5):
        branch = client.post(
            f"/api/projects/{project}/versions/{version}/branches",
            json={
                "prompt": f"Change feature {index}",
                "position": {"x": index * 400, "y": 0},
            },
        ).json()
        _, version = submit_and_execute(
            client, project, branch["node"]["id"], queue, provider
        )
    node_id = branch["node"]["id"]
    prefix = f"/api/projects/{project}/versions/{version}"
    preview = client.get(prefix + "/collapse-preview").json()
    assert preview["status"] == "ready" and preview["steps"] == 5
    assert preview["root_version_id"] == str(root_version)
    assert "ROOT PROMPT" not in preview["instruction"]
    assert preview["instruction"].index("feature 0") < preview["instruction"].index(
        "feature 4"
    )
    assert "feature 0" not in provider.requests[-1].prompt_at_runtime
    assert provider.requests[-1].edit_depth == 5
    graph = client.get(f"/api/projects/{project}/graph").json()
    original = next(node for node in graph["nodes"] if node["id"] == node_id)[
        "versions"
    ][0]
    assert original["masked_outside_change"] is None
    root_node = next(node for node in graph["nodes"] if node["id"] == root["id"])
    assert len(root_node["versions"][0]["branch_node_ids"]) == 1
    with TestingSessionLocal() as db:
        prompts_before = list(db.execute(select(Version.id, Version.prompt_at_runtime)))
    collapsed = client.post(
        f"/api/projects/{project}/versions/{root_version}/branches",
        json={"prompt": preview["instruction"], "position": {"x": 0, "y": 500}},
    ).json()
    submit_and_execute(client, project, collapsed["node"]["id"], queue, provider)
    assert provider.requests[-1].subject.id == str(root_version)
    assert provider.requests[-1].edit_depth == 1
    assert provider.requests[-1].user_prompt == preview["instruction"]
    assert client.delete(f"/api/projects/{project}/nodes/{node_id}").status_code == 204
    with TestingSessionLocal() as db:
        assert db.get(Version, version) is not None
        assert db.get(GraphNode, uuid.UUID(node_id)).deleted_at is not None
        assert set(prompts_before) <= set(
            db.execute(select(Version.id, Version.prompt_at_runtime))
        )
    retained_branch = client.post(
        prefix + "/branches",
        json={"prompt": "Retained subject edit", "position": {"x": 50, "y": 50}},
    )
    assert retained_branch.status_code == 201
    submit_and_execute(
        client, project, retained_branch.json()["node"]["id"], queue, provider
    )
    assert provider.requests[-1].subject.id == str(version)


def test_collapse_does_not_guess_historical_instructions(client: TestClient) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Lamp")
    queue, provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, root = submit_and_execute(client, project, str(node["id"]), queue, provider)
    url = f"/api/projects/{project}/versions"
    assert (
        client.get(f"{url}/{root}/collapse-preview").json()["status"] == "unavailable"
    )
    other_project = create_project(client)
    assert (
        client.get(
            f"/api/projects/{other_project}/versions/{root}/collapse-preview"
        ).status_code
        == 404
    )
    branch = client.post(
        f"{url}/{root}/branches",
        json={"prompt": "Make it blue", "position": {"x": 1, "y": 1}},
    ).json()
    legacy = (
        "Preserve exactly every unmentioned attribute, including geometry,\n"
        "proportions, silhouette, camera angle, framing, lighting direction,\n"
        "and background.\nChange only: {resolved_user_prompt}\n"
        "Do not restyle or reinterpret any other element."
    )
    with patch(
        "app.services.run_freezing.build_prompt",
        return_value=legacy.format(resolved_user_prompt="Make it blue"),
    ):
        _, edit = submit_and_execute(
            client, project, branch["node"]["id"], queue, provider
        )
    with TestingSessionLocal() as db:
        job = db.scalar(
            select(RunJob)
            .join(Version, Version.run_job_id == RunJob.id)
            .where(Version.id == edit)
        )
        # Older jobs have no separate user_prompt; recover only an exact known template.
        job.frozen_request = {
            key: value
            for key, value in job.frozen_request.items()
            if key != "user_prompt"
        }
        db.commit()
    branch = client.post(
        f"{url}/{edit}/branches",
        json={"prompt": "Make the base square", "position": {"x": 2, "y": 2}},
    ).json()
    _, last = submit_and_execute(client, project, branch["node"]["id"], queue, provider)
    preview = client.get(f"{url}/{last}/collapse-preview").json()
    assert preview["status"] == "ready" and "Make it blue" in preview["instruction"]
