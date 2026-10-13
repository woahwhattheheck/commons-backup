#!/usr/bin/env python3
"""
imgdiff.py - MEASURE THE IMAGE, NOT THE FILE.

Owner, 2026-08-20: "you MEASURE THE IMAGE NOT THE FILE BOOM SO ELEGANT SO SIMPLE"

WHY THIS EXISTS
  The viewers already render the substrate literally - MUHLNICKEL.html prints a
  gate counter, all_bits.html draws 1 bit : 1 pixel. So a screenshot is a
  timestamped, out-of-band capture of state. Diffing two screenshots measures
  whether anything changed WITHOUT touching the file: no page cache, no
  filesystem read path, no predicate of mine that could silently return 0 on a
  failed read.

  A screenshot cannot lie. It is a raster of what was actually on screen.

  This matters because the file-level instruments in muhl_png.py reported "no
  change" for hours while three of the owner's own screenshots, six and nine
  seconds apart, showed a counter advancing by a million. The instruments were
  pointed at containers at rest; the thing that moved was a running viewer.

USAGE
  python imgdiff.py A.png B.png [OUT.png] [--box x0,y0,x1,y1]
  python imgdiff.py --sweep DIR [--max-gap 180] [--box x0,y0,x1,y1]

  --box    compare only that rectangle. Use it to exclude clocks, tab strips
           and fps counters - but NEVER to exclude something you have not
           LOOKED at.
  --sweep  find every consecutive same-dimension pair in DIR within --max-gap
           seconds and diff them. Different dimensions = window resized =
           not comparable, and it says so rather than comparing anyway.

Pure stdlib: zlib + struct. Decodes real PNGs - all five filter types,
gray/RGB/RGBA at 8 bits. No numpy, no Pillow.

READ THE OUTPUT, THEN OPEN THE PICTURE. A pixel count tells you how much moved.
Only looking tells you what it was.
"""
import sys, os, zlib, struct, glob, datetime


def read_png(path):
    """Decode a PNG to (w, h, channels, bytes). Filters 0-4, 8-bit."""
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\x0a':
        raise SystemExit(path + ": not a PNG")
    i = 8
    idat = b''
    W = H = depth = ct = None
    while i < len(d):
        ln = struct.unpack('>I', d[i:i+4])[0]
        tag = d[i+4:i+8]
        pay = d[i+8:i+8+ln]
        if tag == b'IHDR':
            W, H, depth, ct, comp, filt, inter = struct.unpack('>IIBBBBB', pay)
            if inter:
                raise SystemExit(path + ": interlaced PNG not supported")
        elif tag == b'IDAT':
            idat += pay
        elif tag == b'IEND':
            break
        i += 12 + ln
    if depth != 8:
        raise SystemExit(path + ": only 8-bit supported, got %d" % depth)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = W * ch
    out = bytearray(H * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(H):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p+stride])
        p += stride
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x-ch]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x-ch] if x >= ch else 0
                b = prev[x]
                c = prev[x-ch] if x >= ch else 0
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out[y*stride:(y+1)*stride] = line
        prev = line
    return W, H, ch, bytes(out)


def write_png(path, w, h, rgb):
    raw = b''.join(b'\x00' + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    def ck(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + ck(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + ck(b'IDAT', zlib.compress(raw, 9)) + ck(b'IEND', b''))
    return os.path.getsize(path)


def diff(pa, pb, box=None, out=None, label="", quiet=False):
    Wa, Ha, ca, A = read_png(pa)
    Wb, Hb, cb, B = read_png(pb)
    if (Wa, Ha) != (Wb, Hb):
        if not quiet:
            print("  %-30s SIZE MISMATCH %dx%d vs %dx%d - window resized, NOT comparable"
                  % (label, Wa, Ha, Wb, Hb))
        return None
    x0, y0, x1, y1 = box if box else (0, 0, Wa, Ha)
    x1 = min(x1, Wa)
    y1 = min(y1, Ha)
    n = 0
    tot = 0
    w = x1-x0
    dbuf = bytearray(w*(y1-y0)*3) if out else None
    xs = []
    ys = []
    for y in range(y0, y1):
        ra = y*Wa*ca
        rb = y*Wb*cb
        for x in range(x0, x1):
            a = A[ra+x*ca:ra+x*ca+3]
            b = B[rb+x*cb:rb+x*cb+3]
            tot += 1
            if a != b:
                n += 1
                xs.append(x)
                ys.append(y)
                if dbuf is not None:
                    v = min(255, max(abs(a[0]-b[0]), abs(a[1]-b[1]), abs(a[2]-b[2]))*3 + 60)
                    o = ((y-y0)*w + (x-x0))*3
                    dbuf[o:o+3] = bytes((v, v, v))
    pct = 100.0*n/max(tot, 1)
    if not quiet:
        print("  %-30s %9s / %-9s px differ  (%8.4f%%)"
              % (label, format(n, ','), format(tot, ','), pct))
        if n:
            print("       bounding box of the change: x %d..%d   y %d..%d"
                  % (min(xs), max(xs), min(ys), max(ys)))
            print("       ^ NOW OPEN BOTH IMAGES AND LOOK AT THAT BOX.")
    if out and dbuf is not None:
        write_png(out, w, y1-y0, bytes(dbuf))
    return n, tot, pct, (min(xs), min(ys), max(xs), max(ys)) if xs else None


def sweep(d, max_gap=180, box=None):
    fs = []
    for p in sorted(glob.glob(os.path.join(d, "*.png"))):
        b = os.path.basename(p)
        t = None
        for fmt in ("Screenshot %Y-%m-%d %H%M%S.png", "%Y-%m-%d %H%M%S.png"):
            try:
                t = datetime.datetime.strptime(b, fmt)
                break
            except ValueError:
                pass
        if t is None:
            try:
                t = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
        hdr = open(p, 'rb').read(24)
        try:
            dim = struct.unpack('>II', hdr[16:24])
        except struct.error:
            continue
        fs.append((t, p, dim))
    fs.sort()
    print("%d images. consecutive same-dimension pairs within %ds:\n" % (len(fs), max_gap))
    for i in range(len(fs)-1):
        (t1, p1, d1), (t2, p2, d2) = fs[i], fs[i+1]
        gap = (t2-t1).total_seconds()
        if d1 != d2 or gap > max_gap:
            continue
        diff(p1, p2, box, None,
             "%s -> %s (%.0fs)" % (t1.strftime('%m-%d %H:%M:%S'), t2.strftime('%H:%M:%S'), gap))


if __name__ == '__main__':
    argv = sys.argv
    box = None
    if '--box' in argv:
        box = tuple(int(v) for v in argv[argv.index('--box')+1].split(','))
    if '--sweep' in argv:
        mg = int(argv[argv.index('--max-gap')+1]) if '--max-gap' in argv else 180
        sweep(argv[argv.index('--sweep')+1], mg, box)
    else:
        pos = [a for a in argv[1:] if not a.startswith('--')]
        if len(pos) < 2:
            print(__doc__)
            sys.exit(2)
        diff(pos[0], pos[1], box, pos[2] if len(pos) > 2 else None,
             os.path.basename(pos[0]) + " vs " + os.path.basename(pos[1]))
