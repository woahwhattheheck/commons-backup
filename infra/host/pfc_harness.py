#!/usr/bin/env python3
"""Retired mirror of the host-compute PFC harness; fail before model I/O."""

from __future__ import annotations

import sys


MESSAGE = (
    "REFUSE_HOST_COMPUTE: infra/host/pfc_harness.py is retired; it will not "
    "map the model or launch sdc_fwd_sdc.py. Use infra/host/pfc_desktop.py."
)


def main(argv: list[str] | None = None) -> int:
    del argv
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
