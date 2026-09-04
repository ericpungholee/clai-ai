"""Canonical masks: one-based row-major start/length pairs, pinned to SAM fixture."""

from io import BytesIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy.ndimage import distance_transform_edt

from app.domain.runs import MaskSnapshot

FEATHER_PX = 3


def decode_rle(rle: str, width: int, height: int) -> NDArray[np.bool_]:
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ValueError("Mask dimensions must be between 1 and 4096 pixels")
    tokens = rle.split()
    if len(tokens) % 2:
        raise ValueError("Mask must contain start/length pairs")
    pixels = np.zeros(width * height, dtype=np.bool_)
    previous_end = 0
    for index in range(0, len(tokens), 2):
        start, length = int(tokens[index]) - 1, int(tokens[index + 1])
        end = start + length
        if start < previous_end or length <= 0 or end > pixels.size:
            raise ValueError("Mask spans overlap or exceed the subject image")
        pixels[start:end] = True
        previous_end = end
    return pixels.reshape(height, width)


def encode_rle(pixels: NDArray[np.bool_]) -> str:
    flat = np.pad(pixels.reshape(-1).astype(np.int8), (1, 1))
    edges = np.flatnonzero(np.diff(flat))
    return " ".join(
        f"{start + 1} {end - start}"
        for start, end in zip(edges[::2], edges[1::2], strict=True)
    )


def validate_mask(mask: MaskSnapshot) -> bool:
    pixels = decode_rle(mask.rle, mask.width, mask.height)
    if not pixels.any():
        raise ValueError("The mask is empty. Select an area or clear the mask.")
    return bool(pixels.all())


def mask_png(mask: MaskSnapshot) -> bytes:
    pixels = decode_rle(mask.rle, mask.width, mask.height)
    buffer = BytesIO()
    Image.fromarray(pixels.astype(np.uint8) * 255).save(buffer, format="PNG")
    return buffer.getvalue()


def composite_masked_output(
    *, original: bytes, generated: bytes, mask: MaskSnapshot
) -> tuple[bytes, float]:
    subject = Image.open(BytesIO(original)).convert("RGBA")
    if subject.size != (mask.width, mask.height):
        raise ValueError("Mask dimensions no longer match the subject image")
    pixels = decode_rle(mask.rle, mask.width, mask.height)
    if not pixels.any() or pixels.all():
        raise ValueError("Compositing requires a nonempty partial mask")
    output = Image.open(BytesIO(generated)).convert("RGBA")
    if output.size != subject.size:
        output = output.resize(subject.size, Image.Resampling.LANCZOS)
    # Blend only in the three-pixel outer band; all farther pixels are originals.
    distance = distance_transform_edt(~pixels)
    alpha = np.clip(1.0 - distance / FEATHER_PX, 0, 1)
    alpha[pixels] = 1
    result = Image.composite(
        output, subject, Image.fromarray(np.rint(alpha * 255).astype(np.uint8))
    )
    outside_band = distance > FEATHER_PX
    delta = np.abs(np.asarray(result).astype(np.int16) - np.asarray(subject))
    drift = float(delta[outside_band].mean() / 255) if outside_band.any() else 0.0
    buffer = BytesIO()
    result.save(buffer, format="PNG")
    return buffer.getvalue(), drift
