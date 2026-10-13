#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose an EOD-priority gate into the exact preserved B7 helper.

This transforms source, not actions. The raw donor remains unchanged. Callers must
still perform current-package and economic gates; nothing is installed or enabled.
At EOD, preserved cargo can displace a later worker's more valuable cargo after
market sales open shed space. Reject that entire turn until priority is proved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DONOR_BLOB = "a27da659884c0f9a9594cbd9332b5edb4d7f3307"
ANCHOR = '    board_size = _strict_positive_int_config(configuration, "boardSize", DEFAULT_BOARD_SIZE)\n'
GATE = '''    # Unit-phase shed equality is insufficient at EOD: preserved earlier
    # cargo can displace a later worker's cargo after market sales free room.
    # Keep exact parent identity until a full-turn priority proof admits EOD.
    turns_per_day = _strict_positive_int_config(configuration, "turnsPerDay", 24)
    step = observation.get("step")
    if turns_per_day is None or type(step) is not int or step < 0:
        telemetry["unverified_day_boundary"] += 1
        return action
    if (step + 1) % turns_per_day == 0:
        telemetry["eod_priority_guard"] += 1
        return action

'''


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def repair_source(source: bytes) -> bytes:
    """Return only the exact donor plus one fail-closed day-boundary gate."""
    if not isinstance(source, bytes):
        raise TypeError("source must be original UTF-8 bytes")
    actual = git_blob_sha(source)
    if actual != DONOR_BLOB:
        raise ValueError(f"B7 donor drift: expected {DONOR_BLOB}, got {actual}")
    text = source.decode("utf-8")
    if text.count(ANCHOR) != 1:
        raise ValueError("B7 configuration anchor is not unique")
    return text.replace(ANCHOR, GATE + ANCHOR, 1).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=Path(__file__).parent / "legacy/b7_shed_room_guard.py")
    parser.add_argument("--output", type=Path,
                        help="Optional NEW scratch file; never overwrite donor or existing source")
    args = parser.parse_args()
    source = args.source.read_bytes()
    repaired = repair_source(source)
    if args.output is not None:
        if args.output.resolve() == args.source.resolve():
            raise ValueError("refusing to overwrite the preserved donor")
        with args.output.open("xb") as stream:
            stream.write(repaired)
    print(json.dumps({"donor_blob": git_blob_sha(source),
                      "repaired_blob": git_blob_sha(repaired),
                      "repaired_bytes": len(repaired),
                      "scope": "source composition only; not installed or enabled"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
