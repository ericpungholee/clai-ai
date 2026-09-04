from app.domain.runs import MaskSnapshot
from app.providers.base import ArtifactBytes, ProviderContractError
from app.providers.fal_transport import FalTransport
from app.services.masks import decode_rle, encode_rle


class SamSelector:
    endpoint = "fal-ai/sam-3/image-rle"

    def __init__(self, transport: FalTransport):
        self._transport = transport

    def select(
        self,
        *,
        image: ArtifactBytes,
        version_id: str,
        width: int,
        height: int,
        text: str,
        points: list[dict[str, int]],
    ) -> MaskSnapshot | None:
        payload = {
            "image_url": self._transport.upload(
                content=image.content, filename=image.filename
            ),
            "prompt": text,
            "point_prompts": points,
            "return_multiple_masks": True,
            "max_masks": 3,
            "apply_mask": False,
        }
        request_id = self._transport.submit(endpoint=self.endpoint, payload=payload)
        response = self._transport.result(endpoint=self.endpoint, request_id=request_id)
        return sam_mask(response, width=width, height=height, version_id=version_id)


def sam_mask(
    response: dict[str, object], *, width: int, height: int, version_id: str
) -> MaskSnapshot | None:
    values = response.get("rle")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise ProviderContractError("SAM returned an unsupported mask format")
    pixels = decode_rle("", width, height)
    for value in values:
        pixels |= decode_rle(value, width, height)
    rle = encode_rle(pixels)
    return MaskSnapshot(rle, width, height, version_id) if rle else None
