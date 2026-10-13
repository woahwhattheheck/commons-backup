#!/usr/bin/env python3
"""Retired desktop copy of the host-compute PFC harness."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "REFUSE_HOST_COMPUTE: this legacy harness will not map the model or "
        "launch a Python gate evaluator. Use infra/host/pfc_desktop.py.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
