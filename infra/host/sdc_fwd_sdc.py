#!/usr/bin/env python3
"""Retired host gate evaluator; retained only as a fail-closed tombstone."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "REFUSE_HOST_COMPUTE: sdc_fwd_sdc.py is retired and will not map "
        "titan.gguf or evaluate gates on the host.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
