import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.runs import FrozenRunRequest, Op
from app.main import app
from app.models.graph import GraphEdge, GraphNode, RunJob, Version, VersionMetric
from app.providers.base import ProviderJob, ProviderResult
from app.services.run_execution import (
    ChangeMagnitudeResult,
    execute_run_job,
)
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import StoredArtifact
from tests.conftest import TestingSessionLocal


class CapturingEnqueuer:
    def __init__(self) -> None:
        self.job_ids: list[uuid.UUID] = []

    def enqueue(self, job_id: uuid.UUID) -> None:
        self.job_ids.append(job_id)


class FakeProvider:
    id = "fake"

    def __init__(self) -> None:
        self.requests: list[FrozenRunRequest] = []

    def execute(self, request: FrozenRunRequest) -> ProviderJob:
        self.requests.append(request)
        return ProviderJob(
            provider="fake",
            model="fixture-image-v1",
            endpoint=f"fake/{request.op.value}",
            request_id=f"fake-{len(self.requests)}",
            request_payload={
                "prompt": request.prompt_at_runtime,
                "seed": request.seed,
            },
        )

    def result(self, job: ProviderJob) -> ProviderResult:
        return ProviderResult(
            job=job,
            output_url=f"https://fake.provider/{job.request_id}.png",
            content_type="image/png",
            width=1024,
            height=1024,
            response_metadata={"fixture": True},
        )


class FakeIngestor:
    def ingest(self, result: ProviderResult) -> StoredArtifact:
        output_name = (
            "same-shoe-navy.png"
            if result.job.endpoint.endswith("edit_instruct")
            else "original-shoe.png"
        )
        return StoredArtifact(
            storage_key=f"fake/{output_name}",
            artifact_url=f"https://cdn.clai.test/{output_name}",
            content_type="image/png",
            byte_size=18,
            sha256="a" * 64,
        )


class FakeDinoV2Scorer:
    def score(
        self, *, request: FrozenRunRequest, artifact: StoredArtifact
    ) -> ChangeMagnitudeResult:
        assert request.op is Op.EDIT_INSTRUCT
        assert artifact.artifact_url.endswith("same-shoe-navy.png")
        return ChangeMagnitudeResult(
            method="dinov2_cosine", status="complete", value=0.9301
        )


def create_project(client: TestClient, name: str = "Footwear") -> str:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def create_node(
    client: TestClient,
    project_id: str,
    *,
    prompt: str,
    x: float = 100,
    y: float = 100,
) -> dict[str, object]:
    response = client.post(
        f"/api/projects/{project_id}/nodes",
        json={"prompt": prompt, "position": {"x": x, "y": y}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_and_execute(
    client: TestClient,
    project_id: str,
    node_id: str,
    enqueuer: CapturingEnqueuer,
    provider: FakeProvider,
) -> tuple[dict[str, object], uuid.UUID]:
    response = client.post(
        f"/api/projects/{project_id}/nodes/{node_id}/runs",
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert response.status_code == 202, response.text
    job_id = enqueuer.job_ids[-1]
    version_id = execute_run_job(
        job_id=job_id,
        session_factory=TestingSessionLocal,
        provider=provider,
        ingestor=FakeIngestor(),
        scorer=FakeDinoV2Scorer(),
    )
    return response.json(), version_id


def test_empty_project_returns_empty_graph(client: TestClient) -> None:
    project_id = create_project(client)

    response = client.get(f"/api/projects/{project_id}/graph")

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_scoped_node_create_and_patch_preserve_position_and_prompt(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    node = create_node(client, project_id, prompt="A blue shoe")

    response = client.patch(
        f"/api/projects/{project_id}/nodes/{node['id']}",
        json={
            "title": "Runner",
            "prompt": "A low-profile running shoe",
            "position": {"x": -40, "y": 315.5},
        },
    )

    assert response.status_code == 200
    saved = client.get(f"/api/projects/{project_id}/graph").json()["nodes"][0]
    assert saved["title"] == "Runner"
    assert saved["prompt"] == "A low-profile running shoe"
    assert saved["position"] == {"x": -40.0, "y": 315.5}


def test_white_background_defaults_for_new_nodes_and_freezes_per_version(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    node = create_node(client, project_id, prompt="A sculptural desk lamp")
    assert node["settings"]["whiteBackground"] is True
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    provider = FakeProvider()

    _, first_version_id = submit_and_execute(
        client, project_id, str(node["id"]), enqueuer, provider
    )
    assert provider.requests[-1].settings.white_background is True
    assert provider.requests[-1].prompt_at_runtime.endswith(
        "Place the object on a clean white background."
    )

    settings = {**node["settings"], "whiteBackground": False}
    patched = client.patch(
        f"/api/projects/{project_id}/nodes/{node['id']}",
        json={"settings": settings},
    )
    assert patched.status_code == 200
    _, second_version_id = submit_and_execute(
        client, project_id, str(node["id"]), enqueuer, provider
    )
    assert provider.requests[-1].settings.white_background is False
    assert provider.requests[-1].prompt_at_runtime == "A sculptural desk lamp"

    graph = client.get(f"/api/projects/{project_id}/graph").json()
    versions = {version["id"]: version for version in graph["nodes"][0]["versions"]}
    assert versions[str(first_version_id)]["params"]["whiteBackground"] is True
    assert versions[str(second_version_id)]["params"]["whiteBackground"] is False
    assert versions[str(first_version_id)]["prompt_at_runtime"].endswith(
        "Place the object on a clean white background."
    )


def test_legacy_node_without_white_background_remains_disabled(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    node_id = uuid.uuid4()
    with TestingSessionLocal.begin() as db:
        db.add(
            GraphNode(
                id=node_id,
                project_id=uuid.UUID(project_id),
                title="Legacy",
                prompt="A legacy lamp",
                settings={"aspect_ratio": "1:1", "width": 1024, "height": 1024},
                position_x=0,
                position_y=0,
            )
        )

    graph_node = client.get(f"/api/projects/{project_id}/graph").json()["nodes"][0]
    assert graph_node["settings"]["whiteBackground"] is False
    with TestingSessionLocal() as db:
        stored_settings = db.get(GraphNode, node_id).settings
        assert "whiteBackground" not in stored_settings


def test_node_validation_rejects_non_finite_position(client: TestClient) -> None:
    project_id = create_project(client)
    payload = '{"prompt":"shoe","position":{"x":1e309,"y":0}}'

    response = client.post(
        f"/api/projects/{project_id}/nodes",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}/graph").json()["nodes"] == []


def test_run_submit_is_idempotent_and_enqueues_once(client: TestClient) -> None:
    project_id = create_project(client)
    node = create_node(client, project_id, prompt="A shoe")
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    key = str(uuid.uuid4())

    first = client.post(
        f"/api/projects/{project_id}/nodes/{node['id']}/runs",
        json={"idempotency_key": key},
    )
    second = client.post(
        f"/api/projects/{project_id}/nodes/{node['id']}/runs",
        json={"idempotency_key": key},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert enqueuer.job_ids == [uuid.UUID(first.json()["id"])]


def test_subject_drag_replaces_existing_pin(client: TestClient) -> None:
    project_id = create_project(client)
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    provider = FakeProvider()
    first = create_node(client, project_id, prompt="First shoe")
    second = create_node(client, project_id, prompt="Second shoe", x=350)
    target = create_node(client, project_id, prompt="make it navy", x=650)
    _, first_version = submit_and_execute(
        client, project_id, str(first["id"]), enqueuer, provider
    )
    _, second_version = submit_and_execute(
        client, project_id, str(second["id"]), enqueuer, provider
    )

    first_edge = client.put(
        f"/api/projects/{project_id}/nodes/{target['id']}/subject",
        json={"source_node_id": first["id"], "version_id": str(first_version)},
    )
    second_edge = client.put(
        f"/api/projects/{project_id}/nodes/{target['id']}/subject",
        json={"source_node_id": second["id"], "version_id": str(second_version)},
    )

    assert first_edge.status_code == 200
    assert second_edge.status_code == 200
    assert first_edge.json()["id"] == second_edge.json()["id"]
    graph = client.get(f"/api/projects/{project_id}/graph").json()
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["pin"] == {
        "mode": "version",
        "version_id": str(second_version),
    }


def test_branch_from_historical_version_creates_pinned_subject(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    source = create_node(client, project_id, prompt="A shoe")
    _, version_id = submit_and_execute(
        client, project_id, str(source["id"]), enqueuer, FakeProvider()
    )

    response = client.post(
        f"/api/projects/{project_id}/versions/{version_id}/branches",
        json={"position": {"x": 450, "y": 100}},
    )

    assert response.status_code == 201
    assert response.json()["edge"]["pin"]["version_id"] == str(version_id)
    assert response.json()["node"]["versions"] == []


def test_navy_shoe_acceptance_runs_real_pipeline_with_fake_provider(
    client: TestClient,
) -> None:
    project_id = create_project(client)
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    provider = FakeProvider()

    shoe = create_node(client, project_id, prompt="A blue and yellow running shoe")
    _, subject_version_id = submit_and_execute(
        client, project_id, str(shoe["id"]), enqueuer, provider
    )
    branch = create_node(client, project_id, prompt="make it navy", x=440)
    wire = client.put(
        f"/api/projects/{project_id}/nodes/{branch['id']}/subject",
        json={
            "source_node_id": shoe["id"],
            "version_id": str(subject_version_id),
        },
    )
    assert wire.status_code == 200
    preview = client.get(f"/api/projects/{project_id}/nodes/{branch['id']}/run-preview")
    assert preview.json() == {"op": "edit_instruct"}

    queued = client.post(
        f"/api/projects/{project_id}/nodes/{branch['id']}/runs",
        json={"idempotency_key": "navy-shoe-acceptance"},
    )
    assert queued.status_code == 202
    job_id = enqueuer.job_ids[-1]

    client.patch(
        f"/api/projects/{project_id}/nodes/{branch['id']}",
        json={"prompt": "this live prompt must not reach the queued worker"},
    )
    navy_version_id = execute_run_job(
        job_id=job_id,
        session_factory=TestingSessionLocal,
        provider=provider,
        ingestor=FakeIngestor(),
        scorer=FakeDinoV2Scorer(),
    )

    assert provider.requests[-1].prompt_at_runtime.endswith(
        "Change only: make it navy\nDo not restyle or reinterpret any other element."
    )
    assert provider.requests[-1].input_snapshot.subject_version_id == str(
        subject_version_id
    )
    graph = client.get(f"/api/projects/{project_id}/graph").json()
    target = next(node for node in graph["nodes"] if node["id"] == branch["id"])
    assert target["active_version_id"] == str(navy_version_id)
    assert len(target["versions"]) == 1
    assert target["versions"][0]["artifact_url"].endswith("same-shoe-navy.png")
    assert target["versions"][0]["input_snapshot"] == {
        "subject_version_id": str(subject_version_id),
        "connect_version_ids": [],
        "mask_hash": None,
    }
    with TestingSessionLocal() as db:
        metric = db.get(VersionMetric, navy_version_id)
        assert metric is not None
        assert metric.op == "edit_instruct"
        assert metric.method == "dinov2_cosine"
        assert metric.change_magnitude == 0.9301
        assert db.scalar(select(RunJob.status).where(RunJob.id == job_id)) == "complete"


def test_commit_is_idempotent_at_version_boundary(client: TestClient) -> None:
    project_id = create_project(client)
    enqueuer = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    node = create_node(client, project_id, prompt="A shoe")
    _, version_id = submit_and_execute(
        client, project_id, str(node["id"]), enqueuer, FakeProvider()
    )

    with TestingSessionLocal() as db:
        versions = list(
            db.scalars(
                select(Version).where(Version.node_id == uuid.UUID(str(node["id"])))
            )
        )
        edges = list(db.scalars(select(GraphEdge)))

    assert [version.id for version in versions] == [version_id]
    assert edges == []
