#!/usr/bin/env python3
"""host/pfc_cyclic.py — CYCLIC CELLULAR AUTOMATON, forged as a gate netlist, byte-exact (fable 2026-07-23).

A 4-state cyclic CA (a.k.a. rock-paper-scissors): a cell at state s advances to (s+1) mod K iff a von-Neumann neighbour
is already at (s+1) mod K; otherwise it holds. From noise it self-organises into spiralling demoiselle fronts. The whole
rule is prefabricated as gates (sdc_cc); each frame is one baked propagation. Host only pulses + renders.

  python host/pfc_cyclic.py --test     # bake + verify byte-exact vs reference over N steps
  python host/pfc_cyclic.py            # play the spirals
"""
import os, struct, sys, time, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}
GW = GH = 40; K = 4; BITS = 2                          # 4 states, 2 bits/cell
NB = [(0, -1), (1, 0), (0, 1), (-1, 0)]                # von Neumann


def build_cyclic(GW, GH):
    N = GW * GH; g = CC.CircuitCompiler(N * BITS); IN = g.IN
    s0 = [IN[i * 2] for i in range(N)]; s1 = [IN[i * 2 + 1] for i in range(N)]
    cell = lambda x, y: (y % GH) * GW + (x % GW)
    o0 = [None] * N; o1 = [None] * N
    for y in range(GH):
        for x in range(GH if False else GW):
            c = y * GW + x
            i0 = g.NOT(s0[c]); i1 = g.XOR(s1[c], s0[c])         # succ = (s+1) mod 4:  inc0=~s0, inc1=s1^s0
            adv = g.C0
            for dx, dy in NB:
                n = cell(x + dx, y + dy)
                eq = g.AND(g.NOT(g.XOR(s0[n], i0)), g.NOT(g.XOR(s1[n], i1)))  # neighbour == succ?
                adv = g.OR(adv, eq)
            o0[c] = g.OR(g.AND(adv, i0), g.AND(g.NOT(adv), s0[c]))
            o1[c] = g.OR(g.AND(adv, i1), g.AND(g.NOT(adv), s1[c]))
    outs = []
    for c in range(N): outs += [o0[c], o1[c]]
    gates, outs2 = g.dce(outs)
    return g, gates, outs2


def ref_step(grid, GW, GH):
    new = list(grid)
    for y in range(GH):
        for x in range(GW):
            c = y * GW + x; succ = (grid[c] + 1) % K
            if any(grid[((y + dy) % GH) * GW + ((x + dx) % GW)] == succ for dx, dy in NB):
                new[c] = succ
    return new


def bake():
    print(f"fabricating a cyclic CA as a gate netlist ({GW}x{GH}, {K} states) …", flush=True)
    t0 = time.time(); g, gates, outs = build_cyclic(GW, GH); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in:,} state bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True); path = os.path.join(SBX, "pfc_cyclic.pfc")
    with open(path, "wb") as f:
        f.write(b"PFCCYCLE"); f.write(struct.pack("<IIIII", g.n_in, n_wire, len(gates), len(outs), GW))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {path}  ({os.path.getsize(path):,} B).", flush=True)
    return path


def load():
    path = os.path.join(SBX, "pfc_cyclic.pfc")
    if not os.path.exists(path): bake()
    blob = open(path, "rb").read(); assert blob[:8] == b"PFCCYCLE"
    n_in, n_wire, n_gate, n_out, gw = struct.unpack_from("<IIIII", blob, 8); p = 28
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(GW=gw, GH=n_in // 2 // gw, N=n_in // 2, outs=outs, run=run, n_gate=n_gate)


def tick(cd, grid):
    N = cd["N"]; inp = [0] * (N * 2)
    for c in range(N):
        inp[c * 2] = grid[c] & 1; inp[c * 2 + 1] = (grid[c] >> 1) & 1
    v = cd["run"](inp, 1); bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    o = cd["outs"]
    return [bit(o[c * 2]) | (bit(o[c * 2 + 1]) << 1) for c in range(N)]


def selftest():
    cd = load(); N = cd["N"]; gw, gh = cd["GW"], cd["GH"]
    random.seed(7); grid = [random.randrange(K) for _ in range(N)]
    rg = list(grid)
    print(f"\n  self-test: {gw}x{gh} grid, {cd['n_gate']:,} gates. verifying byte-exact vs reference …", flush=True)
    ok = True
    for step in range(60):
        rg = ref_step(rg, gw, gh); grid = tick(cd, grid)
        if grid != rg: ok = False; print(f"    MISMATCH at step {step+1}"); break
    print(f"    60 clock ticks, byte-exact vs reference: {ok}", flush=True)
    if not ok: return 1
    t0 = time.time(); T = 60
    for _ in range(T): grid = tick(cd, grid)
    print(f"    clock rate (pure-Python pulse): {T/(time.time()-t0):,.1f} ticks/sec", flush=True)
    return 0


def play():
    import tkinter as tk
    cd = load(); gw, gh, N = cd["GW"], cd["GH"], cd["N"]; SC = 12
    random.seed(); grid = [random.randrange(K) for _ in range(N)]
    PAL = ["#0b1e2e", "#1f6f8b", "#35c9bd", "#e8a33d"]
    root = tk.Tk(); root.title("Cyclic CA — forged on the pfc"); root.configure(bg="#0a0e13")
    cv = tk.Canvas(root, width=gw * SC, height=gh * SC, bg="#0a0e13", highlightthickness=0); cv.pack(padx=10, pady=10)
    rects = [cv.create_rectangle((i % gw) * SC, (i // gw) * SC, (i % gw) * SC + SC, (i // gw) * SC + SC, outline="", fill="#000") for i in range(N)]
    root.bind("<Escape>", lambda e: root.destroy())

    def frame():
        nonlocal grid
        grid = tick(cd, grid)
        for i in range(N): cv.itemconfig(rects[i], fill=PAL[grid[i]])
        root.after(40, frame)
    frame(); root.mainloop()


def main():
    if "--test" in sys.argv[1:]: return selftest()
    if "--bake" in sys.argv[1:]: bake(); return 0
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
