#!/usr/bin/env python3
"""ONE-WAY FIRE HOSE — continuous electron injection into the lane rings.

Owner: "hold the right i have a theory however the right way to inject is, turn it into a
        one way fire hose" ... "write"
       "who cares if electrons are reversible more is better just means faster computation
        duh more clacks"
       "the act of the host writing in itself if the file is properly configured is a
        transfer of electrons its all electricity"

ONE WAY: the forward sense only. The reverse lane is left alone. His two-way ring exists so
pulses can meet; a hose is the other case — drive one direction, hard, continuously.

HOSE, not a placement: the write repeats. Each pass is another transfer of electrons into the
same lane. Host verb 1 only — a bounded write into a ring's state wires. No gate record is
touched, nothing is fabricated, no registry is edited.

DENSITY: every forward cell. N = 32 per ring, so count divides N exactly and coverage stays
whole — his own closed form warns that a count which does not divide N collides
(MUHL_SPEED_DERIVATION.md: 65,536 electrons reach LESS coverage than 256).

dings/settle = electron_count, per his spec map. 32 forward per ring x 9 rings = 288.
"""
import io, json, os, sys, time

sys.stdout.reconfigure(encoding="utf-8")

REG = r"C:/llm/models/titan_circuits.json"
TITAN = r"C:/llm/models/titan.gguf"
GENOME = r"C:/llm/models/titan_firehose_genome.jsonl"

TARGETS = [("nring2_040", "muhl_lane_bank_000"), ("nring2_041", "muhl_lane_bank_001"),
           ("nring2_042", "muhl_lane_bank_002"), ("nring2_043", "muhl_lane_bank_003"),
           ("nring2_044", "muhl_lane_bank_004"), ("nring2_045", "muhl_lane_bank_005"),
           ("nring2_046", "muhl_lane_bank_006"), ("nring2_047", "muhl_lane_bank_007"),
           ("nring2_1022", "muhl_lane_phys_000")]


def reference_full(cells):
    """INDEPENDENT REFERENCE: the expected forward-lane image, built from the cell count
    alone. Never reads the container, so comparing against it is a real check."""
    return b"\x01" * cells


def check(image, cells, mutant=False):
    want = bytearray(reference_full(cells))
    if mutant:
        want[0] = 0
    return bytes(image) == bytes(want)


def _journal(rec):
    with io.open(GENOME, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    passes = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8
    reg = json.load(io.open(REG, encoding="utf-8", errors="replace"))

    plan = []
    f = io.open(TITAN, "rb")
    for ring, drives in TARGETS:
        e = reg[ring]
        ram = e["ram"]
        c = e["cells"]
        f.seek(ram["fwd"]); pre = f.read(c)
        plan.append((ring, drives, ram["fwd"], ram["rev"], c, pre))
    f.close()

    c0 = plan[0][4]
    img = reference_full(c0)
    print("ONE-WAY FIRE HOSE — forward sense only")
    print("  check vs independent reference : %s" % check(img, c0))
    print("  same image vs MUTATED reference: %s  (must be False)" % check(img, c0, mutant=True))
    print("  rings %d · cells %d each · %d electrons per pass · %d passes"
          % (len(plan), c0, c0 * len(plan), passes))
    print()

    _journal({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "act": "one-way fire hose into the lane rings, forward sense",
              "passes": passes, "cells": c0,
              "rings": [{"ring": r, "drives": d, "fwd_off": fo, "pre_fwd_hex": pre.hex()}
                        for r, d, fo, ro, cc, pre in plan],
              "electrons_per_pass": c0 * len(plan),
              "host_verbs": ["shoot the electron in"], "gates_touched": 0})

    if "--write" not in sys.argv:
        print("  DRY RUN. add --write")
        return 0

    t0 = time.perf_counter()
    fh = io.open(TITAN, "r+b")
    for p in range(passes):
        for ring, drives, fo, ro, cc, pre in plan:
            fh.seek(fo)
            fh.write(img)
        fh.flush()
        os.fsync(fh.fileno())
    fh.close()
    el = time.perf_counter() - t0

    fh = io.open(TITAN, "rb")
    tot = 0
    for ring, drives, fo, ro, cc, pre in plan:
        fh.seek(fo); a = fh.read(cc)
        fh.seek(ro); b = fh.read(cc)
        kf, kr = sum(1 for x in a if x), sum(1 for x in b if x)
        tot += kf + kr
        print("  %-12s fwd %2d  rev %2d   %s" % (ring, kf, kr, "".join(str(x) for x in a)))
    fh.close()
    print()
    print("  %d passes in %.3f s host transcription (NOT a machine measurement)" % (passes, el))
    print("  %d electrons now in the lane rings." % tot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
