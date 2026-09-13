from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalTransport

TRELLIS_ENDPOINT = "fal-ai/trellis-2"


class TrellisProvider:
    endpoint = TRELLIS_ENDPOINT

    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    def prepare(self, *, source_url: str, textured: bool = True) -> dict[str, object]:
        image = self.artifact_reader.read(source_url)
        uploaded_url = self.transport.upload(
            content=image.content, filename=image.filename
        )
        return {
            "image_url": uploaded_url,
            # Verified against fal Trellis2Input (2026-09-13). Images only;
            # this endpoint has no prompt or negative-prompt control.
            "seed": 1337,
            "resolution": 1024,
            "texture_size": 2048,
            "decimation_target": 50000,
            "ss_sampling_steps": 12,
            "ss_guidance_strength": 8.0,
            "shape_slat_sampling_steps": 12,
            "shape_slat_guidance_strength": 8.0,
            "tex_slat_sampling_steps": 12,
            "tex_slat_guidance_strength": 1.0,
            "remesh": False,
            "remesh_project": 0.0,
        }
