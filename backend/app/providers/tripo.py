from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalTransport

TRIPO_ENDPOINT = "tripo3d/tripo/v2.5/image-to-3d"


class TripoProvider:
    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    def prepare(self, *, source_url: str, textured: bool = True) -> dict[str, object]:
        image = self.artifact_reader.read(source_url)
        uploaded = self.transport.upload(content=image.content, filename=image.filename)
        return {
            "image_url": uploaded,
            "texture": "standard" if textured else "no",
            "pbr": textured,
            "texture_alignment": "original_image",
            "orientation": "align_image",
        }
