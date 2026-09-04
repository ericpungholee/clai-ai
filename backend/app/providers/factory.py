from app.core.config import Settings
from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalSdkTransport
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
