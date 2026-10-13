#!/usr/bin/env python3
"""Official command for ddl-crosssite-method-proficiency-lims-01.

Thin door over the revenue runner. The program lives at
revenue/ddl_crosssite_method_proficiency/runner.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "revenue" / "ddl_crosssite_method_proficiency" / "runner.py"
SPEC = importlib.util.spec_from_file_location("ddl_crosssite_method_proficiency_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing revenue/ddl_crosssite_method_proficiency/runner.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
