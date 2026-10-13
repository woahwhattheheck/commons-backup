#!/usr/bin/env python3
"""muhl_raytrace.py -- a fixed-point RAY-SPHERE INTERSECTION / 3D renderer fabricated as gates
on Bryce's Muhlnickel substrate, then used to render a shaded ASCII sphere.

The intersection test is a real gate netlist built with the White Box compiler
(sdc_cc.CircuitCompiler): from a pixel's fixed-point screen coordinate (x, y) it computes the
DOT PRODUCTS x*x and y*y (two's-complement squares via abs + shift-add multiply), sums them
(oc . oc), and forms the ray-sphere DISCRIMINANT  disc = R^2 - (x*x + y*y).  The sign of disc is
the hit bit (disc >= 0  <=>  the orthographic ray through (x,y) strikes the sphere of radius R).

Correctness is proven the Muhlnickel way -- BYTE-EXACT and EXHAUSTIVE: for EVERY pixel in the
raster the gate-computed (disc, hit) equals an independent pure-Python fixed-point reference, with
zero mismatch.  The verified gate discriminant then DRIVES the render: z = isqrt(disc) gives the
sphere's surface height, and Lambert shading against a fixed light direction picks the ASCII glyph.

No numpy, no floats in the fabricated path, no host executor as runtime, no touching titan.gguf.
"""
import sys, os, time, math
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared White Box helpers (same conventions as muhl_flex.py) ----------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

def add_bits(g, A, B, cin=None):
    """ripple-carry add of two equal-width LSB-first bit lists -> (sum bits, carry-out)."""
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def negate(g, A):
    """two's-complement negate: ~A + 1, same width."""
    inv = [g.NOT(a) for a in A]
    s, _ = add_bits(g, inv, [g.C1] + [g.C0] * (len(A) - 1))
    return s

def abs_signed(g, A):
    """|A| for an NB-bit two's-complement value (safe for |A| < 2^(NB-1)).
    sign = MSB; conditionally negate: out = (A ^ sign) + sign."""
    sign = A[-1]
    inv = [g.XOR(a, sign) for a in A]
    out, _ = add_bits(g, inv, [sign] + [g.C0] * (len(A) - 1))
    return out                                          # NB bits, magnitude

def umul(g, A, B):
    """unsigned shift-add multiply: |A|=n, |B|=m -> n+m product bits (LSB-first)."""
    n, m = len(A), len(B)
    acc = [g.C0] * (n + m)
    for j in range(m):
        term = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(n)] + [g.C0] * (n + m))[:n + m]
        acc, _ = add_bits(g, acc, term)
    return acc

def square_signed(g, A):
    """A*A for signed A -> unsigned product (always >= 0). abs then unsigned square."""
    a = abs_signed(g, A)
    return umul(g, a, a)

def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]

# ---------- fabricate the ray-sphere intersection test as gates ----------
# Orthographic camera looking down -z at a sphere centred at the origin, radius R.
# For a pixel whose screen coordinate is (x, y) [fixed-point signed integers], the ray
# (origin (x,y,+big), direction (0,0,-1)) meets the sphere iff  x*x + y*y <= R^2, and the
# quarter-discriminant is  disc = R^2 - (x*x + y*y)  (== z_hit^2, the squared surface height).
# The circuit inputs are x, y as NB-bit signed values; R^2 is a baked constant.

NB = 9                                                  # signed coord width (range +-255; coords stay < ~40)

def build_intersection(R):
    R2 = R * R
    PW = 2 * NB                                          # square is 2*NB bits (unsigned)
    SW = PW + 1                                          # x2 + y2 needs one extra bit
    DW = SW + 1                                          # disc is signed -> one more bit for the sign
    g = CC.CircuitCompiler(2 * NB); IN = g.IN
    X = [IN[i] for i in range(NB)]
    Y = [IN[NB + i] for i in range(NB)]
    x2 = square_signed(g, X)                             # dot product term x.x
    y2 = square_signed(g, Y)                             # dot product term y.y
    # sum s = x2 + y2 (zero-extend to SW)
    x2e = x2 + [g.C0] * (SW - len(x2))
    y2e = y2 + [g.C0] * (SW - len(y2))
    s, _ = add_bits(g, x2e, y2e)                         # oc . oc  (NB-appropriate width)
    # disc = R2 - s  (two's complement subtract, signed DW bits)
    R2c = consts(g, R2, DW)
    se = s + [g.C0] * (DW - len(s))
    neg_s = negate(g, se)
    disc, _ = add_bits(g, R2c, neg_s)                    # disc = R2 + (-s), signed DW bits
    hit = g.NOT(disc[-1])                                # sign bit 0  <=>  disc >= 0  <=>  hit
    outs = disc + [hit]
    run, out2, gates, _ = build_run(g, outs)
    disc_w = out2[:DW]; hit_w = out2[DW]
    return g, run, disc_w, hit_w, gates, DW

def to_signed(val, bits):
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val

# ---------- exhaustive byte-exact verification over the whole raster ----------
def verify_and_render(R=18, NX=44, NY=22, aspect=2):
    g, run, disc_w, hit_w, gates, DW = build_intersection(R)
    depth = depth_of(g, gates, disc_w + [hit_w])
    R2 = R * R

    # screen coords: centre the raster; y compressed by `aspect` so glyph cells look square
    def coords(px, py):
        x = px - NX // 2
        y = (py - NY // 2) * aspect
        return x, y

    ok = True; checked = 0; hits = 0; fail = None
    # exhaustive over every pixel in the raster
    grid_disc = [[None] * NX for _ in range(NY)]
    grid_hit = [[0] * NX for _ in range(NY)]
    for py in range(NY):
        for px in range(NX):
            x, y = coords(px, py)
            inp = [0] * (2 * NB)
            setf(inp, 0, NB, x & ((1 << NB) - 1))
            setf(inp, NB, NB, y & ((1 << NB) - 1))
            v = run(inp, 1)
            gdisc = to_signed(rd(v, disc_w), DW)
            ghit = bit(v, hit_w)
            ref_disc = R2 - (x * x + y * y)              # independent Python fixed-point reference
            ref_hit = 1 if ref_disc >= 0 else 0
            if gdisc != ref_disc or ghit != ref_hit:
                ok = False; fail = (px, py, x, y, gdisc, ref_disc, ghit, ref_hit); break
            checked += 1; hits += ghit
            grid_disc[py][px] = gdisc; grid_hit[py][px] = ghit
        if not ok: break

    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] ray-sphere intersection  {len(gates):,} gates  depth {depth}", flush=True)
    print(f"         EXHAUSTIVE: {checked:,} pixels, gate (disc,hit) == Python fixed-point reference, "
          f"byte-exact ({hits:,} hits)", flush=True)
    if not ok:
        print(f"         !!! FAIL detail px,py,x,y,gdisc,ref,ghit,rhit = {fail}", flush=True)
        return ok, len(gates), ""

    # ---- render the ASCII sphere from the VERIFIED gate discriminant ----
    # z = isqrt(disc) is the surface height; normal = (x,y,z)/R; Lambert against a fixed light.
    GLYPHS = " .:-=+*#%@"                                # dark -> bright
    lx, ly, lz = -1.0, -1.0, 1.6                         # light from upper-left, toward viewer
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    lines = []
    for py in range(NY):
        row = []
        for px in range(NX):
            if not grid_hit[py][px]:
                row.append(' ')
                continue
            x, y = coords(px, py)
            disc = grid_disc[py][px]
            z = math.isqrt(disc)                         # integer surface height from gate disc
            # normal (unit): (x, y, z)/R  (float only for glyph choice, not the fabricated path)
            nx, ny, nz = x / R, y / R, z / R
            bright = nx * lx + ny * ly + nz * lz
            if bright < 0: bright = 0.0
            idx = int(bright * (len(GLYPHS) - 1) + 0.5)
            if idx > len(GLYPHS) - 1: idx = len(GLYPHS) - 1
            row.append(GLYPHS[idx])
        lines.append("".join(row))
    render = "\n".join(lines)
    print("\n  --- ASCII sphere (shaded from the gate-verified discriminant) ---\n", flush=True)
    print(render, flush=True)
    return ok, len(gates), render

def main():
    print("\n  MUHLNICKEL RAYTRACE -- fixed-point ray-sphere intersection as gates, verified exhaustive/byte-exact\n", flush=True)
    t = time.time()
    ok, ng, render = verify_and_render()
    print(f"\n  === {'PASS' if ok else 'FAIL'} -- intersection test byte-exact over the full raster "
          f"| {ng:,} gates fabricated | ({time.time()-t:.2f}s) ===", flush=True)

if __name__ == "__main__":
    main()
