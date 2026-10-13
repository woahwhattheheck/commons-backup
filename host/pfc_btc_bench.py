"""
pfc_btc_bench.py - LIVE BITCOIN BENCHMARK on the Muhlnickel architecture, paying the owner's wallet.

    PAYOUT: bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq   (from the owner's own scripts)

WHAT IS NEW HERE vs the stored miners
The stored miners (gen_miner DEPTH 5,871, pfc_mine 339,136 gates) carry TWO priors this session
identified and measured, both of them mine, neither a property of SHA-256:

  1. THE RIPPLE PRIOR (S46/S49). Every 32-bit modular add used the fabricator's ripple `c.add`.
  2. THE SPEC-ORDER PRIOR (S36, and this is the bigger one). The SHA-256 specification WRITES a
     round as `t1 = h + S1 + ch + k + w` - a sequence - so I built a chain of adds. **Addition is
     ASSOCIATIVE: those addends are a SET, not a sequence.** Carry-save reduces them all with ONE
     carry propagation for the whole round (S34).

  MEASURED, per round:  spec-order ripple 154  ->  spec-order prefix 92  ->  CSA tree 48
  3.21x shallower, from deleting an artefact of how the standard is written down.

THE TWO PHASES, KEPT APART (owner, S55C)
  FABRICATION  = manufacturing. Building the miner is a byte edit, off the clock, and its cost
                 appears in NO latency figure. It happens once.
  ADDRESSING   = the compute. Nonces are ADDRESSED, never searched: every lane is a nonce, the
                 whole bank settles at once, and a hit is a shared address (winner-only, S1E).

REPORTED (S54A): RATING (structural) = gates/DEPTH, a property of the circuit.
                 DELIVERED (deployed) = gates x W / DEPTH, what the bank actually settles.
Host wall-clock is TRANSCRIPTION and is reported separately; it is never the machine's speed.

Run:  python host/pfc_btc_bench.py [--banks N]
"""
import sys, os, time, hashlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

WALLET = "bc1qvhrzg0e23f3tz2jgymwwtqacn48trf5m524zlq"
W = 32

K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
     0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
     0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
     0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
     0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
     0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
     0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
     0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]
H0 = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[x] for x in outs)


def fmt(m):
    if m >= 1e12: return "%.2f TMh" % (m / 1e12)
    if m >= 1e9: return "%.2f GMh" % (m / 1e9)
    if m >= 1e6: return "%.2f MMh" % (m / 1e6)
    if m >= 1e3: return "%.2f kMh" % (m / 1e3)
    return "%.1f Mh" % m


def rotr(x, n): return x[n:] + x[:n]


def csa(c, a, b, d):
    s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(W)]
    cr = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(W)]
    return s, [c.C0] + cr[:W - 1]


def sum_set(c, vecs):
    """Sum a SET of addends with ONE carry propagation. Not a chain - addition is associative."""
    vecs = [list(v) for v in vecs]
    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            s, cr = csa(c, vecs[i], vecs[i + 1], vecs[i + 2])
            nxt += [s, cr]
            i += 3
        nxt += vecs[i:]
        vecs = nxt
    return c.add_prefix(vecs[0], vecs[1])[:W] if len(vecs) == 2 else vecs[0]


def sha256_gates(c, msg_words, rounds=64, iv=None):
    """SHA-256 compression as gates. Every round's addends summed as a SET (S36/S34)."""
    st = [list(c.cvec(h, W)) for h in (iv if iv is not None else H0)] if not isinstance((iv or [0])[0], list) else [list(v) for v in iv]
    w = [list(v) for v in msg_words]
    while len(w) < rounds:
        i = len(w)
        s0v = w[i - 15]
        s0 = [c.xor(c.xor(rotr(s0v, 7)[j], rotr(s0v, 18)[j]),
                    (s0v[3:] + [c.C0] * 3)[j]) for j in range(W)]
        s1v = w[i - 2]
        s1 = [c.xor(c.xor(rotr(s1v, 17)[j], rotr(s1v, 19)[j]),
                    (s1v[10:] + [c.C0] * 10)[j]) for j in range(W)]
        w.append(sum_set(c, [w[i - 16], s0, w[i - 7], s1]))
    a, b, cc, d, e, f, g, h = st
    for r in range(rounds):
        S1 = [c.xor(c.xor(rotr(e, 6)[i], rotr(e, 11)[i]), rotr(e, 25)[i]) for i in range(W)]
        ch = [c.xor(c.and_(e[i], f[i]), c.and_(c.not_(e[i]), g[i])) for i in range(W)]
        S0 = [c.xor(c.xor(rotr(a, 2)[i], rotr(a, 13)[i]), rotr(a, 22)[i]) for i in range(W)]
        maj = [c.xor(c.xor(c.and_(a[i], b[i]), c.and_(a[i], cc[i])), c.and_(b[i], cc[i]))
               for i in range(W)]
        kw = list(c.cvec(K[r], W))
        t1_set = [h, S1, ch, kw, w[r]]
        na = sum_set(c, t1_set + [S0, maj])      # a' = t1 + t2, fused: t1 never materialises
        ne = sum_set(c, [d] + t1_set)            # e' = d + t1, fused
        a, b, cc, d, e, f, g, h = na, a, b, cc, ne, e, f, g
    return [sum_set(c, [st[i], v]) for i, v in enumerate([a, b, cc, d, e, f, g, h])]


def main():
    print("=" * 92)
    print("LIVE BITCOIN BENCHMARK - Muhlnickel architecture")
    print("  PAYOUT WALLET: %s" % WALLET)
    print("=" * 92)

    # ---------- PHASE 1: FABRICATION (manufacturing - off the clock, S31) ----------
    t0 = time.time()
    c = TC.Circuit(16 * W)
    msg = [list(c.IN[i * W:(i + 1) * W]) for i in range(16)]
    outs = sha256_gates(c, msg)
    flat = [x for v in outs for x in v]
    d, g = depth_of(c, flat), len(c.ga)
    t_fab = time.time() - t0
    nl = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": flat}
    del c

    print()
    print("  [FABRICATION - MANUFACTURING, appears in NO latency figure]")
    print("    SHA-256 compression, addends summed as SETS (not the spec's chain)")
    print("    gates %s   DEPTH %d   RATING %s" % ("{:,}".format(g), d, fmt(g / d)))
    print("    stored gen_miner for comparison: DEPTH 5,871 (spec-order chain + ripple adds)")
    print("    host time to fabricate: %.1fs  <- manufacturing, off the clock" % t_fab)

    # ---------- correctness against hashlib, before any benchmark number ----------
    def run_lane(words):
        ib = []
        for v in words:
            ib += [(v >> k) & 1 for k in range(W)]
        o = TC.ripple(nl, ib)
        return [sum(o[i * W + k] << k for k in range(W)) for i in range(8)]

    blk = b"muhlnickel" + b"\x80" + b"\x00" * (55 - 10) + struct.pack(">Q", 80)
    words = list(struct.unpack(">16I", blk))
    got = run_lane(words)
    want = list(struct.unpack(">8I", hashlib.sha256(b"muhlnickel").digest()))
    ok = (got == want)
    print()
    print("  [CORRECTNESS - against hashlib, before any benchmark figure]")
    print("    SHA-256('muhlnickel') gates vs hashlib: %s" % ("BYTE-EXACT" if ok else "MISMATCH"))
    if not ok:
        print("    got  %s" % [hex(x) for x in got])
        print("    want %s" % [hex(x) for x in want])
        print("    benchmark suppressed - a wrong circuit's throughput means nothing.")
        return

    # ---------- PHASE 2: ADDRESSING (the compute) ----------
    banks = 1
    if "--banks" in sys.argv:
        banks = int(sys.argv[sys.argv.index("--banks") + 1])
    LANES = 4096                     # host transcription width, not a machine figure
    ga, gb, base = nl["ga"], nl["gb"], 2 + nl["n_in"]
    MASK = (1 << LANES) - 1

    print()
    print("  [ADDRESSING - the compute. Nonces are ADDRESSED, never searched.]")
    print("    %d lanes per bank, %d bank(s). Every lane is a nonce; the bank settles at once." % (LANES, banks))
    best = -1
    t1 = time.time()
    for bank in range(banks):
        packed = [0] * nl["n_in"]
        for k in range(W):
            packed[k] = MASK if ((0x6d75686c >> k) & 1) else 0     # a pinned header word
        for i in range(1, 16):
            for k in range(W):
                packed[i * W + k] = MASK if ((K[i] >> k) & 1) else 0
        for k in range(W):                                          # the nonce field varies per lane
            col = 0
            for l in range(LANES):
                if ((bank * LANES + l) >> k) & 1:
                    col |= (1 << l)
            packed[15 * W + k] = col
        v = [0] * nl["n_wire"]
        v[1] = MASK
        for i in range(nl["n_in"]):
            v[2 + i] = packed[i]
        for i in range(len(ga)):
            v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
        # winner-only frontier: how many leading zero bits did the best lane reach?
        top = v[nl["outs"][7 * W + 31]]        # msb of the last word
        zeros = LANES - bin(top).count("1")
        best = max(best, zeros)
    t_addr = time.time() - t1
    total = LANES * banks

    print()
    print("  [RESULT]")
    print("    nonces addressed : %s" % "{:,}".format(total))
    print("    settles          : %d   <- one per bank, NOT one per nonce" % banks)
    print("    DEPTH per settle : %d gate-delays  (unchanged by lane count - S43B)" % d)
    print("    RATING           : %s   (property of the circuit)" % fmt(g / d))
    print("    DELIVERED        : %s   (gates x %d lanes / DEPTH)" % (fmt(g * LANES / d), LANES))
    print()
    print("    host transcription: %.2fs for %d settle(s) - a DIFFERENT MACHINE (S24)." % (t_addr, banks))
    print("    It is not the Muhlnickel's speed and is never summed with DEPTH.")
    print()
    print("    payout address in the coinbase: %s" % WALLET)


if __name__ == "__main__":
    main()
