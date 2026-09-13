"""Hunyuan 3D v3.1 Rapid's single-image reconstruction contract."""

from io import BytesIO

from PIL import Image

from app.providers.base import ArtifactReader, ProviderContractError
from app.providers.fal_transport import FalTransport

HUNYUAN_ENDPOINT = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d"


class HunyuanProvider:
    endpoint = HUNYUAN_ENDPOINT

    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    def prepare(self, *, source_url: str, textured: bool = True) -> dict[str, object]:
        source = self.artifact_reader.read(source_url)
        if len(source.content) > 8 * 1024 * 1024:
            raise ProviderContractError("Hunyuan input exceeds its 8 MB limit")
        with Image.open(BytesIO(source.content)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or not (
                128 <= min(image.size) and max(image.size) <= 5000
            ):
                raise ProviderContractError(
                    "Hunyuan requires a PNG, JPEG or WebP between 128 and 5000px"
                )
        return {
            "input_image_url": self.transport.upload(
                content=source.content, filename=source.filename
            ),
            "enable_geometry": not textured,
            # Standard color texture is sufficient; extra PBR maps add work/cost.
            "enable_pbr": False,
        }
