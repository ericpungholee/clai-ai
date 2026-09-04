from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

from app.domain.runs import (
    BaseEdge,
    FrozenRunRequest,
    InputSnapshot,
    MaskSnapshot,
    NodeSettings,
    NodeSnapshot,
    Op,
    VersionPin,
    VersionSnapshot,
)
from app.providers.base import (
    ArtifactBytes,
    ProviderContractError,
    ProviderJob,
    ProviderResult,
)
from app.providers.fal_transport import FalSdkTransport
from app.providers.nano_banana import NanoBananaProProvider
from app.services.run_freezing import freeze_run_request
from app.storage.artifacts import (
    ArtifactIngestor,
    ArtifactStorageError,
    FileArtifactStore,
    HttpArtifactReader,
    S3ArtifactStore,
)


class FakeArtifactReader:
    def __init__(self, artifacts: Mapping[str, ArtifactBytes]) -> None:
        self.artifacts = artifacts
        self.read_urls: list[str] = []

    def read(self, artifact_url: str) -> ArtifactBytes:
        self.read_urls.append(artifact_url)
        return self.artifacts[artifact_url]


class FakeFalTransport:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []
        self.submissions: list[tuple[str, dict[str, object]]] = []
        self.response: dict[str, object] = {
            "images": [
                {
                    "url": "https://v3.fal.media/output.png",
                    "content_type": "image/png",
                    "width": 1024,
                    "height": 1024,
                }
            ],
            "description": "",
        }

    def upload(self, *, content: bytes, filename: str) -> str:
        self.uploads.append((content, filename))
        return f"https://v3.fal.media/input-{len(self.uploads)}.png"

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str:
        self.submissions.append((endpoint, payload))
        return "fal-request-1"

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        assert endpoint in {
            NanoBananaProProvider.generate_endpoint,
            NanoBananaProProvider.edit_endpoint,
        }
        assert request_id == "fal-request-1"
        return self.response


class FakeFalClient:
    def upload_file(self, path: str) -> str:
        return f"https://v3.fal.media/{Path(path).name}"

    def result(self, application: str, request_id: str) -> object:
        return {"application": application, "request_id": request_id}


class FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        CacheControl: str,
        Metadata: dict[str, str],
    ) -> object:
        self.puts.append(
            {
                "Bucket": Bucket,
                "Key": Key,
                "Body": Body,
                "ContentType": ContentType,
                "CacheControl": CacheControl,
                "Metadata": Metadata,
            }
        )
        return {"ETag": "fixture"}


def version(version_id: str) -> VersionSnapshot:
    return VersionSnapshot(
        id=version_id,
        node_id=f"node-{version_id}",
        artifact_url=f"clai://{version_id}",
        seed=42,
        edit_depth=0,
    )


def request(
    op: Op,
    *,
    base: VersionSnapshot | None = None,
    connects: tuple[VersionSnapshot, ...] = (),
    mask: MaskSnapshot | None = None,
    settings: NodeSettings | None = None,
) -> FrozenRunRequest:
    return FrozenRunRequest(
        node_id="target",
        op=op,
        prompt_at_runtime="runtime prompt",
        seed=123,
        settings=settings or NodeSettings(),
        base=base,
        connects=connects,
        mask=mask,
        input_snapshot=InputSnapshot(
            base_version_id=base.id if base else None,
            connect_version_ids=tuple(item.id for item in connects),
            mask_hash="mask" if mask else None,
        ),
        edit_depth=1 if base else 0,
    )


def provider_for(
    versions: tuple[VersionSnapshot, ...] = (),
) -> tuple[NanoBananaProProvider, FakeFalTransport, FakeArtifactReader]:
    artifacts = {
        item.artifact_url: ArtifactBytes(
            content=f"bytes-{item.id}".encode(),
            content_type="image/png",
            filename=f"{item.id}.png",
        )
        for item in versions
    }
    transport = FakeFalTransport()
    reader = FakeArtifactReader(artifacts)
    return (
        NanoBananaProProvider(transport=transport, artifact_reader=reader),
        transport,
        reader,
    )


def test_generate_uses_text_endpoint_without_uploads() -> None:
    provider, transport, reader = provider_for()

    job = provider.execute(request(Op.GENERATE))

    assert job.endpoint == "fal-ai/nano-banana-pro"
    assert reader.read_urls == []
    assert transport.uploads == []
    assert transport.submissions == [
        (
            "fal-ai/nano-banana-pro",
            {
                "prompt": "runtime prompt",
                "num_images": 1,
                "seed": 123,
                "aspect_ratio": "1:1",
                "output_format": "png",
                "resolution": "1K",
                "limit_generations": True,
                "enable_web_search": False,
            },
        )
    ]


def test_sdk_transport_submits_paid_request_exactly_once() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "Key fixture-key"
        assert request.url == "https://queue.fal.test/fal-ai/model"
        return httpx.Response(200, json={"request_id": "one-request"})

    transport = FalSdkTransport(
        "fixture-key",
        queue_origin="https://queue.fal.test",
        client=FakeFalClient(),
        queue_client=httpx.Client(
            transport=httpx.MockTransport(respond),
            headers={"Authorization": "Key fixture-key"},
        ),
    )

    request_id = transport.submit(
        endpoint="fal-ai/model",
        payload={"prompt": "fixture"},
    )

    assert request_id == "one-request"
    assert calls == 1


def test_sdk_transport_does_not_retry_failed_paid_submission() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"detail": "unavailable"})

    transport = FalSdkTransport(
        "fixture-key",
        queue_origin="https://queue.fal.test",
        client=FakeFalClient(),
        queue_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        transport.submit(
            endpoint="fal-ai/model",
            payload={"prompt": "fixture"},
        )

    assert calls == 1


def test_edit_uploads_clai_bytes_and_preserves_base_then_connect_order() -> None:
    base = version("base")
    first = version("first")
    second = version("second")
    provider, transport, reader = provider_for((base, first, second))

    job = provider.execute(
        request(Op.EDIT_REF_GUIDED, base=base, connects=(first, second))
    )

    assert job.endpoint == "fal-ai/nano-banana-pro/edit"
    assert reader.read_urls == [
        base.artifact_url,
        first.artifact_url,
        second.artifact_url,
    ]
    assert transport.uploads == [
        (b"bytes-base", "base.png"),
        (b"bytes-first", "first.png"),
        (b"bytes-second", "second.png"),
    ]
    assert job.request_payload["image_urls"] == [
        "https://v3.fal.media/input-1.png",
        "https://v3.fal.media/input-2.png",
        "https://v3.fal.media/input-3.png",
    ]


def test_generate_ref_uses_edit_endpoint_with_connect_images() -> None:
    reference = version("reference")
    provider, _, _ = provider_for((reference,))

    job = provider.execute(request(Op.GENERATE_REF, connects=(reference,)))

    assert job.endpoint == "fal-ai/nano-banana-pro/edit"
    assert job.request_payload["image_urls"] == ["https://v3.fal.media/input-1.png"]


def test_provider_never_silently_drops_a_mask() -> None:
    base = version("base")
    mask = MaskSnapshot("rle", 8, 8, base_version_id="base")
    provider, transport, _ = provider_for((base,))

    with pytest.raises(ProviderContractError, match="cannot execute"):
        provider.execute(request(Op.EDIT_INPAINT, base=base, mask=mask))

    assert transport.submissions == []


def test_provider_rejects_resolution_above_capability() -> None:
    provider, transport, _ = provider_for()

    with pytest.raises(ProviderContractError, match="exceeds"):
        provider.execute(
            request(
                Op.GENERATE,
                settings=NodeSettings(width=4097, height=1024),
            )
        )

    assert transport.submissions == []


def test_provider_result_records_exact_contract_metadata() -> None:
    provider, _, _ = provider_for()
    job = provider.execute(request(Op.GENERATE))

    result = provider.result(job)

    assert result.job.request_id == "fal-request-1"
    assert result.output_url == "https://v3.fal.media/output.png"
    assert result.width == 1024
    assert result.height == 1024
    assert result.response_metadata["description"] == ""


def test_file_store_is_content_addressed_and_immutable(tmp_path: Path) -> None:
    store = FileArtifactStore(
        root=tmp_path / "artifacts",
        public_base_url="https://cdn.clai.test",
    )

    first = store.put(
        key="runs/job/output.png", content=b"image", content_type="image/png"
    )
    second = store.put(
        key="runs/job/output.png",
        content=b"image",
        content_type="image/png",
    )

    assert first == second
    assert first.sha256 in first.storage_key
    assert first.artifact_url.startswith("https://cdn.clai.test/")
    assert (tmp_path / "artifacts" / first.storage_key).read_bytes() == b"image"


def test_file_store_rejects_path_escape(tmp_path: Path) -> None:
    store = FileArtifactStore(
        root=tmp_path / "artifacts",
        public_base_url="https://cdn.clai.test",
    )

    with pytest.raises(ArtifactStorageError, match="invalid"):
        store.put(key="../escape.png", content=b"image", content_type="image/png")


def test_s3_store_sets_immutable_cache_and_digest_metadata() -> None:
    client = FakeS3Client()
    store = S3ArtifactStore(
        client=client,
        bucket="clai-artifacts",
        public_base_url="https://cdn.clai.test",
    )

    stored = store.put(
        key="runs/job/output.png",
        content=b"image",
        content_type="image/png",
    )

    assert client.puts[0]["Bucket"] == "clai-artifacts"
    assert client.puts[0]["Body"] == b"image"
    assert client.puts[0]["CacheControl"] == "public, max-age=31536000, immutable"
    assert client.puts[0]["Metadata"] == {"sha256": stored.sha256}


def test_ingestor_downloads_provider_output_before_returning_durable_url(
    tmp_path: Path,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "v3.fal.media"
        return httpx.Response(
            200,
            content=b"provider-image",
            headers={"content-type": "image/png"},
        )

    reader = HttpArtifactReader(
        allowed_hosts=frozenset({"v3.fal.media"}),
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    store = FileArtifactStore(
        root=tmp_path / "artifacts",
        public_base_url="https://cdn.clai.test",
    )
    result = ProviderResult(
        job=ProviderJob(
            provider="fal",
            model="gemini-3-pro-image",
            endpoint="fal-ai/nano-banana-pro/edit",
            request_id="request-123",
            request_payload={},
        ),
        output_url="https://v3.fal.media/temporary.png",
        content_type="image/png",
        width=1024,
        height=1024,
        response_metadata={},
    )

    stored = ArtifactIngestor(reader=reader, store=store).ingest(result)

    assert stored.artifact_url.startswith("https://cdn.clai.test/")
    assert stored.artifact_url != result.output_url
    assert (tmp_path / "artifacts" / stored.storage_key).read_bytes() == (
        b"provider-image"
    )


def test_http_reader_rejects_non_provider_host_without_requesting() -> None:
    reader = HttpArtifactReader(
        allowed_hosts=frozenset({"v3.fal.media"}),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: pytest.fail(f"unexpected request: {request.url}")
            )
        ),
    )

    with pytest.raises(ArtifactStorageError, match="allowed HTTPS host"):
        reader.read("https://upload.wikimedia.org/input.jpg")


def test_navy_shoe_acceptance_path_uses_only_fakes(tmp_path: Path) -> None:
    base = VersionSnapshot(
        id="shoe-base-v1",
        node_id="source",
        artifact_url="clai://shoe-base-v1",
        seed=3329142776,
        edit_depth=0,
    )
    source = NodeSnapshot(
        id="source",
        prompt="a product shoe",
        active_version_id=base.id,
    )
    target = NodeSnapshot(id="target", prompt="make it navy")
    frozen = freeze_run_request(
        target=target,
        inbound_edges=(
            BaseEdge(
                "base-edge",
                source.id,
                target.id,
                VersionPin(version_id=base.id),
            ),
        ),
        nodes={source.id: source, target.id: target},
        versions={base.id: base},
        random_seed=lambda: pytest.fail("base seed should be inherited"),
    )
    transport = FakeFalTransport()
    artifact_reader = FakeArtifactReader(
        {
            base.artifact_url: ArtifactBytes(
                content=b"original-shoe",
                content_type="image/jpeg",
                filename="shoe.jpg",
            )
        }
    )
    provider = NanoBananaProProvider(
        transport=transport,
        artifact_reader=artifact_reader,
    )
    job = provider.execute(frozen)
    result = provider.result(job)

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"same-shoe-in-navy",
            headers={"content-type": "image/png"},
        )

    ingestor = ArtifactIngestor(
        reader=HttpArtifactReader(
            allowed_hosts=frozenset({"v3.fal.media"}),
            client=httpx.Client(transport=httpx.MockTransport(respond)),
        ),
        store=FileArtifactStore(
            root=tmp_path / "artifacts",
            public_base_url="https://cdn.clai.test",
        ),
    )
    stored = ingestor.ingest(result)

    assert frozen.op is Op.EDIT_INSTRUCT
    assert frozen.seed == base.seed
    assert transport.uploads == [(b"original-shoe", "shoe.jpg")]
    assert job.endpoint == "fal-ai/nano-banana-pro/edit"
    assert job.request_payload["prompt"] == frozen.prompt_at_runtime
    assert (tmp_path / "artifacts" / stored.storage_key).read_bytes() == (
        b"same-shoe-in-navy"
    )
