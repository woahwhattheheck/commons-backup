"""Explicit historical replay surface for the outbound send guard.

This compatibility module is non-authorizing by construction. Historical
evaluation requires an explicit timestamp and emits only the historical schema
with outward HOLD semantics. The old positive CLI is intentionally retired.
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

from ._guard_core import GuardError
from .current import MODE_HISTORICAL, compile_historical_at


def evaluate(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    *,
    historical_at: datetime,
) -> dict[str, Any]:
    return compile_historical_at(
        intent_raw, evidence_raw, historical_at=historical_at
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "outbound-send-guard historical CLI is non-authorizing; "
        "use the current package/guard CLI",
        file=sys.stderr,
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
