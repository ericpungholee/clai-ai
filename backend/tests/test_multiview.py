from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import select

from app.domain.image_views import SUPPORTING_VIEWS, VIEW_ORDER, view_urls
from app.domain.runs import Op
from app.main import app
from app.models.graph import RunJob, Version
from app.providers.base import ArtifactBytes
from app.providers.gpt_image import GptImageProvider
from app.providers.trellis import TrellisProvider
from app.services.run_execution import execute_run_job
from app.services.run_queue import get_run_enqueuer
from tests.conftest import TestingSessionLocal
from tests.test_graph import (
    CapturingEnqueuer,
    FakeIngestor,
    FakeProvider,
    create_node,
    create_project,
)
from tests.test_provider_storage import provider_for, request


@pytest.mark.parametrize("failure_angle", SUPPORTING_VIEWS)
def test_failed_view_never_publishes_a_partial_version(client, failure_angle):
    class FailingProvider(FakeProvider):
        def result(self, job):
            if job.endpoint == f"fake/view-{failure_angle}":
                raise RuntimeError("View provider unavailable")
            return super().result(job)

    project = create_project(client)
    node = create_node(
        client, project, prompt="Deck only with printed crest", generate_views=True
    )
    queue, provider = CapturingEnqueuer(), FailingProvider()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "four-views"},
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        execute_run_job(
            job_id=queue.job_ids[0],
            session_factory=TestingSessionLocal,
            provider=provider,
            ingestor=FakeIngestor(),
        )
    with TestingSessionLocal() as db:
        assert db.scalar(select(Version.id)) is None
        job = db.get(RunJob, queue.job_ids[0])
        assert job.status == "failed"
        assert job.provider_response_metadata["view_jobs"][failure_angle]["request_id"]
    assert tuple(angle for angle, _ in provider.view_requests) == SUPPORTING_VIEWS


def test_duplicate_view_content_is_rejected_even_at_distinct_urls(client):
    class DuplicateIngestor(FakeIngestor):
        def ingest(self, result):
            return replace(super().ingest(result), sha256="same-bytes")

    project = create_project(client)
    node = create_node(client, project, prompt="Deck only", generate_views=True)
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "duplicate-view"},
    )
    with pytest.raises(RuntimeError, match="duplicate view"):
        execute_run_job(
            job_id=queue.job_ids[0],
            session_factory=TestingSessionLocal,
            provider=FakeProvider(),
            ingestor=DuplicateIngestor(),
        )
    with TestingSessionLocal() as db:
        assert db.scalar(select(Version.id)) is None


@pytest.mark.parametrize(
    "bad_views",
    [
        {"front": "front", "left": "left", "back": "back"},
        {"front": "other-version", "left": "left", "back": "back", "right": "right"},
        {"front": "front", "left": "left", "back": "left", "right": "right"},
        {"front": "front", "left": [], "back": "back", "right": "right"},
    ],
)
def test_invalid_view_manifest_fails_closed(bad_views):
    with pytest.raises(ValueError):
        view_urls(front_url="front", metadata={"views": bad_views})


def test_trellis_uploads_in_parallel_but_retains_view_order():
    barrier = Barrier(5)

    class Reader:
        def read(self, url):
            return ArtifactBytes(url.encode(), "image/png", f"{url}.png")

    class Transport:
        def upload(self, *, content, filename):
            barrier.wait(timeout=3)
            return f"https://uploaded/{content.decode()}"

    payload = TrellisProvider(Transport(), Reader()).prepare(source_urls=VIEW_ORDER)
    assert payload["image_urls"] == [
        f"https://uploaded/{angle}" for angle in VIEW_ORDER
    ]
    assert "prompt" not in payload and "negative_prompt" not in payload
    assert payload["resolution"] == 1536 and payload["texture_size"] == 4096


def test_current_image_model_never_falls_back_after_provider_failure():
    provider, transport, _ = provider_for()
    calls = []

    def fail(*, endpoint, payload):
        calls.append(endpoint)
        raise RuntimeError("Model unavailable")

    transport.submit = fail
    with pytest.raises(RuntimeError, match="unavailable"):
        provider.execute(request(Op.GENERATE))
    assert calls == [GptImageProvider.generate_endpoint]


@pytest.mark.parametrize(
    "references",
    [
        {"back": "back"},
        {"front": "front", "back": "back"},
    ],
)
def test_supporting_views_reject_any_reference_other_than_hero(references):
    provider, transport, reader = provider_for()
    with pytest.raises(ValueError, match="canonical hero"):
        provider.execute_views(
            reference_urls=references,
            angles=SUPPORTING_VIEWS,
            request=request(Op.GENERATE),
        )
    assert reader.read_urls == []
    assert transport.submissions == []


def test_new_runs_upgrade_old_draft_speed_settings_before_freezing(client):
    project = create_project(client)
    node = client.post(
        f"/api/projects/{project}/nodes",
        json={
            "prompt": "One solid block",
            "position": {"x": 0, "y": 0},
            "settings": {
                "image_model": "flare",
                "image_quality": "high",
                "generate_views": False,
            },
        },
    ).json()
    queue = CapturingEnqueuer()
    app.dependency_overrides[get_run_enqueuer] = lambda: queue
    response = client.post(
        f"/api/projects/{project}/nodes/{node['id']}/runs",
        json={"idempotency_key": "current-fidelity"},
    )
    assert response.status_code == 202
    with TestingSessionLocal() as db:
        settings = db.get(RunJob, queue.job_ids[0]).frozen_request["settings"]
        assert settings["image_model"] == "sunburst"
        assert settings["image_quality"] == "max"
        assert settings["generate_views"] is True
