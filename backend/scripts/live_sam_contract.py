"""Capture one paid SAM response; never resubmit to debug the decoder."""

import argparse
import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.providers.fal_transport import FalSdkTransport


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    fal_key: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    if not parser.parse_args().live:
        raise SystemExit("Explicit --live is required for one paid SAM call")
    root = Path(__file__).resolve().parents[2]
    output = root / ".progress/phase-b-contracts/sam"
    output.mkdir(parents=True, exist_ok=False)
    source = root / ".progress/p0-zero-spike/inputs/shoe-03.jpg"
    transport = FalSdkTransport(Secrets(_env_file=root / ".env").fal_key)
    payload = {
        "image_url": transport.upload(
            content=source.read_bytes(), filename=source.name
        ),
        "prompt": "logo",
        "return_multiple_masks": True,
        "max_masks": 3,
        "include_scores": True,
        "include_boxes": True,
        "apply_mask": False,
    }
    (output / "request.json").write_text(json.dumps(payload, indent=2) + "\n")
    (output / "attempt.json").write_text('{"paid_submissions": 1}\n')
    request_id = transport.submit(endpoint="fal-ai/sam-3/image-rle", payload=payload)
    (output / "submission.json").write_text(json.dumps({"request_id": request_id}))
    response = transport.result(
        endpoint="fal-ai/sam-3/image-rle", request_id=request_id
    )
    (output / "response.json").write_text(json.dumps(response, indent=2) + "\n")
    fixture = {
        "endpoint": "fal-ai/sam-3/image-rle",
        "request_id": request_id,
        "source_fixture": "shoe-03",
        "width": 1280,
        "height": 1067,
        "prompt": "logo",
        "response": response,
    }
    target = root / "backend/tests/fixtures/sam-3-image-rle.json"
    with target.open("x") as stream:
        json.dump(fixture, stream, indent=2)
        stream.write("\n")
    print(target)


if __name__ == "__main__":
    main()
