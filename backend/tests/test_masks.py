import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.domain.runs import MaskSnapshot, NodeSnapshot, Op, SubjectEdge, VersionPin
from app.providers.base import ArtifactBytes, ProviderContractError
from app.providers.flux_fill import FluxFillProvider
from app.providers.sam import sam_mask
from app.services.masks import (
    composite_masked_output,
    decode_rle,
    encode_rle,
    validate_mask,
)
from app.services.run_freezing import freeze_run_request
from tests.test_provider_storage import (
    FakeArtifactReader,
    FakeFalTransport,
    request,
    version,
)


def test_sam_unions_disjoint_regions_and_returns_no_selection_for_empty_response() -> (
    None
):
    mask = sam_mask({"rle": ["1 2", "8 2"]}, width=3, height=3, version_id="s")
    assert mask is not None and mask.rle == "1 2 8 2"
    for response in ({"rle": []}, {"rle": ""}):
        assert sam_mask(response, width=3, height=3, version_id="s") is None


def test_fill_uploads_subject_and_mask_and_refuses_misalignment_before_upload() -> None:
    subject = version("s")
    transport = FakeFalTransport()
    reader = FakeArtifactReader(
        {
            subject.artifact_url: ArtifactBytes(
                png((10, 10), "white"), "image/png", "subject.png"
            )
        }
    )
    provider = FluxFillProvider(transport=transport, artifact_reader=reader)
    frozen = request(
        Op.EDIT_INPAINT, subject=subject, mask=MaskSnapshot("1 5", 10, 10, "s")
    )
    prepared = provider.prepare(frozen)
    assert len(transport.uploads) == 2
    assert prepared.request_payload["image_url"] != subject.artifact_url
    assert prepared.request_payload["mask_url"] == "https://v3.fal.media/input-2.png"
    assert prepared.request_payload["seed"] == frozen.seed
    assert Image.open(BytesIO(transport.uploads[1][0])).getpixel((0, 0)) == 255
    assert Image.open(BytesIO(transport.uploads[1][0])).getpixel((0, 1)) == 0
    with pytest.raises(ProviderContractError, match="dimensions"):
        provider.prepare(
            request(
                Op.EDIT_INPAINT, subject=subject, mask=MaskSnapshot("1 5", 20, 20, "s")
            )
        )
    assert len(transport.uploads) == 2
    with pytest.raises(ProviderContractError, match="connect"):
        provider.prepare(
            request(
                Op.EDIT_INPAINT,
                subject=subject,
                connects=(version("c"),),
                mask=frozen.mask,
            )
        )


def test_full_mask_resolves_unmasked_but_stale_full_mask_still_blocks() -> None:
    subject = version("s")

    def freeze(mask: MaskSnapshot):
        return freeze_run_request(
            target=NodeSnapshot("target", "square it", mask=mask),
            inbound_edges=(
                SubjectEdge(
                    "edge", subject.node_id, "target", VersionPin(version_id="s")
                ),
            ),
            nodes={},
            versions={"s": subject},
            random_seed=lambda: 1,
        )

    frozen = freeze(MaskSnapshot("1 100", 10, 10, "s"))
    assert frozen.op == Op.EDIT_INSTRUCT and frozen.mask is None
    assert frozen.input_snapshot.mask_hash is None
    with pytest.raises(ValueError, match="different image"):
        freeze(MaskSnapshot("1 100", 10, 10, "old"))


def test_real_sam_response_is_one_based_row_major_and_matches_provider_box() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/sam-3-image-rle.json").read_text()
    )
    rle = fixture["response"]["rle"][0]
    mask = decode_rle(rle, fixture["width"], fixture["height"])
    assert mask[214, 448:452].all()
    assert not mask[214, 447]
    y, x = np.nonzero(mask)
    cx, cy, width, height = fixture["response"]["boxes"][0]
    assert (x.max() + x.min()) / 2 / mask.shape[1] == pytest.approx(cx, abs=0.003)
    assert (y.max() + y.min()) / 2 / mask.shape[0] == pytest.approx(cy, abs=0.003)
    # SAM's detector box encloses the segmentation; it is not a pixel-exact bound.
    assert (cx - width / 2) - 0.003 <= x.min() / mask.shape[1]
    assert x.max() / mask.shape[1] <= (cx + width / 2) + 0.003
    assert (cy - height / 2) - 0.003 <= y.min() / mask.shape[0]
    assert y.max() / mask.shape[0] <= (cy + height / 2) + 0.003
    assert encode_rle(mask) == rle


@pytest.mark.parametrize("rle", ["0 1", "1 0", "100 2", "1 5 4 2", "1"])
def test_invalid_spans_are_rejected(rle: str) -> None:
    with pytest.raises(ValueError):
        decode_rle(rle, 10, 10)


def test_empty_and_entire_image_are_explicit() -> None:
    with pytest.raises(ValueError, match="Select an area first"):
        validate_mask(MaskSnapshot(" ", 10, 10, "subject"))
    assert validate_mask(MaskSnapshot("1 100", 10, 10, "subject"))


def png(size: tuple[int, int], color: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_composite_normalizes_output_and_preserves_outside_feather_band() -> None:
    pixels = np.zeros((20, 20), dtype=np.bool_)
    pixels[7:13, 7:13] = True
    mask = MaskSnapshot(encode_rle(pixels), 20, 20, "subject")
    output, drift = composite_masked_output(
        original=png((20, 20), "white"),
        generated=png((10, 40), "black"),
        mask=mask,
    )
    result = np.asarray(Image.open(BytesIO(output)))
    assert result.shape == (20, 20, 4)
    assert result[8, 8, 0] == 0
    assert 0 < result[6, 8, 0] < result[5, 8, 0] < 255
    assert result[4, 8, 0] == result[0, 0, 0] == 255
    assert drift == 0
    with pytest.raises(ValueError, match="dimensions"):
        composite_masked_output(
            original=png((10, 10), "white"),
            generated=png((20, 20), "black"),
            mask=mask,
        )
