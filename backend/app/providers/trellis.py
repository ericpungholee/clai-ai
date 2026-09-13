from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from app.providers.base import ArtifactReader
from app.providers.fal_transport import FalTransport

TRELLIS_ENDPOINT = "fal-ai/trellis-2"
TRELLIS_MULTI_ENDPOINT = "fal-ai/trellis-2/multi"


class TrellisProvider:
    supports_multiview = True

    def __init__(self, transport: FalTransport, artifact_reader: ArtifactReader):
        self.transport = transport
        self.artifact_reader = artifact_reader

    @staticmethod
    def endpoint_for(source_urls: Sequence[str]) -> str:
        return TRELLIS_MULTI_ENDPOINT

    def prepare(
        self, *, source_urls: Sequence[str], textured: bool = True
    ) -> dict[str, object]:
        if len(source_urls) != 5 or len(set(source_urls)) != len(source_urls):
            raise ValueError("TRELLIS requires five distinct object views")

        def upload(source_url: str) -> str:
            image = self.artifact_reader.read(source_url)
            return self.transport.upload(content=image.content, filename=image.filename)

        # Network-bound uploads run together; map retains the stored view order.
        with ThreadPoolExecutor(max_workers=len(source_urls)) as pool:
            uploaded_urls = list(pool.map(upload, source_urls))
        return {
            "image_urls": uploaded_urls,
            # Verified against fal Trellis2MultiInput (2026-09-13). Images only;
            # this endpoint has no prompt or negative-prompt control.
            "seed": 1337,
            "resolution": 1536,
            "texture_size": 4096,
            "decimation_target": 500000,
            "ss_sampling_steps": 12,
            "ss_guidance_strength": 8.0,
            "shape_slat_sampling_steps": 12,
            "shape_slat_guidance_strength": 8.0,
            "tex_slat_sampling_steps": 12,
            "tex_slat_guidance_strength": 1.0,
            "remesh": True,
            "remesh_band": 1.0,
            "remesh_project": 1.0,
        }
