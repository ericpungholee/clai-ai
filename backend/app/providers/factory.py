from app.core.config import Settings
from app.domain.runs import FrozenRunRequest, Op
from app.providers.base import (
    ArtifactReader,
    ProviderCapabilities,
    ProviderJob,
    ProviderResult,
)
from app.providers.fal_transport import FalSdkTransport
from app.providers.flux_fill import FluxFillProvider
from app.providers.nano_banana import NanoBananaProProvider


def create_nano_banana_provider(
    *, settings: Settings, artifact_reader: ArtifactReader
) -> NanoBananaProProvider:
    api_key = settings.fal_api_key
    if api_key is None:
        raise ValueError("FAL_KEY is required to create the fal provider")
    return NanoBananaProProvider(
        transport=FalSdkTransport(
            api_key,
            timeout_seconds=settings.fal_timeout_seconds,
        ),
        artifact_reader=artifact_reader,
    )


class FalImageProvider:
    id = "fal"
    capabilities = ProviderCapabilities(
        mask=True, references=3, seed=True, max_resolution=(4096, 4096)
    )

    def __init__(self, *, settings: Settings, artifact_reader: ArtifactReader):
        if settings.fal_api_key is None:
            raise ValueError("FAL_KEY is required")
        transport = FalSdkTransport(
            settings.fal_api_key, timeout_seconds=settings.fal_timeout_seconds
        )
        self.nano = NanoBananaProProvider(
            transport=transport, artifact_reader=artifact_reader
        )
        self.fill = FluxFillProvider(
            transport=transport, artifact_reader=artifact_reader
        )

    def execute(self, request: FrozenRunRequest) -> ProviderJob:
        if request.op == Op.EDIT_INPAINT:
            return self.fill.execute(request)
        return self.nano.execute(request)

    def result(self, job: ProviderJob) -> ProviderResult:
        if job.endpoint == self.fill.endpoint:
            return self.fill.result(job)
        return self.nano.result(job)
