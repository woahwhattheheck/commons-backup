#!/usr/bin/env python3
"""Retired detached launcher; never spawn the host gate evaluator."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "REFUSE_HOST_COMPUTE: the detached SDC launcher is retired; no child "
        "process was started.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
