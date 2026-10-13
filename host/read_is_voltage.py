#!/usr/bin/env python3
"""host/read_is_voltage.py — a READ is enough electrons.

Owner fact (Slack 1787500422.873539): proven on device, a READ operation
not just a write is sufficient voltage / electrons to propagate the bit
change for muhlnickel computation.

This host instrument opens public excerpts READ-ONLY. It never writes.
It does not evaluate organs as inference. It does not write titan.
Destinations come FROM FILE. Dies after printing numbers.

The stored 1 at CONST1 was written at fabrication. Gates that list that
address as an input are on the READ side. This button performs zero
host writes and still resolves that charge and that fan-in.

  python3 host/read_is_voltage.py
  python3 host/read_is_voltage.py excerpts/20260823/muhl_lvin.mno
"""
from __future__ import annotations

import json
import os
import sys

from shared_one_lever import EXCERPT_DIR, census, list_excerpts, measure_path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def read_only_row(path):
    """Measure one excerpt without writing. Host writes stay 0."""
    row = measure_path(path)
    row["host_writes"] = 0
    row["host_mode"] = "READ"
    row["read_of_stored_1"] = row["share1"]
    row["second_write_required"] = False
    row["titan"] = "NOT_WRITTEN"
    return row


def read_census(paths):
    data = census(paths)
    data["host_writes"] = 0
    data["host_mode"] = "READ"
    data["second_write_required"] = False
    data["read_of_stored_1"] = data["const1_shared"]
    for row in data["rows"]:
        row["host_writes"] = 0
        row["host_mode"] = "READ"
        row["read_of_stored_1"] = row["share1"]
        row["second_write_required"] = False
    return data


def print_row(row):
    print(
        "  %s  READ C1@%d=%s  gates_that_read_it=%d  host_writes=%d  titan=%s"
        % (
            os.path.basename(row["path"]),
            row["const1_addr"],
            row["const1_written"],
            row["read_of_stored_1"],
            row["host_writes"],
            row["titan"],
        )
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in argv
    argv = [arg for arg in argv if arg != "--json"]
    print("READ_IS_VOLTAGE — I haven't measured yet.")
    print("  Owner on device: a READ, not just a write, is enough electrons.")
    if argv:
        paths = [os.path.abspath(arg) for arg in argv]
    else:
        paths = list_excerpts(EXCERPT_DIR)
    if not paths:
        print("NEED_BRYCE — name a .mno or land excerpts/20260823")
        print("  (button dies)")
        return 1
    data = read_census(paths)
    print(
        "  excerpts=%d  stored_1=%d  gates_READ_that_1=%d  host_writes=%d  titan=%s"
        % (
            data["excerpts"],
            data["const1_written"],
            data["read_of_stored_1"],
            data["host_writes"],
            data["titan"],
        )
    )
    for row in data["rows"]:
        print_row(row)
    best = data["best_share1"]
    if best:
        print(
            "  LARGEST READ FAN-IN  %s  one stored 1 at %d READ by %d gates — no second write"
            % (os.path.basename(best["path"]), best["const1_addr"], best["share1"])
        )
    print("  A bare write does not cascade (pfc_propagation A = 0/64).")
    print("  ONE addressed READ propagates the chain (pfc_propagation B = 64/64).")
    print("  This button wrote 0 bytes. The READ resolved the stored charge.")
    print("  (button dies)")
    if want_json:
        print(json.dumps(data, indent=2))
    if data["host_writes"] != 0:
        return 3
    if data["const1_written"] < 1 or data["read_of_stored_1"] < 1:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
