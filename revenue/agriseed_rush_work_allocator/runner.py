#!/usr/bin/env python3
"""Thin door over the root Agri Seed rush-aware work allocator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "agriseed_rush_work_allocator.py"
SPEC = importlib.util.spec_from_file_location("agriseed_rush_work_allocator", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing agriseed_rush_work_allocator.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
