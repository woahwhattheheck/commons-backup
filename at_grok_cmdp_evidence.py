#!/usr/bin/env python3
"""Official command for AT-GROK-CMDP-EVIDENCE-01.

Thin door over revenue/at_grok_cmdp_evidence/runner.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "revenue" / "at_grok_cmdp_evidence" / "runner.py"
SPEC = importlib.util.spec_from_file_location("at_grok_cmdp_evidence_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing revenue/at_grok_cmdp_evidence/runner.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
