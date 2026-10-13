#!/usr/bin/env python3
"""host/pfc_wireworld.py — WIREWORLD, forged as a gate netlist, byte-exact (fable 2026-07-23).

The most self-referential demo on the chip: Wireworld is a 4-state cellular automaton in which you can BUILD LOGIC GATES
(AND/OR/diodes/clocks out of electron paths) — and here the whole rule is itself prefabricated as logic gates via sdc_cc.
Gates simulating a medium for building gates. States: 0 empty · 1 electron-head · 2 electron-tail · 3 conductor.
Rule: empty->empty, head->tail, tail->conductor, conductor->head iff 1 or 2 of its 8 neighbours are heads (else conductor).

  python host/pfc_wireworld.py --test     # bake + verify byte-exact vs reference over N steps
  python host/pfc_wireworld.py            # play: electrons run the wires
"""
import os, struct, sys, time, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}
GW, GH = 56, 40


def build_wireworld(GW, GH):
    N = GW * GH; g = CC.CircuitCompiler(N * 2); IN = g.IN
    s0 = [IN[i * 2] for i in range(N)]; s1 = [IN[i * 2 + 1] for i in range(N)]
    cell = lambda x, y: (y % GH) * GW + (x % GW)
    get = lambda S, i: S[i] if i < len(S) else g.C0
    o0 = [None] * N; o1 = [None] * N
    for y in range(GH):
        for x in range(GW):
            c = y * GW + x
            S = [g.C0]                                              # popcount of head-neighbours (LSB-first)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0: continue
                    n = cell(x + dx, y + dy)
                    b = g.AND(s0[n], g.NOT(s1[n]))                  # neighbour is a head (state 1)
                    cc = b; ns = []
                    for s in S: ns.append(g.XOR(s, cc)); cc = g.AND(s, cc)
                    ns.append(cc); S = ns
            fire = g.AND(g.AND(g.NOT(get(S, 2)), g.NOT(get(S, 3))), g.XOR(get(S, 0), get(S, 1)))  # count in {1,2}
            o0[c] = s1[c]                                           # next LSB = old MSB (empty/head->0, tail/cond->1)
            o1[c] = g.OR(g.XOR(s0[c], s1[c]), g.AND(g.AND(s0[c], s1[c]), g.NOT(fire)))
    outs = []
    for c in range(N): outs += [o0[c], o1[c]]
    gates, outs2 = g.dce(outs)
    return g, gates, outs2


def ref_step(grid, GW, GH):
    new = list(grid)
    for y in range(GH):
        for x in range(GW):
            c = y * GW + x; v = grid[c]
            if v == 1: new[c] = 2
            elif v == 2: new[c] = 3
            elif v == 3:
                cnt = sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                          if not (dx == 0 and dy == 0) and grid[((y + dy) % GH) * GW + ((x + dx) % GW)] == 1)
                new[c] = 1 if cnt in (1, 2) else 3
            else: new[c] = 0
    return new


def bake():
    print(f"fabricating Wireworld as a gate netlist ({GW}x{GH}) …", flush=True)
    t0 = time.time(); g, gates, outs = build_wireworld(GW, GH); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in:,} state bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True); path = os.path.join(SBX, "pfc_wireworld.pfc")
    with open(path, "wb") as f:
        f.write(b"PFCWIRLD"); f.write(struct.pack("<IIIII", g.n_in, n_wire, len(gates), len(outs), GW))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {path}  ({os.path.getsize(path):,} B).", flush=True)
    return path


def load():
    path = os.path.join(SBX, "pfc_wireworld.pfc")
    if not os.path.exists(path): bake()
    blob = open(path, "rb").read(); assert blob[:8] == b"PFCWIRLD"
    n_in, n_wire, n_gate, n_out, gw = struct.unpack_from("<IIIII", blob, 8); p = 28
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(GW=gw, GH=n_in // 2 // gw, N=n_in // 2, outs=outs, run=run, n_gate=n_gate)


def tick(cd, grid):
    N = cd["N"]; inp = [0] * (N * 2)
    for c in range(N): inp[c * 2] = grid[c] & 1; inp[c * 2 + 1] = (grid[c] >> 1) & 1
    v = cd["run"](inp, 1); bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    o = cd["outs"]; return [bit(o[c * 2]) | (bit(o[c * 2 + 1]) << 1) for c in range(N)]


def selftest():
    cd = load(); N = cd["N"]; gw, gh = cd["GW"], cd["GH"]
    random.seed(11); grid = [random.choice([0, 0, 3, 3, 1, 2]) for _ in range(N)]
    rg = list(grid)
    print(f"\n  self-test: {gw}x{gh} grid, {cd['n_gate']:,} gates. verifying byte-exact vs reference …", flush=True)
    ok = True
    for step in range(60):
        rg = ref_step(rg, gw, gh); grid = tick(cd, grid)
        if grid != rg: ok = False; print(f"    MISMATCH at step {step+1}"); break
    print(f"    60 clock ticks, byte-exact vs reference: {ok}", flush=True)
    if not ok: return 1
    t0 = time.time()
    for _ in range(60): grid = tick(cd, grid)
    print(f"    clock rate (pure-Python pulse): {60/(time.time()-t0):,.1f} ticks/sec", flush=True)
    return 0


def play():
    import tkinter as tk
    cd = load(); gw, gh, N = cd["GW"], cd["GH"], cd["N"]; SC = 11
    random.seed(); grid = [random.choice([0, 0, 0, 3, 3, 3, 3, 1]) for _ in range(N)]
    PAL = ["#0a0e13", "#35c9bd", "#e8a33d", "#3a4658"]     # empty · head · tail · conductor
    root = tk.Tk(); root.title("Wireworld — forged on the pfc"); root.configure(bg="#0a0e13")
    cv = tk.Canvas(root, width=gw * SC, height=gh * SC, bg="#0a0e13", highlightthickness=0); cv.pack(padx=10, pady=10)
    rects = [cv.create_rectangle((i % gw) * SC, (i // gw) * SC, (i % gw) * SC + SC, (i // gw) * SC + SC, outline="", fill="#000") for i in range(N)]
    root.bind("<Escape>", lambda e: root.destroy())

    def frame():
        nonlocal grid
        grid = tick(cd, grid)
        for i in range(N): cv.itemconfig(rects[i], fill=PAL[grid[i]])
        root.after(70, frame)
    frame(); root.mainloop()


def main():
    if "--test" in sys.argv[1:]: return selftest()
    if "--bake" in sys.argv[1:]: bake(); return 0
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
