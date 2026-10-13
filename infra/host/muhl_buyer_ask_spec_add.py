#!/usr/bin/env python3
"""Thin buyer-ask routing button → host/muhl_serve_spec_add.py.

Default --dry (print only). --run ask subprocesses the existing spec launcher.
Fail closed if muhl_serve_spec_add.py is missing. Does not reimplement
inference, inspect titan, or dump offsets/foundry/allocator.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
SPEC_LAUNCHER = HERE / "muhl_serve_spec_add.py"
DEFAULT_PROMPT = "The capital of France is"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Thin subprocess to muhl_serve_spec_add.py ask (default dry)."
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        default=True,
        help="forward --dry to the spec launcher (default)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="forward --run ask to the spec launcher (overrides --dry)",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=DEFAULT_PROMPT,
        help="prompt for ask (default: capital of France)",
    )
    args = parser.parse_args(argv)

    if not SPEC_LAUNCHER.is_file():
        print(
            f"REFUSED (fail closed): required spec launcher is missing: {SPEC_LAUNCHER}",
            file=sys.stderr,
        )
        return 2

    cmd = [sys.executable, str(SPEC_LAUNCHER)]
    if args.run:
        cmd.append("--run")
    else:
        cmd.append("--dry")
    cmd.extend(["ask", args.prompt])

    completed = subprocess.run(cmd, shell=False, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
