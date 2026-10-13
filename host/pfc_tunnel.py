#!/usr/bin/env python3
"""host/pfc_tunnel.py — an animated perspective TUNNEL computed entirely on the Muhlnickel (owner 07-20).

A SELF-CLOCKED demo: the pfc's only state is a time counter. Each clock pulse the pfc advances time and PAINTS the whole
framebuffer — a rainbow tunnel flying forward. Per pixel the pfc computes  idx = (depth + time + angle/8) & 255  where the
pixel's polar geometry (depth = perspective 1/radius, angle) is baked as constants and TIME is the pfc's own state; idx
maps through a rainbow palette (the DAC). Host = pulse + blit only. Byte-exact vs a reference.

  python host/pfc_tunnel.py --test    # build, verify byte-exact, render a frame
  python host/pfc_tunnel.py           # watch it — fullscreen, animating on the pfc
"""
import base64, colorsys, math, os, struct, sys, time, zlib
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = PFCP.SBX; PFC = os.path.join(SBX, "pfc_tunnel.pfc")
SW, SH = 128, 96
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}


def const(g, val, w): return [g.C1 if (val >> i) & 1 else g.C0 for i in range(w)]
def add(g, A, B):
    n = max(len(A), len(B)); A = A + [g.C0] * (n - len(A)); B = B + [g.C0] * (n - len(B)); o = []; c = g.C0
    for k in range(n):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o


# per-pixel baked constant: cp = (depth + angle/8) & 255 ; then idx = (cp + time) & 255
def geom():
    cp = [0] * (SW * SH); cx, cy = SW / 2.0, SH / 2.0
    for y in range(SH):
        for x in range(SW):
            dx = x - cx + 0.5; dy = y - cy + 0.5; r = math.hypot(dx, dy)
            depth = int(min(255, 5000.0 / (r + 1.0)))                       # perspective: center = far
            ang = int(math.atan2(dy, dx) / (2 * math.pi) * 256) & 255
            cp[y * SW + x] = (depth + (ang >> 3)) & 255
    return cp
CP = geom()


def palette():
    pal = [(0, 0, 0)] * 256
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb((i / 256.0) % 1.0, 0.85, 1.0)
        pal[i] = (int(r * 255), int(g * 255), int(b * 255))
    return pal


def ref_step(t):
    fb = bytes((CP[p] + t) & 255 for p in range(SW * SH))
    return (t + 1) & 255, fb


def build(g):
    t = g.IN[0:8]
    outs = list(add(g, t, const(g, 1, 8))[:8])                              # next time = t + 1
    for p in range(SW * SH):
        outs += add(g, const(g, CP[p], 8), t)[:8]                           # idx = (cp + t) & 255
    return g.dce(outs)


def bake():
    g = CC.CircuitCompiler(8)
    print("fabricating the tunnel netlist (one batch) …", flush=True); t0 = time.time()
    gates, outs = build(g); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {len(outs):,} output bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True)
    with open(PFC, "wb") as f:
        f.write(b"PFCTUN01"); f.write(struct.pack("<IIII", g.n_in, n_wire, len(gates), len(outs)))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {PFC} ({os.path.getsize(PFC):,} B).", flush=True)
    return gates, outs, n_wire, g.n_in


def load():
    if not os.path.exists(PFC): bake()
    with open(PFC, "rb") as f: blob = f.read()
    assert blob[:8] == b"PFCTUN01"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(run=run, outs=outs, n_gate=n_gate)


def pulse(cd, t):
    v = cd["run"]([(t >> i) & 1 for i in range(8)], 1); o = cd["outs"]; bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    nt = sum(bit(o[i]) << i for i in range(8))
    fb = bytes(sum(bit(o[8 + p * 8 + i]) << i for i in range(8)) for p in range(SW * SH))
    return nt, fb


def save_png(fb, path, scale):
    pal = palette(); rows = []
    for y in range(SH):
        row = bytearray()
        for x in range(SW):
            r, g, b = pal[fb[y * SW + x]]; row += bytes((r, g, b)) * scale
        line = b"\x00" + bytes(row)
        for _ in range(scale): rows.append(line)
    raw = b"".join(rows)
    ch = lambda tp, d: struct.pack(">I", len(d)) + tp + d + struct.pack(">I", zlib.crc32(tp + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", SW * scale, SH * scale, 8, 2, 0, 0, 0)) +
                           ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))


def test():
    gates, outs, n_wire, n_in = bake()
    cc = CC.CircuitCompiler(n_in); cd = dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=len(gates))
    ok = True
    for t in (0, 1, 7, 64, 128, 200, 255):
        (gt, gfb) = pulse(cd, t); (rt, rfb) = ref_step(t)
        if gt != rt or gfb != rfb: ok = False; print(f"    MISMATCH at t={t}"); break
    print(f"  7 time steps, byte-exact (next time + {SW}x{SH} framebuffer): {ok}", flush=True)
    if ok:
        _, fb = pulse(cd, 40)
        out = os.path.join(os.environ.get("TEMP", SBX), "pfc_tunnel_frame.png"); save_png(fb, out, 5)
        print(f"    rendered a live Muhlnickel frame -> {out}", flush=True)
    return 0 if ok else 1


def play():
    try:
        import tkinter as tk, pfc_blit
    except Exception as e:
        print(f"tkinter unavailable ({e})."); return 1
    cd = load(); pal = palette(); root = tk.Tk(); root.title("pfc tunnel  —  Esc / X to close, F11 fullscreen"); root.configure(bg="#000")
    scale = max(1, min(920 // SW, 720 // SH)); W, H = SW * scale, SH * scale; root.geometry(f"{W}x{H}")
    canvas = tk.Canvas(root, width=W, height=H, bg="#000", highlightthickness=0); canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw"); st = {"t": 0}
    def esc(_=None):
        if root.attributes("-fullscreen"): root.attributes("-fullscreen", False)
        else: root.destroy()
    root.bind("<Escape>", esc); root.bind("q", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    def step():
        nt, fb = pulse(cd, st["t"]); st["t"] = nt
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, g, b = pal[ix]; o = i * 3; rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb)
        big = base.zoom(scale); canvas.itemconfigure(img_id, image=big); canvas.image_big = big
        root.after(1, step)
    print("Muhlnickel tunnel — animating on the Muhlnickel. Esc or the X to close.", flush=True)
    step(); root.mainloop(); return 0


def main():
    if "--test" in sys.argv[1:] or "--bake" in sys.argv[1:]:
        return test()
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
