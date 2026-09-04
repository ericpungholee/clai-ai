import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build Clai's versioned drift manifest from the ignored spike corpus."
        )
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(".progress/p0-zero-spike"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backend/tests/fixtures/drift-corpus-manifest.json"),
    )
    return parser.parse_args()


def summary(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
        "population_stddev": statistics.pstdev(values),
    }


def main() -> None:
    args = parse_args()
    corpus = args.corpus
    source_manifest = json.loads((corpus / "manifest.json").read_text())
    metrics = json.loads((corpus / "metrics.json").read_text())

    images = {image["id"]: image for image in source_manifest["images"]}
    edits = {edit["id"]: edit["text"] for edit in source_manifest["edits"]}
    operation_values: dict[str, list[float]] = defaultdict(list)
    pairs: list[dict[str, object]] = []

    for metric in metrics["rows"]:
        image_id = metric["image_id"]
        operation = metric["edit_id"]
        pair_root = corpus / "pairs" / image_id / operation
        request = json.loads((pair_root / "request.json").read_text())
        response = json.loads((pair_root / "provider-response.json").read_text())
        score = float(metric["cosine_similarity"])
        operation_values[operation].append(score)
        image = images[image_id]

        pairs.append(
            {
                "fixture_id": image_id,
                "fixture_name": image["title"],
                "category": metric["category"],
                "operation": operation,
                "user_prompt": edits[operation],
                "prompt_at_runtime": request["input"]["prompt"],
                "seed": request["input"]["seed"],
                "score": score,
                "input_external_url": image["download_url"],
                "output_external_url": response["result"]["images"][0]["url"],
                "local_pair_path": f"pairs/{image_id}/{operation}",
            }
        )

    shoe_recolors = [
        pair["score"]
        for pair in pairs
        if pair["category"] == "shoe" and pair["operation"] == "recolor"
    ]
    manifest = {
        "schema_version": 1,
        "corpus_id": "clai-p0-zero-2026-09-03",
        "provider_endpoint": source_manifest["provider_endpoint"],
        "scorer": {
            "model": metrics["model"],
            "embedding": metrics["embedding"],
            "meaning": "operation-specific change magnitude, not correctness",
        },
        "artifact_location": {
            "repository_path": ".progress/p0-zero-spike",
            "repository_status": "gitignored",
            "external_urls": "recorded per pair; provider output URLs are not durable",
        },
        "operation_baselines": {
            operation: summary(values)
            for operation, values in sorted(operation_values.items())
        },
        "p0_shoe_recolor_baseline": summary(shoe_recolors),
        "fixtures": list(images.values()),
        "pairs": pairs,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
