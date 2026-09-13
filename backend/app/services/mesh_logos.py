"""A conservative studio-image heuristic, followed by an unresampled source crop.

No provider texture, generated replacement logo, OCR, or extra paid inference.
This deliberately targets one central front graphic; manual selection handles misses.
"""

import logging
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

from app.providers.base import ArtifactReader
from app.schemas.mesh_logo import (
    LogoBounds,
    LogoCrop,
    LogoPreservation,
    LogoSource,
    MeshDecal,
)
from app.storage.artifacts import ArtifactStore

logger = logging.getLogger(__name__)


def _bounds(box: tuple[int, int, int, int], width: int, height: int) -> LogoBounds:
    left, top, right, bottom = box
    return LogoBounds(
        x=left / width,
        y=top / height,
        width=(right - left) / width,
        height=(bottom - top) / height,
    )


def extract_logo(content: bytes) -> tuple[Image.Image, LogoBounds, LogoBounds] | None:
    with Image.open(BytesIO(content)) as opened:
        if max(opened.size) > 4096:
            return None
        original = ImageOps.exif_transpose(opened).convert("RGBA")
    small = original.copy()
    small.thumbnail((384, 384))
    rgba = np.asarray(small).astype(np.float32)
    rgb = rgba[:, :, :3]
    h, w = rgb.shape[:2]
    if min(h, w) < 32:
        return None
    border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]))
    background = np.median(border, axis=0)
    # Busy backgrounds and tight crops have no reliable camera/framing reference.
    if np.median(np.max(np.abs(border - background), axis=1)) > 24:
        return None
    foreground = (np.max(np.abs(rgb - background), axis=2) > 30) & (rgba[:, :, 3] > 128)
    foreground = ndimage.binary_fill_holes(foreground)
    labels, count = ndimage.label(foreground)
    if not count:
        return None
    areas = np.bincount(labels.ravel())
    areas[0] = 0
    subject = labels == areas.argmax()
    ys, xs = np.where(subject)
    left, top, right, bottom = (
        int(xs.min()),
        int(ys.min()),
        int(xs.max()) + 1,
        int(ys.max()) + 1,
    )
    sw, sh = right - left, bottom - top
    if sw < w * 0.2 or sh < h * 0.3:
        return None

    # Fine local contrast catches crests/lettering, excluding silhouette edges.
    smooth = ndimage.gaussian_filter(rgb, sigma=(2, 2, 0))
    contrast = np.max(np.abs(rgb - smooth), axis=2)
    interior = ndimage.distance_transform_edt(subject) > 4
    roi = np.zeros((h, w), dtype=bool)
    roi[
        top + int(sh * 0.36) : top + int(sh * 0.74),
        left + int(sw * 0.20) : left + int(sw * 0.80),
    ] = True
    marks = (contrast > 28) & interior & roi
    groups, _ = ndimage.label(ndimage.binary_dilation(marks, iterations=3))
    candidates = []
    for label, slices in enumerate(ndimage.find_objects(groups), 1):
        if slices is None:
            continue
        sy, sx = slices
        bw, bh = sx.stop - sx.start, sy.stop - sy.start
        pixels = int(np.count_nonzero(marks & (groups == label)))
        cx, cy = (sx.start + sx.stop) / 2, (sy.start + sy.stop) / 2
        if not (0.08 * sw <= bw <= 0.55 * sw and 0.045 * sh <= bh <= 0.30 * sh):
            continue
        if not (0.035 <= pixels / (bw * bh) <= 0.65) or pixels < max(
            12, sw * sh * 0.001
        ):
            continue
        # Do not accept a region clipped by the search window (e.g. a shirt seam).
        if not roi[sy.start, sx.start] or not roi[sy.stop - 1, sx.stop - 1]:
            continue
        distance = abs((cx - left) / sw - 0.5) + abs((cy - top) / sh - 0.53)
        candidates.append(
            (pixels / (1 + 5 * distance), (sx.start, sy.start, sx.stop, sy.stop))
        )
    if not candidates:
        return None
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[1][0] > candidates[0][0] * 0.8:
        return None
    box = candidates[0][1]
    # Detect at low resolution, but keep every original decoded pixel in the PNG.
    full_box = (
        int(np.floor(box[0] * original.width / w)),
        int(np.floor(box[1] * original.height / h)),
        min(original.width, int(np.ceil(box[2] * original.width / w))),
        min(original.height, int(np.ceil(box[3] * original.height / h))),
    )
    return (
        original.crop(full_box),
        _bounds(full_box, original.width, original.height),
        _bounds((left, top, right, bottom), w, h),
    )


def preserve_mesh_logo(
    *,
    source_url: str,
    reader: ArtifactReader,
    store: ArtifactStore,
    attempt_id: str,
) -> LogoPreservation:
    try:
        extracted = extract_logo(reader.read(source_url).content)
        if extracted is None:
            return LogoPreservation(status="not_found")
        crop, bounds, subject = extracted
        png = BytesIO()
        crop.save(png, format="PNG")
        stored = store.put(
            key=f"meshes/{attempt_id}/logo.png",
            content=png.getvalue(),
            content_type="image/png",
        )
        return LogoPreservation(
            status="ready",
            decal=MeshDecal(
                source=LogoSource(
                    url=source_url, bounds=bounds, subjectBounds=subject, mode="auto"
                ),
                crop=LogoCrop(
                    dataUrl=stored.artifact_url, width=crop.width, height=crop.height
                ),
            ),
        )
    except Exception:
        # An optional branding pass must never discard a successfully generated GLB.
        logger.exception("Automatic logo extraction failed for mesh %s", attempt_id)
        return LogoPreservation(status="failed")
