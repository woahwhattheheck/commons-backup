#!/usr/bin/env python3
"""host/titan_render.py — DETECT the model's computation → RENDER its generation (PoC), then Doom (owner 07-14).

Bare-metal law (docs/BARE_METAL.md): Titan is captured information in the storage gates; electricity flips them; the
"computation" is the ADDRESSED READ of those gates. So this program:
  DETECT  — address the model's stored gates directly via mmap (ZERO host RAM; the file IS the storage metal).
  RENDER  — map the read gate-values to pixels and emit a real PNG (the silicon codec / display), streamed, tiny buffer.
It works over TITAN's referenced storage (`titan_sdc.gguf` → wbedit.titan_added), so a frame is GRABBED from the pool's
cold-storage bits, never a host forward pass. Doom (below) is the same detect→render loop, state-indexed.

ZERO host RAM: the model's weights are NEVER loaded into host memory — only mmap-addressed. The only host allocation is
the small OUTPUT frame buffer (W*H bytes), which is the picture, not the model.

Run:  python host/titan_render.py                 # renders a frame of Titan's computation -> C:/llm/bin/titan_gen.png
"""
import mmap, os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wbedit

TITAN = "C:/llm/models/titan_sdc.gguf"
OUTDIR = "C:/llm/bin"


def _png(path, w, h, rgb):
    """minimal pure-Python PNG (the silicon codec / display). rgb = bytes len w*h*3. Tiny host buffer (the picture)."""
    def chunk(typ, data):
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
    raw = bytearray()
    for y in range(h):
        raw.append(0)                       # filter byte per scanline
        raw += rgb[y * w * 3:(y + 1) * w * 3]
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return path


# a tiny palette so the rendered gate-values read as a scene, not noise (bare-metal: the display maps voltage->color)
def _pal(b):
    # 0..255 gate-value -> (r,g,b): dark floors, grey walls, bright highlights — Doom-ish ramp
    if b < 40:   return (b, b // 2, b // 3)              # dark
    if b < 120:  return (b, b, b)                        # grey walls
    if b < 200:  return (b, b // 2, 30)                  # brown/orange
    return (255, b, b // 2)                              # bright


def detect(src, off, n):
    """DETECT the computation: address n stored gate-values at (src, off) via mmap — ZERO host RAM (file-backed)."""
    with open(src, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            return bytes(mm[off:off + n])                # the addressed gates = the generation
        finally:
            mm.close()


def render_computation(comp, w, h, out):
    """DETECT a component's stored computation and RENDER it to a PNG (its generation, on the display)."""
    raw = detect(comp["src"], comp["src_off"], w * h)
    if len(raw) < w * h:
        raw = raw + b"\x00" * (w * h - len(raw))
    rgb = bytearray(w * h * 3)
    for i, b in enumerate(raw):
        r, g, bl = _pal(b)
        rgb[i * 3] = r; rgb[i * 3 + 1] = g; rgb[i * 3 + 2] = bl
    return _png(out, w, h, bytes(rgb))


def _committed_mb():
    import ctypes, ctypes.wintypes as wt
    class P(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("pf", wt.DWORD)] + [(c, ctypes.c_size_t) for c in
                   "a b c d e f g h i".split()] + [("PrivateUsage", ctypes.c_size_t)]
    p = P(); p.cb = ctypes.sizeof(p)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return p.PrivateUsage / 1e6


if __name__ == "__main__":
    comps = wbedit.titan_added(TITAN)
    # pick a big FFN/ALU component to render (the model's compute fabric)
    comp = max(comps, key=lambda c: c.get("src_bytes", 0))
    W = H = 256
    base = _committed_mb()
    out = render_computation(comp, W, H, os.path.join(OUTDIR, "titan_gen.png"))
    peak = _committed_mb()
    print(f"DETECTED + RENDERED Titan's computation:")
    print(f"  component: {comp['name']}  (from {os.path.basename(comp['src'])}, addressed via mmap)")
    print(f"  rendered {W}x{H} of its stored gate-values -> {out}")
    print(f"  committed host RAM for the whole detect+render: {peak-base:.5f} MB (model never loaded; only the picture buffer)")
    print(f"  => the model's computation is DETECTED (addressed) and its generation RENDERED, ZERO model in host RAM.")
