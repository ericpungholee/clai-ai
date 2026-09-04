import argparse
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.runs import (
    FrozenRunRequest,
    InputSnapshot,
    NodeSettings,
    Op,
    VersionSnapshot,
)
from app.providers.base import ArtifactBytes
from app.providers.fal_transport import FalSdkTransport
from app.providers.nano_banana import NanoBananaProProvider
from app.storage.artifacts import (
    ArtifactIngestor,
    FileArtifactStore,
    HttpArtifactReader,
)


class CheckpointSecrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    fal_key: str = Field(alias="FAL_KEY")


class FixtureReader:
    def __init__(self, *, artifact_url: str, path: Path) -> None:
        self._artifact_url = artifact_url
        self._path = path

    def read(self, artifact_url: str) -> ArtifactBytes:
        if artifact_url != self._artifact_url:
            raise ValueError("Checkpoint requested an unknown artifact")
        return ArtifactBytes(
            content=self._path.read_bytes(),
            content_type="image/jpeg",
            filename=self._path.name,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Clai's single paid P0 adapter/storage checkpoint."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Acknowledge that this submits one paid fal generation.",
    )
    parser.add_argument(
        "--score-command",
        nargs=argparse.REMAINDER,
        help=(
            "Optional local command that receives input/output paths and prints "
            "one DINOv2 cosine value."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.live:
        raise SystemExit("Refusing to submit without the explicit --live flag")

    root = Path(__file__).resolve().parents[2]
    output_root = root / ".progress" / "p0-live-navy-checkpoint"
    ledger = output_root / "checkpoint.json"
    if ledger.exists():
        raise SystemExit(
            "Checkpoint record already exists; refusing a second paid submission"
        )

    fixture_path = (
        root
        / ".progress"
        / "p0-zero-spike"
        / "pairs"
        / "shoe-03"
        / "recolor"
        / "input.jpg"
    )
    if not fixture_path.is_file():
        raise SystemExit(f"Missing checkpoint fixture: {fixture_path}")

    secrets = CheckpointSecrets(_env_file=root / ".env")
    output_root.mkdir(parents=True, exist_ok=True)
    fixture_url = "clai-fixture://shoe-03/input.jpg"
    base = VersionSnapshot(
        id="p0-shoe-03-base",
        node_id="p0-shoe-03-source",
        artifact_url=fixture_url,
        seed=3329142776,
        edit_depth=0,
    )
    request = FrozenRunRequest(
        node_id="p0-navy-checkpoint",
        op=Op.EDIT_INSTRUCT,
        prompt_at_runtime=(
            "Preserve exactly every unmentioned attribute, including geometry,\n"
            "proportions, silhouette, camera angle, framing, lighting direction,\n"
            "and background.\n"
            "Change only: make it navy\n"
            "Do not restyle or reinterpret any other element."
        ),
        seed=base.seed,
        settings=NodeSettings(aspect_ratio="auto", width=1024, height=1024),
        base=base,
        connects=(),
        mask=None,
        input_snapshot=InputSnapshot(
            base_version_id=base.id,
            connect_version_ids=(),
            mask_hash=None,
        ),
        edit_depth=1,
    )
    transport = FalSdkTransport(secrets.fal_key)
    provider = NanoBananaProProvider(
        transport=transport,
        artifact_reader=FixtureReader(
            artifact_url=fixture_url,
            path=fixture_path,
        ),
    )

    started_at = datetime.now(UTC).isoformat()
    prepared = provider.prepare(request)
    ledger.write_text(
        json.dumps(
            {
                "status": "submission_starting",
                "started_at": started_at,
                "request": asdict(request),
                "prepared_provider_request": asdict(prepared),
            },
            indent=2,
            default=str,
        )
        + "\n"
    )

    try:
        job = provider.submit(prepared)
    except Exception as error:
        response = getattr(error, "response", None)
        response_body = None
        if response is not None:
            try:
                response_body = response.json()
            except ValueError:
                response_body = response.text
        ledger.write_text(
            json.dumps(
                {
                    "status": "submission_failed_or_ambiguous",
                    "started_at": started_at,
                    "failed_at": datetime.now(UTC).isoformat(),
                    "request": asdict(request),
                    "prepared_provider_request": asdict(prepared),
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                        "status_code": getattr(response, "status_code", None),
                        "response": response_body,
                    },
                },
                indent=2,
                default=str,
            )
            + "\n"
        )
        raise

    ledger.write_text(
        json.dumps(
            {
                "status": "submitted",
                "started_at": started_at,
                "request": asdict(request),
                "prepared_provider_request": asdict(prepared),
                "job": asdict(job),
            },
            indent=2,
            default=str,
        )
        + "\n"
    )

    result = provider.result(job)
    ingestor = ArtifactIngestor(
        reader=HttpArtifactReader(
            allowed_hosts=frozenset({"v3.fal.media", "v3b.fal.media"})
        ),
        store=FileArtifactStore(
            root=output_root / "artifacts",
            public_base_url="clai-checkpoint://artifacts",
        ),
    )
    artifact = ingestor.ingest(result)
    stored_path = output_root / "artifacts" / artifact.storage_key
    drift_manifest = json.loads(
        (root / "backend/tests/fixtures/drift-corpus-manifest.json").read_text()
    )
    score: float | None = None
    score_error: str | None = None
    if args.score_command:
        try:
            completed = subprocess.run(
                [*args.score_command, str(fixture_path), str(stored_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            score = float(completed.stdout.strip())
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            score_error = str(error)
    ledger.write_text(
        json.dumps(
            {
                "status": "completed",
                "started_at": started_at,
                "completed_at": datetime.now(UTC).isoformat(),
                "request": asdict(request),
                "prepared_provider_request": asdict(prepared),
                "job": asdict(job),
                "provider_result": asdict(result),
                "stored_artifact": asdict(artifact),
                "drift": {
                    "score": score,
                    "score_error": score_error,
                    "shoe_recolor_baseline": drift_manifest["p0_shoe_recolor_baseline"],
                    "meaning": "change magnitude, not correctness",
                },
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    print(ledger)
    print(stored_path)


if __name__ == "__main__":
    main()
