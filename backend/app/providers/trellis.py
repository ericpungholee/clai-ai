from collections.abc import Sequence

from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalTransport

TRELLIS_ENDPOINT = "fal-ai/trellis-2/multi"


class TrellisProvider:
    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    def prepare(self, *, source_urls: Sequence[str]) -> dict[str, object]:
        if len(source_urls) != 4:
            raise ValueError("TRELLIS requires exactly four object views")
        uploaded_urls = []
        for source_url in source_urls:
            image = self.artifact_reader.read(source_url)
            uploaded_urls.append(
                self.transport.upload(content=image.content, filename=image.filename)
            )
        return {
            "image_urls": uploaded_urls,
            # Old Clai's balanced_plus values, using the multi-image endpoint.
            "seed": 1337,
            "resolution": 1024,
            "texture_size": 2048,
            "decimation_target": 550000,
            "ss_sampling_steps": 12,
            "ss_guidance_strength": 8.0,
            "shape_slat_sampling_steps": 12,
            "shape_slat_guidance_strength": 8.0,
            "tex_slat_sampling_steps": 12,
            "tex_slat_guidance_strength": 1.0,
            "remesh": True,
            "remesh_band": 1.0,
        }
