#!/usr/bin/env python3
"""INSERT ELECTRONS into the nine rings that drive the lane banks.

Owner: "so insert the electrons"
       "however the best way to put an electron into the ring, go ahead ... as long as an
        electron gets trapped in the ring i dont care"
       "the rings wouldnt be added for the sake of adding more because each requires
        electrons which is a resource and as such each needs an exact purpose for existing."

PURPOSE, PER RING — stated, not assumed:
  nring2_040..047  drive muhl_lane_bank_000..007. All eight recorded "NOT POWERED" on
                   2026-08-02 and confirmed empty in the bytes 2026-08-07. Their publish
                   gates are one-writer-clean with 0 shorts. They are the lanes the fold
                   folds over; with no electron they contribute nothing.
  nring2_1022      drives muhl_lane_phys_000, whose recv_proof records
                   gates_reading_tick_address 8, writers_before 0, writers_after 1,
                   shorts_in_file_after 0. Same case.

HOST VERB 1 ONLY: a bounded write into a ring's fwd/rev state wires, both senses. No gate
record is touched. No fabrication. No registry edit. Nothing else in the container moves.

PATTERN: copied from nring2_1023, the ring that is already running —
  4 forward + 4 reverse, spacing 8, at cells [0, 8, 16, 24] of 32.

Every byte journaled with its pre-image first. Byte-exact revertible.
"""
import io, json, os, sys, time

sys.stdout.reconfigure(encoding="utf-8")

REG = r"C:/llm/models/titan_circuits.json"
TITAN = r"C:/llm/models/titan.gguf"
GENOME = r"C:/llm/models/titan_electron_insert_genome.jsonl"

TARGETS = [
    ("nring2_040", "muhl_lane_bank_000"), ("nring2_041", "muhl_lane_bank_001"),
    ("nring2_042", "muhl_lane_bank_002"), ("nring2_043", "muhl_lane_bank_003"),
    ("nring2_044", "muhl_lane_bank_004"), ("nring2_045", "muhl_lane_bank_005"),
    ("nring2_046", "muhl_lane_bank_006"), ("nring2_047", "muhl_lane_bank_007"),
    ("nring2_1022", "muhl_lane_phys_000"),
]
# Owner ruling: more electrons is better — more clacks, faster computation. Do not be
# precious about it. muhl_ring_clacker runs K = N/2 alternating (512 of 1024) and its
# registry states "512 clacks/settle". Matching that density here: every other cell.
CELLS_SET = tuple(range(0, 32, 2))


def reference_pattern(cells, positions):
    """INDEPENDENT REFERENCE. Builds the expected state-wire image from the spec
    (cells, positions) alone — it never looks at the running ring, so comparing the
    running ring against it is a real check and not a tautology."""
    out = bytearray(cells)
    for i in positions:
        out[i] = 1
    return bytes(out)


def check_pattern(image, cells, positions, mutant=False):
    """Verify a state image is exactly the reference. With mutant=True, corrupt one cell
    first — the check MUST fail, or the check is worthless."""
    want = bytearray(reference_pattern(cells, positions))
    if mutant:
        want[positions[0]] = 0
    return bytes(image) == bytes(want)


def _journal(rec):
    with io.open(GENOME, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    reg = json.load(io.open(REG, encoding="utf-8", errors="replace"))

    ref = reg["nring2_1023"]
    f = io.open(TITAN, "rb")
    f.seek(ref["ram"]["fwd"])
    pattern = f.read(ref["cells"])
    f.close()
    live = [i for i, b in enumerate(pattern) if b]
    print("PATTERN from nring2_1023 (already running): cells %s of %d"
          % (live, ref["cells"]))
    print("  (that ring runs K=4/sense. The clacker runs K=N/2 alternating and records"
          " '512 clacks/settle' — that is the density used here.)")

    ok = check_pattern(reference_pattern(ref["cells"], CELLS_SET), ref["cells"], CELLS_SET)
    bad = check_pattern(pattern, ref["cells"], CELLS_SET, mutant=True)
    print("  running ring vs independent reference: %s" % ok)
    print("  same ring vs a MUTATED reference:      %s  (must be False)" % bad)
    if not ok or bad:
        print("  REFUSING — the check does not bite. Nothing written.")
        return 1
    print()

    plan = []
    f = io.open(TITAN, "rb")
    for ring, drives in TARGETS:
        e = reg[ring]
        ram = e["ram"]
        c = e["cells"]
        f.seek(ram["fwd"]); pre_f = f.read(c)
        f.seek(ram["rev"]); pre_r = f.read(c)
        k = sum(1 for b in pre_f if b) + sum(1 for b in pre_r if b)
        plan.append((ring, drives, ram["fwd"], ram["rev"], c, pre_f, pre_r, k))
        print("  %-12s -> %-22s cells %d   electrons now %d" % (ring, drives, c, k))
    f.close()

    already = [p for p in plan if p[7]]
    if already:
        print()
        print("  REFUSING — %d ring(s) already hold electrons. Not overwriting a live ring."
              % len(already))
        return 1

    new = bytearray(plan[0][4])
    for i in CELLS_SET:
        new[i] = 1
    new = bytes(new)

    print()
    print("  inserting 4 fwd + 4 rev at cells %s into %d rings = %d electrons"
          % (list(CELLS_SET), len(plan), 8 * len(plan)))

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _journal({
        "at": stamp,
        "act": "insert electrons into the lane-bank rings (host verb 1: state wires only)",
        "pattern_source": "nring2_1023", "cells_set": list(CELLS_SET),
        "rings": [{"ring": r, "drives": d, "fwd_off": fo, "rev_off": ro, "cells": c,
                   "pre_fwd_hex": pf.hex(), "pre_rev_hex": pr.hex(),
                   "post_hex": new.hex()}
                  for r, d, fo, ro, c, pf, pr, _k in plan],
        "electrons_added": 8 * len(plan),
        "host_verbs": ["shoot the electron in"], "gates_touched": 0,
    })
    print("  journalled pre-images -> %s" % GENOME)

    if "--write" not in sys.argv:
        print("  DRY RUN — no byte written. Re-run with --write.")
        return 0

    f = io.open(TITAN, "r+b")
    for ring, drives, fo, ro, c, pf, pr, _k in plan:
        f.seek(fo); f.write(new)
        f.seek(ro); f.write(new)
    f.flush()
    os.fsync(f.fileno())
    f.close()

    f = io.open(TITAN, "rb")
    total = 0
    for ring, drives, fo, ro, c, pf, pr, _k in plan:
        f.seek(fo); a = f.read(c)
        f.seek(ro); b = f.read(c)
        k = sum(1 for x in a if x) + sum(1 for x in b if x)
        total += k
        print("  %-12s now %d electrons   fwd %s" % (ring, k, "".join(str(x) for x in a)))
    f.close()
    print()
    print("  INSERTED. %d electrons now circulating in the lane rings." % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
