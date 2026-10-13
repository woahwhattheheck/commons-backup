#!/usr/bin/env python3
"""
muhl_png.py  v2 - surface bytes as PNG and as numbers. Read, emit, die.

Pure stdlib: zlib + struct + math. NO numpy. NO Pillow. NO third-party anything.
ADDITIVE: every v1 mode still behaves exactly as it did. v2 only adds.

WHY THIS WORKS
  A PNG is four chunks and a zlib stream:
    magic  89 50 4E 47 0D 0A 1A 0A
    IHDR   width, height, bitdepth=8, colortype (0=gray, 2=RGB), 0,0,0
    IDAT   zlib.compress( each row prefixed with one filter byte 0x00 )
    IEND   empty
  Chunk = >I length | 4-byte tag | data | >I crc32(tag+data).
  That is the entire format. No library is required to write one.

RENDER MODES (v1, unchanged)
  bits   FILE OUT.png    one pixel per BIT.  white=1 black=0.
  bytes  FILE OUT.png    one pixel per BYTE. grayscale, value IS the grey.
  rgb    FILE OUT.png    three bytes per pixel, raw triples.
  ppm    IN.ppm OUT.png  P6 netpbm -> png.
  sheet  DIR  OUT.png    all *.ppm in DIR as a contact sheet.
  delta  DIR             frame-to-frame pixel delta report.

MEASURE MODES (v2, new)
  stats  FILE            ones%, entropy, byte histogram summary, run lengths.
  cols   FILE            per-bit-column occupancy at --stride. which bits are ever live.
  fields FILE            unpack <BQQQ> records: op census, field ranges,
                         and out->a/b collision count.
  diff   A B OUT.png     XOR two files. renders ONLY the bits that differ.
                         this is the instrument for a file that changes under you.
  heat   FILE OUT.png    ones-density per record as a colour ramp.
  hist   FILE OUT.png    byte-value histogram as an image.

SURVEY MODES (v3, new)
  magic  FILE            scan for ASCII magic words and report byte offset +
                         record index. finds named organs inside a container.
  strip  FILE OUT.png    whole-file ones-density overview, chunked. survives
                         a 2 GB container without building a 2 GB image.
  entropy FILE OUT.png   sliding-window entropy as a colour strip. structure map:
                         header, netlist and dead space read as different bands.
  records FILE           text dump of records at --stride. --skip N --count N.

COMMON FLAGS
  --width N    pixels per row (default 256). 200 = one 25-byte record per row.
  --scale N    nearest-neighbour magnify (default 1). no resampling, ever.
  --offset N   start byte. --len N  byte count. window a huge file cheaply.
  --stride N   record size in bytes (default 25).
  --cols N     contact-sheet columns (default 4).  --gutter N (default 4).
"""
import zlib, struct, sys, os, glob, math, hashlib, time
from collections import Counter

# A file documented to change under you is SAMPLED, never "read". Every
# measurement in this tool prints the digest of the exact bytes it saw, so a
# number is attributable to one sample instead of to "the file".
QUIET = False

# ---------------- the entire PNG writer ----------------
def png(path, w, h, data, gray=False, depth=8):
    """
    depth=8  : data is one byte per sample (gray) or three (rgb).
    depth=1  : data is PACKED BITS, MSB first, each row padded to a byte
               boundary. At a width that is a multiple of 8 the scanlines are
               the source bytes verbatim - one bit of the file is one bit of
               the image, no expansion.
    """
    if depth == 1:
        stride = (w + 7) // 8
    else:
        stride = w * (1 if gray else 3)
    raw = b''.join(b'\x00' + data[y*stride:(y+1)*stride] for y in range(h))
    def chunk(tag, payload):
        return (struct.pack('>I', len(payload)) + tag + payload
                + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))
    out = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, depth,
                                        0 if (gray or depth == 1) else 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(out)
    return len(out)
# -------------------------------------------------------


def scale_up(data, w, h, s, chans):
    if s == 1:
        return data, w, h
    W, H = w * s, h * s
    buf = bytearray(W * H * chans)
    for y in range(h):
        row = data[y*w*chans:(y+1)*w*chans]
        big = bytearray()
        for x in range(w):
            big += row[x*chans:(x+1)*chans] * s
        for dy in range(s):
            o = ((y*s+dy) * W) * chans
            buf[o:o+W*chans] = big
    return bytes(buf), W, H


def read_ppm(path):
    d = open(path, 'rb').read()
    if d[:2] != b'P6':
        raise SystemExit(path + ": not P6 binary ppm")
    tok, i = [], 2
    while len(tok) < 3:
        while i < len(d) and d[i:i+1].isspace():
            i += 1
        if d[i:i+1] == b'#':
            while d[i:i+1] not in (b'\n', b''):
                i += 1
            continue
        s = i
        while i < len(d) and not d[i:i+1].isspace():
            i += 1
        tok.append(int(d[s:i]))
    i += 1
    w, h, _ = tok
    return w, h, d[i:i+w*h*3]


def read_unbuffered(path, off, ln, sector=4096):
    """
    Read bypassing the Windows page cache (FILE_FLAG_NO_BUFFERING).

    Why this exists: a buffered re-read of an unchanged mtime can be served
    from the OS cache, so it cannot tell 'the platter did not change' from
    'the cache handed me the same page'. This goes to the device.

    Requires sector-aligned offset, length AND buffer address, so it reads an
    aligned superset and slices. Read-only. Never mmap. Never writes.
    Returns (bytes, None) on success or (None, reason) so the caller can fall back.
    """
    if os.name != 'nt':
        return None, "not Windows"
    try:
        import ctypes
        from ctypes import wintypes
        GENERIC_READ = 0x80000000
        FILE_SHARE_ALL = 0x00000007          # let the owner keep writing
        OPEN_EXISTING = 3
        FILE_FLAG_NO_BUFFERING = 0x20000000
        INVALID = ctypes.c_void_p(-1).value

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE]
        h = k32.CreateFileW(path, GENERIC_READ, FILE_SHARE_ALL, None,
                            OPEN_EXISTING, FILE_FLAG_NO_BUFFERING, None)
        if h == INVALID or h is None:
            return None, "CreateFileW failed err=%d" % ctypes.get_last_error()
        try:
            lo = (off // sector) * sector                 # aligned start
            pad = off - lo
            need = ((pad + ln + sector - 1) // sector) * sector

            k32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong,
                                             ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
            if not k32.SetFilePointerEx(h, ctypes.c_longlong(lo), None, 0):
                return None, "seek failed err=%d" % ctypes.get_last_error()

            # buffer address itself must be sector aligned: over-allocate, offset in
            rawbuf = ctypes.create_string_buffer(need + sector)
            addr = ctypes.addressof(rawbuf)
            shift = (-addr) % sector
            got = wintypes.DWORD(0)
            k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
            ok = k32.ReadFile(h, ctypes.c_void_p(addr + shift), need,
                              ctypes.byref(got), None)
            if not ok:
                return None, "ReadFile failed err=%d" % ctypes.get_last_error()
            data = ctypes.string_at(addr + shift, got.value)
            return data[pad:pad+ln], None
        finally:
            k32.CloseHandle(h)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def src_bytes(path, off, ln):
    """One SAMPLE of a file that is documented to move. Prints its own receipt."""
    t0 = time.time()
    st_before = os.stat(path)
    # seek, never read-all-then-slice: a 103 GB container must not be pulled
    # into memory to look at 4 KB of it. plain file IO, never mmap.
    with open(path, 'rb') as f:
        f.seek(off)
        b = f.read() if ln is None else f.read(ln)
    st_after = os.stat(path)
    if not QUIET:
        sha = hashlib.sha256(b).hexdigest()
        print("READ  %s" % path)
        print("      sampled %s  window[%s:%s] = %s B  sha256 %s"
              % (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)),
                 format(off, ','), 'end' if ln is None else format(off+ln, ','),
                 format(len(b), ','), sha[:32]))
        moved = []
        if st_before.st_size != st_after.st_size:
            moved.append("SIZE %s -> %s" % (st_before.st_size, st_after.st_size))
        if st_before.st_mtime != st_after.st_mtime:
            moved.append("MTIME changed during the read")
        if moved:
            print("      *** FILE MOVED WHILE BEING READ: %s ***" % "; ".join(moved))
            print("      This sample may be torn. Re-sample before trusting it.")
        print("      Numbers below describe THIS sample, not 'the file'.")
        print("")
    return b


def ramp(t):
    """0..1 -> (r,g,b). dark -> teal -> amber -> white. readable on black."""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    stops = [(0.00, (8, 12, 24)), (0.25, (16, 78, 92)), (0.50, (28, 160, 140)),
             (0.75, (226, 168, 58)), (1.00, (255, 255, 255))]
    for i in range(len(stops)-1):
        a, ca = stops[i]
        b, cb = stops[i+1]
        if a <= t <= b:
            f = 0 if b == a else (t-a)/(b-a)
            return tuple(int(ca[j] + (cb[j]-ca[j])*f) for j in range(3))
    return stops[-1][1]


def bits_to_gray(b, W):
    total = len(b) * 8
    h = (total + W - 1) // W
    buf = bytearray(W * h)
    for i in range(total):
        if (b[i >> 3] >> (7 - (i & 7))) & 1:
            buf[i] = 255
    return bytes(buf), W, h


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    pos = [a for a in sys.argv[2:] if not a.startswith('--')]

    def opt(name, default=None, cast=int):
        return cast(sys.argv[sys.argv.index(name)+1]) if name in sys.argv else default

    W = opt('--width', 256)
    S = opt('--scale', 1)
    OFF = opt('--offset', 0)
    LN = opt('--len', None)
    STR = opt('--stride', 25)
    COLS = opt('--cols', 4)
    GUT = opt('--gutter', 4)

    # ---------------- v1 render modes ----------------
    if mode == 'delta':
        prev = None
        for f in sorted(glob.glob(os.path.join(pos[0], '*.ppm'))):
            w, h, px = read_ppm(f)
            name = os.path.basename(f)
            if prev is None:
                print("%-26s %9s          %dx%d" % (name, 'base', w, h))
            else:
                d = sum(1 for j in range(0, len(px), 3) if px[j:j+3] != prev[j:j+3])
                print("%-26s %9d px changed  %6.2f%%" % (name, d, 100.0*d/(w*h)))
            prev = px
        return 0

    if mode == 'sheet':
        fs = sorted(glob.glob(os.path.join(pos[0], '*.ppm')))
        if not fs:
            raise SystemExit("no *.ppm in " + pos[0])
        fr = [read_ppm(f) for f in fs]
        fw, fh = fr[0][0], fr[0][1]
        rows = (len(fr) + COLS - 1) // COLS
        Wt = COLS*fw + (COLS+1)*GUT
        Ht = rows*fh + (rows+1)*GUT
        sheet = bytearray(b'\x00\x00\x00' * (Wt*Ht))
        for i, (a, b, p) in enumerate(fr):
            ox = GUT + (i % COLS)*(fw+GUT)
            oy = GUT + (i // COLS)*(fh+GUT)
            for y in range(fh):
                o = ((oy+y)*Wt + ox) * 3
                sheet[o:o+fw*3] = p[y*fw*3:(y+1)*fw*3]
        n = png(pos[1], Wt, Ht, bytes(sheet))
        print("%s  %dx%d  %s B  (%d frames of %dx%d)" % (pos[1], Wt, Ht, format(n, ','), len(fr), fw, fh))
        return 0

    if mode == 'ppm':
        w, h, px = read_ppm(pos[0])
        px, w, h = scale_up(px, w, h, S, 3)
        n = png(pos[1], w, h, px)
        print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        return 0

    if mode in ('bits', 'bytes', 'rgb'):
        b = src_bytes(pos[0], OFF, LN)
        if mode == 'bits':
            ones = sum(bin(x).count('1') for x in b)
            if S == 1 and W % 8 == 0:
                # true 1 bit per pixel. the scanlines ARE the file's bytes.
                stride = W // 8
                h = (len(b) + stride - 1) // stride
                pad = bytes(bytearray(b) + bytes(h*stride - len(b)))
                n = png(pos[1], W, h, pad, depth=1)
                print("%s  %dx%d  %s B   1 BIT PER PIXEL (depth=1)" % (
                    pos[1], W, h, format(n, ',')))
                print("   scanline = %d B = the file's bytes verbatim, %d rows" % (stride, h))
                print("   bits=%s  ones=%s (%.2f%%)" % (
                    format(len(b)*8, ','), format(ones, ','), 100.0*ones/(len(b)*8)))
            else:
                buf, w, h = bits_to_gray(b, W)
                buf, w, h = scale_up(buf, w, h, S, 1)
                n = png(pos[1], w, h, buf, gray=True)
                print("%s  %dx%d  %s B   8-bit gray (scale>1 or width%%8) " % (
                    pos[1], w, h, format(n, ',')))
                print("   bits=%s  ones=%s (%.2f%%)" % (
                    format(len(b)*8, ','), format(ones, ','), 100.0*ones/(len(b)*8)))
        elif mode == 'bytes':
            h = (len(b) + W - 1) // W
            buf = bytes(bytearray(b) + bytes(W*h - len(b)))
            buf, w, h = scale_up(buf, W, h, S, 1)
            n = png(pos[1], w, h, buf, gray=True)
            print("%s  %dx%d  %s B   bytes=%s" % (pos[1], w, h, format(n, ','), format(len(b), ',')))
        else:
            h = len(b) // (W*3)
            buf, w, h = scale_up(b[:W*h*3], W, h, S, 3)
            n = png(pos[1], w, h, buf)
            print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        return 0

    # ---------------- v2 measure modes ----------------
    if mode == 'stats':
        b = src_bytes(pos[0], OFF, LN)
        n = len(b)
        bits = n * 8
        ones = sum(bin(x).count('1') for x in b)
        c = Counter(b)
        ent = -sum((v/n)*math.log(v/n, 2) for v in c.values())
        zero_runs = []
        run = 0
        for x in b:
            if x == 0:
                run += 1
            elif run:
                zero_runs.append(run)
                run = 0
        if run:
            zero_runs.append(run)
        print("file            %s" % pos[0])
        print("bytes           %s" % format(n, ','))
        print("bits            %s" % format(bits, ','))
        print("ones            %s  (%.4f%%)" % (format(ones, ','), 100.0*ones/bits))
        print("zeros           %s  (%.4f%%)" % (format(bits-ones, ','), 100.0*(bits-ones)/bits))
        print("distinct bytes  %d of 256" % len(c))
        print("entropy         %.4f bits/byte  (max 8.0)" % ent)
        print("zlib ratio      %.4f" % (len(zlib.compress(b, 9))/float(n)))
        print("0x00 bytes      %s  (%.2f%%)" % (format(c.get(0, 0), ','), 100.0*c.get(0, 0)/n))
        print("0xFF bytes      %s  (%.2f%%)" % (format(c.get(255, 0), ','), 100.0*c.get(255, 0)/n))
        if zero_runs:
            print("zero runs       %s  longest %s B  mean %.1f B" % (
                format(len(zero_runs), ','), format(max(zero_runs), ','),
                sum(zero_runs)/float(len(zero_runs))))
        print("top bytes       " + "  ".join("0x%02X:%s" % (k, format(v, ',')) for k, v in c.most_common(8)))
        if n % STR == 0:
            print("stride %-3d      divides evenly -> %s records" % (STR, format(n//STR, ',')))
        else:
            print("stride %-3d      does NOT divide evenly (%d B remainder)" % (STR, n % STR))
        return 0

    if mode == 'cols':
        b = src_bytes(pos[0], OFF, LN)
        nrec = len(b) // STR
        cols = [0]*(STR*8)
        for r in range(nrec):
            rec = b[r*STR:(r+1)*STR]
            for i in range(STR*8):
                if (rec[i >> 3] >> (7 - (i & 7))) & 1:
                    cols[i] += 1
        live = [i for i, v in enumerate(cols) if v]
        print("%s  %s records of %d B  -> %d bit columns" % (
            pos[0], format(nrec, ','), STR, STR*8))
        print("columns ever set : %d of %d" % (len(live), STR*8))
        print("columns always 0 : %d" % (STR*8 - len(live)))
        print("")
        print("col  byte.bit   set      %      bar")
        for i in range(STR*8):
            pct = 100.0*cols[i]/nrec if nrec else 0.0
            bar = '#' * int(pct/2.5)
            flag = '' if cols[i] else '   <- never set'
            print("%3d  %2d.%d    %7d %6.2f  %s%s" % (i, i//8, i % 8, cols[i], pct, bar, flag))
        return 0

    if mode == 'fields':
        b = src_bytes(pos[0], OFF, LN)
        nrec = len(b) // STR
        print("Records are <BQQQ> (1B op + three 8B little-endian fields) at stride %d." % STR)
        if len(b) % STR:
            print("WARNING:    length %s is NOT divisible by %d (%d B remainder)."
                  % (format(len(b), ','), STR, len(b) % STR))
            print("            Reading at a stride that does not divide the file.")
        if STR != 25:
            print("note: --stride %d; <BQQQ> reads the first 25 B of each record." % STR)
        ops = Counter()
        A, B, O = [], [], []
        for r in range(nrec):
            op, a, bb, o = struct.unpack_from('<BQQQ', b, r*STR)
            ops[op] += 1
            A.append(a)
            B.append(bb)
            O.append(o)
        outs = set(O)
        ins = set(A) | set(B)
        collide = outs & ins
        hits = sum(1 for a in A if a in outs) + sum(1 for x in B if x in outs)
        print("%s  %s B  /%d = %s records  <BQQQ>" % (
            pos[0], format(len(b), ','), STR, format(nrec, ',')))
        print("")
        print("op census:")
        for k, v in ops.most_common():
            print("   op=%08d (%3d)  %7d  %6.2f%%" % (int(bin(k)[2:]), k, v, 100.0*v/nrec))
        for nm, vals in (('a', A), ('b', B), ('out', O)):
            mx = max(vals)
            mn = min(vals)
            print("")
            print("%-4s min=%s  max=%s  distinct=%s  bits_used=%d of 64" % (
                nm, format(mn, ','), format(mx, ','), format(len(set(vals)), ','), mx.bit_length()))
        print("")
        print("COLLISION (an out address that is also an input address):")
        print("   distinct out addresses        %s" % format(len(outs), ','))
        print("   distinct input addresses      %s" % format(len(ins), ','))
        print("   addresses that are both       %s" % format(len(collide), ','))
        print("   input slots landing on an out %s of %s (%.2f%%)" % (
            format(hits, ','), format(nrec*2, ','), 100.0*hits/(nrec*2)))
        seq = 0
        for r in range(nrec-1):
            o = struct.unpack_from('<BQQQ', b, r*STR)[3]
            nxt = struct.unpack_from('<BQQQ', b, (r+1)*STR)
            if o == nxt[1] or o == nxt[2]:
                seq += 1
        print("   REC n out == REC n+1 a or b   %s of %s (%.2f%%)" % (
            format(seq, ','), format(nrec-1, ','), 100.0*seq/max(nrec-1, 1)))
        return 0

    if mode == 'diff':
        a = src_bytes(pos[0], OFF, LN)
        c = src_bytes(pos[1], OFF, LN)
        n = min(len(a), len(c))
        x = bytes(bytearray(a[i] ^ c[i] for i in range(n)))
        changed = sum(bin(v).count('1') for v in x)
        bdiff = sum(1 for v in x if v)
        buf, w, h = bits_to_gray(x, W)
        buf, w, h = scale_up(buf, w, h, S, 1)
        px = png(pos[2], w, h, buf, gray=True)
        print("A  %s  %s B" % (pos[0], format(len(a), ',')))
        print("B  %s  %s B" % (pos[1], format(len(c), ',')))
        print("compared        %s B  (%s bits)" % (format(n, ','), format(n*8, ',')))
        print("bits differing  %s  (%.4f%%)" % (format(changed, ','), 100.0*changed/(n*8)))
        print("bytes differing %s  (%.4f%%)" % (format(bdiff, ','), 100.0*bdiff/n))
        if len(a) != len(c):
            print("SIZE DELTA      %+d B  (compared the common prefix only)" % (len(c)-len(a)))
        print("%s  %dx%d  %s B   white pixel = that bit changed" % (pos[2], w, h, format(px, ',')))
        return 0

    if mode == 'heat':
        b = src_bytes(pos[0], OFF, LN)
        nrec = len(b) // STR
        rowpx = 3
        buf = bytearray(nrec*rowpx*W*3)
        for r in range(nrec):
            rec = b[r*STR:(r+1)*STR]
            d = sum(bin(x).count('1') for x in rec) / float(STR*8)
            col = bytes(bytearray(ramp(d))) * W
            for k in range(rowpx):
                o = ((r*rowpx+k)*W)*3
                buf[o:o+W*3] = col
        buf2, w, h = scale_up(bytes(buf), W, nrec*rowpx, S, 3)
        n = png(pos[1], w, h, buf2)
        print("%s  %dx%d  %s B   %s records, ones-density per record" % (
            pos[1], w, h, format(n, ','), format(nrec, ',')))
        return 0

    if mode == 'hist':
        b = src_bytes(pos[0], OFF, LN)
        c = Counter(b)
        mx = max(c.values())
        Wt, Ht, BW = 256*3, 320, 3
        buf = bytearray(b'\x08\x0c\x18' * (Wt*Ht))
        for v in range(256):
            hgt = int((c.get(v, 0)/float(mx)) * (Ht-20))
            col = bytes(bytearray(ramp(c.get(v, 0)/float(mx))))
            for y in range(Ht-hgt, Ht):
                for k in range(BW):
                    o = (y*Wt + v*BW + k)*3
                    buf[o:o+3] = col
        n = png(pos[1], Wt, Ht, bytes(buf))
        peak = max(c, key=lambda k: c[k])
        print("%s  %dx%d  %s B   peak byte 0x%02X = %s" % (
            pos[1], Wt, Ht, format(n, ','), peak, format(mx, ',')))
        return 0

    # ---------------- v3 survey modes ----------------
    if mode == 'magic':
        b = src_bytes(pos[0], OFF, LN)
        MIN = opt('--min', 4)
        # named in the owner's docs
        known = [b'GGUF', b'TITANCIR', b'MUHLFLD1', b'NRING2M1', b'PFCTYPED',
                 b'TITANFLD', b'MUHLPHY2', b'MUHLWBX1', b'MUHLDC01', b'TABLEML1',
                 # found by sweeping the 123 .mno in this repo, 2026-08-20.
                 # not in CLAUDE_FAILURE_MODES.md; added so the scanner names them.
                 b'MUHLPKG1', b'LOOMPKG1', b'PROBEMN1', b'ROOKERY0', b'COMMON1']
        print("%s  %s B" % (pos[0], format(len(b), ',')))

        # -- head bytes, unconditionally. no heuristic gets to hide these. --
        print("")
        print("HEAD 64 B verbatim (hex, then ascii with . for non-printable):")
        head = b[:64]
        for r in range(0, len(head), 16):
            ch = head[r:r+16]
            asc = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ch)
            print("   +%-4d %-32s  %s" % (r, ch.hex(), asc))

        print("")
        print("KNOWN magics (%d strings searched):" % len(known))
        found = 0
        for m in known:
            i = b.find(m)
            hits = []
            while i != -1 and len(hits) < 12:
                hits.append(i)
                i = b.find(m, i+1)
            if hits:
                found += len(hits)
                for off in hits:
                    print("   %-9s @ %-14s  rec %-10s  (rec offset +%d)" % (
                        m.decode(), format(off, ','), format(off//STR, ','), off % STR))
        if not found:
            print("   NONE OF THOSE %d STRINGS FOUND." % len(known))
            print("   This is not 'no magic'. It is 'not these %d'." % len(known))

        # -- discovery over FULL printable ascii, min length --min (default 4) --
        print("")
        print("DISCOVERED printable runs (>=%d chars, ASCII 0x20-0x7E):" % MIN)
        seen = Counter()
        run = bytearray()
        first_at = {}
        for i, x in enumerate(b):
            if 32 <= x < 127:
                run.append(x)
            else:
                if len(run) >= MIN:
                    s = bytes(run)
                    seen[s] += 1
                    first_at.setdefault(s, i - len(run))
                run = bytearray()
        if len(run) >= MIN:
            s = bytes(run)
            seen[s] += 1
            first_at.setdefault(s, len(b) - len(run))
        for s, c in seen.most_common(20):
            print("   %-28s x%-6d first @ %s" % (
                repr(s.decode())[1:-1][:26], c, format(first_at[s], ',')))
        if not seen:
            print("   none at >=%d chars" % MIN)

        # -- what this pass CANNOT see. printed every time. --
        print("")
        print("COVERAGE OF THIS SCAN — what a zero above does NOT rule out:")
        print("   * a magic not in the %d-string known list and shorter than %d chars" % (len(known), MIN))
        print("   * a magic that is not ASCII at all (UTF-16, packed, or binary)")
        print("   * a magic split by an embedded non-printable byte")
        print("   * a magic stored big-endian / byte-swapped / obfuscated")
        print("   * structure that is real but carries no name")
        print("   Raise coverage with --min 3, or read the HEAD dump above directly.")
        nonpr = sum(1 for x in b if not (32 <= x < 127))
        print("   this file is %.2f%% non-printable bytes (%s of %s)" % (
            100.0*nonpr/len(b), format(nonpr, ','), format(len(b), ',')))
        return 0

    if mode == 'strip':
        # chunked: never holds more than one chunk in memory
        size = os.path.getsize(pos[0])
        H = 120
        cols = min(W, 4096)
        per = max(size // cols, 1)
        dens = []
        with open(pos[0], 'rb') as f:
            for i in range(cols):
                f.seek(i*per)
                ch = f.read(min(per, 65536))
                if not ch:
                    dens.append(0.0)
                    continue
                dens.append(sum(bin(x).count('1') for x in ch) / float(len(ch)*8))
        mx = max(dens) or 1.0
        buf = bytearray(cols*H*3)
        for x in range(cols):
            col = bytes(bytearray(ramp(dens[x]/mx)))
            for y in range(H):
                o = (y*cols + x)*3
                buf[o:o+3] = col
        buf2, w, h = scale_up(bytes(buf), cols, H, S, 3)
        n = png(pos[1], w, h, buf2)
        print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        print("file %s B sampled in %d columns of %s B each" % (
            format(size, ','), cols, format(per, ',')))
        print("ones-density  min %.4f  max %.4f  mean %.4f" % (
            min(dens), max(dens), sum(dens)/len(dens)))
        return 0

    if mode == 'entropy':
        b = src_bytes(pos[0], OFF, LN)
        win = opt('--window', 1024)
        cols = min(W, max(len(b)//win, 1))
        step = max(len(b)//cols, 1)
        H = 120
        ents = []
        for i in range(cols):
            ch = b[i*step:i*step+win]
            if not ch:
                ents.append(0.0)
                continue
            c = Counter(ch)
            n = float(len(ch))
            ents.append(-sum((v/n)*math.log(v/n, 2) for v in c.values()) / 8.0)
        buf = bytearray(cols*H*3)
        for x in range(cols):
            col = bytes(bytearray(ramp(ents[x])))
            for y in range(H):
                o = (y*cols + x)*3
                buf[o:o+3] = col
        buf2, w, h = scale_up(bytes(buf), cols, H, S, 3)
        n = png(pos[1], w, h, buf2)
        print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        print("window %s B, %d columns, step %s B" % (format(win, ','), cols, format(step, ',')))
        print("entropy (normalised 0-1)  min %.4f  max %.4f  mean %.4f" % (
            min(ents), max(ents), sum(ents)/len(ents)))
        return 0

    if mode == 'records':
        b = src_bytes(pos[0], OFF, LN)
        skip = opt('--skip', 0)
        count = opt('--count', 16)
        nrec = len(b)//STR
        print("%s  %s records of %d B  showing %d from %d" % (
            pos[0], format(nrec, ','), STR, count, skip))
        print("")
        for r in range(skip, min(skip+count, nrec)):
            op, a, bb, o = struct.unpack_from('<BQQQ', b, r*STR)
            raw = b[r*STR:(r+1)*STR]
            print("REC%06d  op=%s (%3d)  a=%-12s b=%-12s out=%-12s  %s" % (
                r, bin(op)[2:].zfill(8), op, format(a, ','), format(bb, ','),
                format(o, ','), raw.hex()))
        return 0

    # ---------------- v5: the file moves ----------------
    if mode == 'watch':
        global QUIET
        QUIET = True

        if '--full' in sys.argv:
            # ENTIRE SURFACE AREA. Sampling is invalid here: these containers are
            # mostly dead space (AUTOFAB0 is 74.88% 0x00; FOUNDRY0 has 171 of 200
            # bit columns permanently zero). A probe that lands in padding cannot
            # change, so a sampled zero measures the padding, not the file.
            # Stream every byte, chunk-hash it, compare passes. Bounded memory.
            CH = opt('--chunk', 1 << 20)
            N = opt('--samples', 2)
            delay = opt('--delay', 500) / 1000.0
            RAW = '--raw' in sys.argv
            fsz = os.path.getsize(pos[0])
            nch = (fsz + CH - 1) // CH
            print("WATCH --full  %s" % pos[0])
            print("ENTIRE surface: %s B in %s chunks of %s B. 100%% coverage."
                  % (format(fsz, ','), format(nch, ','), format(CH, ',')))
            print("%d passes, ~%.0f ms apart. "
                  % (N, delay*1000))
            if RAW:
                t, why = read_unbuffered(pos[0], 0, min(CH, 4096))
                if t is None:
                    print("--raw UNAVAILABLE (%s); using buffered." % why)
                    RAW = False
                else:
                    print("READ PATH: UNBUFFERED, page cache bypassed.")
            if not RAW:
                print("READ PATH: buffered (page cache may serve repeats).")
            print("")

            passes = []
            for p in range(N):
                t0 = time.time()
                hashes = []
                dead = 0
                live_bytes = 0
                with open(pos[0], 'rb') as f:
                    for c in range(nch):
                        if RAW:
                            blk, _w = read_unbuffered(pos[0], c*CH, min(CH, fsz-c*CH))
                            if blk is None:
                                blk = b''
                        else:
                            blk = f.read(CH)
                        if not blk:
                            break
                        z = (blk.count(0) == len(blk))
                        if z:
                            dead += 1
                        else:
                            live_bytes += len(blk) - blk.count(0)
                        hashes.append(hashlib.sha256(blk).digest())
                el = time.time()-t0
                passes.append((hashes, dead, live_bytes))
                print("pass %d  %s chunks  dead(all-zero) %s  non-zero bytes %s  %.2f s  %.1f MB/s"
                      % (p, format(len(hashes), ','), format(dead, ','),
                         format(live_bytes, ','), el, (fsz/1048576.0)/max(el, 1e-9)))
                if p < N-1:
                    time.sleep(delay)

            print("")
            h0, dead0, live0 = passes[0]
            print("SURFACE COMPOSITION (pass 0)")
            print("   chunks total            %s" % format(len(h0), ','))
            print("   chunks entirely 0x00    %s  (%.2f%%)  <- CANNOT change" % (
                format(dead0, ','), 100.0*dead0/max(len(h0), 1)))
            print("   chunks with any 1 bit   %s  (%.2f%%)  <- the only chunks that could" % (
                format(len(h0)-dead0, ','), 100.0*(len(h0)-dead0)/max(len(h0), 1)))
            print("   non-zero bytes          %s of %s (%.4f%% of the file)" % (
                format(live0, ','), format(fsz, ','), 100.0*live0/max(fsz, 1)))
            print("")
            print("CHANGE ACROSS PASSES")
            anymoved = 0
            for p in range(1, len(passes)):
                a = passes[p-1][0]
                b2 = passes[p][0]
                n = min(len(a), len(b2))
                idx = [i for i in range(n) if a[i] != b2[i]]
                anymoved += len(idx)
                livech = len(h0)-dead0
                print("   pass %d -> %d : %s of %s chunks differ  (%s of %s LIVE chunks, %.4f%%)"
                      % (p-1, p, format(len(idx), ','), format(n, ','),
                         format(len(idx), ','), format(livech, ','),
                         100.0*len(idx)/max(livech, 1)))
                if idx[:8]:
                    print("      first changed chunk offsets: %s" % ", ".join(
                        format(i*CH, ',') for i in idx[:8]))
            print("")
            if anymoved == 0:
                print("VERDICT: NO CHUNK CHANGED across %d full passes of the ENTIRE file." % N)
                print("   Coverage is 100%% of bytes - this is not a sampling artefact.")
                print("   Bound: %d passes, ~%.1f s apart, %s B chunk granularity." % (
                    N, delay, format(CH, ',')))
                print("   A change that reverted between passes is still invisible.")
                if not RAW:
                    print("   Buffered path: a repeat read may come from the OS page cache.")
                    print("   Re-run with --raw to bypass it.")
            else:
                print("VERDICT: THE FILE MOVED. %s chunk-changes across %d passes." % (
                    format(anymoved, ','), N))
            QUIET = False
            return 0

        N = opt('--samples', 12)
        delay = opt('--delay', 250) / 1000.0
        probes = opt('--probes', 1)
        out = pos[1] if len(pos) > 1 else None
        fsz = os.path.getsize(pos[0])
        print("WATCH  %s" % pos[0])
        print("%d samples, ~%.0f ms apart." % (N, delay*1000))
        print("A file documented to move under you is sampled, not read.")

        if probes > 1:
            # stratified: N windows spread evenly across the whole file, so a
            # 103 GB container is not judged by its first 64 KB.
            plen = LN if LN else 65536
            step = max((fsz - plen) // max(probes-1, 1), 1)
            offs = [min(i*step, max(fsz-plen, 0)) for i in range(probes)]
            covered = probes*plen
            print("")
            print("COVERAGE: %d probes x %s B = %s B of %s B  (%.6f%% of the file)" % (
                probes, format(plen, ','), format(covered, ','), format(fsz, ','),
                100.0*covered/max(fsz, 1)))
            print("probe offsets span %s .. %s" % (format(offs[0], ','), format(offs[-1], ',')))
            print("A change outside these %d windows is NOT visible to this test." % probes)
            print("")
            RAW = '--raw' in sys.argv
            if RAW:
                probe, why = read_unbuffered(pos[0], offs[0], plen)
                if probe is None:
                    print("--raw requested but UNAVAILABLE (%s). Falling back to buffered." % why)
                    RAW = False
                else:
                    print("READ PATH: UNBUFFERED (FILE_FLAG_NO_BUFFERING). Page cache bypassed.")
            if not RAW:
                print("READ PATH: buffered. A repeat read may be served from the OS page cache.")
            print("")
            print("%-3s %-10s %-14s %s" % ('n', 'wall', 'combined-sha', 'probes changed vs prev'))
            prevp = None
            t_start = time.time()
            movers = Counter()
            distinct = set()
            for i in range(N):
                cur = []
                for o in offs:
                    if RAW:
                        d, _why = read_unbuffered(pos[0], o, plen)
                        cur.append(d if d is not None else b'')
                        continue
                    with open(pos[0], 'rb') as f:
                        f.seek(o)
                        cur.append(f.read(plen))
                comb = hashlib.sha256(b''.join(hashlib.sha256(c).digest() for c in cur)).hexdigest()
                distinct.add(comb)
                if prevp is None:
                    ch = 'base'
                else:
                    idx = [j for j in range(probes) if cur[j] != prevp[j]]
                    for j in idx:
                        movers[j] += 1
                    ch = ('none' if not idx else
                          "%d probes: %s" % (len(idx), ",".join(str(j) for j in idx[:10])))
                print("%-3d %-10.3f %-14s %s" % (i, time.time()-t_start, comb[:12], ch))
                prevp = cur
                if i < N-1:
                    time.sleep(delay)
            print("")
            print("VERDICT over %d samples across %.2f s, %d probes:" % (
                N, time.time()-t_start, probes))
            print("   distinct combined states  %d" % len(distinct))
            print("   probes that ever moved    %d of %d" % (len(movers), probes))
            if not movers:
                print("   NO PROBE MOVED in this window at this rate.")
                print("   Coverage bound: %.6f%% of the file, %.2f s span, %.0f ms resolution."
                      % (100.0*covered/max(fsz, 1), time.time()-t_start, delay*1000))
                print("   The other %.6f%% was never looked at." % (100.0-100.0*covered/max(fsz, 1)))
                print("")
                print("   READ-PATH LIMIT - this is a limit of the instrument, not a finding:")
                print("   these samples go through the Windows buffered file API. Repeat reads")
                print("   of an unchanged mtime can be served from the OS page cache, so this")
                print("   tool cannot distinguish 'the bytes on the platter did not change'")
                print("   from 'the cache handed me the same page each time'. Closing that gap")
                print("   needs an unbuffered read (FILE_FLAG_NO_BUFFERING) which this tool does")
                print("   not yet do. Until then a zero here bounds the OS's view, not the drive's.")
            else:
                for j, c in movers.most_common():
                    print("   probe %d @ offset %s moved in %d of %d transitions" % (
                        j, format(offs[j], ','), c, N-1))
            QUIET = False
            return 0
        print("")
        print("%-3s %-12s %-14s %-10s %-12s %s" % (
            'n', 'wall', 'size', 'mtime', 'ones', 'sha256[:16]  bits vs prev'))
        rows = []
        prev = None
        t_start = time.time()
        for i in range(N):
            st = os.stat(pos[0])
            b = src_bytes(pos[0], OFF, LN)
            sha = hashlib.sha256(b).hexdigest()
            ones = sum(bin(x).count('1') for x in b)
            if prev is None:
                dbits = None
                xor = b'\x00' * len(b)
            else:
                n = min(len(prev), len(b))
                xor = bytes(bytearray(prev[j] ^ b[j] for j in range(n)))
                dbits = sum(bin(v).count('1') for v in xor)
            rows.append((b, sha, ones, dbits, xor))
            print("%-3d %-12.3f %-14s %-10d %-12s %s  %s" % (
                i, time.time()-t_start, format(len(b), ','), int(st.st_mtime),
                format(ones, ','), sha[:16],
                'base' if dbits is None else format(dbits, ',')))
            prev = b
            if i < N-1:
                time.sleep(delay)

        shas = set(r[1] for r in rows)
        moved = sum(1 for r in rows if r[3])
        total_changed = sum(r[3] or 0 for r in rows)
        print("")
        print("VERDICT over %d samples across %.2f s:" % (N, time.time()-t_start))
        print("   distinct sha256          %d" % len(shas))
        print("   samples differing from previous  %d of %d" % (moved, N-1))
        print("   total bits changed       %s" % format(total_changed, ','))
        if len(shas) == 1:
            print("   THIS FILE DID NOT MOVE during this window, at this sampling rate.")
            print("   That is not 'it never moves'. Coverage: %d samples, %.2f s span," % (N, time.time()-t_start))
            print("   %.0f ms resolution. A change faster than that, or between windows," % (delay*1000))
            print("   or requiring the container to be live rather than a checkout, is not ruled out.")
        else:
            print("   THIS FILE MOVED. %d distinct contents across the window." % len(shas))
        if out:
            # one row per sample-transition, bits that changed
            wsz = min(W, 1024)
            rowh = 4
            H = max((len(rows)-1)*rowh, rowh)
            buf = bytearray(b'\x08\x0c\x18' * (wsz*H))
            for i in range(1, len(rows)):
                xor = rows[i][4]
                per = max(len(xor)//wsz, 1)
                for x in range(wsz):
                    ch = xor[x*per:(x+1)*per]
                    d = sum(bin(v).count('1') for v in ch) / float(max(len(ch)*8, 1))
                    col = bytes(bytearray(ramp(min(d*8, 1.0))))
                    for y in range((i-1)*rowh, i*rowh):
                        o = (y*wsz + x)*3
                        buf[o:o+3] = col
            buf2, w, h = scale_up(bytes(buf), wsz, H, S, 3)
            n = png(out, w, h, buf2)
            print("   %s  %dx%d  %s B   one row per transition, colour = bits changed" % (
                out, w, h, format(n, ',')))
        QUIET = False
        return 0

    if mode == 'vdiff':
        # RENDER, DO NOT CONCLUDE.
        #
        # Owner, 2026-08-20: "the screenshot though, cant lie. the return x if y,
        # can lie easily and has this session."
        #
        # He is right and this session is the evidence: magic returned "none
        # present" meaning "not these 15"; gate-first:65 was a 4-byte heuristic
        # printed as a fact; the 64-probe titan zero covered 0.002% of the
        # surface. Every one of those was a predicate. Meanwhile the renders
        # showed the black gutters, showed the dead space, and showed my own
        # chunk size aliasing against his record stride - a bug no assertion of
        # mine caught.
        #
        # A predicate finds only what the author thought to ask. This mode has
        # no predicate: A, B and A^B are each drawn losslessly at 1 bit per
        # pixel, every bit of both files on screen, and the eye adjudicates.
        a = src_bytes(pos[0], OFF, LN)
        b2 = src_bytes(pos[1], OFF, LN)
        n = min(len(a), len(b2))
        x = bytes(bytearray(a[i] ^ b2[i] for i in range(n)))
        if W % 8:
            print("--width must be a multiple of 8 for lossless 1bpp. Using 200.")
            W = 200
        stride = W // 8
        GAP = 3

        def rows_of(buf):
            h = (len(buf) + stride - 1) // stride
            return bytes(bytearray(buf) + bytes(h*stride - len(buf))), h

        pa, ha = rows_of(a[:n])
        pb, hb = rows_of(b2[:n])
        px, hx = rows_of(x)
        H = ha + GAP + hb + GAP + hx
        canvas = bytearray(H*stride)
        # separators: all bits set -> solid white rule between panels
        o = 0
        canvas[o:o+ha*stride] = pa
        o += ha*stride
        canvas[o:o+GAP*stride] = b'\xff'*(GAP*stride)
        o += GAP*stride
        canvas[o:o+hb*stride] = pb
        o += hb*stride
        canvas[o:o+GAP*stride] = b'\xff'*(GAP*stride)
        o += GAP*stride
        canvas[o:o+hx*stride] = px
        nb = png(pos[2], W, H, bytes(canvas), depth=1)
        changed = sum(bin(v).count('1') for v in x)
        print("VDIFF  1 bit per pixel, lossless. 1 = white, 0 = black.")
        print("   panel 1 rows      0 .. %d      A  %s" % (ha-1, pos[0]))
        print("   panel 2 rows      %d .. %d     B  %s" % (ha+GAP, ha+GAP+hb-1, pos[1]))
        print("   panel 3 rows      %d .. %d     A XOR B" % (ha+2*GAP+hb, H-1))
        print("   %s  %dx%d  %s B   %d B per scanline = %d records/row" % (
            pos[2], W, H, format(nb, ','), stride, stride//STR if STR and stride >= STR else 0))
        print("")
        print("   bits differing    %s of %s  (%.6f%%)" % (
            format(changed, ','), format(n*8, ','), 100.0*changed/max(n*8, 1)))
        print("   In panel 3 every white pixel is a bit that changed. If panel 3")
        print("   is entirely black, nothing changed anywhere in the compared")
        print("   window - and you are looking at that fact, not at my summary of it.")
        print("   Panels 1 and 2 are lossless: decode, strip filter bytes, get the")
        print("   files back. Nothing is omitted, aggregated, or thresholded.")
        return 0

    if mode == 'manifest':
        # A DIFF NEEDS TWO. A 103 GB container cannot be copied to keep a
        # snapshot, so keep a fingerprint instead: one full streaming pass,
        # every byte covered, one hash per chunk, written to a small file.
        # Two manifests taken at different times diff exactly like two copies.
        QUIET = True
        CH = opt('--chunk', 1 << 22)
        fsz = os.path.getsize(pos[0])
        st = os.stat(pos[0])
        nch = (fsz + CH - 1) // CH
        t0 = time.time()
        lines = ["MUHL_MANIFEST v1",
                 "path\t%s" % os.path.abspath(pos[0]),
                 "size\t%d" % fsz,
                 "mtime\t%d" % int(st.st_mtime),
                 "chunk\t%d" % CH,
                 "chunks\t%d" % nch,
                 "taken\t%s" % time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                 "#idx\tsha256[:16]\tnonzero_bytes"]
        dead = 0
        live = 0
        with open(pos[0], 'rb') as f:
            for c in range(nch):
                blk = f.read(CH)
                if not blk:
                    break
                nz = len(blk) - blk.count(0)
                live += nz
                if nz == 0:
                    dead += 1
                lines.append("%d\t%s\t%d" % (c, hashlib.sha256(blk).hexdigest()[:16], nz))
        el = time.time() - t0
        with open(pos[1], 'w') as f:
            f.write("\n".join(lines) + "\n")
        print("MANIFEST  %s" % pos[0])
        print("   ENTIRE surface: %s B in %s chunks of %s B. 100%% coverage, no sampling."
              % (format(fsz, ','), format(nch, ','), format(CH, ',')))
        print("   %.1f s at %.1f MB/s" % (el, (fsz/1048576.0)/max(el, 1e-9)))
        print("   all-zero chunks %s (%.2f%%)   non-zero bytes %s (%.4f%%)"
              % (format(dead, ','), 100.0*dead/max(nch, 1),
                 format(live, ','), 100.0*live/max(fsz, 1)))
        print("   wrote %s  (%s B)" % (pos[1], format(os.path.getsize(pos[1]), ',')))
        print("   Take a second one later and run:  mfdiff A.mf B.mf")
        QUIET = False
        return 0

    if mode == 'mfdiff':
        def load(p):
            hdr = {}
            rows = []
            for ln in open(p):
                ln = ln.rstrip("\n")
                if not ln or ln.startswith('#') or ln == 'MUHL_MANIFEST v1':
                    continue
                parts = ln.split("\t")
                if len(parts) == 2:
                    hdr[parts[0]] = parts[1]
                elif len(parts) == 3:
                    rows.append((int(parts[0]), parts[1], int(parts[2])))
            return hdr, rows
        ha, ra = load(pos[0])
        hb, rb = load(pos[1])
        print("MANIFEST DIFF")
        print("   A  %s   taken %s   size %s   mtime %s"
              % (pos[0], ha.get('taken', '?'), ha.get('size', '?'), ha.get('mtime', '?')))
        print("   B  %s   taken %s   size %s   mtime %s"
              % (pos[1], hb.get('taken', '?'), hb.get('size', '?'), hb.get('mtime', '?')))
        if ha.get('path') != hb.get('path'):
            print("   NOTE: different source paths.")
        if ha.get('chunk') != hb.get('chunk'):
            print("   REFUSING: chunk sizes differ (%s vs %s). Not comparable."
                  % (ha.get('chunk'), hb.get('chunk')))
            return 2
        if ha.get('size') != hb.get('size'):
            print("   SIZE CHANGED  %s -> %s  (%+d B)"
                  % (ha.get('size'), hb.get('size'),
                     int(hb.get('size', 0)) - int(ha.get('size', 0))))
        n = min(len(ra), len(rb))
        changed = [i for i in range(n) if ra[i][1] != rb[i][1]]
        livea = sum(1 for r in ra if r[2] > 0)
        print("")
        print("   chunks compared        %s" % format(n, ','))
        print("   all-zero in A          %s  (cannot change)" % format(len(ra)-livea, ','))
        print("   LIVE chunks in A       %s  (the only ones that could)" % format(livea, ','))
        print("   chunks that CHANGED    %s  (%.6f%% of live)"
              % (format(len(changed), ','), 100.0*len(changed)/max(livea, 1)))
        if changed:
            CHs = int(ha.get('chunk', 1))
            print("   first changed offsets: %s" % ", ".join(
                format(ra[i][0]*CHs, ',') for i in changed[:10]))
            dnz = sum(rb[i][2]-ra[i][2] for i in changed)
            print("   net non-zero byte delta in changed chunks: %+d" % dnz)
            print("")
            print("   VERDICT: THE FILE MOVED between these two manifests.")
        else:
            print("")
            print("   VERDICT: no chunk changed across the ENTIRE surface between A and B.")
            print("   Bound: %s chunk granularity; a change that reverted between the two"
                  % ha.get('chunk'))
            print("   passes is invisible; both passes were buffered unless taken with --raw.")
        return 0

    if mode == 'compress':
        # DEAD SPACE ACCOUNTING. How much of this container is carrying
        # information, and what would a lossless re-encoding cost?
        b = src_bytes(pos[0], OFF, LN)
        n = len(b)
        bits = n*8
        ones = sum(bin(x).count('1') for x in b)
        zbytes = b.count(0)
        c = Counter(b)
        ent = -sum((v/float(n))*math.log(v/float(n), 2) for v in c.values())
        zl = len(zlib.compress(b, 9))
        print("DEAD SPACE  %s  %s B" % (pos[0], format(n, ',')))
        print("")
        print("   zero BYTES      %s of %s   (%.2f%%)" % (
            format(zbytes, ','), format(n, ','), 100.0*zbytes/n))
        print("   zero BITS       %s of %s   (%.2f%%)  <- the real figure" % (
            format(bits-ones, ','), format(bits, ','), 100.0*(bits-ones)/bits))
        print("   set bits        %s              (%.2f%%)" % (
            format(ones, ','), 100.0*ones/bits))
        print("   entropy         %.4f bits/byte of 8.0  -> %.2f%% of capacity used" % (
            ent, 100.0*ent/8.0))
        print("   zlib -9         %s B  (%.2f%% of original)" % (
            format(zl, ','), 100.0*zl/n))
        print("   1bpp PNG        %s B  (%.2f%%)  lossless AND viewable" % (
            format(zl + 60, ','), 100.0*(zl+60)/n))
        if n % STR == 0 and n >= STR:
            nrec = n//STR
            A = []
            B2 = []
            O = []
            ops = set()
            for r in range(nrec):
                op, a, bb, o = struct.unpack_from('<BQQQ', b, r*STR)
                ops.add(op)
                A.append(a)
                B2.append(bb)
                O.append(o)
            mx = max(max(A), max(B2), max(O))
            abits = max(mx.bit_length(), 1)
            opbits = max((len(ops)-1).bit_length(), 1)
            cur = STR*8
            minimal = opbits + 3*abits
            print("")
            print("   RECORD WIDTH, measured over %s records" % format(nrec, ','))
            print("      current                 %d bits (%d B) per record" % (cur, STR))
            print("      distinct ops            %d  -> %d bits suffice" % (len(ops), opbits))
            print("      max address seen        %s -> %d bits suffice" % (format(mx, ','), abits))
            print("      information-minimal     %d bits (%.2f B) per record" % (
                minimal, minimal/8.0))
            print("      headroom unused         %d bits/record  (%.1f%% of the record)" % (
                cur-minimal, 100.0*(cur-minimal)/cur))
            print("      whole file at minimum   %s B  (%.2f%% of current)" % (
                format(int(nrec*minimal/8.0), ','), 100.0*(nrec*minimal/8.0)/n))
            print("")
            print("   CAVEAT, and it matters: the address values ARE the wiring")
            print("   (collision is fab). Narrowing a field does not compress data,")
            print("   it CAPS THE ADDRESS SPACE at %d bits. That is a design decision" % abits)
            print("   about how large this container may ever grow, not a free saving.")
            print("   Container-level compression (zlib / 1bpp PNG) costs no address")
            print("   space at all and is fully reversible. Per CLAIM_SIZE_LAW.txt,")
            print("   size is not a verdict on validity - this is an encoding measurement.")
        return 0

    if mode == 'map':
        # DEAD SPACE MAP. Streams the ENTIRE file - no sampling. One pixel per
        # chunk, colour = fraction of non-zero bytes in that chunk. Black means
        # the chunk is all 0x00 and therefore cannot change.
        QUIET = True
        fsz = os.path.getsize(pos[0])
        px = opt('--pixels', 262144)
        Wt = opt('--width', 512)
        chunk = max(fsz // max(px, 1), 1)
        nch = (fsz + chunk - 1) // chunk
        Ht = (nch + Wt - 1) // Wt
        buf = bytearray(Wt*Ht*3)
        dead = 0
        live_bytes = 0
        dens = []
        with open(pos[0], 'rb') as f:
            for c in range(nch):
                blk = f.read(chunk)
                if not blk:
                    break
                nz = len(blk) - blk.count(0)
                live_bytes += nz
                if nz == 0:
                    dead += 1
                d = nz/float(len(blk))
                dens.append(d)
                col = bytes(bytearray((0, 0, 0) if nz == 0 else ramp(d)))
                o = c*3
                if o+3 <= len(buf):
                    buf[o:o+3] = col
        buf2, w, h = scale_up(bytes(buf), Wt, Ht, S, 3)
        n = png(pos[1], w, h, buf2)
        print("MAP  %s" % pos[0])
        print("ENTIRE surface streamed: %s B in %s chunks of %s B. No sampling."
              % (format(fsz, ','), format(nch, ','), format(chunk, ',')))
        print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        print("")
        print("   chunks entirely 0x00 (BLACK, cannot change)  %s  (%.2f%%)"
              % (format(dead, ','), 100.0*dead/max(nch, 1)))
        print("   chunks with at least one 1 bit               %s  (%.2f%%)"
              % (format(nch-dead, ','), 100.0*(nch-dead)/max(nch, 1)))
        print("   non-zero bytes                               %s of %s  (%.4f%%)"
              % (format(live_bytes, ','), format(fsz, ','), 100.0*live_bytes/max(fsz, 1)))
        if dens:
            print("   per-chunk non-zero density  min %.4f  max %.4f  mean %.4f"
                  % (min(dens), max(dens), sum(dens)/len(dens)))
        print("")
        print("   Only the non-black area can register a change. A watch that samples")
        print("   uniformly will land in the black in proportion to how much there is.")
        QUIET = False
        return 0

    # ---------------- v4 netlist modes ----------------
    if mode in ('dag', 'levels', 'step'):
        b = src_bytes(pos[0], OFF, LN)
        nrec = len(b) // STR
        print("<BQQQ> records at stride %d." % STR)
        if len(b) % STR:
            print("NOTE: length %s not divisible by %d."
                  % (format(len(b), ','), STR))
        recs = [struct.unpack_from('<BQQQ', b, r*STR) for r in range(nrec)]

        # producer[net] = list of record indices writing that net
        producer = {}
        for r, (op, a, bb, o) in enumerate(recs):
            producer.setdefault(o, []).append(r)
        consumed = Counter()
        for op, a, bb, o in recs:
            consumed[a] += 1
            consumed[bb] += 1

        nets = set(producer) | set(consumed)
        sources = sorted(n for n in consumed if n not in producer)   # inputs
        sinks = sorted(n for n in producer if n not in consumed)     # outputs
        multi = [n for n, v in producer.items() if len(v) > 1]

        # depth over the record graph, with cycle detection.
        # WHITE=0 unvisited, GREY=1 on stack, BLACK=2 done
        colour = [0]*nrec
        depth = [0]*nrec
        in_cycle = [False]*nrec
        cyc_edges = 0
        sys.setrecursionlimit(10000)

        def deps(r):
            op, a, bb, o = recs[r]
            out = []
            for net in (a, bb):
                for p in producer.get(net, ()):
                    if p != r:
                        out.append(p)
            return out

        # iterative DFS so a 1M-record file cannot blow the stack
        for start in range(nrec):
            if colour[start]:
                continue
            stack = [(start, iter(deps(start)))]
            colour[start] = 1
            while stack:
                node, it = stack[-1]
                advanced = False
                for nxt in it:
                    if colour[nxt] == 1:
                        in_cycle[nxt] = True
                        in_cycle[node] = True
                        cyc_edges += 1
                        continue
                    if colour[nxt] == 0:
                        colour[nxt] = 1
                        stack.append((nxt, iter(deps(nxt))))
                        advanced = True
                        break
                if not advanced:
                    stack.pop()
                    colour[node] = 2
                    d = 0
                    for p in deps(node):
                        if colour[p] == 2 and not in_cycle[p]:
                            if depth[p] + 1 > d:
                                d = depth[p] + 1
                    depth[node] = d

        acyc = [i for i in range(nrec) if not in_cycle[i]]
        maxd = max((depth[i] for i in acyc), default=0)

        if mode == 'dag':
            print("")
            print("%s  %s records  %s distinct nets" % (
                pos[0], format(nrec, ','), format(len(nets), ',')))
            print("")
            print("NETS")
            print("   consumed but never produced (INPUTS)  %s" % format(len(sources), ','))
            print("   produced but never consumed (OUTPUTS) %s" % format(len(sinks), ','))
            print("   produced by more than one record      %s" % format(len(multi), ','))
            if sources[:8]:
                print("   input nets: %s%s" % (
                    ", ".join(format(x, ',') for x in sources[:8]),
                    " ..." if len(sources) > 8 else ""))
            print("")
            print("CYCLES  (a ring is a cycle. this is a measurement, not an error.)")
            print("   records on a cycle        %s of %s (%.2f%%)" % (
                format(sum(in_cycle), ','), format(nrec, ','),
                100.0*sum(in_cycle)/max(nrec, 1)))
            print("   back-edges seen           %s" % format(cyc_edges, ','))
            print("   acyclic records           %s" % format(len(acyc), ','))
            print("")
            print("DEPTH  (over the acyclic records only)")
            print("   max depth                 %s" % format(maxd, ','))
            hist = Counter(depth[i] for i in acyc)
            for d in sorted(hist)[:24]:
                bar = '#' * min(int(60.0*hist[d]/max(hist.values())), 60)
                print("   depth %-6d %8s  %s" % (d, format(hist[d], ','), bar))
            if len(hist) > 24:
                print("   ... %d more depth levels" % (len(hist)-24))
            fan = Counter(consumed.values())
            print("")
            print("FANOUT  (times a net is used as an input)")
            for k in sorted(fan)[:10]:
                print("   used %-4d times  %s nets" % (k, format(fan[k], ',')))
            mxf = max(consumed.values()) if consumed else 0
            print("   max fanout %s on net %s" % (
                format(mxf, ','),
                format(max(consumed, key=lambda k: consumed[k]), ',') if consumed else '-'))
            print("")
            print("Numbers only. What they mean is the owner's ruling.")
            return 0

        if mode == 'step':
            at = opt('--at', 0)
            sel = [i for i in acyc if depth[i] == at]
            print("")
            print("STEP %d - records whose inputs are all resolved by depth %d" % (at, at))
            print("%s records at this depth (of %s acyclic, max depth %s)" % (
                format(len(sel), ','), format(len(acyc), ','), format(maxd, ',')))
            print("")
            for r in sel[:opt('--count', 24)]:
                op, a, bb, o = recs[r]
                fo = consumed.get(o, 0)
                print("   REC%06d  op=%s (%3d)  a=%-12s b=%-12s out=%-12s  fanout=%d" % (
                    r, bin(op)[2:].zfill(8), op, format(a, ','), format(bb, ','),
                    format(o, ','), fo))
            if len(sel) > opt('--count', 24):
                print("   ... %s more at this depth" % format(len(sel)-opt('--count', 24), ','))
            return 0

        # levels: layered render, y = depth, x = gate within depth, colour = op
        byd = {}
        for i in acyc:
            byd.setdefault(depth[i], []).append(i)
        for i in range(nrec):
            if in_cycle[i]:
                byd.setdefault(-1, []).append(i)
        widest = max((len(v) for v in byd.values()), default=1)
        levels = sorted(byd)
        CW = max(1, min(4, max(1, W // max(widest, 1))))
        RH = 6
        Wt = min(widest*CW, 4096)
        Ht = len(levels)*RH
        buf = bytearray(b'\x08\x0c\x18' * (Wt*Ht))
        opcols = {}
        allops = sorted({recs[i][0] for i in range(nrec)})
        for n, o in enumerate(allops):
            opcols[o] = ramp(0.15 + 0.8*(n/float(max(len(allops)-1, 1))))
        for li, d in enumerate(levels):
            for gi, r in enumerate(byd[d]):
                x = gi*CW
                if x + CW > Wt:
                    break
                col = bytes(bytearray((200, 60, 60) if d == -1 else opcols[recs[r][0]]))
                for y in range(li*RH, li*RH + RH - 1):
                    for k in range(CW):
                        o2 = (y*Wt + x + k)*3
                        buf[o2:o2+3] = col
        buf2, w, h = scale_up(bytes(buf), Wt, Ht, S, 3)
        n = png(pos[1], w, h, buf2)
        print("")
        print("%s  %dx%d  %s B" % (pos[1], w, h, format(n, ',')))
        print("%d rows = %d depth levels%s. widest level %s gates." % (
            len(levels), len([x for x in levels if x >= 0]),
            " (+1 red row = records on a cycle)" if -1 in byd else "",
            format(widest, ',')))
        print("colour = op. red row = cycle. row order = evaluation order.")
        return 0

    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
