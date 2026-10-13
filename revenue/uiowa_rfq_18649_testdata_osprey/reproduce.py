#!/usr/bin/env python3
"""Reproduce the complete fictional demo without changing tracked fixtures."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

from canonical_bridge import run_bridge
from fixture_lab import (CatalogError, assess_catalog, build_bundle, canonical,
                         digest, render_review, write_bundle)
from make_example import example


def reproduce(destination: Path) -> dict:
    catalog = example()
    cutoff = date(2026, 9, 19)
    files = {"example_catalog.json": canonical(catalog),
             "example_review.md": render_review(assess_catalog(catalog, cutoff)).encode()}
    files.update({"example_bundle/" + name: raw for name, raw in build_bundle(catalog, cutoff).items()})
    write_bundle(files, destination)
    bridge_files = run_bridge(destination / "example_bundle", "2026-09-19T11:00:00Z", "2026-09-19T12:00:00Z")
    write_bundle(bridge_files, destination / "canonical_bridge")
    return {"schema": "osprey-reproduction/v1", "synthetic": True,
            "files": {p.relative_to(destination).as_posix(): digest(p.read_bytes())
                      for p in sorted(destination.rglob("*")) if p.is_file()}}


def verify(destination: Path) -> dict:
    expected = json.loads(Path(__file__).with_name("EXPECTED_EXAMPLE.json").read_text())
    actual = {p.relative_to(destination).as_posix(): digest(p.read_bytes())
              for p in sorted(destination.rglob("*")) if p.is_file()}
    if expected["files"] != actual:
        changed = sorted(k for k in expected["files"].keys() | actual.keys()
                         if expected["files"].get(k) != actual.get(k))
        raise CatalogError("pinned example mismatch: " + ", ".join(changed))
    return {"state": "PINNED_FICTIONAL_EXAMPLE_MATCH", "files": len(actual),
            "notice": "Reproducibility only; no application or institutional assessment was executed."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.verify_only:
            reproduce(args.destination)
        print(canonical(verify(args.destination)).decode(), end="")
        return 0
    except (CatalogError, OSError, ValueError) as exc:
        print(f"reproduce: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
