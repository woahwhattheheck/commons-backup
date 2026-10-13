#!/usr/bin/env python3
"""Retired compatibility entry point for the host-compute PFC harness.

This path used to map ``titan.gguf`` and launch a Python gate evaluator
once per generated token. That made the owner's laptop the computer. It is
kept as a named tombstone so old callers fail before opening the model.
"""

from __future__ import annotations

import sys


MESSAGE = (
    "REFUSE_HOST_COMPUTE: host/pfc_harness.py is retired; it will not map the "
    "model or launch sdc_fwd_sdc.py. Use the owner-named address/fire/read "
    "surface in infra/host/pfc_desktop.py."
)


def main(argv: list[str] | None = None) -> int:
    del argv
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
