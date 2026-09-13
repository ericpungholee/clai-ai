import json
import struct
import uuid
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image

from app.api.meshes import get_mesh_enqueuer
from app.domain.runs import NodeSettings, Op
from app.main import app
from app.models.graph import RunJob, Version, VersionMesh
from app.providers.base import ArtifactBytes
from app.providers.hunyuan import HUNYUAN_ENDPOINT, HunyuanProvider
from app.providers.trellis import TRELLIS_ENDPOINT, TrellisProvider
from app.services.frozen_request_codec import (
    decode_frozen_request,
    encode_frozen_request,
)
from app.services.mesh_jobs import execute_mesh_job
from app.services.operation_routing import OperationRoutingError, resolve_op
from app.services.run_execution import execute_run_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import FileArtifactStore
from app.storage.meshes import ingest_mesh, validate_glb
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeIngestor,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)
from tests.test_meshes import Queue, Reader, Transport, glb, textured_document
from tests.test_provider_storage import provider_for, request


def test_image_choices_are_frozen_and_legacy_jobs_keep_their_original_policy():
    frozen = request(Op.GENERATE)
    assert decode_frozen_request(encode_frozen_request(frozen)) == frozen
    assert frozen.settings == NodeSettings()
    provider, _, _ = provider_for()
    precise = replace(
        frozen,
        settings=NodeSettings(
            image_model="sunburst",
            image_quality="max",
        ),
    )
    job = provider.execute(decode_frozen_request(encode_frozen_request(precise)))
    assert job.endpoint == "openai/gpt-image-2.5/sunburst/text-to-image"
    assert job.request_payload["quality"] == "max"
    legacy = encode_frozen_request(frozen)
    for key in ("image_model", "image_quality"):
        del legacy["settings"][key]
    settings = decode_frozen_request(legacy).settings
    assert (settings.image_model, settings.image_quality) == (
        "sunburst",
        "max",
    )


def test_corrupt_frozen_job_fails_without_staying_queued_or_calling_fal(client):
    project = create_project(client)
    node = create_node(client, project, prompt="Deck")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "bad-snapshot"},
    )
    with TestingSessionLocal.begin() as db:
        db.get(RunJob, queue.job_ids[0]).frozen_request = {"broken": True}
    provider = FakeProvider()
    with pytest.raises(ValueError):
        execute_run_job(
            job_id=queue.job_ids[0],
            session_factory=TestingSessionLocal,
            provider=provider,
            ingestor=FakeIngestor(),
        )
    with TestingSessionLocal() as db:
        assert db.get(RunJob, queue.job_ids[0]).status == "failed"
    assert provider.requests == []


def test_canonical_image_enters_mesh_and_regeneration_is_idempotent(client, tmp_path):
    project = create_project(client)
    node = create_node(client, project, prompt="Bare deck")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version_id = submit_and_execute(
        client, project, node["id"], queue, FakeProvider()
    )
    mesh_queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: mesh_queue
    path = f"/api/projects/{project}/versions/{version_id}/mesh"
    attempt = uuid.uuid4()
    client.post(path, json={"attempt_id": str(attempt)})
    reader, transport = Reader(), Transport()
    execute_mesh_job(
        version_id=version_id,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=TrellisProvider(transport, reader),
        output_reader=Reader(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
    )
    with TestingSessionLocal() as db:
        source = db.get(Version, version_id)
        assert reader.urls == [source.artifact_url]
        assert (
            db.get(VersionMesh, version_id).provider_response_metadata["input_policy"]
            == "canonical_image"
        )
    assert (
        transport.submissions[0]["image_url"] == "https://uploaded.fal.test/image-1.png"
    )
    assert "image_urls" not in transport.submissions[0]
    next_attempt = str(uuid.uuid4())
    data = {"attempt_id": next_attempt, "regenerate": True}
    assert client.post(path, json=data).json()["status"] == "queued"
    assert client.post(path, json=data).json()["attempt_id"] == next_attempt
    assert (
        client.post(path, json={**data, "attempt_id": str(uuid.uuid4())}).json()[
            "attempt_id"
        ]
        == next_attempt
    )
    assert len(mesh_queue.calls) == 2


def test_bad_thumbnail_does_not_discard_good_mesh(tmp_path):
    class PreviewFailure(Reader):
        def read(self, url):
            if url.endswith("preview.png"):
                raise OSError("Preview download unavailable")
            return super().read(url)

    stored = ingest_mesh(
        response={
            "model_glb": {"url": "https://provider.test/textured.glb"},
            "rendered_image": {"url": "https://provider.test/preview.png"},
        },
        reader=PreviewFailure(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        attempt_id="preview-failure",
    )
    assert stored.model.artifact_url.endswith(".glb")
    assert stored.preview is None


def test_glb_cannot_claim_a_json_chunk_beyond_its_file():
    content = bytearray(glb(textured_document()))
    struct.pack_into("<I", content, 12, len(content) + 100)
    with pytest.raises(ValueError, match="JSON chunk"):
        validate_glb(bytes(content), require_texture=True)


def test_unsupported_composite_operation_is_rejected_at_routing():
    with pytest.raises(OperationRoutingError, match="reference images"):
        resolve_op(has_subject=True, has_mask=True, connect_count=1)


@pytest.mark.parametrize("textured", [True, False])
def test_hunyuan_uses_original_image_and_honors_geometry_only(textured):
    png = BytesIO()
    Image.new("RGB", (1024, 1024), "navy").save(png, "PNG")

    class Source:
        def read(self, url):
            assert url == "source"
            return ArtifactBytes(png.getvalue(), "image/png", "deck.png")

    transport = Transport()
    provider = HunyuanProvider(transport, Source())
    assert provider.endpoint == HUNYUAN_ENDPOINT
    payload = provider.prepare(source_url="source", textured=textured)
    assert payload == {
        "input_image_url": "https://uploaded.fal.test/image-1.png",
        "enable_geometry": not textured,
        "enable_pbr": False,
    }
    assert transport.uploads == [png.getvalue()]


def test_hunyuan_explicit_glb_wins_over_mislabelled_obj_and_keeps_thumbnail(tmp_path):
    reader = Reader()
    stored = ingest_mesh(
        response={
            "model_glb": {"url": "https://provider.test/wrong.obj"},
            "model_urls": {"glb": {"url": "https://provider.test/textured.glb"}},
            "thumbnail": {"url": "https://provider.test/preview.png"},
        },
        reader=reader,
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        attempt_id="hunyuan-output",
    )
    assert reader.urls == [
        "https://provider.test/textured.glb",
        "https://provider.test/preview.png",
    ]
    assert stored.preview is not None


def test_mesh_model_selection_is_frozen_at_enqueue(client):
    project = create_project(client)
    node = create_node(client, project, prompt="Bare deck")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version_id = submit_and_execute(
        client, project, node["id"], queue, FakeProvider()
    )
    mesh_queue = Queue()
    app.dependency_overrides[get_mesh_enqueuer] = lambda: mesh_queue
    path = f"/api/projects/{project}/versions/{version_id}/mesh"
    rejected = client.post(
        path, json={"attempt_id": str(uuid.uuid4()), "model": "hunyuan"}
    )
    assert rejected.status_code == 422
    first = client.post(path, json={"attempt_id": str(uuid.uuid4())})
    assert first.json()["model"] == TRELLIS_ENDPOINT
    assert "source_views" not in first.json()
    second = client.post(path, json={"attempt_id": str(uuid.uuid4())})
    assert second.json()["attempt_id"] == first.json()["attempt_id"]
    assert len(mesh_queue.calls) == 1


def test_obj_output_is_packaged_with_embedded_texture_and_diffuse_material(tmp_path):
    png = BytesIO()
    Image.new("RGB", (4, 4), "navy").save(png, "PNG")
    assets = {
        "https://provider.test/deck.obj": (
            b"mtllib material.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\n"
            b"vt 0 0\nvt 1 0\nvt 0 1\nusemtl deck\nf 1/1 2/2 3/3\n"
        ),
        "https://provider.test/material.mtl": (
            b"newmtl deck\nKd 1 1 1\nmap_Kd texture.png\n"
        ),
        "https://provider.test/texture.png": png.getvalue(),
    }

    class Output:
        def read(self, url):
            return ArtifactBytes(
                assets[url], "application/octet-stream", url.rsplit("/", 1)[1]
            )

    stored = ingest_mesh(
        response={
            "model_glb": {
                "url": "https://provider.test/deck.obj",
                "content_type": "model/obj",
            },
            "material_mtl": {
                "url": "https://provider.test/material.mtl",
                "file_name": "material.mtl",
            },
            "texture": {
                "url": "https://provider.test/texture.png",
                "file_name": "texture.png",
            },
        },
        reader=Output(),
        store=FileArtifactStore(root=tmp_path, public_base_url="https://clai.test"),
        attempt_id="obj-conversion",
    )
    content = (tmp_path / stored.model.storage_key).read_bytes()
    validate_glb(content, require_texture=True)
    document = json.loads(content[20 : 20 + struct.unpack_from("<I", content, 12)[0]])
    assert document["materials"][0]["pbrMetallicRoughness"]["metallicFactor"] == 0
    assert all("uri" not in image for image in document["images"])
