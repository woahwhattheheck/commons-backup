#!/usr/bin/env python3
"""Thin pack entrypoint for the KC Water synthetic routing engine."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import kcwater_phased_lab_relocation_lims as router


def main(argv: list[str] | None = None) -> int:
    return int(router.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
