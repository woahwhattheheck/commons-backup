#!/usr/bin/env python3
"""Thin pack entrypoint for the APL synthetic dossier engine."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import apl_fda_polymer_compliance_dossier_lims as dossier


def main(argv: list[str] | None = None) -> int:
    return int(dossier.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
