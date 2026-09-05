"""One $0.20 untextured Tripo check. Preserve the first attempt; never retry."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.providers.fal_transport import FalSdkTransport
from app.providers.tripo import TRIPO_ENDPOINT, TripoProvider
from app.storage.artifacts import (
    FileArtifactReader,
    FileArtifactStore,
    HttpArtifactReader,
)
from app.storage.meshes import ingest_mesh


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    fal_key: str


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        raise SystemExit("Explicit --live is required for the one paid Tripo check")
    root = Path(__file__).resolve().parents[2]
    output = root / ".progress/phase-e-tripo-contract"
    output.mkdir(parents=True, exist_ok=False)
    transport = FalSdkTransport(Secrets(_env_file=root / ".env").fal_key)
    provider = TripoProvider(
        transport,
        FileArtifactReader(
            root=root / ".progress/p0-zero-spike/inputs",
            public_base_url="clai-fixture://inputs",
        ),
    )
    start = time.monotonic()
    try:
        payload = provider.prepare(
            source_url="clai-fixture://inputs/shoe-03.jpg",
            textured=False,
        )
        (output / "request.json").write_text(
            json.dumps({"endpoint": TRIPO_ENDPOINT, "payload": payload}, indent=2)
        )
        (output / "attempt.json").write_text(
            '{"paid_submissions": 1, "listed_usd": 0.20}\n'
        )
        submitted_at = time.monotonic()
        request_id = transport.submit(endpoint=TRIPO_ENDPOINT, payload=payload)
        (output / "submission.json").write_text(json.dumps({"request_id": request_id}))
        print(f"Submitted exactly once: {request_id}", flush=True)
        response = transport.result(endpoint=TRIPO_ENDPOINT, request_id=request_id)
        provider_seconds = time.monotonic() - submitted_at
        (output / "response.json").write_text(json.dumps(response, indent=2))
        stored = ingest_mesh(
            response=response,
            reader=HttpArtifactReader(
                allowed_hosts=frozenset({"v3.fal.media", "v3b.fal.media"}),
                max_bytes=128 * 1024 * 1024,
            ),
            store=FileArtifactStore(
                root=output / "artifacts", public_base_url="clai-check://tripo"
            ),
            attempt_id=request_id,
        )
        summary = {
            "endpoint": TRIPO_ENDPOINT,
            "texture": "no",
            "listed_usd": 0.20,
            "provider_seconds": provider_seconds,
            "end_to_end_seconds": time.monotonic() - start,
            "stored": asdict(stored),
        }
        (output / "result.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    except Exception as error:
        (output / "error.json").write_text(
            json.dumps(
                {"error": str(error), "elapsed_seconds": time.monotonic() - start}
            )
        )
        raise


if __name__ == "__main__":
    main()
