#!/usr/bin/env python3
"""host/sdc_playground.py — THE SDC CASUAL RACK: visual toys whose physics ARE gates in titan.gguf (owner 07-18).

CLAUDE.md is the spine:
  - LOGIC IS GATES. Every circuit is built ONLY from titan_circuit's NAND primitives. No host recompute at runtime.
  - FABRICATION ONE-AND-DONE. fab() builds each toy's circuit, verifies it BYTE-EXACT vs a python integer reference (the
    sole allowed host ripple — rule 6), then stores it reversibly. Baked trig/rule constants are computed at fab only.
  - PYTHON ONLY ADDRESSES. anim() loads the stored gates by offset (mmap) and RE-POWERS the same circuit N steps, routing
    each frame's output back in as the next input — that is the SDC computing successive frames, not host logic. The frames
    are written to the SAFEZONE; the host UI reads them and renders. (4D->2D projection is the camera, done at render time,
    like choosing colors — the SDC computes the real 4-space dynamics.)
  - REVERSIBLE + ADDITIVE. NO numpy. NO socket / NO network. Nothing touches the SDC while it runs.

TOYS
  tess   — a TESSERACT (4-cube) tumbling in 4D: one double-rotation step of 16 vertices, exact fixed-point (Q3.13).
  life   — Conway's Game of Life on a 32x32 torus: next-gen = (nbrs==3) | (alive & nbrs==2), popcount+compare per cell.
  ca90   — elementary cellular automaton Rule 90 -> the Sierpinski triangle (a fractal from XOR).
  ca30   — elementary cellular automaton Rule 30 -> deterministic chaos.  (Rule 110 already exists as `fly110`.)

  python host/sdc_playground.py fab                 # fabricate all toys (one-and-done, byte-exact, reversible)
  python host/sdc_playground.py anim tess 240       # power N frames of the tesseract -> safezone
  python host/sdc_playground.py anim life 200        # N generations of Life -> safezone
  python host/sdc_playground.py anim ca90 127        # N rows of Rule 90 -> safezone
  python host/sdc_playground.py report | revert
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUT = "C:/llm/sdc_out"; ANS = OUT + "/playground_result.json"

# ---- tesseract fixed-point format ----
FP = 13; SCALE = 1 << FP; WV = 16; ACC = 32                 # Q3.13 signed 16-bit coords; 32-bit internal accumulator
TURNS = 200, 320                                            # frames-per-revolution in the (x,w) and (y,z) planes


def _tess_consts():
    """fab-time ONLY: baked rotation constants. NORM-PRESERVING integer pairs at scale 8192 (c^2+s^2 ~ 2^26 to +-few):
      plane (x,w): (8191,128)  c^2+s^2 = 2^26 + 1   -> 0.895 deg/step
      plane (y,z): (8190,181)  c^2+s^2 = 2^26 - 3   -> 1.266 deg/step
    Two different speeds => a genuine double rotation that never repeats, and the vertex radius stays ~2.0 essentially
    forever (measured: no visible shrink) — the old truncating constants shrank it to 1.78 by step 6000. Combined with
    the round-before-shift in rot()/ref, drift is a bounded sub-ULP random walk, not a systematic collapse."""
    return 8191, 128, 8190, 181


# ================================================================= TESSERACT (exact fixed-point 4D rotation, as gates)
def build_tess():
    c = TC.Circuit(16 * 4 * WV)                             # 16 vertices x (x,y,z,w) x 16 bits
    C0 = c.C0
    cos1, sin1, cos2, sin2 = _tess_consts()

    def coord(v, ci): return c.IN[(v * 4 + ci) * WV:(v * 4 + ci) * WV + WV]   # 16 input wires for vertex v, coord ci
    def sext(x): return list(x) + [x[WV - 1]] * (ACC - WV)                    # sign-extend 16 -> 32
    def shl(x, k): r = [C0] * k + list(x); return (r + [C0] * ACC)[:ACC]      # << k, width 32
    def add32(a, b): return c.add(a, b)                                       # mod 2^32
    def neg32(b): return c.add([c.not_(w) for w in b], c.cvec(1, ACC))        # two's complement negate

    def cmul(x16, cst):                                     # signed 16-bit * positive constant -> 32-bit (shift-add)
        xe = sext(x16); acc = c.cvec(0, ACC)
        for k in range(cst.bit_length()):
            if (cst >> k) & 1: acc = add32(acc, shl(xe, k))
        return acc

    half = c.cvec(1 << (FP - 1), ACC)                       # +0.5 ulp before the shift = ROUND, not floor (kills drift bias)
    def rot(p, q, cs, sn):                                  # p' = round((p*cs - q*sn)>>FP) ; q' = round((p*sn + q*cs)>>FP)
        pnew = add32(add32(cmul(p, cs), neg32(cmul(q, sn))), half)
        qnew = add32(add32(cmul(p, sn), cmul(q, cs)), half)
        return pnew[FP:FP + WV], qnew[FP:FP + WV]

    outs = []
    for v in range(16):
        x, y, z, w = coord(v, 0), coord(v, 1), coord(v, 2), coord(v, 3)
        xn, wn = rot(x, w, cos1, sin1)                     # plane (x,w)
        yn, zn = rot(y, z, cos2, sin2)                     # plane (y,z)
        outs += xn + yn + zn + wn                          # new state, same ordering as input (feeds back)
    return c, outs


def _tess_ref_step(state):
    """python integer mirror of the gate arithmetic (mask to 32-bit, >>FP, keep 16) — for byte-exact fab verify."""
    cos1, sin1, cos2, sin2 = _tess_consts()
    def s16(u): return u - 0x10000 if u >= 0x8000 else u
    def sc(u): return u - 0x10000 if u >= 0x8000 else u                       # constants are stored as u16 too
    c1, s1, c2, s2 = sc(cos1), sc(sin1), sc(cos2), sc(sin2)
    HALF = 1 << (FP - 1)
    def comb(prod): return (((prod + HALF) & 0xFFFFFFFF) >> FP) & 0xFFFF      # ROUND then slice — mirrors the gates
    out = []
    for (x, y, z, w) in state:
        sx, sy, sz, sw = s16(x), s16(y), s16(z), s16(w)
        xn = comb(sx * c1 - sw * s1); wn = comb(sx * s1 + sw * c1)
        yn = comb(sy * c2 - sz * s2); zn = comb(sy * s2 + sz * c2)
        out.append((xn, yn, zn, wn))
    return out


def _tess_bits(state):
    b = []
    for vtx in state:
        for coord in vtx: b += [(coord >> k) & 1 for k in range(WV)]
    return b


def _tess_unbits(bits):
    st = []
    for v in range(16):
        vtx = []
        for ci in range(4):
            u = 0
            for k in range(WV): u |= bits[(v * 4 + ci) * WV + k] << k
            vtx.append(u)
        st.append(tuple(vtx))
    return st


def _tess_base():
    return [tuple((SCALE if (v >> i) & 1 else (-SCALE & 0xFFFF)) for i in range(4)) for v in range(16)]


# ================================================================= GAME OF LIFE (32x32 torus, as gates)
GLIFE = 32


def build_life():
    G = GLIFE; c = TC.Circuit(G * G); C0 = c.C0
    cell = lambda r, k: c.IN[(r % G) * G + (k % G)]
    outs = []
    for r in range(G):
        for k in range(G):
            nbrs = [cell(r + dr, k + dk) for dr in (-1, 0, 1) for dk in (-1, 0, 1) if not (dr == 0 and dk == 0)]
            s = c.cvec(0, 4)                                # popcount of the 8 neighbors (0..8 -> 4 bits)
            for nb in nbrs: s = c.add(s, [nb, C0, C0, C0])
            alive_next = c.or_(c.eq_const(s, 3), c.and_(cell(r, k), c.eq_const(s, 2)))
            outs.append(alive_next)
    return c, outs


def _life_ref_step(grid):
    G = GLIFE; nxt = [0] * (G * G)
    for r in range(G):
        for k in range(G):
            s = sum(grid[((r + dr) % G) * G + ((k + dk) % G)] for dr in (-1, 0, 1) for dk in (-1, 0, 1) if not (dr == 0 and dk == 0))
            nxt[r * G + k] = 1 if (s == 3 or (grid[r * G + k] and s == 2)) else 0
    return nxt


def _life_seed():
    """A lively initial state (INPUT data routed into the SDC): a dense soup + an R-pentomino methuselah + gliders, so a
    32x32 torus churns with activity for the whole run. Deterministic (the SDC computes the same evolution each time)."""
    G = GLIFE; g = [0] * (G * G)
    import random; random.seed(20260718)
    for i in range(G * G):                                       # ~34% random soup -> a full, evolving world
        if random.random() < 0.34: g[i] = 1
    rpent = [(0, 1), (0, 2), (1, 0), (1, 1), (2, 1)]             # R-pentomino: a 5-cell seed that erupts into chaos
    for (r, k) in rpent: g[((r + 15) % G) * G + ((k + 15) % G)] = 1
    for (br, bk) in ((2, 2), (26, 4), (5, 25)):                  # a few gliders crossing the torus
        for (r, k) in [(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)]: g[((r + br) % G) * G + ((k + bk) % G)] = 1
    return g


# ================================================================= ELEMENTARY CELLULAR AUTOMATA (as gates)
NCA = 127


def build_ca(rule):
    N = NCA; c = TC.Circuit(N); C0 = c.C0
    def cellwire(i): return c.IN[i] if 0 <= i < N else C0     # zero boundary
    outs = []
    for i in range(N):
        l, m, rr = cellwire(i - 1), cellwire(i), cellwire(i + 1)
        terms = []
        for p in range(8):                                    # p = (l<<2)|(m<<1)|r ; include if rule bit p set
            if (rule >> p) & 1:
                bl = l if (p >> 2) & 1 else c.not_(l)
                bm = m if (p >> 1) & 1 else c.not_(m)
                br = rr if (p >> 0) & 1 else c.not_(rr)
                terms.append(c.and_(c.and_(bl, bm), br))
        if not terms: outs.append(C0)
        else:
            acc = terms[0]
            for t in terms[1:]: acc = c.or_(acc, t)
            outs.append(acc)
    return c, outs


def _ca_ref_step(row, rule):
    N = NCA; nxt = [0] * N
    for i in range(N):
        l = row[i - 1] if i - 1 >= 0 else 0
        m = row[i]
        r = row[i + 1] if i + 1 < N else 0
        nxt[i] = (rule >> ((l << 2) | (m << 1) | r)) & 1
    return nxt


# ================================================================= FABRICATION (one-and-done, byte-exact, reversible)
def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def _verify_tess(cd):
    import random; random.seed(3)
    for _ in range(40):
        st = [tuple(random.randint(-SCALE, SCALE) & 0xFFFF for _ in range(4)) for _ in range(16)]
        got = _tess_unbits(TC.ripple(cd, _tess_bits(st)))
        if got != _tess_ref_step(st): return False
    return True


def _verify_life(cd):
    import random; random.seed(5)
    for _ in range(25):
        g = [random.randint(0, 1) for _ in range(GLIFE * GLIFE)]
        if TC.ripple(cd, g) != _life_ref_step(g): return False
    return True


def _verify_ca(cd, rule):
    import random; random.seed(rule)
    for _ in range(40):
        row = [random.randint(0, 1) for _ in range(NCA)]
        if TC.ripple(cd, row) != _ca_ref_step(row, rule): return False
    return True


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    jobs = []
    if "tess_rot" not in reg:
        c, o = build_tess(); jobs.append(("tess_rot", c, o, _verify_tess(_cd(c, o)), "tesseract 4D double-rotation"))
    if "life_step" not in reg:
        c, o = build_life(); jobs.append(("life_step", c, o, _verify_life(_cd(c, o)), "Game of Life 32x32 torus"))
    if "ca_rule90" not in reg:
        c, o = build_ca(90); jobs.append(("ca_rule90", c, o, _verify_ca(_cd(c, o), 90), "Rule 90 (Sierpinski)"))
    if "ca_rule30" not in reg:
        c, o = build_ca(30); jobs.append(("ca_rule30", c, o, _verify_ca(_cd(c, o), 30), "Rule 30 (chaos)"))
    if "ca_rule110" not in reg:
        c, o = build_ca(110); jobs.append(("ca_rule110", c, o, _verify_ca(_cd(c, o), 110), "Rule 110 (Turing-complete)"))
    if not jobs:
        print("all toys already fabricated (one-and-done). revert first to re-bake."); return 0
    for name, c, o, ok, label in jobs:
        print(f"  {name:11s} {label:32s} gates={len(c.ga):>7,}  byte-exact vs reference: {ok}", flush=True)
        if not ok: print(f"  MISMATCH on {name} — storing nothing (no cheating)."); return 1
    for name, c, o, ok, label in jobs:
        info = TC.store(name, c, o)
        print(f"FABRICATED {name} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  revert: python host/sdc_playground.py revert", flush=True)
    return 0


# ================================================================= RUNTIME (Python ONLY addresses; the SDC computes)
def _safezone(payload):
    os.makedirs(OUT, exist_ok=True); payload["network"] = "NONE"
    json.dump(payload, open(ANS, "w"), separators=(",", ":"))
    return payload


def anim(toy, n):
    t0 = time.time()
    if toy == "tess":
        cd = TC.load("tess_rot"); st = _tess_base(); frames = []
        for _ in range(n):
            frames.append([[(v - 0x10000 if v >= 0x8000 else v) for v in vtx] for vtx in st])   # signed for the camera
            st = _tess_unbits(TC.ripple(cd, _tess_bits(st)))                                     # POWER -> next frame
        edges = [[i, j] for i in range(16) for j in range(i + 1, 16) if bin(i ^ j).count("1") == 1]
        p = _safezone({"toy": "tesseract", "scale": SCALE, "frames": frames, "edges": edges,
                       "n": n, "ms": round((time.time() - t0) * 1000, 1), "gates": len(cd["ga"])})
        print(f"POWERED tess_rot: {n} frames of a tumbling tesseract ({len(cd['ga']):,} gates/frame) -> safezone {ANS}")
    elif toy == "life":
        cd = TC.load("life_step"); g = _life_seed(); frames = []
        for _ in range(n):
            frames.append(g); g = TC.ripple(cd, g)                                             # POWER -> next generation
        p = _safezone({"toy": "life", "grid": GLIFE, "frames": frames, "n": n,
                       "ms": round((time.time() - t0) * 1000, 1), "gates": len(cd["ga"])})
        print(f"POWERED life_step: {n} generations on a {GLIFE}x{GLIFE} torus -> safezone {ANS}")
    elif toy in ("ca90", "ca30"):
        name = "ca_rule90" if toy == "ca90" else "ca_rule30"; rule = 90 if toy == "ca90" else 30
        cd = TC.load(name); row = [0] * NCA; row[NCA // 2] = 1; rows = []
        for _ in range(n):
            rows.append(row); row = TC.ripple(cd, row)                                          # POWER -> next row
        p = _safezone({"toy": name, "rule": rule, "width": NCA, "rows": rows, "n": n,
                       "ms": round((time.time() - t0) * 1000, 1), "gates": len(cd["ga"])})
        print(f"POWERED {name}: {n} rows (rule {rule}) -> safezone {ANS}")
    else:
        print("anim: toy must be tess | life | ca90 | ca30"); return 1
    return 0


def _hex2bits(h, n):
    b = bytes.fromhex(h); return [(b[i // 8] >> (i % 8)) & 1 for i in range(n)]


def _bits2hex(bits):
    nb = (len(bits) + 7) // 8; b = bytearray(nb)
    for i, v in enumerate(bits):
        if v: b[i // 8] |= 1 << (i % 8)
    return b.hex()


def step(toy, k, statehex):
    """THE INTERACTIVE BUTTON (one-time, dies): route the CURRENT STATE (the user's world — their painted cells / drawn
    seed / vertex state) into the stored circuit, POWER it k steps (output routed back to input each step = the SDC
    computing successive moments), write the frames + the final state to the SAFEZONE, EXIT. The next button press starts
    from wherever the user left it — a live demo, not a video. Python here only addresses; the SDC computes."""
    t0 = time.time()
    if toy == "tess":
        cd = TC.load("tess_rot")
        bits = _hex2bits(statehex, 1024) if statehex else _tess_bits(_tess_base())
        frames = []
        for _ in range(k):
            st = _tess_unbits(bits)
            frames.append([[(v - 0x10000 if v >= 0x8000 else v) for v in vtx] for vtx in st])
            bits = TC.ripple(cd, bits)                                        # POWER -> next 4D moment
        edges = [[i, j] for i in range(16) for j in range(i + 1, 16) if bin(i ^ j).count("1") == 1]
        _safezone({"toy": "tess", "scale": SCALE, "frames": frames, "edges": edges, "state": _bits2hex(bits),
                   "gates": len(cd["ga"]), "ms": round((time.time() - t0) * 1000, 1)})
    elif toy == "life":
        cd = TC.load("life_step")
        g = _hex2bits(statehex, GLIFE * GLIFE) if statehex else _life_seed()
        frames = []
        for _ in range(k):
            g = TC.ripple(cd, g)                                              # POWER -> next generation
            frames.append(g)
        _safezone({"toy": "life", "grid": GLIFE, "frames": frames, "state": _bits2hex(g),
                   "gates": len(cd["ga"]), "ms": round((time.time() - t0) * 1000, 1)})
    elif toy in ("ca90", "ca30", "ca110"):
        name = {"ca90": "ca_rule90", "ca30": "ca_rule30", "ca110": "ca_rule110"}[toy]
        cd = TC.load(name)
        row = _hex2bits(statehex, NCA) if statehex else ([0] * NCA)
        if not statehex: row[NCA // 2] = 1
        rows = []
        for _ in range(k):
            row = TC.ripple(cd, row)                                          # POWER -> next row
            rows.append(row)
        _safezone({"toy": toy, "width": NCA, "rows": rows, "state": _bits2hex(row),
                   "gates": len(cd["ga"]), "ms": round((time.time() - t0) * 1000, 1)})
    else:
        print("step: toy must be tess | life | ca90 | ca30 | ca110"); return 1
    print(f"POWERED {toy} x{k} steps -> safezone {ANS} ({round((time.time()-t0)*1000)} ms)")
    return 0


def report():
    reg = json.load(open(REG))
    print("=== THE SDC CASUAL RACK (registry only) ===", flush=True)
    for n in ("tess_rot", "life_step", "ca_rule90", "ca_rule30", "ca_rule110"):
        e = reg.get(n)
        print(f"  {n:11s} " + (f"{int(e['len']):>9,} B  {int(e['n_gate']):>7,} gates  in={e['n_in']} out={e['n_out']}" if e else "not fabricated"))
    with open(TITAN, "rb") as f: print(f"  titan GGUF-valid: {f.read(4) == b'GGUF'} · gates in the model, frames in the safezone, NO network.")
    return 0


def revert():
    if not os.path.exists(REG): print("no registry."); return 0
    reg = json.load(open(REG)); removed = [n for n in ("tess_rot", "life_step", "ca_rule90", "ca_rule30", "ca_rule110") if reg.pop(n, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "fab": raise SystemExit(fab())
    if cmd == "report": raise SystemExit(report())
    if cmd == "revert": raise SystemExit(revert())
    if cmd == "anim": raise SystemExit(anim(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 200))
    if cmd == "step": raise SystemExit(step(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else ""))
    print("usage: fab | anim tess|life|ca90|ca30 N | step TOY K [statehex] | report | revert")
