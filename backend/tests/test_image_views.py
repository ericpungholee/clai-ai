import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.meshes import get_mesh_enqueuer
from app.main import app
from app.models.graph import RunJob, Version, VersionImageView, VersionMesh
from app.providers.base import ProviderJob, ProviderResult
from app.providers.mesh import TRELLIS_ENDPOINT, MeshProvider
from app.providers.tripo import PreparedMeshRequest
from app.services.image_view_jobs import execute_image_view_job
from app.services.mesh_jobs import execute_mesh_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import ArtifactIngestor, FileArtifactStore, StoredArtifact
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeIngestor,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)
from tests.test_meshes import Queue, Reader, Transport


class FakeRearProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute_angle_view(
        self,
        *,
        source_url: str,
        aspect_ratio: str,
        resolution: str,
        seed: int,
        white_background: bool,
        angle: str,
        design_prompt: str,
    ) -> ProviderJob:
        self.calls.append(
            {
                "angle": angle,
                "source_url": source_url,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "seed": seed,
                "white_background": white_background,
                "design_prompt": design_prompt,
            }
        )
        return ProviderJob(
            provider="fake",
            model="fixture-image-v1",
            endpoint="fal-ai/nano-banana-pro/edit",
            request_id=f"rear-{len(self.calls)}",
            request_payload={
                "prompt": "rear",
                "image_urls": [source_url],
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "seed": seed,
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


class FakeRearIngestor:
    def ingest(self, result: ProviderResult) -> StoredArtifact:
        name = f"{result.job.request_id}.png"
        return StoredArtifact(
            storage_key=f"fake/{name}",
            artifact_url=f"https://cdn.clai.test/{name}",
            content_type="image/png",
            byte_size=18,
            sha256="b" * 64,
        )


class BrokenRearProvider(FakeRearProvider):
    def result(self, job: ProviderJob) -> ProviderResult:
        raise RuntimeError("rear fixture failure")


def generate_image(client: TestClient, project: str, prompt: str, x: float = 100):
    node = create_node(client, project, prompt=prompt, x=x)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version_id = submit_and_execute(
        client, project, str(node["id"]), queue, FakeProvider()
    )
    return node, version_id


def generate_rear(version_id: uuid.UUID, provider: FakeRearProvider | None = None):
    rear_provider = provider or FakeRearProvider()
    execute_image_view_job(
        version_id=version_id,
        angle="back",
        session_factory=TestingSessionLocal,
        provider=rear_provider,
        ingestor=FakeRearIngestor(),
    )
    return rear_provider


def version_from_graph(client: TestClient, project: str, version_id: uuid.UUID) -> dict:
    graph = client.get(f"/api/projects/{project}/graph").json()
    versions = {
        version["id"]: version
        for node in graph["nodes"]
        for version in node["versions"]
    }
    return versions[str(version_id)]


def test_primary_image_is_usable_before_rear_view_exists(
    client: TestClient,
) -> None:
    project = create_project(client)
    node, version_id = generate_image(client, project, "A blue skateboard")
    saved = version_from_graph(client, project, version_id)
    assert saved["artifact_url"].endswith("original-shoe.png")
    assert saved["views"]["back"]["image_url"] is None
    assert node["id"] == saved["node_id"]


@pytest.mark.parametrize("queue_failure", [False, True])
def test_worker_commits_primary_before_queuing_rear_without_waiting(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, queue_failure: bool
) -> None:
    from app.workers import celery_app as worker

    project = create_project(client)
    node = create_node(client, project, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    response = client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "rear-queue-test"},
    )
    assert response.status_code == 202
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "create_artifact_reader", lambda _: Reader())
    monkeypatch.setattr(worker, "FalImageProvider", lambda **_: FakeProvider())
    monkeypatch.setattr(
        worker, "create_provider_output_ingestor", lambda _: FakeIngestor()
    )
    rear_ids: list[str] = []

    def enqueue_rear(version_id: str, angle: str) -> None:
        rear_ids.append(angle)
        with TestingSessionLocal() as db:
            assert db.get(Version, uuid.UUID(version_id)).artifact_url
            assert (
                db.get(VersionImageView, (uuid.UUID(version_id), angle)).status
                == "queued"
            )
            assert db.get(RunJob, uuid.UUID(response.json()["id"])).status == "complete"
        if queue_failure:
            raise OSError("rear queue unavailable")

    monkeypatch.setattr(worker.image_view_job, "delay", enqueue_rear)
    version_id = worker.run_job.run(response.json()["id"])
    assert rear_ids == ["right", "back", "left"]
    saved = version_from_graph(client, project, uuid.UUID(version_id))
    for angle in ("right", "back", "left"):
        assert saved["views"][angle]["status"] == (
            "failed" if queue_failure else "queued"
        )
    assert (
        version_from_graph(client, project, uuid.UUID(version_id))["views"]["back"][
            "image_url"
        ]
        is None
    )


def test_primary_and_rear_are_persisted_as_separate_unmodified_files(
    client: TestClient, tmp_path: Path
) -> None:
    from app.services.run_execution import execute_run_job

    project = create_project(client)
    node = create_node(client, project, prompt="A lamp")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    response = client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "separate-files"},
    )
    assert response.status_code == 202
    output_reader = Reader()
    ingestor = ArtifactIngestor(
        reader=output_reader,
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    version_id = execute_run_job(
        job_id=queue.job_ids[-1],
        session_factory=TestingSessionLocal,
        provider=FakeProvider(),
        ingestor=ingestor,
    )
    execute_image_view_job(
        version_id=version_id,
        angle="back",
        session_factory=TestingSessionLocal,
        provider=FakeRearProvider(),
        ingestor=ingestor,
    )
    with TestingSessionLocal() as db:
        primary = db.get(Version, version_id)
        rear = db.get(VersionImageView, (version_id, "back"))
        assert primary.artifact_url != rear.artifact_url
        assert rear.source_artifact_url == primary.artifact_url
        assert (tmp_path / primary.artifact_storage_key).read_bytes() == Reader().read(
            "https://fake.provider/fake-1.png"
        ).content
        assert (tmp_path / rear.artifact_storage_key).read_bytes() == Reader().read(
            "https://fake.provider/rear-1.png"
        ).content
    assert len(list(tmp_path.rglob("*.webp"))) == 2


def test_rear_view_is_stored_on_the_producing_version_not_a_node(
    client: TestClient,
) -> None:
    project = create_project(client)
    _, first = generate_image(client, project, "Front of a lamp", x=0)
    rear_provider = FakeRearProvider()
    generate_rear(first, rear_provider)
    branch = client.post(
        f"/api/projects/{project}/versions/{first}/branches",
        json={
            "prompt": "Keep the lamp, change nothing",
            "position": {"x": 400, "y": 0},
        },
    ).json()
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, second = submit_and_execute(
        client, project, branch["node"]["id"], queue, FakeProvider()
    )
    generate_rear(second, rear_provider)

    first_saved = version_from_graph(client, project, first)
    second_saved = version_from_graph(client, project, second)
    assert (
        first_saved["views"]["back"]["image_url"] == "https://cdn.clai.test/rear-1.png"
    )
    assert (
        second_saved["views"]["back"]["image_url"] == "https://cdn.clai.test/rear-2.png"
    )
    assert first_saved["views"]["back"]["image_url"] != first_saved["artifact_url"]
    assert second_saved["id"] != first_saved["id"]
    with TestingSessionLocal() as db:
        assert (
            db.get(VersionImageView, (first, "back")).source_artifact_url
            == db.get(Version, first).artifact_url
        )
        assert (
            db.get(VersionImageView, (second, "back")).source_artifact_url
            == db.get(Version, second).artifact_url
        )


def test_angle_failure_leaves_primary_image_and_blocks_partial_view_3d(
    client: TestClient,
) -> None:
    project = create_project(client)
    _, version_id = generate_image(client, project, "A lamp")
    with pytest.raises(RuntimeError, match="rear fixture"):
        generate_rear(version_id, BrokenRearProvider())
    saved = version_from_graph(client, project, version_id)
    assert saved["artifact_url"].endswith("original-shoe.png")
    assert saved["views"]["back"]["image_url"] is None
    with TestingSessionLocal() as db:
        assert db.get(Version, version_id).artifact_url == saved["artifact_url"]
        assert db.get(VersionImageView, (version_id, "back")).status == "failed"

    app.dependency_overrides[get_mesh_enqueuer] = Queue
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    attempt = uuid.uuid4()
    response = client.post(prefix, json={"attempt_id": str(attempt)})
    assert response.status_code == 409
    assert "front, right, back, and left" in response.json()["detail"]
    with TestingSessionLocal() as db:
        assert db.get(VersionMesh, version_id) is None


def test_mesh_rejects_a_partial_front_and_back_set(
    client: TestClient,
) -> None:
    project = create_project(client)
    _, version_id = generate_image(client, project, "A university skateboard")
    provider = generate_rear(version_id)
    with TestingSessionLocal() as db:
        source_url = db.get(Version, version_id).artifact_url
    assert provider.calls[0]["source_url"] == source_url

    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    attempt = uuid.uuid4()
    response = client.post(prefix, json={"attempt_id": str(attempt)})
    assert response.status_code == 409
    assert queue.calls == []
    with TestingSessionLocal() as db:
        assert db.get(VersionMesh, version_id) is None


def test_mesh_waits_for_all_four_views_and_freezes_canonical_order(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    _, version_id = generate_image(client, project, "A lamp")
    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    assert (
        client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).status_code == 409
    )
    generate_rear(version_id)
    assert (
        client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).status_code == 409
    )
    generate_angles(version_id)
    attempt = uuid.uuid4()
    queued = client.post(prefix, json={"attempt_id": str(attempt)})
    assert queued.status_code == 202
    assert queued.json()["input_image_count"] == 4
    assert len(queue.calls) == 1
    transport = Transport()
    arguments = dict(
        version_id=version_id,
        session_factory=TestingSessionLocal,
        provider=MeshProvider(transport, Reader()),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    execute_mesh_job(attempt_id=attempt, **arguments)
    assert transport.endpoints == [TRELLIS_ENDPOINT]
    assert transport.submissions[0] == {
        "resolution": 1536,
        "texture_size": 4096,
        "ss_sampling_steps": 12,
        "shape_slat_sampling_steps": 12,
        "tex_slat_sampling_steps": 12,
        "image_urls": [
            "https://uploaded.fal.test/image-1.png",
            "https://uploaded.fal.test/image-2.png",
            "https://uploaded.fal.test/image-3.png",
            "https://uploaded.fal.test/image-4.png",
        ],
    }
    assert client.get(prefix).json()["status"] == "complete"


class AngleProvider(FakeRearProvider):
    def __init__(self, failed_angle=None):
        super().__init__()
        self.failed_angle = failed_angle

    def execute_angle_view(self, **kwargs):
        job = super().execute_angle_view(**kwargs)
        return replace(job, request_id=f"{kwargs['angle']}-{len(self.calls)}")

    def result(self, job):
        if job.request_id.startswith(f"{self.failed_angle}-"):
            raise RuntimeError("Angle failed")
        return super().result(job)


def generate_angles(version_id, provider=None, ingestor=None):
    provider = provider or AngleProvider()
    for angle in ("right", "back", "left"):
        try:
            execute_image_view_job(
                version_id=version_id,
                angle=angle,
                session_factory=TestingSessionLocal,
                provider=provider,
                ingestor=ingestor or FakeRearIngestor(),
            )
        except RuntimeError:
            if provider.failed_angle != angle:
                raise
    return provider


@pytest.mark.parametrize(
    ("failed_angle", "expected_status"), [(None, "complete"), ("back", "failed")]
)
def test_run_is_not_reported_complete_until_all_angle_jobs_finish(
    client: TestClient, failed_angle: str | None, expected_status: str
) -> None:
    project = create_project(client)
    node, version_id = generate_image(client, project, "A printed skateboard deck")
    graph = client.get(f"/api/projects/{project}/graph").json()
    saved_node = next(item for item in graph["nodes"] if item["id"] == node["id"])
    job_id = saved_node["run"]["id"]
    assert saved_node["run"]["status"] == "ingesting"
    assert saved_node["run"]["version_id"] == str(version_id)
    assert saved_node["run"]["completed_at"] is None

    generate_angles(version_id, AngleProvider(failed_angle))

    run = client.get(f"/api/projects/{project}/runs/{job_id}").json()
    assert run["status"] == expected_status
    assert (run["error"] is not None) == (failed_angle is not None)


@pytest.mark.parametrize("failed_angle", [None, "right", "back", "left"])
def test_four_view_pipeline_and_partial_failures(client, tmp_path, failed_angle):
    project = create_project(client)
    _, version_id = generate_image(client, project, "A lamp")
    ingestor = ArtifactIngestor(
        reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    provider = generate_angles(version_id, AngleProvider(failed_angle), ingestor)
    saved = version_from_graph(client, project, version_id)
    assert set(saved["views"]) == {"front", "right", "back", "left"}
    assert saved["views"]["front"]["image_url"] == saved["artifact_url"]
    for angle in ("right", "back", "left"):
        assert saved["views"][angle]["status"] == (
            "failed" if angle == failed_angle else "complete"
        )
    assert all(call["source_url"] == saved["artifact_url"] for call in provider.calls)
    assert len(client.get(f"/api/projects/{project}/graph").json()["nodes"]) == 1
    # Duplicate delivery never submits another paid generation.
    generate_angles(version_id, provider, ingestor)
    assert len(provider.calls) == 3
    expected = [
        saved["views"][angle]["image_url"]
        for angle in ("front", "right", "back", "left")
        if angle != failed_angle
    ]
    with TestingSessionLocal() as db:
        views = list(
            db.scalars(
                select(VersionImageView).where(
                    VersionImageView.version_id == version_id
                )
            )
        )
        assert len(views) == 3
        assert (
            len({view.artifact_sha256 for view in views if view.status == "complete"})
            == len(expected) - 1
        )
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    attempt = uuid.uuid4()
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    response = client.post(prefix, json={"attempt_id": str(attempt)})
    if failed_angle is not None:
        assert response.status_code == 409
        assert "front, right, back, and left" in response.json()["detail"]
        with TestingSessionLocal() as db:
            assert db.get(VersionMesh, version_id) is None
        return
    queued = response.json()
    assert queued["input_image_count"] == 4
    reader, transport = Reader(), Transport()
    execute_mesh_job(
        version_id=version_id,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=MeshProvider(transport, reader),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    assert reader.urls == expected
    assert transport.endpoints == [TRELLIS_ENDPOINT]
    assert transport.submissions == [
        {
            "resolution": 1536,
            "texture_size": 4096,
            "ss_sampling_steps": 12,
            "shape_slat_sampling_steps": 12,
            "tex_slat_sampling_steps": 12,
            "image_urls": [
                f"https://uploaded.fal.test/image-{i}.png"
                for i in range(1, len(expected) + 1)
            ],
        }
    ]
    assert client.get(prefix).json()["status"] == "complete"


def test_iteration_and_branch_from_older_version_have_independent_view_sets(client):
    project = create_project(client)
    _, original = generate_image(client, project, "A lamp")
    provider = generate_angles(original)
    original_saved = version_from_graph(client, project, original)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    children = []
    # Continuing an image and branching from the older image both create a draft.
    for source in (original, original):
        branch = client.post(
            f"/api/projects/{project}/versions/{source}/branches",
            json={
                "prompt": "Make it navy",
                "position": {"x": 400, "y": len(children) * 400},
            },
        ).json()
        _, child = submit_and_execute(
            client, project, branch["node"]["id"], queue, FakeProvider()
        )
        children.append(child)
        generate_angles(child, provider)
        saved = version_from_graph(client, project, child)
        assert saved["input_snapshot"]["subject_version_id"] == str(original)
        assert all(
            saved["views"][a]["image_url"] != original_saved["views"][a]["image_url"]
            for a in ("right", "back", "left")
        )
        with TestingSessionLocal() as db:
            assert all(
                view.source_artifact_url == saved["artifact_url"]
                for view in db.scalars(
                    select(VersionImageView).where(VersionImageView.version_id == child)
                )
            )
    assert (
        version_from_graph(client, project, original)["views"]
        == original_saved["views"]
    )
    assert len(client.get(f"/api/projects/{project}/graph").json()["nodes"]) == 3


@pytest.mark.parametrize(
    "fault", ["root_route", "dropped_view", "single_image", "duplicate_view"]
)
def test_four_view_job_rejects_invalid_provider_request_before_submit(
    client, tmp_path, fault
):
    project = create_project(client)
    _, version_id = generate_image(client, project, "A lamp")
    generate_angles(version_id)
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    attempt = uuid.uuid4()
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    client.post(prefix, json={"attempt_id": str(attempt)})

    class BrokenProvider(MeshProvider):
        def prepare(self, **kwargs):
            prepared = super().prepare(**kwargs)
            if fault == "root_route":
                return PreparedMeshRequest(
                    endpoint="fal-ai/trellis-2", payload=prepared.payload
                )
            urls = prepared.payload["image_urls"]
            if fault == "dropped_view":
                urls.pop()
            elif fault == "duplicate_view":
                urls[-1] = urls[0]
            else:
                prepared.payload["image_url"] = urls[0]
            return prepared

    transport = Transport()
    with pytest.raises(ValueError, match="Multi-angle jobs|4-view mesh job"):
        execute_mesh_job(
            version_id=version_id,
            attempt_id=attempt,
            session_factory=TestingSessionLocal,
            provider=BrokenProvider(transport, Reader()),
            output_reader=Reader(),
            store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        )
    assert transport.submissions == []
    assert client.get(prefix).json()["status"] == "failed"
    assert all(
        view["image_url"]
        for view in version_from_graph(client, project, version_id)["views"].values()
    )


@pytest.mark.parametrize("outdated", ["model", "quality", None])
def test_four_view_cache_upgrades_outdated_model_or_quality_once(
    client, tmp_path, outdated
):
    project = create_project(client)
    _, version_id = generate_image(client, project, "A lamp")
    generate_angles(version_id)
    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    attempt = uuid.uuid4()
    client.post(prefix, json={"attempt_id": str(attempt)})
    execute_mesh_job(
        version_id=version_id,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=MeshProvider(Transport(), Reader()),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    with TestingSessionLocal.begin() as db:
        mesh = db.get(VersionMesh, version_id)
        if outdated == "model":
            mesh.model = "fal-ai/trellis/multi"
        elif outdated == "quality":
            mesh.request_payload = {**mesh.request_payload, "resolution": 1024}
    # Re-delivery of the original attempt remains idempotent.
    assert (
        client.post(prefix, json={"attempt_id": str(attempt)}).json()["status"]
        == "complete"
    )
    new_attempt = uuid.uuid4()
    result = client.post(prefix, json={"attempt_id": str(new_attempt)}).json()
    assert result["status"] == ("queued" if outdated else "complete")
    assert result["input_image_count"] == 4
    client.post(prefix, json={"attempt_id": str(uuid.uuid4())})
    assert len(queue.calls) == (2 if outdated else 1)
