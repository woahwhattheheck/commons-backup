#!/usr/bin/env python3
"""host/pfc_ram.py — GIVE THE Muhlnickel RAM (owner 07-19): fabricate an addressable read/write memory out of gates.
A memory is just addressable dynamic bits: an array of cells + an address decoder. Baked as a circuit, the pfc stops
being a stateless calculator and becomes a computer with a working store — write to an address, read it back, state
persists (fed back each tick). Byte-exact verified vs a reference memory. This is the missing 'RAM' block; the parallel
'GPU' fabric is the natural next one.

  python host/pfc_ram.py
"""
import os, random, sys
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
sys.path.insert(0, PFCP.SBX)
import sdc_cc as CC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_exp_levers import finish

N = 16          # cells
W = 8           # bits per cell (so: 16 bytes of fabricated RAM)
A = 4           # address bits (log2 N)
M = N * W       # total memory bits
NIN = M + A + A + 1 + W     # cells | read-addr | write-addr | write-enable | write-data


def build_ram():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    cells = [[IN[i * W + b] for b in range(W)] for i in range(N)]
    ra = [IN[M + j] for j in range(A)]
    wa = [IN[M + A + j] for j in range(A)]
    we = IN[M + 2 * A]
    wd = [IN[M + 2 * A + 1 + b] for b in range(W)]

    def onehot(addr):                                  # decoder: sel[i]=1 iff addr==i
        sel = []
        for i in range(N):
            m = g.C1
            for j in range(A):
                m = g.AND(m, addr[j] if (i >> j) & 1 else g.NOT(addr[j]))
            sel.append(m)
        return sel
    rsel, wsel = onehot(ra), onehot(wa)

    read = []                                          # read_data[b] = OR_i (rsel[i] & cell[i][b])
    for b in range(W):
        acc = g.C0
        for i in range(N): acc = g.OR(acc, g.AND(rsel[i], cells[i][b]))
        read.append(acc)

    nxt = []                                           # next_cell[i][b] = (we & wsel[i]) ? wd[b] : cell[i][b]
    for i in range(N):
        wen = g.AND(we, wsel[i])
        for b in range(W):
            nxt.append(g.OR(g.AND(wen, wd[b]), g.AND(g.NOT(wen), cells[i][b])))
    return g, nxt + read                                # outs: M next-cell wires, then W read wires


def pack(cells, ra, wa, we, wd):
    inp = [0] * NIN
    for i in range(N):
        for b in range(W):
            if (cells[i] >> b) & 1: inp[i * W + b] = 1
    for j in range(A):
        if (ra >> j) & 1: inp[M + j] = 1
        if (wa >> j) & 1: inp[M + A + j] = 1
    inp[M + 2 * A] = 1 if we else 0
    for b in range(W):
        if (wd >> b) & 1: inp[M + 2 * A + 1 + b] = 1
    return inp


def unpack(v, out2):
    def bit(w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
    nxt = [0] * N
    for i in range(N):
        for b in range(W):
            if bit(out2[i * W + b]): nxt[i] |= (1 << b)
    read = 0
    for b in range(W):
        if bit(out2[M + b]): read |= (1 << b)
    return nxt, read


def ref(cells, ra, wa, we, wd):
    nxt = list(cells)
    if we: nxt[wa] = wd & 0xff
    return nxt, cells[ra]


def main():
    g, outs = build_ram()
    run, out2, n_gate, n_wire, _ = finish(g, outs)
    print(f"fabricated RAM: {N} cells x {W} bits = {M} bits addressable, {n_gate} gates.\n", flush=True)

    # VERIFY byte-exact vs a reference memory over random ops (no cheating)
    ok = True
    for _ in range(400):
        cells = [random.getrandbits(W) for _ in range(N)]
        ra, wa, we, wd = random.randrange(N), random.randrange(N), random.randrange(2), random.getrandbits(W)
        v = run(pack(cells, ra, wa, we, wd), 1)
        gn, gr = unpack(v, out2)
        rn, rr = ref(cells, ra, wa, we, wd)
        if gn != rn or gr != rr: ok = False; break
    print(f"byte-exact vs reference memory over 400 random ops: {ok}\n", flush=True)
    if not ok:
        print("MISMATCH."); return 1

    # DEMO: a little program that WRITES then READS — state persists across ticks
    print("running a program on the fabricated RAM (state fed back each tick):", flush=True)
    cells = [0] * N
    prog = [("W", 3, 0xAB), ("W", 5, 0xCD), ("W", 9, 0x42), ("W", 3, 0x77),   # write (0x77 overwrites addr 3)
            ("R", 3, 0), ("R", 5, 0), ("R", 9, 0), ("R", 0, 0)]
    for kind, addr, data in prog:
        we = 1 if kind == "W" else 0
        v = run(pack(cells, addr, addr, we, data), 1)
        cells, read = unpack(v, out2)
        if kind == "W":
            print(f"  WRITE cell[{addr:2d}] = 0x{data:02X}", flush=True)
        else:
            print(f"  READ  cell[{addr:2d}] -> 0x{read:02X}", flush=True)
    print(f"\n  final memory: {[hex(c) for c in cells]}", flush=True)
    print("  => the Muhlnickel holds state. it has RAM.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
