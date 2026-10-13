#!/usr/bin/env python3
"""host/pfc_langton.py — LANGTON'S ANT, forged as a self-clocked gate netlist and PROVEN byte-exact (fable 2026-07-23).

A contribution to the titan chip's demo family (alongside Life / Brian's Brain): the ant's ENTIRE rule is prefabricated
as gates via the real compiler (sdc_cc), the state (grid + ant one-hot position + 2-bit heading) lives in storage, and
each frame is ONE baked next-state propagation. The host only pulses the clock and blits. Toroidal grid.

Rule: on a white cell turn RIGHT, flip to black, step forward; on a black cell turn LEFT, flip to white, step forward.

  python host/pfc_langton.py --test     # bake + verify byte-exact vs reference over N steps + clock rate
  python host/pfc_langton.py            # play it (host only renders; logic runs on the baked netlist)
"""
import os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}
OPN = {v: k for k, v in OPC.items()}
GW = GH = 32
DXY = [(0, -1), (1, 0), (0, 1), (-1, 0)]           # heading 0=N 1=E 2=S 3=W


# ============================ build the ant as a gate netlist ============================
def build_langton(GW, GH):
    N = GW * GH
    g = CC.CircuitCompiler(2 * N + 2)              # inputs: grid[0..N) , ant_onehot[N..2N) , dir bit0, dir bit1
    IN = g.IN
    grid = [IN[i] for i in range(N)]
    ant = [IN[N + i] for i in range(N)]
    d0, d1 = IN[2 * N], IN[2 * N + 1]
    cell = lambda x, y: (y % GH) * GW + (x % GW)

    cur = g.C0                                      # colour under the ant = OR_c (ant[c] & grid[c])
    for c in range(N):
        cur = g.OR(cur, g.AND(ant[c], grid[c]))
    ncur = g.NOT(cur)

    r0 = g.NOT(d0); r1 = g.XOR(d1, d0)              # turn right = dir+1 (mod4)
    l0 = g.NOT(d0); l1 = g.NOT(g.XOR(d1, d0))       # turn left  = dir-1 (mod4)
    nd0 = g.OR(g.AND(cur, l0), g.AND(ncur, r0))     # cur ? left : right
    nd1 = g.OR(g.AND(cur, l1), g.AND(ncur, r1))
    is_ = [g.AND(g.NOT(nd1), g.NOT(nd0)), g.AND(g.NOT(nd1), nd0),
           g.AND(nd1, g.NOT(nd0)), g.AND(nd1, nd0)]  # one-hot new heading

    ngrid = [g.XOR(grid[c], ant[c]) for c in range(N)]                # flip the cell under the ant
    nant = []
    for ty in range(GH):
        for tx in range(GW):
            a = g.C0
            for d, (dx, dy) in enumerate(DXY):                       # target t gets the ant from source t-delta(d)
                a = g.OR(a, g.AND(ant[cell(tx - dx, ty - dy)], is_[d]))
            nant.append(a)
    gates, outs2 = g.dce(ngrid + nant + [nd0, nd1])
    return g, gates, outs2


# ============================ python reference (ground truth) ============================
def ref_step(grid, ant, d, GW, GH):
    cur = grid[ant]; nd = (d - 1) % 4 if cur else (d + 1) % 4
    ng = list(grid); ng[ant] ^= 1
    ax, ay = ant % GW, ant // GW; dx, dy = DXY[nd]
    return ng, ((ay + dy) % GH) * GW + ((ax + dx) % GW), nd


# ============================ bake / load the netlist (logic in storage) ============================
def bake():
    print(f"fabricating Langton's Ant as a gate netlist ({GW}x{GH} grid) …", flush=True)
    t0 = time.time(); g, gates, outs = build_langton(GW, GH); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in:,} state bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True); path = os.path.join(SBX, "pfc_langton.pfc")
    with open(path, "wb") as f:
        f.write(b"PFCLANGT"); f.write(struct.pack("<IIIII", g.n_in, n_wire, len(gates), len(outs), GW))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {path}  ({os.path.getsize(path):,} B). logic now lives in storage.", flush=True)
    return path


def load():
    path = os.path.join(SBX, "pfc_langton.pfc")
    if not os.path.exists(path): bake()
    blob = open(path, "rb").read(); assert blob[:8] == b"PFCLANGT"
    n_in, n_wire, n_gate, n_out, gw = struct.unpack_from("<IIIII", blob, 8); p = 8 + 20
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(GW=gw, GH=n_in // 2 // gw, N=(n_in - 2) // 2, outs=outs, run=run, n_gate=n_gate)


def tick(cd, grid, ant, d):
    N = cd["N"]
    inp = [0] * (2 * N + 2)
    for c in range(N): inp[c] = grid[c] & 1
    inp[N + ant] = 1; inp[2 * N] = d & 1; inp[2 * N + 1] = (d >> 1) & 1
    v = cd["run"](inp, 1)
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    o = cd["outs"]
    ng = [bit(o[c]) for c in range(N)]
    nant = next((c for c in range(N) if bit(o[N + c])), ant)
    nd = bit(o[2 * N]) | (bit(o[2 * N + 1]) << 1)
    return ng, nant, nd


# ============================ headless self-test ============================
def selftest():
    cd = load(); N = cd["N"]; gw = cd["GW"]; gh = cd["GH"]
    grid = [0] * N; ant = (gh // 2) * gw + gw // 2; d = 0
    rg, ra, rd = list(grid), ant, d
    print(f"\n  self-test: {gw}x{gh} grid, {cd['n_gate']:,} gates. verifying byte-exact vs reference …", flush=True)
    ok = True
    for step in range(200):
        rg, ra, rd = ref_step(rg, ra, rd, gw, gh)
        grid, ant, d = tick(cd, grid, ant, d)
        if grid != rg or ant != ra or d != rd:
            ok = False; print(f"    MISMATCH at step {step+1}"); break
    print(f"    200 clock ticks, byte-exact vs reference: {ok}", flush=True)
    if not ok: return 1
    t0 = time.time(); T = 200
    for _ in range(T): grid, ant, d = tick(cd, grid, ant, d)
    black = sum(grid)
    print(f"    clock rate (pure-Python pulse): {T/(time.time()-t0):,.1f} ticks/sec · {black} black cells after 400 steps", flush=True)
    print(f"\n  the ant's whole rule is baked gates; a tick = one propagation. host = clock only.", flush=True)
    return 0


def play():
    import tkinter as tk
    cd = load(); gw, gh, N = cd["GW"], cd["GH"], cd["N"]
    SC = 14; grid = [0] * N; ant = (gh // 2) * gw + gw // 2; d = 0
    root = tk.Tk(); root.title("Langton's Ant — forged on the pfc"); root.configure(bg="#0a0e13")
    cv = tk.Canvas(root, width=gw * SC, height=gh * SC, bg="#0a0e13", highlightthickness=0); cv.pack(padx=10, pady=10)
    rects = [cv.create_rectangle((i % gw) * SC, (i // gw) * SC, (i % gw) * SC + SC, (i // gw) * SC + SC,
                                 outline="", fill="#0a0e13") for i in range(N)]
    root.bind("<Escape>", lambda e: root.destroy())

    def frame():
        nonlocal grid, ant, d
        for _ in range(3): grid, ant, d = tick(cd, grid, ant, d)   # a few pulses per rendered frame
        for i in range(N):
            cv.itemconfig(rects[i], fill="#e8434e" if i == ant else ("#d7dde5" if grid[i] else "#121821"))
        root.after(16, frame)
    frame(); root.mainloop()


def main():
    if "--test" in sys.argv[1:]: return selftest()
    if "--bake" in sys.argv[1:]: bake(); return 0
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
