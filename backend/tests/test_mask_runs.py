import uuid
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api import masks
from app.main import app
from app.models.graph import Version, VersionMetric
from app.providers.base import ArtifactBytes
from app.services.run_execution import PendingDinoV2Scorer, execute_run_job
from app.services.run_queue import get_run_enqueuer
from app.storage.artifacts import (
    ArtifactIngestor,
    FileArtifactStore,
    HttpArtifactReader,
)
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeProvider,
    create_node,
    create_project,
    submit_and_execute,
)
from tests.test_masks import png
from tests.test_provider_storage import FakeArtifactReader


def test_mask_save_stale_block_and_frozen_composited_commit(
    client: TestClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    project = create_project(client)
    source = create_node(client, project, prompt="a shoe")
    target = create_node(client, project, prompt="remove the logo")
    queue, provider = CapturingEnqueuer(), FakeProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    _, subject_id = submit_and_execute(
        client, project, str(source["id"]), queue, provider
    )
    prefix = f"/api/projects/{project}/nodes/{target['id']}"
    assert (
        client.put(
            prefix + "/subject",
            json={"source_node_id": source["id"], "version_id": str(subject_id)},
        ).status_code
        == 200
    )
    reader = FakeArtifactReader(
        {
            "https://cdn.clai.test/original-shoe.png": ArtifactBytes(
                png((20, 20), "white"), "image/png", "subject.png"
            )
        }
    )
    monkeypatch.setattr(masks, "create_artifact_reader", lambda settings: reader)
    mask = {
        "rle": "148 6 168 6 188 6",
        "width": 20,
        "height": 20,
        "subject_version_id": str(subject_id),
    }
    assert client.put(prefix + "/mask", json={**mask, "width": 40}).status_code == 422
    assert client.put(prefix + "/mask", json={**mask, "rle": " "}).status_code == 422
    assert client.put(prefix + "/mask", json=mask).status_code == 200
    references = [
        {
            "type": "connect",
            "edge_id": str(uuid.uuid4()),
            "source_node_id": source["id"],
        }
    ]
    assert (
        client.put(
            prefix + "/prompt", json={"document": references, "expected_revision": 0}
        ).status_code
        == 422
    )
    assert client.put(prefix + "/mask", json=None).status_code == 200
    assert (
        client.put(
            prefix + "/prompt", json={"document": references, "expected_revision": 0}
        ).status_code
        == 200
    )
    assert client.put(prefix + "/mask", json=mask).status_code == 409
    assert (
        client.put(
            prefix + "/prompt",
            json={
                "document": [{"type": "text", "text": "remove the logo"}],
                "expected_revision": 1,
            },
        ).status_code
        == 200
    )
    assert client.put(prefix + "/mask", json=mask).status_code == 200
    submitted = client.post(prefix + "/runs", json={"idempotency_key": "masked"})
    assert submitted.status_code == 202
    assert submitted.json()["op"] == "edit_inpaint"
    assert client.put(prefix + "/mask", json=None).status_code == 409
    assert client.patch(prefix, json={"prompt": "a newer draft"}).status_code == 409
    generated_reader = HttpArtifactReader(
        allowed_hosts=frozenset({"fake.provider"}),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=png((10, 40), "black"),
                    headers={"content-type": "image/png"},
                )
            )
        ),
    )
    version_id = execute_run_job(
        job_id=uuid.UUID(submitted.json()["id"]),
        session_factory=TestingSessionLocal,
        provider=provider,
        ingestor=ArtifactIngestor(
            reader=generated_reader,
            subject_reader=reader,
            store=FileArtifactStore(
                root=tmp_path, public_base_url="https://first.party"
            ),
        ),
        scorer=PendingDinoV2Scorer(),
    )
    with TestingSessionLocal() as db:
        result = db.get(Version, version_id)
        assert result is not None and result.artifact_url.startswith(
            "https://first.party/"
        )
        assert (
            "remove the logo" in result.prompt_at_runtime
            and "newer draft" not in result.prompt_at_runtime
        )
        metric = db.get(VersionMetric, version_id)
        assert (
            metric is not None
            and metric.method == "outside_feather_pixel_diff"
            and metric.change_magnitude == 0
        )
    assert client.put(prefix + "/mask", json=mask).status_code == 409
    revised = client.post(
        prefix + "/duplicate", json={"position": {"x": 0, "y": 850}}
    ).json()
    prefix = f"/api/projects/{project}/nodes/{revised['id']}"
    other = create_node(client, project, prompt="another shoe")
    _, second_id = submit_and_execute(
        client, project, str(other["id"]), queue, provider
    )
    assert (
        client.put(
            prefix + "/subject",
            json={"source_node_id": other["id"], "version_id": str(second_id)},
        ).status_code
        == 200
    )
    assert client.put(prefix + "/mask", json=mask).status_code == 409
    stale = client.post(prefix + "/runs", json={"idempotency_key": "stale"})
    assert stale.status_code == 422 and "different image" in stale.text
