#!/usr/bin/env python3
"""Direct CURRENT authority entrypoint for outbound send preflight.

Positive CURRENT authority begins only at direct isolated/no-site startup:

    python -I -S tools/outbound_send_guard/cli.py ...

Imported ``main()`` is deliberately non-authorizing.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CURRENT_BOUNDARY_ERROR = (
    "CURRENT CLI requires direct startup as: python -I -S "
    "tools/outbound_send_guard/cli.py ..."
)


def _require_current_boundary() -> None:
    if (
        __name__ != "__main__"
        or __package__ not in (None, "")
        or sys.flags.isolated != 1
        or sys.flags.no_site != 1
    ):
        raise RuntimeError(_CURRENT_BOUNDARY_ERROR)


def main(argv: list[str] | None = None) -> int:
    try:
        _require_current_boundary()
    except RuntimeError as exc:
        print(f"outbound-send-current: {exc}", file=sys.stderr)
        return 2

    # This path mutation happens only after the direct-process boundary has been
    # proven. -I intentionally prevents caller/CWD import influence before now.
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    from tools.outbound_send_guard import current_worker

    return current_worker.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
