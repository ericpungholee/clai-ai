import base64
import uuid
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.api.meshes import get_logo_store, get_mesh_enqueuer
from app.main import app
from app.models.graph import Version, VersionMesh
from app.providers.base import ArtifactBytes
from app.providers.trellis import TrellisProvider
from app.services.mesh_jobs import execute_mesh_job
from app.services.mesh_logos import extract_logo
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import FileArtifactStore
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)
from tests.test_meshes import Queue, Reader, Transport

# Deterministically drawn test art, not a provider-generated quality benchmark.
BEAR = Path(__file__).parent / "fixtures/logo-bear.png"


def test_extraction_keeps_exact_original_pixels_and_full_crest() -> None:
    crop, bounds, subject = extract_logo(BEAR.read_bytes())
    original = Image.open(BEAR).convert("RGBA")
    x, y = round(bounds.x * original.width), round(bounds.y * original.height)
    assert x <= 213 and y <= 321
    assert x + crop.width >= 300 and y + crop.height >= 397
    assert bounds.width < subject.width / 2
    assert np.array_equal(
        np.asarray(crop), np.asarray(original)[y : y + crop.height, x : x + crop.width]
    )


@pytest.mark.parametrize("kind", ["plain", "blank_bear", "gradient", "noise"])
def test_low_confidence_images_get_no_automatic_decal(kind: str) -> None:
    image = Image.new("RGB", (512, 640), "white")
    if kind == "blank_bear":
        image = Image.open(BEAR).convert("RGB")
        ImageDraw.Draw(image).rectangle((200, 308, 311, 406), fill="#17365d")
    elif kind == "gradient":
        a = np.tile(np.arange(256, dtype=np.uint8), (320, 1))
        image = Image.fromarray(a).convert("RGB")
    elif kind == "noise":
        image = Image.fromarray(
            np.random.default_rng(7).integers(0, 256, (320, 256, 3), dtype=np.uint8)
        )
    encoded = BytesIO()
    image.save(encoded, "PNG")
    assert extract_logo(encoded.getvalue()) is None


def test_worker_leaves_raw_glb_and_manual_logo_can_be_saved(
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = create_project(client)
    node = create_node(client, project, prompt="Bear with a chest crest")
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, version = submit_and_execute(
        client, project, str(node["id"]), queue, FakeProvider()
    )
    app.dependency_overrides[get_mesh_enqueuer] = Queue
    store = FileArtifactStore(root=tmp_path, public_base_url="https://clai.test/assets")
    app.dependency_overrides[get_logo_store] = lambda: store
    prefix = f"/api/projects/{project}/versions/{version}/mesh"
    attempt = uuid.uuid4()
    client.post(prefix, json={"attempt_id": str(attempt)})
    with TestingSessionLocal() as db:
        source_url = db.get(Version, version).artifact_url

    class SourceReader(Reader):
        def read(self, url: str) -> ArtifactBytes:
            self.urls.append(url)
            return ArtifactBytes(BEAR.read_bytes(), "image/png", "bear.png")

    source_reader = SourceReader()
    execute_mesh_job(
        version_id=version,
        attempt_id=attempt,
        session_factory=TestingSessionLocal,
        provider=TrellisProvider(Transport(), source_reader),
        output_reader=Reader(),
        store=store,
    )
    cached = client.get(prefix).json()
    assert cached["status"] == "complete"
    assert cached["logo_preservation"] is None
    assert len(source_reader.urls) == 5  # No extra source read for automatic decals.
    expected_crop, bounds, subject = extract_logo(BEAR.read_bytes())
    png = BytesIO()
    expected_crop.save(png, "PNG")
    decal = {
        "source": {
            "url": source_url,
            "bounds": bounds.model_dump(),
            "subjectBounds": subject.model_dump(),
            "mode": "manual",
        },
        "crop": {
            "dataUrl": "data:image/png;base64,"
            + base64.b64encode(png.getvalue()).decode(),
            "width": expected_crop.width,
            "height": expected_crop.height,
        },
    }
    decal["placement"] = {
        "meshIndex": 0,
        "position": [0, 0, 0.2],
        "orientation": [0, 0, 0, 1],
    }
    decal["size"], decal["rotation"] = 0.18, 12
    update = {"attempt_id": str(attempt), "decal": decal}
    saved = client.put(prefix + "/logo", json=update)
    assert saved.status_code == 200
    decal = saved.json()["decal"]
    update["decal"] = decal
    reopened = client.get(prefix).json()
    assert reopened["logo_preservation"]["decal"] == decal
    assert reopened["artifact_url"] == cached["artifact_url"]
    with TestingSessionLocal() as db:
        metadata = db.get(VersionMesh, version).provider_response_metadata
        assert (
            "artifact_sha256" in metadata
            and metadata["logo_preservation"]["decal"] == decal
        )
    assert (
        client.put(
            prefix + "/logo", json={**update, "attempt_id": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    foreign_project = create_project(client)
    assert (
        client.put(
            prefix.replace(str(project), str(foreign_project)) + "/logo", json=update
        ).status_code
        == 404
    )
    decal["source"]["url"] = "https://example.com/unrelated.png"
    assert client.put(prefix + "/logo", json=update).status_code == 422
    decal["source"]["url"] = source_url
    decal["source"]["bounds"]["x"] = 0.99
    assert client.put(prefix + "/logo", json=update).status_code == 422
    decal["source"]["bounds"]["x"] = 0.4
    decal["crop"]["dataUrl"] = "https://example.com/untrusted.png"
    assert client.put(prefix + "/logo", json=update).status_code == 422
    # Manual selection uses the same record, with an uploaded PNG stored as an asset.
    png = BytesIO()
    expected_crop.save(png, "PNG")
    decal["source"]["mode"] = "manual"
    decal["crop"]["dataUrl"] = (
        "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    )
    assert client.put(prefix + "/logo", json=update).status_code == 200
    assert (
        not client.get(prefix)
        .json()["logo_preservation"]["decal"]["crop"]["dataUrl"]
        .startswith("data:")
    )
    assert (
        client.put(
            prefix + "/logo", json={"attempt_id": str(attempt), "decal": None}
        ).status_code
        == 200
    )
    assert client.get(prefix).json()["logo_preservation"] == {
        "status": "removed",
        "decal": None,
    }
