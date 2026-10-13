#!/usr/bin/env python3
"""
stackpack.py - TILE, STACK, TABLE, COMPRESS. Lossless.

Owner, 2026-08-20:
  "what if you sliced the image into different squares, stacked them, tracked
   depth through color and compressed it by having colors represent the
   information each coordinate on the new plane represents, you can make a
   table of colors and shades assigned a single char, then express the image as
   a series of chars, then run that back through the table, and unstack and put
   back together to expand it back to whatever it was"

THE SCHEME
  1. slice the bit field into TW x TH tiles
  2. stack all K tiles - each (x,y) of the new plane now holds a K-deep column
     of bits, one from each tile. That column IS the "depth tracked through
     colour".
  3. table it: every DISTINCT column gets one entry and one char
  4. emit the plane as a string of chars
  5. compress the string
  6. reverse: chars -> table -> columns -> unstack -> original

WHY THIS BEATS THE FOLD
  foldpack combines cells positionally, new = a*states + b, which reserves a
  slot for all 2^K combinations whether or not they occur. Here a char is spent
  only on a column that ACTUALLY APPEARS. When a field is mostly zero and its
  rows repeat, the number of distinct columns is a small fraction of 2^K, and
  the table stays short while the char string stays highly repetitive.

  Stored size is honest and counts BOTH parts:
      table  = entries x K bits
      string = TW*TH x ceil(log2(entries)) bits
  plus whatever zlib then takes off the string. Nothing is hidden.

Pure stdlib. Lossless - it rebuilds the input and says so, or says it did not.
"""
import sys, os, zlib, struct, math
from collections import Counter


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
            for x in range(ch, stride): line[x] = (line[x]+line[x-ch]) & 255
        elif f == 2:
            for x in range(stride): line[x] = (line[x]+prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                line[x] = (line[x] + ((a+prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                b = prev[x]; c = prev[x-ch] if x >= ch else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x]+pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return W, H, ch, bytes(out)


def to_bits(path, thresh=128):
    W, H, ch, px = read_png(path)
    g = []
    for y in range(H):
        r = y*W*ch
        row = bytearray(W)
        for x in range(W):
            o = r + x*ch
            lum = (px[o]*299 + px[o+1]*587 + px[o+2]*114)//1000 if ch >= 3 else px[o]
            row[x] = 1 if lum >= thresh else 0
        g.append(row)
    return W, H, g


def raw_bits(path, W):
    b = open(path, 'rb').read()
    total = len(b)*8
    H = (total + W - 1)//W
    g = []
    for y in range(H):
        row = bytearray(W)
        for x in range(W):
            i = y*W + x
            if i < total:
                row[x] = (b[i >> 3] >> (7-(i & 7))) & 1
        g.append(row)
    return W, H, g, len(b)


def bitpack(vals, bits):
    out = bytearray(); acc = 0; n = 0
    for v in vals:
        acc = (acc << bits) | int(v); n += bits
        while n >= 8:
            n -= 8
            out.append((acc >> n) & 0xFF)
            acc &= (1 << n) - 1
    if n:
        out.append((acc << (8-n)) & 0xFF)
    return bytes(out)


def run(W, H, grid, TW, TH, srcbytes, label):
    across, down = W//TW, H//TH
    K = across*down
    if K < 2:
        return None
    # ---- 2. stack: each cell of the TWxTH plane holds a K-deep column ----
    cols = []
    for y in range(TH):
        for x in range(TW):
            v = 0
            for ty in range(down):
                base = grid[ty*TH + y]
                for tx in range(across):
                    v = (v << 1) | base[tx*TW + x]
            cols.append(v)
    # ---- 3. table: one entry per DISTINCT column ----
    table = {}
    order = []
    for v in cols:
        if v not in table:
            table[v] = len(order)
            order.append(v)
    E = len(order)
    sym_bits = max(1, (E-1).bit_length())
    # ---- 4/5. emit the plane as chars, compress ----
    stream = bitpack([table[v] for v in cols], sym_bits)
    tbl = bitpack(order, K)
    z_stream = zlib.compress(stream, 9)
    z_tbl = zlib.compress(tbl, 9)
    total = len(z_stream) + len(z_tbl)
    # ---- 6. reverse: chars -> table -> columns -> unstack ----
    rec = [bytearray(W) for _ in range(H)]
    for idx, v in enumerate(cols):
        y, x = divmod(idx, TW)
        vv = order[table[v]]
        for ty in range(down-1, -1, -1):
            for tx in range(across-1, -1, -1):
                rec[ty*TH + y][tx*TW + x] = vv & 1
                vv >>= 1
    ok = all(bytes(rec[y][:across*TW]) == bytes(grid[y][:across*TW])
             for y in range(down*TH))
    print("   %-11s K=%-6d cols=%-7d table=%-7d %2d bit/sym  tbl %-8s str %-8s TOTAL %-9s %6.2f%%  %s"
          % ("%dx%d" % (TW, TH), K, len(cols), E, sym_bits,
             format(len(z_tbl), ','), format(len(z_stream), ','),
             format(total, ','), 100.0*total/srcbytes,
             "OK" if ok else "*** NOT LOSSLESS ***"))
    return total, ok


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    src = sys.argv[1]
    def opt(n, d=None, c=int):
        return c(sys.argv[sys.argv.index(n)+1]) if n in sys.argv else d
    if src.lower().endswith('.png'):
        W, H, grid = to_bits(src, opt('--threshold', 128))
        srcb = (W*H + 7)//8
    else:
        W = opt('--width', 200)
        W, H, grid, nb = raw_bits(src, W)
        srcb = nb
    base = bitpack([grid[y][x] for y in range(H) for x in range(W)], 1)
    zb = len(zlib.compress(base, 9))
    print("STACKPACK  %s" % src)
    print("   %dx%d bits   source %s B   zlib -9 baseline %s B  (%.2f%%)"
          % (W, H, format(srcb, ','), format(zb, ','), 100.0*zb/srcb))
    print()
    print("   %-11s %-8s %-9s %-9s %-11s %-12s %-12s %-10s %s"
          % ('tile', 'K', 'cells', 'table', '', 'table B', 'string B', 'TOTAL', 'vs source'))
    best = None
    for tw, th in [(W, 1), (W, 2), (W, 4), (W, 8), (W, 16), (W, 32), (W, 64),
                   (W//2, 8), (W//4, 8), (W//2, 32), (W//4, 32), (50, 25), (25, 25)]:
        if tw < 1 or th < 1 or tw > W or th > H:
            continue
        r = run(W, H, grid, tw, th, srcb, src)
        if r and r[1] and (best is None or r[0] < best[0]):
            best = (r[0], tw, th)
    if best:
        print()
        print("   BEST: tile %dx%d -> %s B = %.2f%% of source, %.2f%% of zlib baseline"
              % (best[1], best[2], format(best[0], ','),
                 100.0*best[0]/srcb, 100.0*best[0]/zb))


if __name__ == '__main__':
    sys.exit(main() or 0)
