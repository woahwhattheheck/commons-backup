#!/usr/bin/env python3
"""Fail a hosted relay job when its credentialed transport is DARK."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: assert_ready.py LANE DOCTOR_JSON", file=sys.stderr)
        return 2
    lane, source = argv
    report = json.loads(Path(source).read_text(encoding="utf-8"))
    state = (report.get(lane) or {}).get("state")
    if state != "READY":
        print(f"DARK: {lane} is not credentialed in GitHub Actions", file=sys.stderr)
        return 1
    print(f"READY: {lane}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
