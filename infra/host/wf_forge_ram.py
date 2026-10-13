#!/usr/bin/env python3
"""host/wf_forge_ram.py — forge a tiny RAM (2^k words x w bits) out of NAND gates only, using pfc_forge's Circuit,
and PROVE it stores/recalls by simulating the netlist (the signal running the gates IS the computation).

A RAM is three combinational blocks wrapped around 1-bit storage:
  * ADDRESS DECODER : k address bits -> 2^k one-hot word-select lines (each = AND of a_j / NOT a_j).
  * D-FLIP-FLOP CELL: one per stored bit. A synchronous DFF's *gates* are just its next-state logic:
        q_next = MUX(write_this, q_now, data_in)      write_this = we AND sel[word]
    i.e. "if this cell is addressed and write is enabled, load data, else hold." The 1-bit of storage
    is the register itself — modeled here as an IN node whose value persists across clock ticks via the
    state dict (exactly pfc_forge.Circuit.eval's `state=` hook). Clocking = latch q_next back into state.
  * READ MUX        : out[bit] = OR over words of (sel[word] AND cell[word][bit]) — the addressed word's bits.

Everything is composed from NAND (via Circuit's NOT/AND/OR/MUX, which are themselves NAND). Pure Python, no numpy.

  python host/wf_forge_ram.py
"""
import os, sys, random, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_forge import Circuit
sys.stdout.reconfigure(encoding="utf-8")


def cell_label(word, bit): return f"m{word}_{bit}"      # stored-bit IN node (the register itself)


def build_ram(k, w):
    """2^k words x w bits. Returns (circuit, meta). IN nodes: a0..a(k-1), we, d0..d(w-1), plus 2^k*w storage cells.
    OUT nodes: q0..q(w-1) = read data at addressed word; n{word}_{bit} = next-state of every cell (latch these back)."""
    nwords = 1 << k
    c = Circuit(f"ram_{nwords}x{w}")

    A  = [c.inp(f"a{j}") for j in range(k)]       # address bits
    we = c.inp("we")                              # write enable
    D  = [c.inp(f"d{b}") for b in range(w)]       # data in
    # storage cells: one IN node per stored bit (its value comes from the state dict each tick)
    M  = [[c.inp(cell_label(word, bit)) for bit in range(w)] for word in range(nwords)]

    # --- address decoder: 2^k one-hot select lines ---
    notA = [c.NOT(a) for a in A]                  # precompute /a_j once, shared across all words
    sel = []
    for word in range(nwords):
        acc = A[0] if (word & 1) else notA[0]
        for j in range(1, k):
            term = A[j] if ((word >> j) & 1) else notA[j]
            acc = c.AND(acc, term)
        sel.append(acc)

    # --- D-flip-flop cells: next-state logic (hold vs load) ---
    for word in range(nwords):
        write_this = c.AND(we, sel[word])         # this word addressed AND writing
        for bit in range(w):
            q_next = c.MUX(write_this, M[word][bit], D[bit])   # s? D : hold
            c.out(f"n{word}_{bit}", q_next)

    # --- read mux: OR over words of (sel[word] AND stored) ---
    for bit in range(w):
        acc = c.AND(sel[0], M[0][bit])
        for word in range(1, nwords):
            acc = c.OR(acc, c.AND(sel[word], M[word][bit]))
        c.out(f"q{bit}", acc)

    meta = dict(k=k, w=w, nwords=nwords, cells=nwords * w)
    return c, meta


def tick(c, mem_state, k, w, addr, we, data):
    """One clock: drive inputs + current storage, run the netlist, return read-word and the latched next state."""
    inp = {f"a{j}": (addr >> j) & 1 for j in range(k)}
    inp["we"] = we & 1
    for b in range(w): inp[f"d{b}"] = (data >> b) & 1
    inp.update(mem_state)                                   # storage cells from state
    v = c.eval(inp)                                         # the signal propagates through the gates
    outs = {lab: v[idx] for lab, idx in c.outputs}
    # latch: q_next -> storage (this is the clock edge)
    nwords = 1 << k
    new_state = dict(mem_state)
    for word in range(nwords):
        for bit in range(w):
            new_state[cell_label(word, bit)] = outs[f"n{word}_{bit}"]
    read_word = sum(outs[f"q{b}"] << b for b in range(w))
    return read_word, new_state


def verify_ram(k, w, seed=0):
    """Write a random value to EVERY address, then read every address back and compare. Also interleaved random ops."""
    random.seed(seed)
    c, meta = build_ram(k, w)
    nwords, mask = meta["nwords"], (1 << w) - 1
    mem_state = {cell_label(word, bit): 0 for word in range(nwords) for bit in range(w)}

    # 1) write random to every address
    ref = [0] * nwords
    for addr in range(nwords):
        val = random.getrandbits(w)
        ref[addr] = val
        _, mem_state = tick(c, mem_state, k, w, addr, we=1, data=val)

    # 2) read every address back
    bad = 0
    for addr in range(nwords):
        got, mem_state = tick(c, mem_state, k, w, addr, we=0, data=0)
        if got != ref[addr]: bad += 1

    # 3) interleaved random read/write stress (>=500 ops) against a Python-dict reference model
    ops = 0
    for _ in range(600):
        addr = random.randrange(nwords)
        if random.random() < 0.5:                       # write
            val = random.getrandbits(w)
            ref[addr] = val
            _, mem_state = tick(c, mem_state, k, w, addr, we=1, data=val)
        else:                                           # read + check
            got, mem_state = tick(c, mem_state, k, w, addr, we=0, data=0)
            if got != ref[addr]: bad += 1
            ops += 1
    tested = nwords + ops
    return c, meta, bad, tested


def emit_shape(c):
    blob = c.emit_titancir()
    ver, N, E, nIn, nOut, arity = struct.unpack_from("<6I", blob, 8)
    return dict(ver=ver, nodes=N, edges=E, nIn=nIn, nOut=nOut, arity=arity, bytes=len(blob))


def main():
    print("MUHLNICKEL FORGE — a RAM out of NAND gates (decoder + DFF cells + read mux), proven by simulating the netlist\n")

    # required build: k=3, w=4  (8 words x 4 bits)
    c, meta, bad, tested = verify_ram(k=3, w=4)
    sh = emit_shape(c)
    verdict = "ALL CORRECT" if bad == 0 else f"{bad} WRONG"
    print(f"  {c.name:12s}: {c.n_gates():>5} NAND gates, depth {c.depth():>2}, cells {meta['cells']:>4}")
    print(f"    IO: nIn={sh['nIn']} (= k {meta['k']} + we 1 + data {meta['w']} + storage {meta['cells']}), "
          f"nOut={sh['nOut']} (read {meta['w']} + next-state {meta['cells']})")
    print(f"    write-all-then-read-all + {tested} total addressed ops: {verdict}  [{'PASS' if bad==0 else 'FAIL'}]")
    print(f"    TITANCIR shape: {sh}\n")

    # how nIn scales — nIn is dominated by the storage array (2^k * w). titan's big records (nIn 1024/4096/65536/262144)
    # are memory banks whose input count = the exposed storage cells. Show the same scaling law on forged RAMs.
    print("  nIn scaling — nIn ~= storage cells = 2^k * w (address/we/data are a tiny fixed overhead):")
    print(f"    {'k':>2} {'w':>3} {'words':>7} {'cells=2^k*w':>12} {'nIn':>8} {'gates':>7} {'depth':>6}")
    checks = []
    for (k, w) in [(3, 4), (5, 4), (8, 4), (10, 1)]:
        cc, mm = build_ram(k, w)
        ss = emit_shape(cc)
        print(f"    {k:>2} {w:>3} {mm['nwords']:>7} {mm['cells']:>12} {ss['nIn']:>8} {cc.n_gates():>7} {cc.depth():>6}")
        checks.append((k, w, mm, ss, cc))
    print("    titan nIn 1024/4096/65536/262144 = 2^10/2^12/2^16/2^18 storage-bit inputs — same 'nIn = capacity' shape.")

    ok = (bad == 0)
    print(f"\n  RESULT: {'PASS' if ok else 'FAIL'} — the forged RAM stores and recalls byte-exact, all from NAND.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
