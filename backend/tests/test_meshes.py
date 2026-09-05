import json
import struct
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.meshes import get_mesh_enqueuer
from app.main import app
from app.models.graph import Version, VersionMesh
from app.providers.base import ArtifactBytes
from app.providers.tripo import TRIPO_ENDPOINT, TripoProvider
from app.services.mesh_jobs import execute_mesh_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import FileArtifactStore
from app.storage.meshes import validate_glb
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)


def glb(document: dict[str, object]) -> bytes:
    payload = json.dumps(document).encode()
    payload += b" " * (-len(payload) % 4)
    return (
        struct.pack("<4sIIII", b"glTF", 2, len(payload) + 20, len(payload), 0x4E4F534A)
        + payload
    )


class Reader:
    def read(self, artifact_url: str) -> ArtifactBytes:
        if artifact_url.endswith(".glb"):
            return ArtifactBytes(
                glb({"asset": {"version": "2.0"}, "scenes": [{}]}),
                "model/gltf-binary",
                "model.glb",
            )
        image = BytesIO()
        Image.new("RGB", (4, 4), "grey").save(image, "WEBP")
        return ArtifactBytes(
            image.getvalue(), "application/octet-stream", "preview.webp"
        )


class Transport:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []
        self.uploads: list[bytes] = []

    def upload(self, *, content: bytes, filename: str) -> str:
        self.uploads.append(content)
        return "https://uploaded.fal.test/image.png"

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str:
        assert endpoint == TRIPO_ENDPOINT
        self.submissions.append(payload)
        return "fake-mesh-request"

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        return {
            "task_id": "fake",
            "model_mesh": None,
            "base_model": {"url": "https://provider.test/model.glb"},
            "pbr_model": None,
            "rendered_image": {"url": "https://provider.test/preview.png"},
        }


class Queue:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    def enqueue(self, version_id: uuid.UUID, attempt_id: uuid.UUID) -> None:
        self.calls.append((version_id, attempt_id))


def test_mesh_is_a_version_cache_with_uploaded_input_and_ingested_assets(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Lamp")
    image_queue, image_provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: image_queue
    _, first = submit_and_execute(
        client, project, str(node["id"]), image_queue, image_provider
    )
    _, second = submit_and_execute(
        client, project, str(node["id"]), image_queue, image_provider
    )
    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions"
    attempt = uuid.uuid4()
    assert client.get(f"{prefix}/{first}/mesh").json() is None
    assert (
        client.post(
            f"{prefix}/{first}/mesh", json={"attempt_id": str(attempt)}
        ).status_code
        == 202
    )
    client.post(
        f"{prefix}/{first}/mesh",
        json={"attempt_id": str(uuid.uuid4()), "texture": "standard"},
    )
    assert len(queue.calls) == 1
    assert client.get(f"{prefix}/{second}/mesh").json() is None
    transport = Transport()
    arguments = dict(
        version_id=first,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=TripoProvider(transport, Reader()),
        output_reader=Reader(),
        store=FileArtifactStore(
            root=tmp_path, public_base_url="https://clai.test/assets"
        ),
    )
    execute_mesh_job(**arguments)
    execute_mesh_job(**arguments)
    assert len(transport.submissions) == 1
    payload = transport.submissions[0]
    assert payload["texture"] == "no" and payload["pbr"] is False
    assert payload["image_url"] == "https://uploaded.fal.test/image.png"
    cached = client.get(f"{prefix}/{first}/mesh").json()
    assert cached["status"] == "complete"
    assert cached["artifact_url"].startswith("https://clai.test/assets/")
    assert cached["preview_url"].startswith("https://clai.test/assets/")
    assert cached["preview_url"].endswith(".webp")
    assert client.get(f"{prefix}/{second}/mesh").json() is None
    assert (
        client.put(f"{prefix}/{first}/visibility", json={"hidden": True}).status_code
        == 204
    )
    assert (
        client.get(f"{prefix}/{first}/mesh").json()["artifact_url"]
        == cached["artifact_url"]
    )
    assert (
        client.post(
            f"{prefix}/{first}/mesh", json={"attempt_id": str(uuid.uuid4())}
        ).json()["status"]
        == "complete"
    )
    assert len(queue.calls) == 1
    textured = TripoProvider(transport, Reader()).prepare(
        source_url="https://clai.test/image.png", textured=True
    )
    assert textured["texture"] == "standard" and textured["pbr"] is False


def test_mesh_failure_cannot_invalidate_its_image(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Lamp")
    image_queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: image_queue
    _, version = submit_and_execute(
        client, project, str(node["id"]), image_queue, FakeProvider()
    )
    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions/{version}/mesh"
    attempt = uuid.uuid4()
    client.post(prefix, json={"attempt_id": str(attempt)})

    class BrokenTransport(Transport):
        def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
            raise RuntimeError("fixture provider failure")

    with TestingSessionLocal() as db:
        before = db.get(Version, version).prompt_at_runtime
    with pytest.raises(RuntimeError, match="fixture"):
        execute_mesh_job(
            version_id=version,
            attempt_id=attempt,
            session_factory=TestingSessionLocal,
            provider=TripoProvider(BrokenTransport(), Reader()),
            output_reader=Reader(),
            store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        )
    with TestingSessionLocal() as db:
        assert db.get(VersionMesh, version).status == "failed"
        assert db.get(Version, version).prompt_at_runtime == before
    assert client.get(prefix).json()["status"] == "failed"
    assert (
        client.post(prefix, json={"attempt_id": str(attempt)}).json()["status"]
        == "failed"
    )
    assert len(queue.calls) == 1
    assert (
        client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).json()["status"]
        == "queued"
    )
    assert len(queue.calls) == 2


def test_glb_must_not_reference_expiring_external_assets() -> None:
    with pytest.raises(ValueError, match="external"):
        validate_glb(
            glb(
                {
                    "asset": {"version": "2.0"},
                    "images": [{"uri": "https://provider.test/texture.png"}],
                }
            )
        )
    with pytest.raises(ValueError, match="GLB"):
        validate_glb(b"not a mesh")
