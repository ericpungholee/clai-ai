"""One paid Fill check using the captured SAM mask. No paid retry path."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.runs import (
    FrozenRunRequest,
    InputSnapshot,
    MaskSnapshot,
    NodeSettings,
    Op,
    VersionSnapshot,
)
from app.providers.base import ProviderJob
from app.providers.fal_transport import FalSdkTransport
from app.providers.flux_fill import FluxFillProvider
from app.services.masks import mask_png
from app.services.prompt_builder import build_prompt
from app.storage.artifacts import (
    ArtifactIngestor,
    FileArtifactReader,
    FileArtifactStore,
    HttpArtifactReader,
)


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    fal_key: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        raise SystemExit("Explicit --live is required for one paid FLUX Fill call")
    root = Path(__file__).resolve().parents[2]
    output = root / ".progress/phase-b-contracts/fill"
    output.mkdir(parents=True, exist_ok=False)
    fixture = json.loads(
        (root / "backend/tests/fixtures/sam-3-image-rle.json").read_text()
    )
    reader = FileArtifactReader(
        root=root / ".progress/p0-zero-spike/inputs",
        public_base_url="clai-fixture://inputs",
    )
    subject = VersionSnapshot(
        "sam-subject", "source", "clai-fixture://inputs/shoe-03.jpg", 3329142776, 0
    )
    mask = MaskSnapshot(
        fixture["response"]["rle"][0], fixture["width"], fixture["height"], subject.id
    )
    request = FrozenRunRequest(
        "fill-check",
        Op.EDIT_INPAINT,
        build_prompt(
            user_prompt=(
                "Remove the logo from the tongue label, leaving a plain white label"
            ),
            op=Op.EDIT_INPAINT,
        ),
        subject.seed,
        NodeSettings(),
        subject,
        (),
        mask,
        InputSnapshot(subject.id, (), None),
        1,
    )
    transport = FalSdkTransport(Secrets(_env_file=root / ".env").fal_key)
    provider = FluxFillProvider(transport=transport, artifact_reader=reader)
    prepared = provider.prepare(request)
    (output / "request.json").write_text(json.dumps(asdict(prepared), indent=2))
    (output / "frozen.json").write_text(json.dumps(asdict(request), indent=2))
    (output / "mask.png").write_bytes(mask_png(mask))
    (output / "attempt.json").write_text('{"paid_submissions": 1}\n')
    request_id = transport.submit(
        endpoint=prepared.endpoint, payload=prepared.request_payload
    )
    (output / "submission.json").write_text(json.dumps({"request_id": request_id}))
    result = provider.result(
        ProviderJob(
            prepared.provider,
            prepared.model,
            prepared.endpoint,
            request_id,
            prepared.request_payload,
        )
    )
    (output / "response.json").write_text(json.dumps(asdict(result), indent=2))
    ingestor = ArtifactIngestor(
        reader=HttpArtifactReader(
            allowed_hosts=frozenset({"v3.fal.media", "v3b.fal.media"})
        ),
        store=FileArtifactStore(
            root=output / "artifacts", public_base_url="clai-check://fill"
        ),
        subject_reader=reader,
    )
    artifact, drift = ingestor.ingest_masked(result, request)
    (output / "result.json").write_text(
        json.dumps(
            {"artifact": asdict(artifact), "outside_feather_diff": drift}, indent=2
        )
    )
    print(output / "result.json")


if __name__ == "__main__":
    main()
