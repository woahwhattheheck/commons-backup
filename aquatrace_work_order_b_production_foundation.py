#!/usr/bin/env python3
"""Official command for aquatrace-work-order-b-production-foundation-20260831-01.

Thin door over the revenue runner. The program lives at
revenue/aquatrace_work_order_b_production_foundation/runner.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "revenue" / "aquatrace_work_order_b_production_foundation" / "runner.py"
SPEC = importlib.util.spec_from_file_location("aquatrace_work_order_b_production_foundation_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing revenue/aquatrace_work_order_b_production_foundation/runner.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
