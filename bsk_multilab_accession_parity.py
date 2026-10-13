#!/usr/bin/env python3
"""Official command for bsk-multilab-accession-parity-lims-01.

Thin door over the revenue runner. The program lives at
revenue/bsk_multilab_accession_parity/runner.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "revenue" / "bsk_multilab_accession_parity" / "runner.py"
SPEC = importlib.util.spec_from_file_location("bsk_multilab_accession_parity_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing revenue/bsk_multilab_accession_parity/runner.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
