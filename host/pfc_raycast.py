#!/usr/bin/env python3
"""host/pfc_raycast.py — a REAL first-person RAYCASTER that runs ON THE Muhlnickel (owner 07-20).

FAITHFUL to spec: the ACTUAL raycasting source (rays marched through a real map, walls projected to columns) is
prefabricated as ONE gate netlist and stored in a pfc file. The player state (x, y, angle) lives in the pfc's storage.
Every tick the host does NOTHING but PULSE THE CLOCK (one bounded next-state ripple = the pfc's own compute, electron-
speed by design); the pfc reads the input SIGNALS (the keys the host routed in), MOVES the player, CASTS every ray, and
PAINTS the full framebuffer (an 8-bit palette index per pixel, exactly how DOOM/Wolf3D's VGA DAC worked). The host reads
the framebuffer and shows it — the window is just a monitor; the palette is the DAC. No game logic, no 3D math, no
rendering on the host. Verified byte-exact vs a reference raycaster in one batch (aim blind).

  python host/pfc_raycast.py --test          # build the whole netlist, verify byte-exact vs reference, render a frame
  python host/pfc_raycast.py                 # play: fullscreen, running on the pfc; host = clock + monitor only
"""
import base64, math, os, struct, sys, time, zlib
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = PFCP.SBX; PFC = os.path.join(SBX, "pfc_raycast.pfc")
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}

# ----- world + screen params -----
MW, MH = 8, 8                                            # map cells
SW, SH = 80, 60                                          # screen (columns x rows) — smaller = the clock pulses far faster
FP = 8                                                   # Q8.8 fixed point (world unit = 256)
MAXSTEP = 32                                             # ray-march steps (STEPFRAC=1/4 -> reaches 8 cells)
STEPSHIFT = 2                                            # increment = ray_dir >> 2  (STEPFRAC = 1/4 cell)
FOV = 46                                                 # field of view in angle units (256 = full circle)
MOVESHIFT = 1                                            # move speed = dir >> 1 per tick (0.5 cell/pulse — big, smooth steps)
TURN = 8                                                 # turn speed in angle units per tick (fast turning)
# a real little maze (1 = wall, 0 = empty), bordered
MAP = [1, 1, 1, 1, 1, 1, 1, 1,
       1, 0, 0, 0, 0, 2, 0, 1,
       1, 0, 1, 1, 0, 0, 0, 1,
       1, 0, 1, 0, 0, 3, 0, 1,
       1, 0, 0, 0, 3, 0, 0, 1,
       1, 0, 2, 0, 0, 0, 0, 1,
       1, 0, 0, 0, 0, 0, 0, 1,
       1, 1, 1, 1, 1, 1, 1, 1]
START = (3 * 256 + 128, 3 * 256 + 128, 0)               # px, py (Q8.8), angle

COS = [round(math.cos(a / 256 * 2 * math.pi) * 256) & 0xffff for a in range(256)]   # Q8.8 signed cos, two's-comp 16b
SINi = lambda a: COS[(a - 64) & 255]
COSi = lambda a: COS[a & 255]


def s16(v): return v - 0x10000 if v & 0x8000 else v      # 16-bit two's-comp -> signed int
def u16(v): return v & 0xffff


# ============================ gate helpers (fixed-width, LSB-first wire lists) ============================
def const(g, val, w): return [g.C1 if (val >> i) & 1 else g.C0 for i in range(w)]
def add(g, A, B):
    n = max(len(A), len(B)); A = A + [g.C0] * (n - len(A)); B = B + [g.C0] * (n - len(B))
    o = []; c = g.C0
    for k in range(n):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o
def neg(g, A): return add(g, [g.NOT(x) for x in A], const(g, 1, len(A)))
def sub(g, A, B): B = B + [g.C0] * (len(A) - len(B)); return add(g, A, neg(g, B))[:len(A)]
def sext(g, A, w): return A + [A[-1]] * (w - len(A))
def ashr(g, A, n): return A[n:] + [A[-1]] * n            # arithmetic shift right (floor)
def mux(g, s, A, B):
    n = max(len(A), len(B)); A = A + [g.C0] * (n - len(A)); B = B + [g.C0] * (n - len(B)); ns = g.NOT(s)
    return [g.OR(g.AND(s, A[i]), g.AND(ns, B[i])) for i in range(n)]
def ult(g, A, B):                                        # unsigned A < B -> wire
    n = max(len(A), len(B)); A = A + [g.C0] * (n - len(A)); B = B + [g.C0] * (n - len(B)); lt = g.C0; eq = g.C1
    for i in range(n - 1, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), B[i]))); eq = g.AND(eq, g.NOT(g.XOR(A[i], B[i])))
    return lt
def mulc_s(g, A, k):                                     # signed A(16b) * constant k -> 32-bit signed
    if k == 0: return const(g, 0, 32)
    ak = abs(k); A32 = sext(g, A, 32); acc = const(g, 0, 32)
    for i in range(ak.bit_length()):
        if (ak >> i) & 1:
            acc = add(g, acc, ([g.C0] * i + A32)[:32])
    return neg(g, acc) if k < 0 else acc
def rom(g, addr, table, w):                              # balanced mux ROM; constants fold away
    if not addr: return const(g, table[0] if table else 0, w)
    h = 1 << (len(addr) - 1)
    lo = rom(g, addr[:-1], table[:h], w); hi = rom(g, addr[:-1], table[h:], w)
    return mux(g, addr[-1], hi, lo)


# ============================ per-column fisheye-corrected wall-height table (baked constants) ============================
def height_table(col):
    ca = (col - (SW - 1) / 2) * FOV / SW                 # column angle offset (units)
    cosc = math.cos(ca / 256 * 2 * math.pi)
    tab = []
    for hs in range(MAXSTEP + 1):
        perp = (hs + 0.5) * (1.0 / (1 << STEPSHIFT)) * cosc     # perpendicular distance in cells
        h = int(round(SH * 0.9 / perp)) if perp > 1e-3 else SH
        tab.append(max(0, min(SH, h)))
    return tab                                           # index by hitstep (0..MAXSTEP)


# ============================ palette (the DAC — host side, fixed) ============================
def palette():
    pal = [(0, 0, 0)] * 256
    for r in range(16):                                  # 1..16 ceiling (deep blue -> dark)
        pal[1 + r] = (8, 10 + (15 - r), 22 + (15 - r) * 3)
    for r in range(16):                                  # 17..32 floor (grey)
        pal[17 + r] = (22 + r, 22 + r, 26 + r)
    wallcol = {1: (210, 70, 60), 2: (80, 200, 110), 3: (90, 150, 235)}   # wall types 1/2/3
    for t in (1, 2, 3):
        base = 33 + (t - 1) * 16; br, bg, bb = wallcol[t]
        for s in range(16):                              # 16 shades, darker with distance
            f = (16 - s) / 16.0
            pal[base + s] = (int(br * f), int(bg * f), int(bb * f))
    return pal


CEIL_IDX = lambda r: 1 + min(15, r * 16 // (SH // 2))
FLOOR_IDX = lambda r: 17 + min(15, (r - SH // 2) * 16 // (SH - SH // 2))


# ============================ THE RAYCASTER — reference (byte-exact target) ============================
def ref_step(px, py, ang, keys):
    fwd, bak, tl, tr = keys & 1, (keys >> 1) & 1, (keys >> 2) & 1, (keys >> 3) & 1
    nang = (ang + (TURN if tr else 0) - (TURN if tl else 0)) & 255
    dirx = s16(COSi(ang)); diry = s16(SINi(ang))
    mvx = dirx >> MOVESHIFT; mvy = diry >> MOVESHIFT
    dx = (mvx if fwd else 0) - (mvx if bak else 0); dy = (mvy if fwd else 0) - (mvy if bak else 0)
    cxp, cyp = u16(px + dx), u16(py + dy)
    cell = MAP[((cyp >> FP) & 7) * MW + ((cxp >> FP) & 7)]
    npx, npy = (px, py) if cell else (cxp, cyp)          # block on wall
    fb = bytearray(SW * SH)
    for c in range(SW):
        ca = (c - (SW - 1) // 2)                         # integer column index offset
        cang = round(ca * FOV / SW)
        cosc = s16(COSi(cang)); sinc = s16(SINi(cang))
        rdx = ((dirx * cosc - diry * sinc) >> FP)
        rdy = ((dirx * sinc + diry * cosc) >> FP)
        ix = rdx >> STEPSHIFT; iy = rdy >> STEPSHIFT
        posx, posy = npx, npy; hit = 0; hs = MAXSTEP; wt = 0; sidedark = 0
        pcy = (npy >> FP) & 7
        for s in range(MAXSTEP):
            posx = u16(posx + ix); posy = u16(posy + iy)
            cx = (posx >> FP) & 7; cy = (posy >> FP) & 7
            w = MAP[cy * MW + cx]
            if w and not hit:
                hit = 1; hs = s; wt = w; sidedark = 1 if cy != pcy else 0   # entered via N/S face -> darker
            pcy = cy
        h = height_table(c)[hs] if hit else 0
        top = SH // 2 - (h >> 1); bot = SH // 2 + (h >> 1)
        shade = min(15, (hs >> 1) + (4 if sidedark else 0))
        widx = 33 + (max(1, wt) - 1) * 16 + shade
        for r in range(SH):
            fb[r * SW + c] = widx if (top <= r < bot and hit) else (CEIL_IDX(r) if r < SH // 2 else FLOOR_IDX(r))
    return (npx, npy, nang), bytes(fb)


# ============================ THE RAYCASTER — gate netlist (mirrors ref_step exactly) ============================
def build(g):
    px = g.IN[0:16]; py = g.IN[16:32]; ang = g.IN[32:40]; keys = g.IN[40:46]
    fwd, bak, tl, tr = keys[0], keys[1], keys[2], keys[3]
    nang = add(g, add(g, ang, mux(g, tr, const(g, TURN, 8), const(g, 0, 8))),
               neg(g, mux(g, tl, const(g, TURN, 8), const(g, 0, 8))))[:8]
    dirx = rom(g, ang, [s16(COSi(a)) & 0xffff for a in range(256)], 16)
    diry = rom(g, ang, [s16(SINi(a)) & 0xffff for a in range(256)], 16)
    mvx = ashr(g, dirx, MOVESHIFT); mvy = ashr(g, diry, MOVESHIFT)
    dx = sub(g, mux(g, fwd, mvx, const(g, 0, 16)), mux(g, bak, mvx, const(g, 0, 16)))
    dy = sub(g, mux(g, fwd, mvy, const(g, 0, 16)), mux(g, bak, mvy, const(g, 0, 16)))
    cxp = add(g, px, dx)[:16]; cyp = add(g, py, dy)[:16]
    caddr = [cxp[8], cxp[9], cxp[10], cyp[8], cyp[9], cyp[10]]    # (cellx3 | celly3)
    blocked = ult(g, const(g, 0, 2), rom(g, caddr, MAP, 2))      # MAP cell != 0
    npx = mux(g, blocked, px, cxp); npy = mux(g, blocked, py, cyp)

    outs = list(npx) + list(npy) + list(nang)            # next state (40)
    fb_cols = []                                         # per column: (top,bot 6b, hit, widx 8b)
    for c in range(SW):
        ca = c - (SW - 1) // 2; cang = round(ca * FOV / SW)
        cosc = s16(COSi(cang)); sinc = s16(SINi(cang))
        rdx = ashr(g, sub(g, mulc_s(g, dirx, cosc), mulc_s(g, diry, sinc)), FP)[:16]
        rdy = ashr(g, add(g, mulc_s(g, dirx, sinc), mulc_s(g, diry, cosc)), FP)[:16]
        ix = ashr(g, rdx, STEPSHIFT); iy = ashr(g, rdy, STEPSHIFT)
        posx, posy = list(npx), list(npy); hit = g.C0; hs = const(g, 0, 6); wt = const(g, 0, 2); sidedark = g.C0
        pcy = [npy[8], npy[9], npy[10]]
        for s in range(MAXSTEP):
            posx = add(g, posx, ix)[:16]; posy = add(g, posy, iy)[:16]
            cy = [posy[8], posy[9], posy[10]]
            w = rom(g, [posx[8], posx[9], posx[10]] + cy, MAP, 2); is_w = g.OR(w[0], w[1]); newhit = g.AND(is_w, g.NOT(hit))
            ychg = g.OR(g.OR(g.XOR(cy[0], pcy[0]), g.XOR(cy[1], pcy[1])), g.XOR(cy[2], pcy[2]))
            hs = mux(g, newhit, const(g, s, 6), hs); wt = mux(g, newhit, w, wt)
            sidedark = mux(g, newhit, [ychg], [sidedark])[0]; hit = g.OR(hit, is_w); pcy = cy
        h = rom(g, hs, height_table(c) + [0] * (64 - (MAXSTEP + 1)), 7)   # hitstep(6b) -> height (7b: up to SH)
        h = mux(g, hit, h, const(g, 0, 7))
        half = const(g, SH // 2, 8); hh = sext(g, h[1:] + [g.C0], 8)    # SH/2 and h>>1
        top = sub(g, half, hh)[:8]; bot = add(g, half, hh)[:8]
        hsr = hs[1:6]                                       # hs >> 1 (5 bits)
        base_shade = mux(g, hsr[4], const(g, 15, 4), hsr[0:4])          # min(15, hs>>1)
        sh_plus = add(g, base_shade + [g.C0], mux(g, sidedark, const(g, 4, 4), const(g, 0, 4)) + [g.C0])  # +4 for N/S face
        shade = mux(g, sh_plus[4], const(g, 15, 4), sh_plus[0:4])       # clamp to 15
        wtm1 = sub(g, wt, const(g, 1, 2))[:2]              # (wt-1), wt in {1,2,3}
        widx = add(g, add(g, const(g, 33, 8), ([g.C0] * 4 + wtm1)[:8]), shade + [g.C0] * 4)[:8]  # zero-extend shade
        fb_cols.append((top, bot, hit, widx))

    for r in range(SH):
        cf = CEIL_IDX(r) if r < SH // 2 else FLOOR_IDX(r)
        for c in range(SW):
            top, bot, hit, widx = fb_cols[c]
            rc = const(g, r, 8)
            inwall = g.AND(g.AND(g.NOT(ult(g, rc, top)), ult(g, rc, bot)), hit)   # top<=r<bot & hit
            outs += mux(g, inwall, widx, const(g, cf, 8))
    return g.dce(outs)


# ============================ bake / load / pulse ============================
def bake():
    g = CC.CircuitCompiler(46)
    print("fabricating the raycaster netlist (one batch) …", flush=True); t0 = time.time()
    gates, outs = build(g); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in} input bits, {len(outs):,} output bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True)
    with open(PFC, "wb") as f:
        f.write(b"PFCRAY01"); f.write(struct.pack("<IIII", g.n_in, n_wire, len(gates), len(outs)))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {PFC} ({os.path.getsize(PFC):,} B). the raycaster now lives in storage as gates.", flush=True)
    return gates, outs, n_wire, g.n_in


def load():
    if not os.path.exists(PFC): bake()
    with open(PFC, "rb") as f: blob = f.read()
    assert blob[:8] == b"PFCRAY01"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(run=run, outs=outs, n_in=n_in, n_gate=n_gate)


def pulse(cd, px, py, ang, keys):                        # ONE clock pulse -> (next state, framebuffer bytes)
    inp = [(px >> i) & 1 for i in range(16)] + [(py >> i) & 1 for i in range(16)] + \
          [(ang >> i) & 1 for i in range(8)] + [(keys >> i) & 1 for i in range(6)]
    v = cd["run"](inp, 1); o = cd["outs"]; bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    npx = sum(bit(o[i]) << i for i in range(16)); npy = sum(bit(o[16 + i]) << i for i in range(16))
    nang = sum(bit(o[32 + i]) << i for i in range(8))
    fb = bytes(sum(bit(o[40 + p * 8 + i]) << i for i in range(8)) for p in range(SW * SH))
    return (npx, npy, nang), fb


# ============================ png (view a frame) ============================
def save_png(fb, path, scale):
    pal = palette(); rows = []
    for y in range(SH):
        row = bytearray()
        for x in range(SW):
            r, gg, b = pal[fb[y * SW + x]]; row += bytes((r, gg, b)) * scale
        line = b"\x00" + bytes(row)
        for _ in range(scale): rows.append(line)
    raw = b"".join(rows)
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", SW * scale, SH * scale, 8, 2, 0, 0, 0)) +
                           ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))


def test():
    gates, outs, n_wire, n_in = bake()
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    cd = dict(run=run, outs=outs, n_in=n_in, n_gate=len(gates))
    print(f"\n  verifying byte-exact vs the reference raycaster (state + full framebuffer) …", flush=True)
    cases = [(START[0], START[1], START[2], 0), (START[0], START[1], 40, 1), (900, 700, 96, 0),
             (1100, 1000, 200, 2), (600, 1400, 130, 4), (START[0], START[1], START[2], 8)]
    ok = True
    for (px, py, ang, keys) in cases:
        (gpx, gpy, gang), gfb = pulse(cd, px, py, ang, keys)
        (rpx, rpy, rang), rfb = ref_step(px, py, ang, keys)
        if (gpx, gpy, gang) != (rpx, rpy, rang) or gfb != rfb:
            ok = False
            nd = sum(1 for i in range(len(gfb)) if gfb[i] != rfb[i])
            print(f"    MISMATCH @ (px={px},py={py},ang={ang},keys={keys}): state {(gpx,gpy,gang)} vs {(rpx,rpy,rang)}, {nd} px differ")
            break
    print(f"    6 cases, byte-exact (next state + {SW}x{SH} framebuffer): {ok}", flush=True)
    if ok:
        px, py, ang = START
        for _ in range(2):
            (px, py, ang), fb = pulse(cd, px, py, ang, 0)
        out = os.path.join(os.environ.get("TEMP", SBX), "pfc_raycast_frame.png")
        save_png(fb, out, 8)
        print(f"    rendered a live Muhlnickel frame -> {out} ({SW*8}x{SH*8})", flush=True)
        print(f"\n  the Muhlnickel cast every ray + painted every pixel from its own state; host = clock only.", flush=True)
    return 0 if ok else 1


def main():
    if "--test" in sys.argv[1:] or "--bake" in sys.argv[1:]:
        return test()
    import pfc_raycast_ui
    return pfc_raycast_ui.play(load, pulse, palette, SW, SH, START)


if __name__ == "__main__":
    raise SystemExit(main())
