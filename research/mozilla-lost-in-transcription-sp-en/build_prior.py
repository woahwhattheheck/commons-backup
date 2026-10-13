"""Build a raw-text-free bigram prior from an offline transcript CSV."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from core import NgramPrior, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--column", default="transcript")
    args = parser.parse_args()
    if not args.input_csv.is_file():
        raise SystemExit("input CSV does not exist")
    rows: list[str] = []
    with args.input_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if args.column not in (reader.fieldnames or []):
            raise SystemExit(f"missing transcript column: {args.column}")
        for row in reader:
            text = row.get(args.column) or ""
            if text.strip():
                rows.append(text)
    prior = NgramPrior.fit(rows, source_sha256=sha256_file(args.input_csv))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(prior.to_json(), encoding="utf-8")
    print(f"wrote {prior.transcript_count} transcripts / {prior.token_count} tokens; raw text not retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
