#!/usr/bin/env python3
"""Generate and byte-check the complete fictional economics example offline."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

from economics import analyze, artifacts
from synthetic_cases import synthetic_document

ROOT = Path(__file__).resolve().parent


def generated_files() -> dict[str, str]:
    doc = synthetic_document()
    files = artifacts(doc, analyze(doc))
    files["synthetic-input.json"] = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    return files


def verify(files: dict[str, str], expected: dict[str, str]) -> None:
    if set(files) != set(expected):
        raise ValueError("example manifest does not name exactly the generated files")
    for name, text in files.items():
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual != expected[name]:
            raise ValueError(f"example byte digest mismatch: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        files = generated_files()
        expected = json.loads((ROOT / "example/expected-output-sha256.json").read_text(encoding="utf-8"))
        verify(files, expected)
        destinations = {name: args.out / (name if name == "synthetic-input.json" else "result/" + name) for name in files}
        for path in destinations.values():
            if path.resolve().is_relative_to(ROOT):
                raise ValueError("rehearsal output must be outside the source component")
        for name, path in destinations.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(files[name], encoding="utf-8", newline="")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
                raise ValueError(f"written output digest mismatch: {name}")
        report = json.loads(files["report.json"])
    except (OSError, UnicodeError, ValueError, ArithmeticError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"PASS: {len(files)} generated files match the checked-in SHA-256 manifest")
    for row in report["scenarios"]:
        print(f"{row['id']}: {row['economic_classification']}")
    print("SYNTHETIC / MODELED_NOT_OBSERVED; no institution finding or spend authorization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
