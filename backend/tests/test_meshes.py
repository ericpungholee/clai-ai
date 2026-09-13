import base64
import json
import struct
import uuid
from io import BytesIO
from pathlib import Path
from threading import Lock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.meshes import get_mesh_enqueuer
from app.main import app
from app.models.graph import Version, VersionMesh
from app.providers.base import ArtifactBytes
from app.providers.trellis import TRELLIS_MULTI_ENDPOINT, TrellisProvider
from app.services.mesh_jobs import execute_mesh_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import FileArtifactStore
from app.storage.meshes import ingest_mesh, validate_glb
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


def textured_document() -> dict[str, object]:
    image = BytesIO()
    Image.new("RGB", (4, 4), "orange").save(image, "PNG")
    encoded = base64.b64encode(image.getvalue()).decode()
    return {
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"uri": f"data:image/png;base64,{encoded}"}],
    }


class Reader:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def read(self, artifact_url: str) -> ArtifactBytes:
        self.urls.append(artifact_url)
        if artifact_url.endswith(".glb"):
            return ArtifactBytes(
                glb(
                    textured_document()
                    if artifact_url.endswith("/textured.glb")
                    else {"asset": {"version": "2.0"}, "scenes": [{}]}
                ),
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
        self.upload_lock = Lock()

    def upload(self, *, content: bytes, filename: str) -> str:
        with self.upload_lock:
            self.uploads.append(content)
            return f"https://uploaded.fal.test/image-{len(self.uploads)}.png"

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str:
        assert endpoint == TRELLIS_MULTI_ENDPOINT == "fal-ai/trellis-2/multi"
        self.submissions.append(payload)
        return "fake-mesh-request"

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        return {
            "model_glb": {"url": "https://provider.test/textured.glb"},
            "timings": {"inference": 1.0},
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
    another = create_node(client, project, prompt="Another lamp")
    _, second = submit_and_execute(
        client, project, str(another["id"]), image_queue, image_provider
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
    source_reader, output_reader = Reader(), Reader()
    arguments = dict(
        version_id=first,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=TrellisProvider(transport, source_reader),
        output_reader=output_reader,
        store=FileArtifactStore(
            root=tmp_path, public_base_url="https://clai.test/assets"
        ),
    )
    execute_mesh_job(**arguments)
    execute_mesh_job(**arguments)
    assert len(transport.submissions) == 1
    payload = transport.submissions[0]
    assert len(payload["image_urls"]) == 5
    assert {key: value for key, value in payload.items() if key != "image_urls"} == {
        "seed": 1337,
        "resolution": 1536,
        "texture_size": 4096,
        "decimation_target": 500000,
        "ss_sampling_steps": 12,
        "ss_guidance_strength": 8.0,
        "shape_slat_sampling_steps": 12,
        "shape_slat_guidance_strength": 8.0,
        "tex_slat_sampling_steps": 12,
        "tex_slat_guidance_strength": 1.0,
        "remesh": True,
        "remesh_band": 1.0,
        "remesh_project": 1.0,
    }
    with TestingSessionLocal() as db:
        source_url = db.get(Version, first).artifact_url
        mesh = db.get(VersionMesh, first)
        assert mesh.source_artifact_url == source_url
        views = db.get(Version, first).provider_response_metadata["views"]
        assert mesh.provider_response_metadata["source_views"] == views
    assert set(source_reader.urls) == set(views.values())
    assert len(transport.uploads) == 5
    assert output_reader.urls[0] == "https://provider.test/textured.glb"
    cached = client.get(f"{prefix}/{first}/mesh").json()
    assert cached["status"] == "complete"
    assert cached["texture"] == "standard"
    assert cached["logo_preservation"] is None
    validate_glb(next(tmp_path.rglob("model.glb")).read_bytes(), require_texture=True)
    assert cached["artifact_url"].startswith("https://clai.test/assets/")
    assert cached["preview_url"].startswith("https://clai.test/assets/")
    assert cached["preview_url"].endswith(".webp")
    assert client.get(f"{prefix}/{second}/mesh").json() is None
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
    assert (
        client.post(
            f"{prefix}/{first}/mesh",
            json={"attempt_id": str(uuid.uuid4()), "texture": "no"},
        ).json()
        == cached
    )
    prepared_again = TrellisProvider(transport, Reader()).prepare(
        source_urls=[f"https://clai.test/image-{index}.png" for index in range(5)]
    )
    assert len(prepared_again["image_urls"]) == 5


def test_grey_cache_can_be_upgraded_once_from_its_original_image(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Printed lamp")
    image_queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: image_queue
    _, version = submit_and_execute(
        client, project, str(node["id"]), image_queue, FakeProvider()
    )
    queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: queue
    prefix = f"/api/projects/{project}/versions/{version}/mesh"
    old_attempt = uuid.uuid4()
    client.post(prefix, json={"attempt_id": str(old_attempt), "texture": "no"})
    transport = Transport()
    reader = Reader()
    arguments = dict(
        version_id=version,
        session_factory=TestingSessionLocal,
        provider=TrellisProvider(transport, reader),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    execute_mesh_job(attempt_id=old_attempt, **arguments)
    grey = client.get(prefix).json()
    assert grey["status"] == "complete" and grey["texture"] == "no"
    assert client.post(prefix, json={"attempt_id": str(old_attempt)}).json() == grey

    attempt = uuid.uuid4()
    upgraded = client.post(prefix, json={"attempt_id": str(attempt)}).json()
    assert upgraded["status"] == "queued" and upgraded["texture"] == "standard"
    assert upgraded["artifact_url"] is None and upgraded["preview_url"] is None
    assert upgraded["elapsed_seconds"] is None
    assert client.post(prefix, json={"attempt_id": str(attempt)}).json() == upgraded
    assert (
        client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).json() == upgraded
    )
    assert len(queue.calls) == 2
    execute_mesh_job(attempt_id=old_attempt, **arguments)
    assert len(transport.submissions) == 1
    execute_mesh_job(attempt_id=attempt, **arguments)
    colored = client.get(prefix).json()
    assert colored["status"] == "complete" and colored["texture"] == "standard"
    assert colored["artifact_url"] != grey["artifact_url"]
    assert len(reader.urls) == 10 and set(reader.urls[:5]) == set(reader.urls[5:])
    assert client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).json() == colored
    assert len(queue.calls) == 2


def test_textured_job_rejects_grey_provider_output(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Printed lamp")
    image_queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: image_queue
    _, version = submit_and_execute(
        client, project, str(node["id"]), image_queue, FakeProvider()
    )
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    prefix = f"/api/projects/{project}/versions/{version}/mesh"
    attempt = uuid.uuid4()
    client.post(prefix, json={"attempt_id": str(attempt)})

    class GreyTransport(Transport):
        def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
            return {"model_mesh": {"url": "https://provider.test/model.glb"}}

    with pytest.raises(ValueError, match="color texture"):
        execute_mesh_job(
            version_id=version,
            attempt_id=attempt,
            session_factory=TestingSessionLocal,
            provider=TrellisProvider(GreyTransport(), Reader()),
            output_reader=Reader(),
            store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        )
    failed = client.get(prefix).json()
    assert failed["status"] == "failed" and failed["artifact_url"] is None
    assert "color texture" in failed["error"]
    assert not list(tmp_path.rglob("*.glb"))


def test_ingest_accepts_textured_model_mesh_without_pbr_model(tmp_path: Path) -> None:
    stored = ingest_mesh(
        response={"model_mesh": {"url": "https://provider.test/textured.glb"}},
        reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        attempt_id="textured",
    )
    validate_glb(
        (tmp_path / stored.model.storage_key).read_bytes(), require_texture=True
    )


def test_color_texture_must_be_used_by_the_mesh() -> None:
    document = textured_document()
    document["meshes"] = [{"primitives": [{}]}]
    with pytest.raises(ValueError, match="color texture"):
        validate_glb(glb(document), require_texture=True)


def test_trellis_webp_texture_extension_is_accepted() -> None:
    document = textured_document()
    document["textures"] = [{"extensions": {"EXT_texture_webp": {"source": 0}}}]
    document["extensionsUsed"] = ["EXT_texture_webp"]

    validate_glb(glb(document), require_texture=True)


def test_historical_image_without_views_cannot_silently_use_single_image(
    client: TestClient, tmp_path: Path
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Legacy lamp")
    image_queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: image_queue
    _, version = submit_and_execute(
        client, project, str(node["id"]), image_queue, FakeProvider()
    )
    with TestingSessionLocal.begin() as db:
        db.get(Version, version).provider_response_metadata = {"fixture": True}
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    prefix = f"/api/projects/{project}/versions/{version}/mesh"
    attempt = uuid.uuid4()
    response = client.post(prefix, json={"attempt_id": str(attempt)})
    assert response.status_code == 409
    assert "five coherent views" in response.json()["detail"]
    assert client.get(prefix).json() is None


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
            provider=TrellisProvider(BrokenTransport(), Reader()),
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
    with TestingSessionLocal.begin() as db:
        db.get(VersionMesh, version).model = "retired/multi-image"
    assert (
        client.post(prefix, json={"attempt_id": str(uuid.uuid4())}).json()["status"]
        == "queued"
    )
    assert len(queue.calls) == 2
    with TestingSessionLocal() as db:
        assert db.get(VersionMesh, version).model == TRELLIS_MULTI_ENDPOINT


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
