"""Compare locally rescored corpus images with their operation-specific baselines."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import TypedDict


class Pair(TypedDict):
    fixture_id: str
    operation: str
    score: float


class Manifest(TypedDict):
    pairs: list[Pair]
    operation_baselines: dict[str, dict[str, float | int]]


class Observation(TypedDict):
    image_id: str
    edit_id: str
    cosine_similarity: float


class Observations(TypedDict):
    rows: list[Observation]


def report(manifest: Manifest, observations: Observations) -> dict[str, object]:
    saved = {
        (pair["fixture_id"], pair["operation"]): pair["score"]
        for pair in manifest["pairs"]
    }
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in observations["rows"]:
        key = (row["image_id"], row["edit_id"])
        if key in seen or key not in saved:
            raise ValueError(
                "Observations must match each saved corpus pair exactly once"
            )
        seen.add(key)
        score = float(row["cosine_similarity"])
        if not 0 <= score <= 1:
            raise ValueError("Cosine scores must be in [0, 1]")
        grouped[key[1]].append((saved[key], score))
    if seen != set(saved):
        raise ValueError("Rescore all 100 saved pairs; do not generate new images")
    return {
        "meaning": "Change-magnitude regression telemetry, never a correctness score",
        "operations": {
            operation: {
                "baseline": manifest["operation_baselines"][operation],
                "observed_mean": statistics.fmean(value for _, value in pairs),
                "mean_delta": statistics.fmean(value - old for old, value in pairs),
                "largest_pair_delta": max(abs(value - old) for old, value in pairs),
            }
            for operation, pairs in sorted(grouped.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observations",
        type=Path,
        required=True,
        help="Locally computed DINO metrics.json; no provider calls",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("backend/tests/fixtures/drift-corpus-manifest.json"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            report(
                json.loads(args.manifest.read_text()),
                json.loads(args.observations.read_text()),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
