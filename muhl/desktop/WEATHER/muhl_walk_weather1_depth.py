#!/usr/bin/env python3
# Independent WEATHER1 DEPTH walker. Does not import the fabricator.
# Reads <BQQQ> records. Recomputes DEPTH from the bytes. Dies.
# Gravekeeper / Team Stone: header DEPTH is a claim; this walk is from records.
#
#   python muhl_walk_weather1_depth.py C:\Users\lucys\Desktop\WEATHER\weather_v2_denoms.mno
#
# DEPTH = max dep of tmp wires (out >= n_fixed).
# n_fixed = next_base - wire_base + n_out  (field + next live in the wire plane).
# Each gate: dep[out] = 1+max(dep[a], dep[b]) iff out is a tmp (file addr >= wire_base+n_fixed).
# Inputs/const/field/rings/next stay 0. NAND=0 AND=1; rings XOR/AND/OR do not add field DEPTH
# when their outs sit in n_fixed (they do).

import os, struct, sys

NAND, AND, OR, XOR = 0, 1, 2, 3
HDR = 96


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("NEED_BRYCE — name a WEATHER1 .mno")
        return 1
    path = os.path.normpath(argv[0])
    base = os.path.basename(path).lower()
    if base in ("titan.gguf", "muhlnickel_dc.mno", "dc.mno"):
        print("REFUSE — not titan, not dc")
        return 2
    with open(path, "rb") as f:
        raw = f.read()
    assert raw[:8] == b"WEATHER1", raw[:8]
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    hdr_depth = struct.unpack_from("<I", raw, 24)[0]
    stride = struct.unpack_from("<I", raw, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
    assert stride == 25
    n_fixed = (next_base - wire_base) + n_out
    gate_base = wire_base + n_wire
    dep = [0] * n_wire
    dmax = 0
    wmax = None
    why = {}
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * stride)
        ia = a - wire_base
        ib = b - wire_base
        io = out - wire_base
        if io < 0 or io >= n_wire:
            continue
        da = dep[ia] if 0 <= ia < n_wire else 0
        db = dep[ib] if 0 <= ib < n_wire else 0
        if io >= n_fixed:
            dep[io] = 1 + max(da, db)
            why[io] = (op, ia, ib, dep[io])
            if dep[io] > dmax:
                dmax = dep[io]
                wmax = io
    chain = []
    w = wmax
    seen = set()
    while w is not None and w >= n_fixed and w in why and w not in seen:
        seen.add(w)
        op, ia, ib, d = why[w]
        chain.append((w, op, ia, ib, d))
        da = dep[ia] if 0 <= ia < n_wire else 0
        db = dep[ib] if 0 <= ib < n_wire else 0
        w = ia if da >= db else ib
    chain.reverse()
    cpt = (float(n_gate) / dmax) if dmax else 0.0
    opname = {0: "NAND", 1: "AND", 2: "OR", 3: "XOR"}
    print("WALK", path)
    print("  n_in", n_in, "n_wire", n_wire, "n_gate", n_gate, "n_out", n_out)
    print("  n_fixed", n_fixed, "wire_base", wire_base)
    print("  header_DEPTH", hdr_depth)
    print("  records_DEPTH", dmax)
    print("  match", "YES" if dmax == hdr_depth else "NO")
    print("  (a)", "%.3f" % cpt)
    print("  longest tmp chain %d steps (follow higher-dep parent)" % len(chain))
    for i, (out, op, a, b, d) in enumerate(chain, 1):
        print("  %d out=%d %s a=%d b=%d dep=%d" % (i, out, opname.get(op, str(op)), a, b, d))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
