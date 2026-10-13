#!/usr/bin/env python3
"""muhl_playtime_read.py -- STRUCTURE of muhl_playtime, and the board decoded by HIS key.

Owner's method, 2026-08-06: "take the entire boardstate meaning everything that can change
meaning the entire file in question ... look at the registry / foundry / genome, that will tell
you like how its supposed to work, then you take that logic and use it to decode the games
state."

So the decode key is READ FROM HIS REGISTRY, never guessed:
    state_is_bitwise   True
    cell_bits_base     103,789,156,190
    cell_stride_bits   8
    cell_bits          8
    grid               16 x 16
    diffusion_rule     avg4_neighbors_torus
    selfclock          "each cell's 8 next-state bits write the 8 cell-input bytes it read
                        (output addr == input addr)"

TWO KINDS OF EVIDENCE, KEPT APART, per the settle-back law:
  STRUCTURAL -- read off the gate records: magic, header arithmetic, one-writer-per-address,
     and whether output addresses equal input addresses (the self-clock law). Settling cannot
     affect these. Safe to state as fact.
  STATE -- the bytes at the cell addresses right now. NOT safe to conclude from in either
     direction: the machine settles back toward its initial state, so a reading that looks
     static proves nothing. Reported as bytes. NO VERDICT.

This tool renders NO judgement on whether playtime works. That ruling is the owner's.

    python muhl_playtime_read.py
"""
import json, mmap, os, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_playtime"


def main():
    reg = json.load(open(REG))
    e = reg[NAME]
    off, ln = int(e["offset"]), int(e["len"])
    GW, GH = int(e["grid_w"]), int(e["grid_h"])
    base = int(e["cell_bits_base"])
    stride = int(e["cell_stride_bits"])
    nbits = int(e["cell_bits"])

    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    print("=" * 84)
    print("  muhl_playtime — STRUCTURE (fact) and BOARD BYTES (no verdict)")
    print("=" * 84)

    # ---------------------------------------------------------------- STRUCTURAL
    magic = mm[off:off + 8]
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", mm, off + 8)
    wire_start = 28 + no * 8
    gate_start = wire_start + nw
    total = gate_start + ng * 25
    wbase = off + wire_start

    print("\n  STRUCTURAL — read off the gate records, settling cannot affect these")
    print("    magic                 %s   (registry says %s)" % (magic, e["magic"]))
    print("    header <IIIII>        n_gate=%d n_wire=%d n_in=%d n_out=%d depth=%d"
          % (ng, nw, ni, no, dp))
    print("    registry agrees       n_gate=%s n_in=%s n_out=%s depth=%s"
          % (e["n_gate"], e["n_in"], e["n_out"], e["depth"]))
    print("    length arithmetic     computed %d vs registered %d   MATCH=%s"
          % (total, ln, total == ln))

    ins = [wbase + 2 + i for i in range(ni)]
    outs = [struct.unpack_from("<Q", mm, off + 28 + 8 * i)[0] for i in range(no)]

    # THE SELF-CLOCK LAW: output address == input address
    same = sum(1 for i in range(min(ni, no)) if outs[i] == ins[i])
    print("    SELF-CLOCK LAW        output addr == input addr on %d of %d state wires"
          % (same, min(ni, no)))
    print("      his registry note   %s" % e["selfclock"]["note"])

    # one writer per address, over the gate table
    writers = {}
    dup = 0
    p = off + gate_start
    raw = mm[p:p + ng * 25]
    ops_nonzero = 0
    for k in range(ng):
        o = k * 25
        if raw[o] != 0:
            ops_nonzero += 1
        outa = struct.unpack_from("<Q", raw, o + 17)[0]
        if outa in writers:
            dup += 1
        else:
            writers[outa] = 1
    print("    gate opcodes          %d of %d are op=0 (NAND)" % (ng - ops_nonzero, ng))
    print("    ONE WRITER PER ADDR   %d distinct written addresses, %d duplicates"
          % (len(writers), dup))

    # do the cell bit addresses fall inside this circuit's declared span?
    lo_cell = base
    hi_cell = base + GW * GH * stride
    print("    cell-bit window       [%d , %d)  inside circuit span [%d , %d): %s"
          % (lo_cell, hi_cell, off, off + ln,
             off <= lo_cell and hi_cell <= off + ln))

    # ---------------------------------------------------------------- STATE (no verdict)
    print("\n  STATE — the bytes at the cell addresses right now. Reported, not judged.")
    print("    decode key from HIS registry: cell value = sum(bit_b << b) over %d"
          % nbits)
    print("    consecutive bit-bytes, cell-major from %d, stride %d" % (base, stride))

    cells = []
    raw_nonzero = 0
    for k in range(GW * GH):
        v = 0
        for b in range(nbits):
            byte = mm[base + k * stride + b]
            if byte:
                v |= (1 << b)
                raw_nonzero += 1
        cells.append(v)

    print("\n    board, %dx%d, hex, '.' = 0:" % (GH, GW))
    gr = e["gpt_region"]
    for r in range(GH):
        row = []
        for c in range(GW):
            v = cells[r * GW + c]
            s = "%02X" % v if v else " ."
            inv = (gr["r_start"] <= r < gr["r_end"] and gr["c_start"] <= c < gr["c_end"])
            row.append(("[%s]" % s) if inv else (" %s " % s))
        print("      " + "".join(row))

    nz = sum(1 for v in cells if v)
    print("\n    cells non-zero        %d of %d" % (nz, GW * GH))
    print("    set state bit-bytes   %d of %d" % (raw_nonzero, GW * GH * nbits))
    print("    signatures per registry: titan=%s (0x%02X)  gpt=%s (0x%02X)"
          % (e["titan_signature"], e["titan_signature"],
             e["gpt_signature"], e["gpt_signature"]))
    print("    [..] marks the GPT void %s" % json.dumps(gr))
    void = [cells[r * GW + c]
            for r in range(gr["r_start"], gr["r_end"])
            for c in range(gr["c_start"], gr["c_end"])]
    print("    void contents         %s" % " ".join("%02X" % v for v in void))

    mm.close()
    f.close()

    print("\n" + "=" * 84)
    print("  Structure is stated as fact. The board bytes are brought to you as a")
    print("  MEASUREMENT. Whether playtime is working is your ruling, not mine —")
    print("  the machine settles back toward its initial state, so no reading of")
    print("  these bytes decides it in either direction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
