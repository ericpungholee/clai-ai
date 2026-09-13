"""Regressions for removing synthetic camera images from existing saved jobs."""

import uuid

from app.api.meshes import get_mesh_enqueuer
from app.main import app
from app.models.graph import RunJob, Version, VersionMesh
from app.providers.trellis import TRELLIS_ENDPOINT, TrellisProvider
from app.services.frozen_request_codec import (
    decode_frozen_request,
    encode_frozen_request,
)
from app.services.mesh_jobs import execute_mesh_job
from app.services.run_execution import execute_run_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import FileArtifactStore
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeIngestor,
    FakeProvider,
    create_project,
)
from tests.test_meshes import Queue, Reader, Transport


def _prepare_legacy_job(client):
    project = create_project(client)
    node = client.post(
        f"/api/projects/{project}/nodes",
        json={
            "prompt": "One product",
            "position": {"x": 0, "y": 0},
            "settings": {"generate_views": True},
        },
    ).json()
    assert "generate_views" not in node["settings"]
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "single-image"},
    )
    with TestingSessionLocal.begin() as db:
        run = db.get(RunJob, queue.job_ids[0])
        assert "generate_views" not in run.frozen_request["settings"]
        # Previously frozen requests must also complete with only one submission.
        run.frozen_request = {
            **run.frozen_request,
            "settings": {**run.frozen_request["settings"], "generate_views": True},
        }
        decoded = decode_frozen_request(run.frozen_request)
        assert "generate_views" not in encode_frozen_request(decoded)["settings"]
    provider = FakeProvider()  # Implements no camera-edit method.
    version_id = execute_run_job(
        job_id=queue.job_ids[0],
        session_factory=TestingSessionLocal,
        provider=provider,
        ingestor=FakeIngestor(),
    )
    assert len(provider.requests) == 1
    with TestingSessionLocal() as db:
        assert db.get(RunJob, queue.job_ids[0]).status == "complete"
        source = db.get(Version, version_id)
        source_url = source.artifact_url
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    attempt = uuid.uuid4()
    prefix = f"/api/projects/{project}/versions/{version_id}/mesh"
    assert client.post(prefix, json={"attempt_id": str(attempt)}).status_code == 202
    return project, version_id, attempt, source_url


def test_legacy_angle_setting_cannot_start_extra_image_jobs(client):
    _prepare_legacy_job(client)


def test_legacy_support_metadata_is_ignored_by_graph_and_mesh(client, tmp_path):
    project, version_id, attempt, source_url = _prepare_legacy_job(client)
    with TestingSessionLocal.begin() as db:
        version = db.get(Version, version_id)
        version.provider_response_metadata = {
            "views": {"front": "wrong-source", "rear_right": "missing-image"},
            "view_jobs": {"rear_right": {"status": "failed"}},
        }
        db.get(RunJob, version.run_job_id).provider_response_metadata = {
            "support_status": "generating",
            "views": {"front": "wrong-source"},
        }
    graph = client.get(f"/api/projects/{project}/graph").json()
    saved = graph["nodes"][0]["versions"][0]
    assert saved["artifact_url"] == source_url
    assert "views" not in saved
    reader, transport = Reader(), Transport()
    execute_mesh_job(
        version_id=version_id,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=TrellisProvider(transport, reader),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    assert reader.urls == [source_url]
    assert len(transport.uploads) == len(transport.submissions) == 1
    with TestingSessionLocal() as db:
        mesh = db.get(VersionMesh, version_id)
        assert mesh.status == "complete"
        assert mesh.model == TRELLIS_ENDPOINT
        assert mesh.provider_response_metadata["source_artifact_url"] == source_url
        assert mesh.request_payload["image_url"]
        assert "image_urls" not in mesh.request_payload
