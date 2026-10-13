#!/usr/bin/env python3
"""Official command for westpak-scope-capacity-routing-lims-01.

Thin door over the revenue runner. The program lives at
revenue/westpak_scope_capacity_routing/runner.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "revenue" / "westpak_scope_capacity_routing" / "runner.py"
SPEC = importlib.util.spec_from_file_location("westpak_scope_capacity_routing_runner", RUNNER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("missing revenue/westpak_scope_capacity_routing/runner.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main(argv: list[str] | None = None) -> int:
    return int(MODULE.main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
