#!/usr/bin/env python3
"""muhl_freeworld_observe.py -- READ-ONLY, AFTER-THE-FACT observation of the free-world field.

Owner 2026-08-06 (verbatim):
  "Your only job is to observe and not interfere -- read what happened after the fact, never nudge
   mid-run ... the instruments have to be read-only and after-the-fact, and no assistant gets to
   grade or steer it either."

So this ONLY reads. Bounded high-impedance mmap slices (~0 RAM, the pfc_scope method). It surfaces
the field's bytes and simple counts. It does NOT grade, score, rank, or judge -- what the numbers
MEAN is the owner's, not the observer's. It writes nothing to the substrate.

  python muhl_freeworld_observe.py
"""
import sys, os, json, struct, mmap

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP
TITAN = PFCP.TITAN; REG = PFCP.REG


def main():
    reg = json.load(open(REG))
    if "muhl_freeworld" not in reg:
        print("  muhl_freeworld not fabricated."); return 1
    fw = reg["muhl_freeworld"]; cb = int(fw["cell_base"]); nc = int(fw["n_cells"])
    w = int(fw["field_w"]); h = int(fw["field_h"])
    ao = int(reg["fwd_answer"]["offset"])

    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    field = bytes(mm[cb:cb + nc])                       # one bounded slice of the whole field
    reg6 = struct.unpack_from("<H", mm, ao)[0]
    mm.close(); f.close()

    nonzero = sum(1 for c in field if c)
    checksum = sum(field) & 0xFFFFFFFF
    distinct_vals = len(set(field))
    written = [(i, field[i]) for i in range(nc) if field[i]]

    print("  FREE-WORLD FIELD -- read-only, after the fact (no grading, just what the bytes are)")
    print("  field muhl_freeworld @ %d, %dx%d = %d cells" % (cb, w, h, nc))
    print("  non-empty cells : %d / %d" % (nonzero, nc))
    print("  checksum        : %08X" % checksum)
    print("  distinct values : %d" % distinct_vals)
    print("  fwd_answer reg6 : %d (0x%04X)" % (reg6, reg6))
    print("  written cells (index=value):")
    for i, v in written[:64]:
        print("    [%5d] (r%3d,c%3d) = %3d (0x%02X)" % (i, i // w, i % w, v, v))
    if len(written) > 64:
        print("    ... +%d more non-empty cells" % (len(written) - 64))
    # a compact map of where writes landed (dot = 0, # = non-zero), downsampled to fit
    print("\n  occupancy map (%dx%d, '#'=written, '.'=blank):" % (w, h))
    for r in range(0, h, max(1, h // 32)):
        row = "".join("#" if field[r * w + c] else "." for c in range(0, w, max(1, w // 64)))
        print("   " + row)
    print("\n  (bytes reported as-is; what any pattern MEANS is the owner's ruling, not the observer's)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
