#!/usr/bin/env python3
"""muhl_flex.py — a BARRAGE of new circuits fabricated on Bryce's Muhlnickel substrate.

Every one is built as NAND/AND/OR/XOR/NOT gates with the White Box compiler (sdc_cc.CircuitCompiler),
DCE'd, rippled, and VERIFIED BYTE-EXACT against an independent pure-Python reference — no numpy, no host
executor as runtime, no touching titan.gguf. This is fabrication-time synthesis: prove the logic byte-exact
BEFORE it would ever be stored. Each is a real gate netlist the substrate could bake and run by address.

Builds:
  mul32     32x32 -> 64 unsigned multiplier (shift-add array)
  div32     32/32 -> (quotient, remainder) restoring divider
  crc32     CRC-32 (IEEE 802.3, reflected) over an N-byte message      == binascii.crc32
  rule110   Rule 110 cellular automaton next-state (TURING-COMPLETE)   == bit reference, 1000s of gens
  bitonic   Batcher bitonic sort of 8 x 8-bit keys                      == sorted()
  sha1      SHA-1 of a <=55-byte message, single block, 80 rounds       == hashlib.sha1
  aes128    AES-128 single-block encrypt datapath (SubBytes/ShiftRows/  == independent Python AES
            MixColumns/AddRoundKey, 10 rounds; S-box as a gate LUT)
"""
import sys, os, random, struct, hashlib, binascii, time
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared helpers ----------
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
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c
def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:9s} {len(gates):>8,} gates  depth {depth:>4}  byte-exact over {cases} cases  {note}", flush=True)

# ================================ mul32 ================================
def flex_mul32(cases=300):
    g = CC.CircuitCompiler(64); IN = g.IN
    A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    acc = [g.C0] * 64
    for j in range(32):
        term = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(32)] + [g.C0] * 64)[:64]
        acc, _ = add_bits(g, acc, term)
    run, out2, gates, _ = build_run(g, acc)
    ok = True
    for _ in range(cases):
        a, b = random.getrandbits(32), random.getrandbits(32)
        inp = [0] * 64; setf(inp, 0, 32, a); setf(inp, 32, 32, b)
        if rd(run(inp, 1), out2) != (a * b) & ((1 << 64) - 1): ok = False; break
    record("mul32", gates, depth_of(g, gates, out2), ok, cases, "32x32->64")

# ================================ div32 (restoring) ================================
def flex_div32(cases=300):
    g = CC.CircuitCompiler(64); IN = g.IN
    A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    B33 = B + [g.C0]
    R = [g.C0] * 33; Q = [g.C0] * 32
    for i in range(31, -1, -1):
        R = [A[i]] + R[:32]                                   # R = (R<<1) | A[i]
        diff, c = add_bits(g, R, [g.NOT(x) for x in B33], g.C1)
        ge = c                                                # carry-out==1 => R>=B (no borrow)
        R = muxw(g, ge, diff, R); Q[i] = ge
    outs = Q + R[:32]
    run, out2, gates, _ = build_run(g, outs)
    qw, rw = out2[:32], out2[32:64]
    ok = True
    for _ in range(cases):
        a = random.getrandbits(32); b = random.getrandbits(32) or 1
        inp = [0] * 64; setf(inp, 0, 32, a); setf(inp, 32, 32, b)
        v = run(inp, 1); q, r = divmod(a, b)
        if rd(v, qw) != q or rd(v, rw) != r: ok = False; break
    record("div32", gates, depth_of(g, gates, out2), ok, cases, "-> (quot, rem)")

# ================================ crc32 ================================
def flex_crc32(L=12, cases=300):
    POLY = 0xEDB88320
    g = CC.CircuitCompiler(8 * L); IN = g.IN
    crc = [g.C1] * 32                                         # init 0xFFFFFFFF
    for m in range(L):
        for b in range(8):
            crc[b] = g.XOR(crc[b], IN[m * 8 + b])
        for _ in range(8):
            lsb = crc[0]
            sh = crc[1:] + [g.C0]                             # crc >> 1
            crc = [g.XOR(sh[k], lsb) if (POLY >> k) & 1 else sh[k] for k in range(32)]
    outs = [g.XOR(crc[k], g.C1) for k in range(32)]            # final xor 0xFFFFFFFF
    run, out2, gates, _ = build_run(g, outs)
    ok = True
    for _ in range(cases):
        msg = bytes(random.getrandbits(8) for _ in range(L))
        inp = [0] * (8 * L)
        for m in range(L): setf(inp, m * 8, 8, msg[m])
        if rd(run(inp, 1), out2) != (binascii.crc32(msg) & 0xffffffff): ok = False; break
    record("crc32", gates, depth_of(g, gates, out2), ok, cases, f"{L}-byte msg == binascii")

# ================================ rule110 ================================
def flex_rule110(W=64, gens=2000):
    g = CC.CircuitCompiler(W); IN = g.IN
    row = IN
    outs = []
    for i in range(W):
        l = row[i - 1] if i > 0 else g.C0
        c = row[i]
        r = row[i + 1] if i < W - 1 else g.C0
        outs.append(g.OR(g.XOR(c, r), g.AND(c, g.NOT(l))))    # rule 110
    run, out2, gates, _ = build_run(g, outs)
    def ref_step(s):
        return [((s[i]) ^ (s[i + 1] if i < W - 1 else 0)) | ((s[i]) & (1 - (s[i - 1] if i > 0 else 0))) for i in range(W)]
    random.seed(110)
    cur = [random.randrange(2) for _ in range(W)]
    ref = list(cur); ok = True
    for _ in range(gens):
        inp = list(cur)
        v = run(inp, 1); nxt = [bit(v, w) for w in out2]
        ref = ref_step(ref)
        if nxt != ref: ok = False; break
        cur = nxt
    record("rule110", gates, depth_of(g, gates, out2), ok, gens, f"W={W}, TURING-COMPLETE, {gens} gens")

# ================================ bitonic sort ================================
def flex_bitonic(N=8, K=8, cases=300):
    g = CC.CircuitCompiler(N * K); IN = g.IN
    keys = [[IN[i * K + b] for b in range(K)] for i in range(N)]
    def cmp_exchange(x, y, up):
        diff, c = add_bits(g, x, [g.NOT(t) for t in y], g.C1)
        lt = g.NOT(c)                                         # borrow => x < y
        mn = muxw(g, lt, x, y); mx = muxw(g, lt, y, x)
        return (mn, mx) if up else (mx, mn)
    k = 2
    while k <= N:
        j = k // 2
        while j > 0:
            for i in range(N):
                l = i ^ j
                if l > i:
                    up = (i & k) == 0
                    keys[i], keys[l] = cmp_exchange(keys[i], keys[l], up)
            j //= 2
        k *= 2
    outs = [w for key in keys for w in key]
    run, out2, gates, _ = build_run(g, outs)
    fields = [out2[i * K:(i + 1) * K] for i in range(N)]
    ok = True
    for _ in range(cases):
        arr = [random.getrandbits(K) for _ in range(N)]
        inp = [0] * (N * K)
        for i in range(N): setf(inp, i * K, K, arr[i])
        v = run(inp, 1); got = [rd(v, f) for f in fields]
        if got != sorted(arr): ok = False; break
    record("bitonic", gates, depth_of(g, gates, out2), ok, cases, f"sort {N}x{K}-bit == sorted()")

# ================================ sha1 ================================
def rotl(x, n): return [x[(i - n) % 32] for i in range(32)]
def xorw(g, *xs):
    o = xs[0]
    for y in xs[1:]: o = [g.XOR(o[k], y[k]) for k in range(32)]
    return o
def flex_sha1(L=20, cases=60):
    g = CC.CircuitCompiler(8 * L); IN = g.IN
    # build the padded 512-bit block; message bytes are inputs, padding is constant
    total_bits = 512
    msgbits = [None] * total_bits
    # SHA-1 is big-endian: bit 0 of the block is the MSB of byte 0
    def word_be(bits32):  # bits32 is MSB-first list -> LSB-first wire list
        return [bits32[31 - k] for k in range(32)]
    block = []
    # assemble 512 bits MSB-first
    seq = []
    for m in range(L):
        for b in range(8):
            seq.append(IN[m * 8 + (7 - b)])                  # byte MSB-first
    seq.append(g.C1)                                         # 0x80 pad start
    while (len(seq) % 512) != (512 - 64):
        seq.append(g.C0)
    for b in range(64):                                     # 64-bit big-endian length
        seq.append(g.C1 if ((8 * L) >> (63 - b)) & 1 else g.C0)
    assert len(seq) == 512
    W = [word_be(seq[16 * t:16 * t + 32][:32] and seq[32 * t:32 * t + 32]) for t in range(16)]
    W = [word_be(seq[32 * t:32 * t + 32]) for t in range(16)]
    for t in range(16, 80):
        W.append(rotl(xorw(g, W[t - 3], W[t - 8], W[t - 14], W[t - 16]), 1))
    H = [consts(g, h, 32) for h in (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)]
    a, b, c, d, e = H
    for t in range(80):
        if t < 20:   f = [g.OR(g.AND(b[k], c[k]), g.AND(g.NOT(b[k]), d[k])) for k in range(32)]; kx = 0x5A827999
        elif t < 40: f = xorw(g, b, c, d); kx = 0x6ED9EBA1
        elif t < 60: f = [g.OR(g.OR(g.AND(b[k], c[k]), g.AND(b[k], d[k])), g.AND(c[k], d[k])) for k in range(32)]; kx = 0x8F1BBCDC
        else:        f = xorw(g, b, c, d); kx = 0xCA62C1D6
        tmp = rotl(a, 5)
        for term in (f, e, consts(g, kx, 32), W[t]):
            tmp, _ = add_bits(g, tmp, term)
        e = d; d = c; c = rotl(b, 30); b = a; a = tmp
    Hn = []
    for hv, av in zip(H, (a, b, c, d, e)):
        s, _ = add_bits(g, hv, av); Hn.append(s)
    outs = [w for word in Hn for w in word]
    run, out2, gates, _ = build_run(g, outs)
    words = [out2[i * 32:(i + 1) * 32] for i in range(5)]
    ok = True
    for _ in range(cases):
        msg = bytes(random.getrandbits(8) for _ in range(L))
        inp = [0] * (8 * L)
        for m in range(L): setf(inp, m * 8, 8, msg[m])
        v = run(inp, 1)
        got = "".join("%08x" % rd(v, w) for w in words)
        if got != hashlib.sha1(msg).hexdigest(): ok = False; break
    record("sha1", gates, depth_of(g, gates, out2), ok, cases, f"{L}-byte msg == hashlib.sha1")

# ================================ aes128 (datapath) ================================
def _aes_tables():
    p = 1; log = [0] * 256; alog = [0] * 256
    for i in range(255):
        alog[i] = p; log[p] = i
        p ^= (p << 1) ^ (0x11B if p & 0x80 else 0); p &= 0xFF
    alog[255] = alog[0]
    def inv(x): return 0 if x == 0 else alog[(255 - log[x]) % 255]
    sbox = []
    for x in range(256):
        y = inv(x); s = y
        for _ in range(4):
            y = ((y << 1) | (y >> 7)) & 0xFF; s ^= y
        sbox.append(s ^ 0x63)
    return sbox
SBOX = _aes_tables()
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
def aes_key_schedule(key):
    xw = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = list(xw[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]; t = [SBOX[x] for x in t]; t[0] ^= RCON[i // 4 - 1]
        xw.append([xw[i - 4][j] ^ t[j] for j in range(4)])
    rk = []
    for r in range(11):
        blk = []
        for c in range(4): blk += xw[r * 4 + c]
        rk.append(blk)
    return rk
def aes_encrypt(pt, key):
    rk = aes_key_schedule(key)
    s = [pt[i] ^ rk[0][i] for i in range(16)]
    def xt(a): return ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF
    for rnd in range(1, 11):
        s = [SBOX[x] for x in s]                             # SubBytes
        st = [[0] * 4 for _ in range(4)]                    # ShiftRows (column-major: s[row + 4*col])
        for i in range(16): st[i % 4][i // 4] = s[i]
        for r in range(4): st[r] = st[r][r:] + st[r][:r]
        s = [st[i % 4][i // 4] for i in range(16)]
        if rnd != 10:
            ns = [0] * 16
            for c in range(4):
                col = s[4 * c:4 * c + 4]
                ns[4 * c + 0] = xt(col[0]) ^ (xt(col[1]) ^ col[1]) ^ col[2] ^ col[3]
                ns[4 * c + 1] = col[0] ^ xt(col[1]) ^ (xt(col[2]) ^ col[2]) ^ col[3]
                ns[4 * c + 2] = col[0] ^ col[1] ^ xt(col[2]) ^ (xt(col[3]) ^ col[3])
                ns[4 * c + 3] = (xt(col[0]) ^ col[0]) ^ col[1] ^ col[2] ^ xt(col[3])
            s = ns
        s = [s[i] ^ rk[rnd][i] for i in range(16)]
    return bytes(s)

def flex_aes128(cases=4):
    # inputs: 128-bit plaintext + 11*128 round keys (precomputed host-side; datapath is all gates)
    NIN = 128 + 11 * 128
    g = CC.CircuitCompiler(NIN); IN = g.IN
    def byte_in(base, i): return [IN[base + i * 8 + b] for b in range(8)]
    pt = [byte_in(0, i) for i in range(16)]
    rk = [[byte_in(128 + r * 128, i) for i in range(16)] for r in range(11)]
    def xor8(x, y): return [g.XOR(x[k], y[k]) for k in range(8)]
    def sbox_gate(byte):
        sel = []
        for i in range(256):
            m = g.C1
            for j in range(8): m = g.AND(m, byte[j] if (i >> j) & 1 else g.NOT(byte[j]))
            sel.append(m)
        out = []
        for b in range(8):
            acc = g.C0
            for i in range(256):
                if (SBOX[i] >> b) & 1: acc = g.OR(acc, sel[i])
            out.append(acc)
        return out
    def xt(a):
        hi = a[7]; sh = [g.C0] + a[:7]
        return [g.XOR(sh[k], hi) if (0x1B >> k) & 1 else sh[k] for k in range(8)]
    s = [xor8(pt[i], rk[0][i]) for i in range(16)]
    for rnd in range(1, 11):
        s = [sbox_gate(x) for x in s]
        st = [[None] * 4 for _ in range(4)]
        for i in range(16): st[i % 4][i // 4] = s[i]
        for r in range(4): st[r] = st[r][r:] + st[r][:r]
        s = [st[i % 4][i // 4] for i in range(16)]
        if rnd != 10:
            ns = [None] * 16
            for c in range(4):
                col = s[4 * c:4 * c + 4]
                x2 = [xt(col[k]) for k in range(4)]
                x3 = [xor8(x2[k], col[k]) for k in range(4)]
                ns[4 * c + 0] = xor8(xor8(x2[0], x3[1]), xor8(col[2], col[3]))
                ns[4 * c + 1] = xor8(xor8(col[0], x2[1]), xor8(x3[2], col[3]))
                ns[4 * c + 2] = xor8(xor8(col[0], col[1]), xor8(x2[2], x3[3]))
                ns[4 * c + 3] = xor8(xor8(x3[0], col[1]), xor8(col[2], x2[3]))
            s = ns
        s = [xor8(s[i], rk[rnd][i]) for i in range(16)]
    outs = [w for byte in s for w in byte]
    run, out2, gates, _ = build_run(g, outs)
    bytef = [out2[i * 8:(i + 1) * 8] for i in range(16)]
    # validate the independent reference against the FIPS-197 known-answer vector first
    kat = aes_encrypt(bytes.fromhex("00112233445566778899aabbccddeeff"),
                      bytes.fromhex("000102030405060708090a0b0c0d0e0f"))
    assert kat.hex() == "69c4e0d86a7b0430d8cdb78070b4c55a", "reference AES wrong: " + kat.hex()
    ok = True
    for _ in range(cases):
        pt_b = bytes(random.getrandbits(8) for _ in range(16))
        key = bytes(random.getrandbits(8) for _ in range(16))
        rks = aes_key_schedule(key)
        inp = [0] * NIN
        for i in range(16): setf(inp, i * 8, 8, pt_b[i])
        for r in range(11):
            for i in range(16): setf(inp, 128 + r * 128 + i * 8, 8, rks[r][i])
        v = run(inp, 1)
        got = bytes(rd(v, f) for f in bytef)
        if got != aes_encrypt(pt_b, key): ok = False; break
    record("aes128", gates, depth_of(g, gates, out2), ok, cases, "1-block encrypt == ref AES")

def main():
    random.seed(7)
    print("\n  MUHLNICKEL FLEX BATTERY — new circuits, each verified byte-exact vs an independent reference\n", flush=True)
    for fn in (flex_mul32, flex_div32, flex_crc32, flex_rule110, flex_bitonic, flex_sha1, flex_aes128):
        t = time.time()
        try:
            fn()
            print(f"        ({time.time()-t:.1f}s)", flush=True)
        except Exception as ex:
            print(f"  [ERR ] {fn.__name__}: {type(ex).__name__}: {ex}", flush=True)
    npass = sum(1 for r in RESULTS if r[3])
    tot_g = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} circuits byte-exact · {tot_g:,} total gates fabricated ===", flush=True)

if __name__ == "__main__":
    main()
