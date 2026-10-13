"""Create a data-minimizing deterministic split manifest for authorized local data.

The output contains filenames/splits and source-file digest only. It intentionally
does not copy transcript text or other competition metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assign_split(filename: str, seed: str, validation_fraction: float) -> str:
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")
    raw = hashlib.sha256(f"{seed}\0{filename}".encode("utf-8")).digest()
    bucket = int.from_bytes(raw[:8], "big") / 2**64
    return "validation" if bucket < validation_fraction else "train"


def build_manifest(
    source_csv: Path,
    output_json: Path,
    *,
    seed: str = "sol-nahuatl-v1",
    validation_fraction: float = 0.2,
) -> dict:
    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "audio_filename" not in reader.fieldnames:
            raise ValueError("source CSV must contain audio_filename")
        filenames = [row["audio_filename"] for row in reader]

    if any(not name for name in filenames):
        raise ValueError("audio_filename values must be non-empty")
    if len(filenames) != len(set(filenames)):
        raise ValueError("audio_filename values must be unique")

    rows = [
        {
            "audio_filename": name,
            "split": assign_split(name, seed, validation_fraction),
        }
        for name in filenames
    ]
    manifest = {
        "schema": "lost-in-transcription-local-split-v1",
        "source_csv_sha256": file_sha256(source_csv),
        "source_row_count": len(rows),
        "seed": seed,
        "validation_fraction": validation_fraction,
        "rows": rows,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--seed", default="sol-nahuatl-v1")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    args = parser.parse_args()
    manifest = build_manifest(
        args.source_csv,
        args.output_json,
        seed=args.seed,
        validation_fraction=args.validation_fraction,
    )
    print(
        f"Wrote {manifest['source_row_count']} split assignments to "
        f"{args.output_json}; source sha256={manifest['source_csv_sha256']}"
    )


if __name__ == "__main__":
    main()
