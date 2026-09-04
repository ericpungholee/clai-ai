import argparse
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

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
from app.storage.artifacts import HttpArtifactReader

OLD_PREAMBLE = (
    "Preserve exactly every unmentioned attribute, including geometry,\n"
    "proportions, silhouette, camera angle, framing, lighting direction,\n"
    "and background.\n"
    "Change only: {instruction}\n"
    "Do not restyle or reinterpret any other element."
)

NEW_PREAMBLE = (
    "This is an edit of the attached image. Keep the same object and the same\n"
    "photograph: same camera angle, same framing, same background.\n"
    "Keep every attribute the instruction does not mention.\n"
    "The instruction may change any attribute it names, including form,\n"
    "proportions, colour, material, and finish. Apply it fully.\n\n"
    "Instruction: {instruction}"
)


class LiveSecrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fal_key: str


class FixtureReader:
    def __init__(self, *, artifact_url: str, path: Path) -> None:
        self._artifact_url = artifact_url
        self._path = path

    def read(self, artifact_url: str) -> ArtifactBytes:
        if artifact_url != self._artifact_url:
            raise ValueError("Unexpected A/B fixture URL")
        content_type = (
            "image/png" if self._path.suffix.lower() == ".png" else "image/jpeg"
        )
        return ArtifactBytes(
            content=self._path.read_bytes(),
            content_type=content_type,
            filename=self._path.name,
        )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the capped eight-call P0.5 preservation-preamble A/B."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Required acknowledgement that this submits exactly eight paid calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.live:
        raise SystemExit("Refusing to submit without the explicit --live flag")

    root = Path(__file__).resolve().parents[2]
    output_root = root / ".progress" / "p0-5-preamble-ab"
    if output_root.exists():
        raise SystemExit(
            "A/B output directory already exists; refusing any repeat paid submission"
        )

    fixtures = (
        {
            "id": "water-bottle-live",
            "path": root
            / "backend/.data/artifacts/runs/01a06a39-3583-7401-957b-7c79255cbf93"
            / "3e2a458ad49dea5a957bca01b14adbab29b876408d9867dea0ab5ef090de1752"
            / "output.png",
            "instruction": "make the base of the water bottle square",
            "seed": 3779905142,
        },
        {
            "id": "shoe-03",
            "path": root / ".progress/p0-zero-spike/inputs/shoe-03.jpg",
            "instruction": "make the toe box square",
            "seed": 3329142776,
        },
        {
            "id": "chair-02",
            "path": root / ".progress/p0-zero-spike/inputs/chair-02.jpg",
            "instruction": "make each chair back a single flat wooden panel",
            "seed": 1550414862,
        },
        {
            "id": "electronics-05",
            "path": root / ".progress/p0-zero-spike/inputs/electronics-05-mouse.jpg",
            "instruction": "make the mouse body a rectangular slab with square corners",
            "seed": 419729051,
        },
    )
    if len(fixtures) * 2 != 8:
        raise SystemExit("The A/B plan must contain exactly eight calls")
    missing = [
        str(fixture["path"]) for fixture in fixtures if not fixture["path"].is_file()
    ]
    if missing:
        raise SystemExit(f"Missing A/B fixtures: {missing}")

    output_root.mkdir(parents=True)
    manifest: dict[str, object] = {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "hard_cap": 8,
        "calls_attempted": 0,
        "fixtures": [
            {
                "id": fixture["id"],
                "source": str(Path(fixture["path"]).relative_to(root)),
                "instruction": fixture["instruction"],
                "seed": fixture["seed"],
            }
            for fixture in fixtures
        ],
        "calls": [],
    }
    write_json(output_root / "manifest.json", manifest)

    secrets = LiveSecrets(_env_file=root / ".env")
    transport = FalSdkTransport(secrets.fal_key)
    output_reader = HttpArtifactReader(
        allowed_hosts=frozenset({"v3.fal.media", "v3b.fal.media"})
    )

    try:
        for fixture in fixtures:
            for variant, template in (("old", OLD_PREAMBLE), ("new", NEW_PREAMBLE)):
                fixture_id = str(fixture["id"])
                fixture_path = Path(fixture["path"])
                call_dir = output_root / fixture_id / variant
                call_dir.mkdir(parents=True)
                shutil.copy2(
                    fixture_path,
                    call_dir / f"input{fixture_path.suffix.lower()}",
                )

                artifact_url = f"clai-preamble-ab://{fixture_id}/input"
                subject = VersionSnapshot(
                    id=f"{fixture_id}-subject",
                    node_id=f"{fixture_id}-source",
                    artifact_url=artifact_url,
                    seed=int(fixture["seed"]),
                    edit_depth=0,
                )
                request = FrozenRunRequest(
                    node_id=f"p0-5-{fixture_id}-{variant}",
                    op=Op.EDIT_INSTRUCT,
                    prompt_at_runtime=template.format(
                        instruction=str(fixture["instruction"])
                    ),
                    seed=subject.seed,
                    settings=NodeSettings(aspect_ratio="auto", width=1024, height=1024),
                    subject=subject,
                    connects=(),
                    mask=None,
                    input_snapshot=InputSnapshot(
                        subject_version_id=subject.id,
                        connect_version_ids=(),
                        mask_hash=None,
                    ),
                    edit_depth=1,
                )
                write_json(call_dir / "frozen-request.json", asdict(request))

                provider = NanoBananaProProvider(
                    transport=transport,
                    artifact_reader=FixtureReader(
                        artifact_url=artifact_url,
                        path=fixture_path,
                    ),
                )
                prepared = provider.prepare(request)
                write_json(call_dir / "provider-request.json", asdict(prepared))

                attempted_at = datetime.now(UTC).isoformat()
                call_record = {
                    "fixture_id": fixture_id,
                    "variant": variant,
                    "status": "submission_starting",
                    "attempted_at": attempted_at,
                }
                manifest["calls_attempted"] = int(manifest["calls_attempted"]) + 1
                calls = manifest["calls"]
                if not isinstance(calls, list):
                    raise TypeError("Invalid in-memory A/B manifest")
                calls.append(call_record)
                write_json(call_dir / "attempt.json", call_record)
                write_json(output_root / "manifest.json", manifest)

                job = provider.submit(prepared)
                write_json(call_dir / "submission.json", asdict(job))
                call_record["status"] = "submitted"
                call_record["request_id"] = job.request_id
                write_json(output_root / "manifest.json", manifest)

                result = provider.result(job)
                write_json(call_dir / "provider-response.json", asdict(result))
                artifact = output_reader.read(result.output_url)
                extension = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }.get(artifact.content_type, ".bin")
                output_path = call_dir / f"output{extension}"
                output_path.write_bytes(artifact.content)
                call_record["status"] = "completed"
                call_record["completed_at"] = datetime.now(UTC).isoformat()
                call_record["output"] = str(output_path.relative_to(output_root))
                write_json(output_root / "manifest.json", manifest)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failed_at"] = datetime.now(UTC).isoformat()
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
        write_json(output_root / "manifest.json", manifest)
        raise

    manifest["status"] = "completed"
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    write_json(output_root / "manifest.json", manifest)
    print(output_root / "manifest.json")


if __name__ == "__main__":
    main()
