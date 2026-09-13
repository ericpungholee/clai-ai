import logging
from dataclasses import dataclass
from typing import Final

from app.providers.tripo import PreparedMeshRequest, TripoProvider

logger = logging.getLogger(__name__)

# The root TRELLIS-2 route requires image_url. Its /multi route conditions on
# every image_urls entry; adding that field to the root request does not enable it.
TRELLIS_ENDPOINT: Final = "fal-ai/trellis-2/multi"
MESH_RESPONSE_FIELDS: Final = (
    "model_glb",
    "model_mesh",
    "pbr_model",
    "base_model",
    "rendered_image",
    "task_id",
)


@dataclass(frozen=True)
class TrellisPreset:
    name: str
    resolution: int
    texture_size: int
    ss_sampling_steps: int
    shape_slat_sampling_steps: int
    tex_slat_sampling_steps: int


TRELLIS_HIGH_QUALITY: Final = TrellisPreset(
    name="high_quality",
    resolution=1536,
    texture_size=4096,
    ss_sampling_steps=12,
    shape_slat_sampling_steps=12,
    tex_slat_sampling_steps=12,
)


class MeshProvider(TripoProvider):
    """Use TRELLIS-2 native multi-image input for demo multi-angle jobs."""

    def __init__(
        self,
        *args,
        multi_image_enabled: bool = True,
        preset: TrellisPreset = TRELLIS_HIGH_QUALITY,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.multi_image_enabled = multi_image_enabled
        if preset.name != "high_quality":
            raise ValueError(f"Unsupported TRELLIS preset: {preset.name}")
        self.preset = preset

    def prepare(
        self,
        *,
        source_url: str,
        image_urls: list[str] | None = None,
        textured: bool = True,
    ) -> PreparedMeshRequest:
        urls = image_urls or [source_url]
        if len(urls) > 1:
            if not self.multi_image_enabled:
                raise ValueError(
                    "Multi-angle 3D generation requires TRELLIS_ENABLE_MULTI_IMAGE=true"
                )
            if urls[0] != source_url:
                raise ValueError("Multi-angle inputs must start with the front image")
            if len(urls) != 4 or len(set(urls)) != 4:
                raise ValueError(
                    "TRELLIS-2 multi-image input requires exactly four distinct "
                    "views in front, right, back, left order"
                )
            uploaded_urls = []
            for url in urls:
                logger.info(
                    "fal 3D input upload model_id=%s preset=%s "
                    "multi_image_enabled=%s image_count=%s image_urls=%s "
                    "resolution=%s texture_size=%s sampling_steps=%s",
                    TRELLIS_ENDPOINT,
                    self.preset.name,
                    self.multi_image_enabled,
                    len(urls),
                    urls,
                    self.preset.resolution,
                    self.preset.texture_size,
                    {
                        "ss": self.preset.ss_sampling_steps,
                        "shape_slat": self.preset.shape_slat_sampling_steps,
                        "tex_slat": self.preset.tex_slat_sampling_steps,
                    },
                )
                uploaded_urls.append(self._upload(url))
            return PreparedMeshRequest(
                endpoint=TRELLIS_ENDPOINT,
                payload={
                    "resolution": self.preset.resolution,
                    "texture_size": self.preset.texture_size,
                    "ss_sampling_steps": self.preset.ss_sampling_steps,
                    "shape_slat_sampling_steps": (
                        self.preset.shape_slat_sampling_steps
                    ),
                    "tex_slat_sampling_steps": (self.preset.tex_slat_sampling_steps),
                    "image_urls": uploaded_urls,
                },
            )
        return super().prepare(source_url=source_url, textured=textured)


def snapshot_mesh_response(response: dict[str, object]) -> dict[str, object]:
    """Keep only provider fields needed to ingest a completed result again."""
    return {key: response[key] for key in MESH_RESPONSE_FIELDS if key in response}


def recoverable_mesh_response(
    metadata: dict[str, object],
) -> dict[str, object] | None:
    response = metadata.get("provider_response")
    if not isinstance(response, dict):
        return None
    if not any(
        isinstance(response.get(key), dict)
        and isinstance(response[key].get("url"), str)
        for key in ("model_glb", "model_mesh", "pbr_model", "base_model")
    ):
        return None
    return response
