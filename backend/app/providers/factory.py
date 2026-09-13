from app.core.config import Settings
from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalSdkTransport
from app.providers.gpt_image import GptImageProvider


class FalImageProvider(GptImageProvider):
    def __init__(self, *, settings: Settings, artifact_reader: ArtifactReader):
        if settings.fal_api_key is None:
            raise ValueError("FAL_KEY is required")
        super().__init__(
            transport=FalSdkTransport(
                settings.fal_api_key,
                timeout_seconds=settings.fal_timeout_seconds,
                queue_timeout_seconds=settings.fal_queue_timeout_seconds,
            ),
            artifact_reader=artifact_reader,
        )
