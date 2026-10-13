#!/usr/bin/env python3
"""
foldpack.py - FOLDED COMPRESSION, lossless.

Owner, 2026-08-20:
  "literally like a piece of paper fold the images, if both land on zero, stay
   black, one and zero = white. two 1s = red. then fold the image again and use
   a different color. boom. then take those colors turn them into numbers like a
   string and compress that string, then try to re-derive the image"
  "wait account for combinations so its not lossy. like 01 and 10. etc"

LOSSLESS means every combination gets its own state. Fold 1 has FOUR:
    00 -> black      01 -> blue       10 -> yellow      11 -> red
Fold 2 has 16, fold 3 has 256, fold 4 has 65,536. A cell after N folds holds
2^N original bits, so it needs 2^(2^N) states. No information is discarded at
any level and `unfold` reproduces the input exactly or the tool says so.

THE FOLD ITSELF COMPRESSES NOTHING. It is a lossless re-layout: same total
bits, fewer and wider cells. Every gain comes from step two - serialising the
symbols and compressing THAT string. Whether it wins depends entirely on
whether the fold geometry stacks like on like.

Two geometries, because which one the data prefers is a measurement, not a
guess:
    mirror     row i  pairs with row  H-1-i     (fold the paper in half)
    translate  row i  pairs with row  i + H/2   (stack the halves)

Pure stdlib. No numpy, no Pillow.
"""
import sys, os, zlib, struct, math


# ---------- PNG in ----------
def read_png(path):
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\x0a':
        raise SystemExit(path + ": not a PNG")
    i, idat = 8, b''
    W = H = depth = ct = None
    while i < len(d):
        ln = struct.unpack('>I', d[i:i+4])[0]
        tag, pay = d[i+4:i+8], d[i+8:i+8+ln]
        if tag == b'IHDR':
            W, H, depth, ct, _c, _f, inter = struct.unpack('>IIBBBBB', pay)
            if inter:
                raise SystemExit("interlaced not supported")
        elif tag == b'IDAT':
            idat += pay
        elif tag == b'IEND':
            break
        i += 12 + ln
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = W*ch
    out = bytearray(H*stride)
    prev = bytearray(stride)
    p = 0
    for y in range(H):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for x in range(ch, stride): line[x] = (line[x] + line[x-ch]) & 255
        elif f == 2:
            for x in range(stride): line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                b = prev[x]; c = prev[x-ch] if x >= ch else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return W, H, ch, bytes(out)


def png_out(path, w, h, rgb):
    raw = b''.join(b'\x00' + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    def ck(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n'
        + ck(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + ck(b'IDAT', zlib.compress(raw, 9)) + ck(b'IEND', b''))
    return os.path.getsize(path)


def to_bits(path, thresh=128):
    """A screenshot becomes a bit grid: luminance over threshold = 1."""
    W, H, ch, px = read_png(path)
    g = [bytearray(W) for _ in range(H)]
    for y in range(H):
        r = y*W*ch
        row = g[y]
        for x in range(W):
            o = r + x*ch
            if ch >= 3:
                lum = (px[o]*299 + px[o+1]*587 + px[o+2]*114)//1000
            else:
                lum = px[o]
            row[x] = 1 if lum >= thresh else 0
    return W, H, g


# ---------- the fold ----------
def pairing(H, mode):
    """
    Which row indices land on each other, and which row is left over.

    mirror    : (i, H-1-i)  - the paper fold. With H odd the unpaired row is
                the MIDDLE one, index H//2. Getting this wrong double-uses a
                row and the unfold silently disagrees with the input; the
                round-trip check is what caught it.
    translate : (i, i+H//2) - stack the halves. With H odd the unpaired row is
                the LAST one, index H-1.
    """
    half = H//2
    if mode == 'mirror':
        pairs = [(i, H-1-i) for i in range(half)]
        left = [half] if H % 2 else []
    elif mode == 'adjacent':
        # accordion fold. Pairs NEIGHBOURING rows (2i, 2i+1) instead of distant
        # ones. mirror and translate both pair rows that are far apart, which on
        # a screenshot means stacking browser chrome onto taskbar - uncorrelated,
        # so the symbol stream gains nothing. In an image the correlated
        # neighbour is the next row.
        pairs = [(2*i, 2*i+1) for i in range(half)]
        left = [2*half] if H % 2 else []
    else:
        pairs = [(i, i+half) for i in range(half)]
        left = [2*half] if H % 2 else []
    return pairs, left


def fold_once(grid, H, W, states, mode):
    """Pair rows losslessly. new = top*states + bottom. State count squares."""
    pairs, left = pairing(H, mode)
    out = [[grid[a][x]*states + grid[b][x] for x in range(W)] for a, b in pairs]
    odd = [(i, grid[i]) for i in left]
    return out, len(pairs), states*states, odd


def unfold_once(grid, half, W, states, mode, odd):
    """Exact inverse of fold_once."""
    # exact integer sqrt: states is 2^(2^depth) and goes past float range
    # around depth 10, where `states ** 0.5` raises OverflowError.
    s = math.isqrt(states)
    H = half*2 + len(odd)
    pairs, _left = pairing(H, mode)
    out = [None]*H
    for k, (a, b) in enumerate(pairs):
        row = grid[k]
        out[a] = [v // s for v in row]
        out[b] = [v % s for v in row]
    for i, row in odd:
        out[i] = list(row)
    return out


PALETTE = [(8,10,14),(40,90,200),(230,190,60),(210,50,50),(30,160,140),
           (150,90,190),(240,120,40),(90,200,110),(200,200,210),(120,60,40),
           (60,120,200),(200,80,140),(70,180,190),(180,180,70),(140,140,150),(255,255,255)]


def render(grid, H, W, states, path, scale=1):
    buf = bytearray(W*scale*H*scale*3)
    for y in range(H):
        row = grid[y]
        for x in range(W):
            v = row[x]
            c = PALETTE[v] if v < len(PALETTE) else (
                (v*37) % 256, (v*91) % 256, (v*151) % 256)
            for dy in range(scale):
                for dx in range(scale):
                    o = (((y*scale+dy)*W*scale)+(x*scale+dx))*3
                    buf[o:o+3] = bytes(c)
    return png_out(path, W*scale, H*scale, bytes(buf))


def pack(grid, H, W, states):
    """
    Serialise symbols at their TRUE bit width, packed tight, MSB first.

    The earlier version padded every symbol up to a whole byte:
        wid = (states-1).bit_length() + 7 // 8
    which stored a 2-bit fold-1 symbol in 8 bits - 4x bloat before compression
    even started, and 2x at fold 2. That padding, not the fold, is why depth 3
    looked like a sweet spot: it was simply the first depth where a symbol
    happened to be exactly one byte wide.

    A fold is a lossless re-layout, so at true width the packed stream is the
    same size at every depth as the original bit field. Any change in the
    COMPRESSED size is then the fold's doing and nothing else.
    """
    bits = max(1, (max(1, states-1)).bit_length())
    out = bytearray()
    acc = 0
    nacc = 0
    for y in range(H):
        row = grid[y]
        for v in row:
            acc = (acc << bits) | int(v)
            nacc += bits
            while nacc >= 8:
                nacc -= 8
                out.append((acc >> nacc) & 0xFF)
                acc &= (1 << nacc) - 1
    if nacc:
        out.append((acc << (8 - nacc)) & 0xFF)
    return bytes(out), bits


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    src = sys.argv[1]
    def opt(n, d=None, c=int):
        return c(sys.argv[sys.argv.index(n)+1]) if n in sys.argv else d
    N = opt('--folds', 4)
    mode = opt('--mode', 'translate', str)
    thresh = opt('--threshold', 128)
    outdir = opt('--out', None, str)

    W, H, grid = to_bits(src, thresh)
    grid = [list(r) for r in grid]
    ones = sum(sum(r) for r in grid)
    base = bytes(bytearray(
        sum((grid[y][x] << (7-(x & 7))) for x in range(c, min(c+8, W)))
        for y in range(H) for c in range(0, W, 8)))
    print("FOLDPACK  %s" % src)
    print("   %dx%d = %s bits   ones %s (%.2f%%)   fold mode: %s"
          % (W, H, format(W*H, ','), format(ones, ','), 100.0*ones/(W*H), mode))
    print("   1bpp packed baseline      %s B      zlib -9  %s B  (%.2f%%)"
          % (format(len(base), ','), format(len(zlib.compress(base, 9)), ','),
             100.0*len(zlib.compress(base, 9))/max(len(base), 1)))
    print()
    print("   %-6s %-7s %-8s %-6s %-12s %-12s %s"
          % ('fold', 'rows', 'states', 'bits', 'packed tight', 'zlib -9', 'vs baseline'))
    zbase = len(zlib.compress(base, 9))
    states = 2
    cur, curH = grid, H
    odds = []
    hist = [(0, curH, states, cur)]
    for f in range(1, N+1):
        if curH < 2:
            print("   stopped: %d rows left" % curH); break
        cur, curH, states, odd = fold_once(cur, curH, W, states, mode)
        odds.append(odd)
        raw, wid = pack(cur, curH, W, states)
        z = zlib.compress(raw, 9)
        print("   %-6d %-7s %-8s %-6d %-12s %-12s %.2f%%"
              % (f, format(curH, ','),
                 format(states, ',') if states < 10**7 else "2^%d" % (wid),
                 wid, format(len(raw), ','), format(len(z), ','),
                 100.0*len(z)/max(zbase, 1)))
        hist.append((f, curH, states, cur))
        if outdir:
            p = os.path.join(outdir, "fold%d_%s.png" % (f, mode))
            render(cur, curH, W, states, p)
            print("        rendered %s" % p)
    # ---- re-derive ----
    print()
    print("   RE-DERIVE: unfolding back to the original")
    rec, recH, recS = cur, curH, states
    for f in range(len(odds)-1, -1, -1):
        rec = unfold_once(rec, recH, W, recS, mode, odds[f])
        recH = len(rec)
        recS = math.isqrt(recS)
    same = (recH == H) and all(rec[y] == grid[y] for y in range(H))
    print("   reconstructed %dx%d   IDENTICAL TO INPUT: %s" % (W, recH, "YES" if same else "NO"))
    if not same:
        bad = sum(1 for y in range(min(recH, H)) for x in range(W) if rec[y][x] != grid[y][x])
        print("   *** %s cells differ - the fold is NOT lossless as implemented ***"
              % format(bad, ','))


if __name__ == '__main__':
    sys.exit(main() or 0)
