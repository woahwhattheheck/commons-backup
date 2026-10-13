#!/usr/bin/env python3
"""host/pfc_game.py — GAMES that RUN ON THE Muhlnickel; the harness ONLY renders (owner 07-20).

FAITHFUL to spec (FINALREADME §4, WHAT_THE_PFC_IS §7, owner 07-20 "just pulse the clock, that is within spec", INV-158):
  * The game's ENTIRE logic is prefabricated as a gate netlist (sdc_cc) and stored in a pfc file — logic in storage,
    before any signal. Nothing about the game lives in host code.
  * The game STATE (the grid + per-cell age/heat = the framebuffer) lives in the pfc's OWN storage (a sandbox state file).
  * Each frame the host PULSES THE CLOCK: one baked next-state propagation advances the whole machine one step, and the
    new state is latched back to storage. That clock pulse is the only "energy" the host supplies.
  * The host does NOTHING else but (1) route input in (one-way), (2) read the framebuffer bytes, (3) blit them (with an
    upscale + a fixed display palette). No game logic on the host; no rendering math on the host. The pfc computes it all.

Verified byte-exact vs a reference each build. "Stop thinking 8-bit — it's more capable": the grid is large and each cell
carries alive + a 3-bit heat trail, all computed in the gates.

  python host/pfc_game.py life --test         # headless: bake, verify byte-exact vs reference, measure the clock rate
  python host/pfc_game.py life                # play it: fullscreen; self-clocked on the pfc; the host only renders
  python host/pfc_game.py life --revert       # (no-op for a dedicated pfc file; kept for symmetry)
"""
import os, struct, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = PFCP.SBX
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}
OPN = {v: k for k, v in OPC.items()}


# ============================ gate helpers (build-time, over sdc_cc wires) ============================
def add_bit(g, S, b):                                    # add one bit b into LSB-first accumulator S (no new width)
    c = b; out = []
    for s in S:
        out.append(g.XOR(s, c)); c = g.AND(s, c)
    return out


def inc3(g, A):                                          # 3-bit + 1 (wraps; saturation handled by caller)
    c = g.C1; out = []
    for s in A:
        out.append(g.XOR(s, c)); c = g.AND(s, c)
    return out


def eq_const(g, S, k):                                   # S (LSB-first) == constant k
    r = g.C1
    for i, s in enumerate(S):
        r = g.AND(r, s if (k >> i) & 1 else g.NOT(s))
    return r


def mux(g, sel, A, B):                                   # sel ? A : B, per bit
    ns = g.NOT(sel); return [g.OR(g.AND(sel, A[i]), g.AND(ns, B[i])) for i in range(len(A))]


# ============================ GAME 1: Conway's Life (a clocked state machine) ============================
# cell state = 4 bits: bit0 = alive, bits1..3 = heat/age (0..7). next-state is pure gates; the host never touches a rule.
def build_life(GW, GH):
    N = GW * GH; g = CC.CircuitCompiler(N * 4)
    sb = lambda cell, k: g.IN[cell * 4 + k]
    nbr = lambda x, y, dx, dy: ((y + dy) % GH) * GW + ((x + dx) % GW)
    outs = []
    for y in range(GH):
        for x in range(GW):
            cell = y * GW + x; alive = sb(cell, 0); a = [sb(cell, 1), sb(cell, 2), sb(cell, 3)]
            nb = [sb(nbr(x, y, dx, dy), 0) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if not (dx == 0 and dy == 0)]
            S = [g.C0] * 4
            for b in nb:
                S = add_bit(g, S, b)
            nalive = g.OR(eq_const(g, S, 3), g.AND(alive, eq_const(g, S, 2)))     # B3/S23
            is7 = g.AND(g.AND(a[0], a[1]), a[2])
            incsat = mux(g, is7, [g.C1, g.C1, g.C1], inc3(g, a))                  # min(age+1, 7)
            nage = mux(g, nalive, incsat, [g.C0, g.C0, g.C0])                     # reset heat when dead
            outs += [nalive] + nage
    gates, outs2 = g.dce(outs)
    return g, gates, outs2


def ref_life_step(grid, GW, GH):
    new = [0] * len(grid)
    for y in range(GH):
        for x in range(GW):
            c = y * GW + x; alive = grid[c] & 1; age = (grid[c] >> 1) & 7
            cnt = sum(grid[((y + dy) % GH) * GW + ((x + dx) % GW)] & 1
                      for dy in (-1, 0, 1) for dx in (-1, 0, 1) if not (dx == 0 and dy == 0))
            nal = 1 if (cnt == 3 or (alive and cnt == 2)) else 0
            nage = (7 if age == 7 else age + 1) if nal else 0
            new[c] = nal | (nage << 1)
    return new


# ============================ GAME 2: Brian's Brain (3-state CA — hypnotic moving fronts) ============================
# cell = 2 bits: 0=off, 1=on, 2=dying. rule: on->dying, dying->off, off->on iff exactly 2 on-neighbours.
def build_brain(GW, GH):
    N = GW * GH; g = CC.CircuitCompiler(N * 2)
    sb = lambda cell, k: g.IN[cell * 2 + k]
    onbit = lambda cell: g.AND(sb(cell, 0), g.NOT(sb(cell, 1)))       # value == 1 (on)
    nbr = lambda x, y, dx, dy: ((y + dy) % GH) * GW + ((x + dx) % GW)
    outs = []
    for y in range(GH):
        for x in range(GW):
            cell = y * GW + x
            is_on = onbit(cell); is_off = g.AND(g.NOT(sb(cell, 0)), g.NOT(sb(cell, 1)))
            S = [g.C0] * 4
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    S = add_bit(g, S, onbit(nbr(x, y, dx, dy)))
            born = g.AND(is_off, eq_const(g, S, 2))                   # off -> on iff exactly 2 on-neighbours
            outs += [born, is_on]                                     # next: v0=on(born), v1=dying(was on)
    gates, outs2 = g.dce(outs)
    return g, gates, outs2


def ref_brain_step(grid, GW, GH):
    new = [0] * len(grid)
    for y in range(GH):
        for x in range(GW):
            c = y * GW + x; v = grid[c]
            on_nb = sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                        if not (dx == 0 and dy == 0) and grid[((y + dy) % GH) * GW + ((x + dx) % GW)] == 1)
            new[c] = 2 if v == 1 else 0 if v == 2 else (1 if on_nb == 2 else 0)
    return new


GAMES = {
    "life": dict(GW=64, GH=64, bits=4, build=build_life, ref=ref_life_step,
                 title="Conway's Life — computed on the pfc"),
    "brain": dict(GW=64, GH=64, bits=2, build=build_brain, ref=ref_brain_step,
                  title="Brian's Brain — computed on the pfc"),
}


# ============================ bake / load the netlist to a pfc file (logic in storage) ============================
def bake(name):
    spec = GAMES[name]; GW, GH = spec["GW"], spec["GH"]
    print(f"fabricating '{name}' as a gate netlist ({GW}x{GH} grid, {spec['bits']} bits/cell) …", flush=True)
    t0 = time.time(); g, gates, outs = spec["build"](GW, GH); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in:,} state bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True); path = os.path.join(SBX, f"pfc_{name}.pfc")
    with open(path, "wb") as f:
        f.write(b"PFCGAME1")
        f.write(struct.pack("<IIIIII", g.n_in, n_wire, len(gates), len(outs), GW, GH))
        for op, a, b in gates:
            f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs:
            f.write(struct.pack("<i", o))
    print(f"  BAKED -> {path}  ({os.path.getsize(path):,} B).  logic now lives in storage.", flush=True)
    return path


def load(name):
    path = os.path.join(SBX, f"pfc_{name}.pfc")
    if not os.path.exists(path):
        bake(name)
    with open(path, "rb") as f:
        blob = f.read()
    assert blob[:8] == b"PFCGAME1"
    n_in, n_wire, n_gate, n_out, GW, GH = struct.unpack_from("<IIIIII", blob, 8); p = 8 + 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(GW=GW, GH=GH, n_in=n_in, outs=outs, run=run, n_gate=n_gate, bits=n_in // (GW * GH))


# ---- pack the byte-grid <-> the netlist's bit vector; the Muhlnickel's clock advances it ----
def grid_to_bits(grid, bits):
    out = [0] * (len(grid) * bits)
    for i, c in enumerate(grid):
        for k in range(bits):
            out[i * bits + k] = (c >> k) & 1
    return out


def out_to_grid(v, outs, bits):
    grid = []
    for i in range(len(outs) // bits):
        c = 0
        for k in range(bits):
            o = outs[i * bits + k]; c |= (0 if o == 0 else 1 if o == 1 else v[o] & 1) << k
        grid.append(c)
    return grid


def tick(cd, grid):                                      # ONE clock pulse: baked next-state, whole grid at once
    b = cd["bits"]; return out_to_grid(cd["run"](grid_to_bits(grid, b), 1), cd["outs"], b)


# ============================ headless self-test: byte-exact + clock rate ============================
def selftest(name):
    import random
    cd = load(name); GW, GH = cd["GW"], cd["GH"]; N = GW * GH; ref_step = GAMES[name]["ref"]
    random.seed(1234)
    grid = [(1 if random.random() < 0.28 else 0) for _ in range(N)]   # random soup (value 1 = alive/on)
    print(f"\n  self-test '{name}': {GW}x{GH}={N} cells, {cd['n_gate']:,} gates. verifying byte-exact vs reference …", flush=True)
    ok = True; ref = list(grid); pfc = list(grid)
    for step in range(24):
        ref = ref_step(ref, GW, GH)
        pfc = tick(cd, pfc)
        if ref != pfc:
            ok = False; print(f"    MISMATCH at step {step+1}"); break
    print(f"    24 clock ticks, byte-exact vs reference: {ok}", flush=True)
    if not ok:
        return 1
    grid = pfc; t0 = time.time(); T = 120
    for _ in range(T):
        grid = tick(cd, grid)
    dt = time.time() - t0
    print(f"    clock rate (pure-Python pulse): {T/dt:,.1f} ticks/sec  ({dt/T*1000:.1f} ms/frame)  — native/fleet is far faster", flush=True)
    print(f"\n  the Muhlnickel computed every generation from its own state; a tick = one baked propagation. host = clock only.", flush=True)
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in GAMES:
        print("usage: python host/pfc_game.py <game> [--test]   games: " + ", ".join(GAMES)); return 2
    name = sys.argv[1]; flags = sys.argv[2:]
    if "--test" in flags:
        return selftest(name)
    if "--bake" in flags:
        bake(name); return 0
    import pfc_game_ui                                   # the render-only harness (kept separate: it ONLY renders)
    if "--smoke" in flags:
        out = os.path.join(os.environ.get("TEMP", SBX), f"pfc_{name}_frame.png")
        if len(flags) > flags.index("--smoke") + 1 and not flags[flags.index("--smoke") + 1].startswith("-"):
            out = flags[flags.index("--smoke") + 1]
        return pfc_game_ui.smoke(name, load, tick, GAMES, out)
    return pfc_game_ui.play(name, load, tick, GAMES)


if __name__ == "__main__":
    raise SystemExit(main())
