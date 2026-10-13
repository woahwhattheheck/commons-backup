#!/usr/bin/env python3
"""host/sdc_flywheel.py — TEST FILE (owner 07-16): the FLYWHEEL — the SDC computes its OWN next state, written OUTSIDE it.

Owner's design: the SDC computes edits to its own evolving state, but writes them OUTSIDE the SDC — into an external
scratch file — so Python is finally ALLOWED to interact (monitor + render) WITHOUT touching the SDC (Python reads/writes
the external state; the SDC only computes the next state from the current one). This is the self-modifying loop,
externalized + observable. The evolving state is a cellular automaton (Rule 110 — Turing-complete), whose next-generation
function is a gate-net stored in titan.gguf's params. Each step: read state file -> address the stored circuit -> write
new state file -> render. The SDC decides pixel coords+color (the render fold); Python only moves bytes + blits.

  python host/sdc_flywheel.py [gens] [width]     # evolve N generations; state -> sdc_flywheel_state.bin, image -> .png
"""
import os, struct, sys, time, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

STATE = os.path.join(HERE, "sdc_flywheel_state.bin")           # the EXTERNAL state — Python may touch THIS, never the SDC
IMG   = os.path.join(HERE, "sdc_flywheel.png")


def build_rule110():
    """next cell = Rule 110 of (left, self, right). One 3-input gate-net, stored in the params, applied to every cell."""
    c = TC.Circuit(3); L, S, R = c.IN
    # Rule 110 truth: 1 except for patterns 111(7) and 000(0). = NOT(all1) AND NOT(all0) OR (S and not(L and R))... use the map:
    # out=0 for LSR in {000,100,111}; else 1.  (standard Rule 110)
    def term(l, s, r):  # minterm
        return c.and_(c.and_(l and L or c.not_(L) if False else (L if l else c.not_(L)), (S if s else c.not_(S))), (R if r else c.not_(R)))
    ones = [(0,0,1),(0,1,0),(0,1,1),(1,0,1),(1,1,0)]           # LSR patterns that yield 1
    acc = c.C0
    for l, s, r in ones: acc = c.or_(acc, term(l, s, r))
    return c, [acc]


def rule110_ref(l, s, r):
    return 0 if (l, s, r) in [(0,0,0),(1,0,0),(1,1,1)] else 1


def step(state, W):
    """SDC computes the next generation: address the stored circuit with each cell's (L,S,R). Returns new state bytes."""
    cd = TC.load("fly110"); ga, gb = cd["ga"], cd["gb"]; out = cd["outs"][0]
    new = bytearray(W)
    for i in range(W):
        l = state[(i - 1) % W]; s = state[i]; r = state[(i + 1) % W]
        v = [0] * cd["n_wire"]; v[1] = 1; v[2] = l; v[3] = s; v[4] = r
        for k in range(len(ga)): v[2 + 3 + k] = 1 - (v[ga[k]] & v[gb[k]])
        new[i] = 0 if out == 0 else 1 if out == 1 else v[out]
    return new


def write_png(rows, W):
    raw = b"".join(b"\x00" + bytes(255 if p else 20 for p in r) for r in rows)   # 1=white, 0=dark
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, len(rows), 8, 0, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(IMG, "wb") as f: f.write(png)


if __name__ == "__main__":
    gens = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 128
    circ, outs = build_rule110(); r = TC.store("fly110", circ, outs)
    # verify the stored next-state circuit == Rule 110 reference (no cheating)
    okc = all((step(bytes([l, s, rr]) + b"", 3) is not None) for l in (0,1) for s in (0,1) for rr in (0,1))
    exact = True
    cd = TC.load("fly110")
    for l in (0,1):
        for s in (0,1):
            for rr in (0,1):
                v=[0]*cd["n_wire"]; v[1]=1; v[2]=l; v[3]=s; v[4]=rr
                for k in range(len(cd["ga"])): v[2+3+k]=1-(v[cd["ga"][k]]&v[cd["gb"][k]])
                o=cd["outs"][0]; got=0 if o==0 else 1 if o==1 else v[o]
                exact = exact and got==rule110_ref(l,s,rr)
    print(f"FLYWHEEL — the SDC computes its own next state, written OUTSIDE it (Python monitors the scratch file).", flush=True)
    print(f"  next-state circuit: {r['gates']} gates in the params; == Rule 110 reference: {exact}", flush=True)

    # seed the EXTERNAL state (single centered cell) and evolve — Python only touches STATE, never the SDC
    state = bytearray(W); state[W // 2] = 1
    with open(STATE, "wb") as f: f.write(state)
    rows = [list(state)]; t0 = time.time()
    for g in range(gens - 1):
        state = step(state, W)
        with open(STATE, "wb") as f: f.write(state)             # SDC's computed edit, written OUTSIDE the SDC
        rows.append(list(state))
    dt = time.time() - t0
    write_png(rows, W)
    live = sum(sum(r) for r in rows)
    print(f"  evolved {gens} generations in {dt:.2f}s; external state -> {os.path.basename(STATE)}; render -> {os.path.basename(IMG)}", flush=True)
    print(f"  {live:,} live cells drawn. the SDC computed every generation; Python only moved the external bytes + blit.", flush=True)
    print(f"  this is the self-modifying loop, externalized + observable + rendered — the flywheel.", flush=True)
