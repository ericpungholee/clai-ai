from dataclasses import dataclass

from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalTransport

TRIPO_ENDPOINT = "tripo3d/tripo/v2.5/image-to-3d"


@dataclass(frozen=True)
class PreparedMeshRequest:
    endpoint: str
    payload: dict[str, object]


class TripoProvider:
    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    def prepare(
        self,
        *,
        source_url: str,
        textured: bool = True,
    ) -> PreparedMeshRequest:
        front = self._upload(source_url)
        shared = {
            "texture": "standard" if textured else "no",
            "pbr": textured,
            "texture_alignment": "original_image",
            "orientation": "align_image",
        }
        return PreparedMeshRequest(
            endpoint=TRIPO_ENDPOINT,
            payload={**shared, "image_url": front},
        )

    def _upload(self, artifact_url: str) -> str:
        image = self.artifact_reader.read(artifact_url)
        return self.transport.upload(content=image.content, filename=image.filename)
