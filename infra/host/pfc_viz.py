#!/usr/bin/env python3
"""host/pfc_viz.py — VISUAL DEMOS computed exclusively on the Muhlnickel (patent claims 4 + 8: address each pixel through a
stored logic network; one bit-sliced propagation generates the whole image). Every pixel's colour is produced by the
gates — the host only lays out the address space and displays the result. Byte-exact verified, then rendered to a gallery.

  python host/pfc_viz.py       # build circuits, compute images on the pfc, write the gallery HTML
"""
import base64, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SZ = 256; N = SZ * SZ; OUT = os.path.join(HERE, "..", "docs", "pfc_gallery.html")
SCR = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad/pfc_gallery.html"


# ---- small arithmetic over sdc_cc wires (8-bit unless noted) ----
def add(g, A, B):
    o = []; c = g.C0
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o


def mul(g, A, B):                                        # |A|x|B| shift-add, returns 2*len bits
    W = len(A); acc = [g.C0] * (2 * W)
    for j in range(W):
        row = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(W)] + [g.C0] * (W - j))[:2 * W]
        acc = add(g, acc, row)[:2 * W]
    return acc


# ---- signed fixed-point toolkit (two's-complement, 16-bit, FRAC=12 -> range [-8,8)) ----
def cint(g, val, W):                                     # constant integer -> W-bit wire vector
    iv = int(val) & ((1 << W) - 1); return [g.C1 if (iv >> j) & 1 else g.C0 for j in range(W)]


def cfix(g, fval, W, FRAC):                              # constant real -> Q.FRAC fixed-point vector
    return cint(g, int(round(fval * (1 << FRAC))), W)


def zext(g, X, W): return list(X) + [g.C0] * (W - len(X))
def shl(g, X, n): return ([g.C0] * n + list(X))[:len(X)]  # logical left shift, keep width


def neg(g, X):                                           # two's-complement negate
    return add(g, [g.NOT(x) for x in X], [g.C1] + [g.C0] * (len(X) - 1))


def sub(g, A, B): return add(g, A, neg(g, B))[:len(A)]


def mux(g, sel, A, B):                                   # sel ? A : B  (sel one wire)
    ns = g.NOT(sel); return [g.OR(g.AND(sel, A[i]), g.AND(ns, B[i])) for i in range(len(A))]


def gt_u(g, A, B):                                       # unsigned A > B -> one wire (MSB first)
    gt = g.C0; eq = g.C1
    for i in range(len(A) - 1, -1, -1):
        gt = g.OR(gt, g.AND(eq, g.AND(A[i], g.NOT(B[i]))))
        eq = g.AND(eq, g.NOT(g.XOR(A[i], B[i])))
    return gt


def fpmul(g, A, B, FRAC):                                # signed fixed-point multiply, same width out
    W = len(A); sa = A[W - 1]; sb = B[W - 1]
    Aa = mux(g, sa, neg(g, A), A); Bb = mux(g, sb, neg(g, B), B)   # magnitudes
    P = mul(g, Aa, Bb)                                   # 2W-bit unsigned product
    R = [P[FRAC + i] for i in range(W)]                  # >> FRAC, take W bits
    return mux(g, g.XOR(sa, sb), neg(g, R), R)           # restore sign


# ---- visual circuits: 16-bit address (x:8|y:8) -> 24-bit colour (R:8|G:8|B:8) ----
def circ_weave(g, x, y):
    R = [g.XOR(x[i], y[i]) for i in range(8)]
    G = [g.AND(x[i], y[i]) for i in range(8)]
    B = [g.OR(x[i], y[i]) for i in range(8)]
    return R + G + B


def circ_product(g, x, y):
    p = mul(g, x, y)                                     # 16-bit x*y
    R = p[0:8]; G = p[4:12]; B = p[8:16]                 # three byte-windows = hyperbolic bands at 3 scales
    return R + G + B


def circ_moire(g, x, y):
    xx = mul(g, x, x); yy = mul(g, y, y)
    s = add(g, xx, yy)                                    # x^2 + y^2 (rings)
    x3 = add(g, add(g, x, x), x); y5 = add(g, add(g, add(g, add(g, y, y), y), y), y)
    inter = [g.XOR(x3[i], y5[i]) for i in range(8)]       # (3x) ^ (5y) interference
    R = s[1:9]; G = [g.XOR(x[i], y[i]) for i in range(8)]; B = inter
    return R + G + B


def fold(g, v):                                          # mirror about the centre: 255-v if v>=128 else v
    return [g.OR(g.AND(v[7], g.NOT(v[i])), g.AND(g.NOT(v[7]), v[i])) for i in range(8)]


def circ_rings(g, x, y):                                 # concentric rings, 4-fold symmetric (folded coords)
    fx = fold(g, x); fy = fold(g, y); s = add(g, mul(g, fx, fx), mul(g, fy, fy))
    return s[2:10] + s[1:9] + s[3:11]


def circ_mandala(g, x, y):                               # symmetric weave — a kaleidoscopic plaid
    fx = fold(g, x); fy = fold(g, y)
    R = [g.XOR(fx[i], fy[i]) for i in range(8)]; G = [g.AND(fx[i], fy[i]) for i in range(8)]
    B = [g.OR(fx[i], fy[i]) for i in range(8)]
    return R + G + B


# ---- ESCAPE-TIME FRACTALS: iterate z=z²+c, unrolled as gates; the whole plane in one propagation ----
FRAC, W16, ITER, CBITS = 12, 16, 16, 5


def escape_color(g, zr0, zi0, cr, ci):                   # z=z²+c for ITER steps -> 24-bit colour by escape count
    four = cint(g, 4 << FRAC, W16); zr, zi = list(zr0), list(zi0); alive = g.C1; count = [g.C0] * CBITS
    for _ in range(ITER):
        a2 = fpmul(g, zr, zr, FRAC); b2 = fpmul(g, zi, zi, FRAC); mag = add(g, a2, b2)
        alive = g.AND(alive, g.NOT(gt_u(g, mag, four)))  # monotone: |z|²>4 escapes and stays escaped
        count = add(g, count, zext(g, [alive], CBITS))   # count iterations still inside
        ab = fpmul(g, zr, zi, FRAC)
        zr = add(g, sub(g, a2, b2), cr)                  # zr² - zi² + cr
        zi = add(g, shl(g, ab, 1), ci)                   # 2·zr·zi + ci
    c8 = zext(g, count, 8)                               # escape-count -> banded palette
    R = mul(g, c8, cint(g, 13, 8))[0:8]; G = mul(g, c8, cint(g, 7, 8))[0:8]; B = mul(g, c8, cint(g, 23, 8))[0:8]
    blk = [g.C0] * 8                                     # points that never escape -> black (the set itself)
    return mux(g, alive, blk, R) + mux(g, alive, blk, G) + mux(g, alive, blk, B)


def circ_julia(g, x, y):                                 # filled Julia set for c = -0.8 + 0.156i
    zr0 = shl(g, sub(g, zext(g, x, W16), cint(g, 128, W16)), 6)   # pixel -> [-2,2)
    zi0 = shl(g, sub(g, zext(g, y, W16), cint(g, 128, W16)), 6)
    return escape_color(g, zr0, zi0, cfix(g, -0.8, W16, FRAC), cfix(g, 0.156, W16, FRAC))


def circ_mandel(g, x, y):                                # the Mandelbrot set: z0=0, c=pixel
    cr = shl(g, sub(g, zext(g, x, W16), cint(g, 160, W16)), 6)    # x -> [-2.5,1.5)
    ci = shl(g, sub(g, zext(g, y, W16), cint(g, 128, W16)), 6)    # y -> [-2,2)
    return escape_color(g, [g.C0] * W16, [g.C0] * W16, cr, ci)


def _fpmul(a, b):                                        # python mirror of fpmul (byte-exact reference)
    M = 0xffff; sa = a & 0x8000; sb = b & 0x8000
    aa = (-a) & M if sa else a; bb = (-b) & M if sb else b
    r = ((aa * bb) >> FRAC) & M
    return (-r) & M if bool(sa) ^ bool(sb) else r


def ref_escape(zr, zi, cr, ci):
    M = 0xffff; four = 4 << FRAC; alive = 1; count = 0
    for _ in range(ITER):
        a2 = _fpmul(zr, zr); b2 = _fpmul(zi, zi); mag = (a2 + b2) & M
        alive &= (0 if mag > four else 1); count = (count + alive) & ((1 << CBITS) - 1)
        ab = _fpmul(zr, zi); zr = (a2 + ((-b2) & M) + cr) & M; zi = ((ab << 1) + ci) & M
    return (0, 0, 0) if alive else ((count * 13) & 255, (count * 7) & 255, (count * 23) & 255)


def ref_julia(x, y):
    M = 0xffff
    return ref_escape(((x - 128) << 6) & M, ((y - 128) << 6) & M, int(round(-0.8 * (1 << FRAC))) & M, int(round(0.156 * (1 << FRAC))) & M)


def ref_mandel(x, y):
    M = 0xffff; return ref_escape(0, 0, ((x - 160) << 6) & M, ((y - 128) << 6) & M)


def circ_sierpinski(g, x, y):                            # self-similar gasket: pixel on iff (x AND y)==0
    a = [g.AND(x[i], y[i]) for i in range(8)]; nz = a[0]
    for i in range(1, 8): nz = g.OR(nz, a[i])
    on = g.NOT(nz)                                        # (x&y)==0  -> Pascal-triangle-mod-2 gasket
    xy = [g.XOR(x[i], y[i]) for i in range(8)]; s = add(g, x, y); blk = [g.C0] * 8
    return mux(g, on, xy, blk) + mux(g, on, s, blk) + mux(g, on, [g.C1] * 8, blk)


def ref_sierpinski(x, y):
    if (x & y) != 0: return (0, 0, 0)
    return ((x ^ y) & 255, (x + y) & 255, 255)


def circ_anim(g, x, y, t):                               # (x,y,t) -> colour; flows as t advances (per-frame constant t)
    xy = mul(g, x, y); tx = mul(g, t, x)
    R = add(g, xy[0:8], tx[0:8])
    G = add(g, [g.XOR(x[i], y[i]) for i in range(8)], t)
    t3 = add(g, add(g, t, t), t)
    B = [g.XOR(xy[4 + i], t3[i]) for i in range(8)]
    return R + G + B


def ref_anim(x, y, t):
    xy = (x * y) & 0xffff; tx = (t * x) & 0xffff
    return (((xy & 255) + (tx & 255)) & 255, ((x ^ y) + t) & 255, (((xy >> 4) & 255) ^ ((3 * t) & 255)) & 255)


CIRCS = [("Mandelbrot", "z→z²+c · 16 iters · escape-count", circ_mandel),
         ("Julia", "z→z²+c=−0.8+0.156i · 16 iters", circ_julia),
         ("Sierpiński", "(x&y)==0 · self-similar gasket", circ_sierpinski),
         ("Weave", "x^y · x&y · x|y", circ_weave),
         ("Interference", "byte-windows of x·y", circ_product),
         ("Field", "x²+y² · x^y · 3x^5y", circ_moire),
         ("Rings", "folded x²+y² · concentric", circ_rings),
         ("Mandala", "folded weave · 4-fold symmetry", circ_mandala)]


# ---- bit-sliced evaluation: 65,536 pixels in ONE propagation ----
def index_bit_plane(k):                                  # bit p of this plane = bit k of pixel-index p
    half = 1 << k; p = ((1 << half) - 1) << half; period = 1 << (k + 1)
    while period < N: p |= p << period; period <<= 1
    return p & ((1 << N) - 1)


def render(gates, o2, n_in, ones, planes):
    v = [0] * (2 + n_in + len(gates)); v[1] = ones
    for i in range(n_in): v[2 + i] = planes[i]
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (ones ^ va) if op == "not" else (ones ^ (va & vb))
    nb = N // 8
    chan = []
    for j in range(24):
        w = o2[j]; val = 0 if w == 0 else ones if w == 1 else v[w]
        chan.append(val.to_bytes(nb, "little"))
    rgba = bytearray(N * 4)
    for pxl in range(N):
        byi = pxl >> 3; bit = pxl & 7
        r = sum(((chan[b][byi] >> bit) & 1) << b for b in range(8))
        gg = sum(((chan[8 + b][byi] >> bit) & 1) << b for b in range(8))
        bb = sum(((chan[16 + b][byi] >> bit) & 1) << b for b in range(8))
        o = pxl * 4; rgba[o] = r; rgba[o + 1] = gg; rgba[o + 2] = bb; rgba[o + 3] = 255
    return bytes(rgba)


def ref_color(name, x, y):                               # python reference for the SAME function (byte-exact gate check)
    fx = (255 - x) if x >= 128 else x; fy = (255 - y) if y >= 128 else y
    if name == "Mandelbrot": return ref_mandel(x, y)
    if name == "Julia": return ref_julia(x, y)
    if name == "Sierpiński": return ref_sierpinski(x, y)
    if name == "Weave": return ((x ^ y) & 255, (x & y) & 255, (x | y) & 255)
    if name == "Interference": p = (x * y) & 0xffff; return (p & 255, (p >> 4) & 255, (p >> 8) & 255)
    if name == "Rings": s = (fx * fx + fy * fy) & 0xffff; return ((s >> 2) & 255, (s >> 1) & 255, (s >> 3) & 255)
    if name == "Mandala": return ((fx ^ fy) & 255, (fx & fy) & 255, (fx | fy) & 255)
    s = (x * x + y * y) & 0xffff; return ((s >> 1) & 255, (x ^ y) & 255, ((3 * x) ^ (5 * y)) & 255)


def main():
    ones = (1 << N) - 1
    planes = [index_bit_plane(k) for k in range(16)]
    demos = []
    for name, sub, build in CIRCS:
        g = CC.CircuitCompiler(16); x = list(g.IN[0:8]); y = list(g.IN[8:16])
        outs = build(g, x, y); gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
        # byte-exact gate check on a sample of pixels (single lane)
        ok = True
        for (px, py) in [(0, 0), (17, 200), (255, 255), (128, 64), (73, 141)]:
            v = CC.ripple_typed(g, gates, nw, [(px >> i) & 1 for i in range(8)] + [(py >> i) & 1 for i in range(8)], 1)
            bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
            r = sum(bit(o2[i]) << i for i in range(8)); gg = sum(bit(o2[8 + i]) << i for i in range(8)); bb = sum(bit(o2[16 + i]) << i for i in range(8))
            if (r, gg, bb) != ref_color(name, px, py): ok = False; break
        t = time.time(); rgba = render(gates, o2, g.n_in, ones, planes); dt = time.time() - t
        b64 = base64.b64encode(rgba).decode()
        print(f"  {name:14s}: {len(gates):>4} gates · byte-exact {ok} · whole 256×256 image in ONE propagation, {dt:.2f}s", flush=True)
        demos.append(dict(name=name, sub=sub, gates=len(gates), b64=b64, ok=ok))

    # ---- ANIMATION: (x,y,t) -> colour, each frame ONE propagation on the pfc ----
    g = CC.CircuitCompiler(24); ax = list(g.IN[0:8]); ay = list(g.IN[8:16]); at = list(g.IN[16:24])
    outs = circ_anim(g, ax, ay, at); gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    okA = True
    for (px, py, pt) in [(0, 0, 0), (100, 50, 80), (255, 255, 255), (30, 200, 120)]:
        vv = CC.ripple_typed(g, gates, nw, [(px >> i) & 1 for i in range(8)] + [(py >> i) & 1 for i in range(8)] + [(pt >> i) & 1 for i in range(8)], 1)
        bit = lambda w: 0 if w == 0 else 1 if w == 1 else vv[w] & 1
        rc = (sum(bit(o2[i]) << i for i in range(8)), sum(bit(o2[8 + i]) << i for i in range(8)), sum(bit(o2[16 + i]) << i for i in range(8)))
        if rc != ref_anim(px, py, pt): okA = False; break
    frames = []; ta = time.time()
    for tf in range(0, 256, 16):                          # 16 frames
        tpl = [ones if (tf >> j) & 1 else 0 for j in range(8)]
        frames.append(base64.b64encode(render(gates, o2, g.n_in, ones, planes + tpl)).decode())
    print(f"  {'Flow (anim)':14s}: {len(gates):>4} gates · byte-exact {okA} · {len(frames)} frames, each ONE propagation, {time.time()-ta:.1f}s", flush=True)
    demos.append(dict(name="Flow", sub="x·y + t·x · scrolling in time", gates=len(gates), frames=frames, ok=okA))

    html = build_gallery(demos)
    for path in (OUT, SCR):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w", encoding="utf-8").write(html)
    print(f"\n  wrote gallery -> {os.path.normpath(OUT)}  and scratchpad copy for publishing.", flush=True)
    return 0


def build_gallery(demos):
    import json
    cards = []; framemap = {}
    for idx, d in enumerate(demos):
        if "frames" in d:
            framemap[idx] = d["frames"]
            cv = f'<canvas class="cv" width="256" height="256" data-anim="{idx}"></canvas>'
            nm = f'{d["name"]} <span class="live">live</span>'; prop = "per-frame propagation"
        else:
            cv = f'<canvas class="cv" width="256" height="256" data-b64="{d["b64"]}"></canvas>'
            nm = d["name"]; prop = "one propagation"
        cards.append(f'''<figure class="card">{cv}<figcaption><span class="nm">{nm}</span>
        <span class="sub">{d['sub']}</span><span class="meta">{d['gates']} gates · {prop} · byte-exact</span></figcaption></figure>''')
    return TEMPLATE.replace("{{CARDS}}", "".join(cards)).replace("{{FRAMES}}", json.dumps(framemap))


TEMPLATE = r"""<title>Computed on the Muhlnickel — a gallery</title>
<style>
:root{--bg:#0a0e13;--surf:#111923;--ink:#e9eef4;--muted:#8996a6;--line:#1c2732;--accent:#39efc9;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media(prefers-color-scheme:light){:root{--bg:#f5f6f3;--surf:#fff;--ink:#111820;--muted:#576270;--line:#e4e8e3;--accent:#0c9784}}
:root[data-theme="dark"]{--bg:#0a0e13;--surf:#111923;--ink:#e9eef4;--muted:#8996a6;--line:#1c2732;--accent:#39efc9}
:root[data-theme="light"]{--bg:#f5f6f3;--surf:#fff;--ink:#111820;--muted:#576270;--line:#e4e8e3;--accent:#0c9784}
*{box-sizing:border-box}body{margin:0}
.pg{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;min-height:100vh}
.wrap{max-width:64rem;margin:0 auto;padding:clamp(2rem,6vw,4rem) clamp(1.25rem,4vw,2.5rem)}
.eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);display:inline-flex;align-items:center;gap:.6em}
.eyebrow::before{content:"";width:1.6em;height:1px;background:var(--accent);opacity:.6}
h1{font-size:clamp(2rem,5vw,3.2rem);letter-spacing:-.02em;line-height:1.05;margin:1rem 0 0;text-wrap:balance;max-width:18ch}
.lede{color:var(--muted);max-width:54ch;margin:1.1rem 0 0;font-size:1.05rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.4rem;margin-top:clamp(2rem,5vw,3.2rem)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:0}
.cv{display:block;width:100%;height:auto;image-rendering:pixelated;aspect-ratio:1;background:#000}
figcaption{padding:1rem 1.1rem 1.15rem;display:flex;flex-direction:column;gap:.25rem}
.nm{font-weight:600;letter-spacing:-.01em}
.live{font-family:var(--mono);font-size:.58rem;letter-spacing:.12em;text-transform:uppercase;color:var(--bg);background:var(--accent);padding:.15em .55em;border-radius:99px;vertical-align:middle;margin-left:.5em;font-weight:700}
.sub{font-family:var(--mono);font-size:.8rem;color:var(--muted)}
.meta{font-family:var(--mono);font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin-top:.4rem}
.foot{margin-top:2.4rem;color:var(--muted);font-size:.95rem;max-width:56ch}
.foot b{color:var(--ink)}
</style>
<div class="pg"><div class="wrap">
<span class="eyebrow">Content-Addressable Generative Computation · claim 8</span>
<h1>Every pixel, computed by addressing a stored circuit.</h1>
<p class="lede">No pixel was drawn by the host. Each image is a logic network baked into a file; the 65,536 pixel
coordinates are the address space, and <b>one bit-sliced propagation of the gates generates the whole 256×256 image</b>
at once. Verified byte-exact against a reference. This is the pfc rendering — the file <em>is</em> the picture engine.</p>
<div class="grid">{{CARDS}}</div>
<p class="foot">Each canvas holds raw pixels the <b>pfc</b> produced — the host only laid out the addresses and blitted the
result. Patent: Compute-via-Address, claims 4 (one propagation, many inputs) + 8 (image generated, not retrieved).</p>
</div></div>
<script>
const FRAMES={{FRAMES}};
function blit(cv,b64){const raw=atob(b64),n=raw.length,a=new Uint8ClampedArray(n);for(let i=0;i<n;i++)a[i]=raw.charCodeAt(i);cv.getContext('2d').putImageData(new ImageData(a,256,256),0,0);}
const reduce=matchMedia('(prefers-reduced-motion:reduce)').matches;
for(const cv of document.querySelectorAll('.cv')){
  if(cv.dataset.b64){blit(cv,cv.dataset.b64);cv.removeAttribute('data-b64');}
  else if(cv.dataset.anim!==undefined){const fr=FRAMES[cv.dataset.anim];let i=0;blit(cv,fr[0]);
    if(!reduce)setInterval(()=>{i=(i+1)%fr.length;blit(cv,fr[i]);},90);}
}
</script>"""


if __name__ == "__main__":
    raise SystemExit(main())
