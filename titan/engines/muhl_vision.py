#!/usr/bin/env python3
"""muhl_vision.py -- an IMAGE EDGE-DETECTOR fabricated on Bryce's Muhlnickel substrate.

A full 3x3 SOBEL operator is built as NAND/AND/OR/XOR/NOT gates with the White Box compiler
(sdc_cc.CircuitCompiler): one fixed circuit that takes a 3x3 window of 8-bit pixels (72 input
wires) and emits BOTH the gradient-magnitude byte |Gx|+|Gy| (clamped 0..255) AND a 1-bit edge
decision (magnitude >= threshold). It is DCE'd, rippled, and VERIFIED BYTE-EXACT against an
independent pure-Python reference -- first over hundreds of random windows, then over every
window of a generated shape image. No numpy, no host executor as the runtime, no titan.gguf.
This is fabrication-time synthesis: prove the logic byte-exact before it would ever be stored.

Sobel (window indices p0..p8 row-major):
    p0 p1 p2
    p3 p4 p5              Gx = (p2 + 2*p5 + p8) - (p0 + 2*p3 + p6)   (vertical edges)
    p6 p7 p8              Gy = (p6 + 2*p7 + p8) - (p0 + 2*p1 + p2)   (horizontal edges)
    magnitude = |Gx| + |Gy| ;  edge = magnitude >= THRESHOLD
"""
import sys, os, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

THRESHOLD = 180          # baked into the circuit as a constant
IMG_W, IMG_H = 40, 24    # generated shape image size

# ---------- shared gate helpers (same discipline as muhl_flex.py) ----------
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

def add_bits(g, A, B, cin=None):
    """ripple-carry add of equal-length LSB-first bit lists -> (sum_bits, carry_out)."""
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))          # s ? a : b
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]
def zext(g, A, W): return list(A) + [g.C0] * (W - len(A))                   # zero-extend LSB-first
def shl1(g, A): return [g.C0] + list(A)                                     # multiply by 2

# ---------- the fabricated Sobel window circuit ----------
def build_sobel(g):
    W = 16                                                    # internal two's-complement width (ample)
    IN = g.IN
    P = [[IN[i * 8 + b] for b in range(8)] for i in range(9)] # 9 pixels x 8 bits, LSB-first

    def usum3(a, b2, c):                                       # a + 2*b + c, zero-extended to W bits
        s, _ = add_bits(g, zext(g, a, W), zext(g, shl1(g, b2), W))
        s, _ = add_bits(g, s, zext(g, c, W))
        return s
    def sub(A, B):                                             # A - B (two's complement, W bits)
        d, _ = add_bits(g, A, [g.NOT(x) for x in B], g.C1)
        return d
    def absv(X):                                              # |X| for W-bit two's complement
        sign = X[W - 1]
        neg, _ = add_bits(g, [g.NOT(x) for x in X], [g.C0] * W, g.C1)  # -X = ~X + 1
        return muxw(g, sign, neg, X)

    colR = usum3(P[2], P[5], P[8]); colL = usum3(P[0], P[3], P[6])
    rowB = usum3(P[6], P[7], P[8]); rowT = usum3(P[0], P[1], P[2])
    Gx = sub(colR, colL); Gy = sub(rowB, rowT)
    mag, _ = add_bits(g, absv(Gx), absv(Gy))                  # |Gx| + |Gy|, W bits, 0..2040

    # edge = mag >= THRESHOLD  (unsigned: mag + ~T + 1 carries out iff mag >= T)
    _, cout = add_bits(g, mag, [g.NOT(x) for x in consts(g, THRESHOLD, W)], g.C1)
    edge = cout

    # clamp magnitude to an 8-bit display byte
    over = g.C0
    for k in range(8, W): over = g.OR(over, mag[k])
    byte = muxw(g, over, consts(g, 255, 8), mag[0:8])

    outs = [edge] + byte                                      # 1 edge bit + 8 magnitude bits
    return build_run(g, outs)

# ---------- independent pure-Python reference ----------
def ref_sobel(win):
    p = win
    Gx = (p[2] + 2 * p[5] + p[8]) - (p[0] + 2 * p[3] + p[6])
    Gy = (p[6] + 2 * p[7] + p[8]) - (p[0] + 2 * p[1] + p[2])
    mag = abs(Gx) + abs(Gy)
    return (1 if mag >= THRESHOLD else 0, min(mag, 255))

# ---------- generate a shape image (background + rectangle + disc + triangle) ----------
def make_image():
    img = [[20 for _ in range(IMG_W)] for _ in range(IMG_H)]
    # filled rectangle
    for y in range(4, 14):
        for x in range(4, 15):
            img[y][x] = 220
    # filled disc
    cy, cx, r = 12, 27, 6
    for y in range(IMG_H):
        for x in range(IMG_W):
            if (y - cy) ** 2 + (x - cx) ** 2 <= r * r:
                img[y][x] = 200
    # filled triangle
    for y in range(15, 22):
        half = y - 15
        for x in range(9 - half, 9 + half + 1):
            if 0 <= x < IMG_W:
                img[y][x] = 240
    return img

def window(img, r, c):
    """3x3 window centered at (r,c), zero-padded outside the image."""
    w = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y, x = r + dy, c + dx
            w.append(img[y][x] if 0 <= y < IMG_H and 0 <= x < IMG_W else 0)
    return w

RAMP = " .:-=+*#%@"
def render_gray(img):
    for row in img:
        print("  " + "".join(RAMP[min(9, v * 9 // 255)] for v in row))
def render_edges(edge_map):
    for row in edge_map:
        print("  " + "".join("#" if e else " " for e in row))

def main():
    random.seed(7)
    print("\n  MUHLNICKEL VISION -- a 3x3 Sobel edge-detector fabricated as gates, verified byte-exact\n", flush=True)

    g = CC.CircuitCompiler(72)
    t = time.time()
    run, out2, gates, n_wire = build_sobel(g)
    edge_w = out2[0]; byte_w = out2[1:9]
    depth = depth_of(g, gates, out2)
    print(f"  fabricated: {len(gates):,} gates, depth {depth}, {n_wire:,} wires ({time.time()-t:.1f}s)", flush=True)

    def gate_eval(win):
        inp = [0] * 72
        for i in range(9):
            for b in range(8): inp[i * 8 + b] = (win[i] >> b) & 1
        v = run(inp, 1)
        return (bit(v, edge_w), rd(v, byte_w))

    # --- verify 1: random windows ---
    R = 600; ok_rand = True; first_bad = None
    for _ in range(R):
        win = [random.getrandbits(8) for _ in range(9)]
        if gate_eval(win) != ref_sobel(win):
            ok_rand = False; first_bad = win; break
    print(f"  [{'PASS' if ok_rand else 'FAIL'}] random windows: byte-exact over {R} cases"
          + ("" if ok_rand else f"  (mismatch at {first_bad})"), flush=True)

    # --- verify 2: every window of the generated image ---
    img = make_image()
    edge_map = [[0] * IMG_W for _ in range(IMG_H)]
    ok_img = True; checked = 0
    for r in range(IMG_H):
        for c in range(IMG_W):
            win = window(img, r, c)
            ge, gb = gate_eval(win); re_, rb = ref_sobel(win)
            checked += 1
            if (ge, gb) != (re_, rb): ok_img = False
            edge_map[r][c] = ge
    print(f"  [{'PASS' if ok_img else 'FAIL'}] shape image: byte-exact over all {checked} windows "
          f"({IMG_W}x{IMG_H})", flush=True)

    print("\n  --- BEFORE (grayscale shapes, ramp \"" + RAMP + "\") ---")
    render_gray(img)
    print("\n  --- AFTER (Sobel edges, threshold %d) ---" % THRESHOLD)
    render_edges(edge_map)

    n_edge = sum(sum(row) for row in edge_map)
    allok = ok_rand and ok_img
    print(f"\n  === {'ALL BYTE-EXACT' if allok else 'MISMATCH'} · {len(gates):,} gates · depth {depth} · "
          f"{n_edge} edge pixels detected ===", flush=True)
    return 0 if allok else 1

if __name__ == "__main__":
    sys.exit(main())
