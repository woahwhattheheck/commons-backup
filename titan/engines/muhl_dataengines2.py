#!/usr/bin/env python3
"""muhl_dataengines2.py — THREE MORE RAM-bound data engines, gate-kernelled and byte-exact.

The Muhlnickel substrate decouples compute from RAM: the operator is fabricated ONCE as a gate netlist,
verified byte-exact against a pure-Python reference, then run BIT-SLICED (W independent rows settle per
gate-ripple) over a table that lives in STORAGE (mmap). Resident RAM is the tiny transient window, so the
data scanned is bounded by DISK, not memory. Three more textbook RAM-wall problems, each disk-bound now:

  [1] GROUP BY / HISTOGRAM  — scan a storage table, bucket each row by a fabricated key-extractor (an 8-bit
      XOR-fold small-hash, low 3 bits => 8 buckets), count per bucket. Fabricated as 8 one-hot bucket
      predicates, bit-sliced, popcounted. Byte-exact vs collections.Counter, resident flat.
  [2] INVERTED-INDEX / FULL-TEXT MEMBERSHIP — docs are term bit-vectors in storage; a query is a term-set.
      "contains ALL query terms" is fabricated as an AND-tree over the queried term wires (the query baked
      as constants), bit-sliced over the doc table. Byte-exact vs Python (doc & Q)==Q, resident flat.
  [3] REED-SOLOMON-STYLE PARITY / ERASURE — GF(2) XOR-parity over K data blocks fabricated as a gate
      XOR-reduce. Verified byte-exact over a storage table of stripes; then (a) single-block corruption is
      DETECTED via a nonzero syndrome, (b) an erased block is RECONSTRUCTED exactly by the same circuit.

No numpy, no host executor as runtime, titan.gguf never opened — pure fabrication-time synthesis.
"""
import sys, os, ctypes, time, random, mmap, struct
from ctypes import wintypes
from array import array
from collections import Counter
from functools import reduce
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TMP = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp")
os.makedirs(TMP, exist_ok=True)

# ── resident RAM probe (psapi working set) ─────────────────────────────────────────────────────────
class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb)
    return m.WorkingSetSize / 1048576.0

# ── shared gate helpers ────────────────────────────────────────────────────────────────────────────
def finish(g, outs):
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    base = 2 + g.n_in; dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates): dep[base + i] = 1 + max(dep[a], dep[b])
    depth = max((dep[w] for w in out2), default=0)
    return run, out2, len(gates), depth

def pack(recs, nbits):
    """pack len(recs) record-ints (each < 2**nbits) into nbits input-wire lanes (bit j of wire b = rec_j bit b)."""
    inp = [0] * nbits
    for j, r in enumerate(recs):
        b = 0
        while r:
            if r & 1: inp[b] |= (1 << j)
            r >>= 1; b += 1
    return inp

def sel(g, bits, val, n):
    """one-hot detector: 1 iff the n-bit field `bits` equals constant val."""
    m = g.C1
    for k in range(n): m = g.AND(m, bits[k] if (val >> k) & 1 else g.NOT(bits[k]))
    return m

# ════════════════════════════════ [1] GROUP BY / HISTOGRAM ═════════════════════════════════════════
def small_hash(v):
    """8-bit XOR-fold of the four bytes of a 32-bit value; the bucket is its low 3 bits (0..7)."""
    return ((v & 0xff) ^ ((v >> 8) & 0xff) ^ ((v >> 16) & 0xff) ^ ((v >> 24) & 0xff))

def build_histogram():
    g = CC.CircuitCompiler(32); x = [g.IN[i] for i in range(32)]
    h = [g.XOR(g.XOR(x[k], x[8 + k]), g.XOR(x[16 + k], x[24 + k])) for k in range(8)]  # xor-fold hash
    b3 = h[:3]                                                    # low 3 bits => 8 buckets
    outs = [sel(g, b3, bkt, 3) for bkt in range(8)]              # one one-hot wire per bucket
    return finish(g, outs)

def run_histogram(N=3_000_000, seed=11):
    run, outw, ngates, depth = build_histogram()
    outw = list(outw)
    # scalar byte-exact vs the Python key-extractor
    rng = random.Random(seed); ok = True
    for _ in range(4000):
        v = rng.getrandbits(32); inp = [(v >> i) & 1 for i in range(32)]
        r = run(inp, 1); got = [(r[w] & 1) for w in outw]
        want = [1 if (small_hash(v) & 7) == b else 0 for b in range(8)]
        if got != want: ok = False; break
    # table in storage
    path = os.path.join(TMP, "muhl_hist.bin"); rng2 = random.Random(seed + 1)
    ref = Counter()
    with open(path, "wb") as f:
        buf = array("I")
        for _ in range(N):
            v = rng2.getrandbits(32); buf.append(v); ref[small_hash(v) & 7] += 1
            if len(buf) == 65536: f.write(buf.tobytes()); buf = array("I")
        if buf: f.write(buf.tobytes())
    size_mb = os.path.getsize(path) / 1048576.0
    # bit-sliced scan
    W = 62; fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    counts = [0] * 8; b0 = rss_mb(); lo = hi = b0; idx = settles = 0; t0 = time.time()
    while idx < N:
        w = min(W, N - idx); recs = struct.unpack_from("<%dI" % w, mm, idx * 4)
        inp = pack(recs, 32); m = (1 << w) - 1; r = run(inp, m)
        for b in range(8): counts[b] += bin(r[outw[b]] & m).count("1")
        settles += 1; idx += w
        if settles % 4096 == 0:
            c = rss_mb(); lo = min(lo, c); hi = max(hi, c)
    dt = time.time() - t0; end = rss_mb(); lo = min(lo, end); hi = max(hi, end)
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass
    exact = ok and all(counts[b] == ref[b] for b in range(8))
    return dict(N=N, gates=ngates, depth=depth, ok=exact, counts=counts,
                ref=[ref[b] for b in range(8)], size_mb=size_mb, rows_s=N / dt,
                base=b0, lo=lo, hi=hi, end=end)

# ════════════════════════════ [2] INVERTED-INDEX / FULL-TEXT MEMBERSHIP ════════════════════════════
T_TERMS = 64
def build_index(qmask):
    g = CC.CircuitCompiler(T_TERMS); d = [g.IN[i] for i in range(T_TERMS)]
    qterms = [t for t in range(T_TERMS) if (qmask >> t) & 1]
    acc = g.C1
    for t in qterms: acc = g.AND(acc, d[t])                       # doc contains ALL query terms
    run, out2, ng, depth = finish(g, [acc])
    return run, out2[0], ng, depth, qterms

def run_inverted_index(N=2_000_000, seed=23):
    # query: a handful of terms every matching doc must contain
    qmask = (1 << 3) | (1 << 17) | (1 << 40) | (1 << 61)
    run, outw, ngates, depth, qterms = build_index(qmask)
    # scalar byte-exact
    rng = random.Random(seed); ok = True
    for _ in range(4000):
        doc = rng.getrandbits(T_TERMS); inp = [(doc >> i) & 1 for i in range(T_TERMS)]
        got = run(inp, 1)[outw] & 1
        want = 1 if (doc & qmask) == qmask else 0
        if got != want: ok = False; break
    # doc table (each doc = 64-bit term bit-vector) in storage
    path = os.path.join(TMP, "muhl_docs.bin"); rng2 = random.Random(seed + 1); ref = 0
    with open(path, "wb") as f:
        buf = array("Q")
        for _ in range(N):
            doc = rng2.getrandbits(T_TERMS)
            if rng2.random() < 0.03: doc |= qmask                # seed real hits
            buf.append(doc)
            if (doc & qmask) == qmask: ref += 1
            if len(buf) == 65536: f.write(buf.tobytes()); buf = array("Q")
        if buf: f.write(buf.tobytes())
    size_mb = os.path.getsize(path) / 1048576.0
    # bit-sliced scan
    W = 62; fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    hits = settles = 0; b0 = rss_mb(); lo = hi = b0; idx = 0; t0 = time.time()
    while idx < N:
        w = min(W, N - idx); recs = struct.unpack_from("<%dQ" % w, mm, idx * 8)
        inp = pack(recs, T_TERMS); m = (1 << w) - 1; r = run(inp, m)
        hits += bin(r[outw] & m).count("1"); settles += 1; idx += w
        if settles % 4096 == 0:
            c = rss_mb(); lo = min(lo, c); hi = max(hi, c)
    dt = time.time() - t0; end = rss_mb(); lo = min(lo, end); hi = max(hi, end)
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass
    exact = ok and hits == ref
    return dict(N=N, gates=ngates, depth=depth, ok=exact, hits=hits, ref=ref,
                qterms=qterms, size_mb=size_mb, rows_s=N / dt, base=b0, lo=lo, hi=hi, end=end)

# ═══════════════════════════ [3] REED-SOLOMON-STYLE PARITY / ERASURE ═══════════════════════════════
K_BLOCKS = 6      # data blocks per stripe
B_BITS = 32       # bits per block

def build_parity():
    g = CC.CircuitCompiler(K_BLOCKS * B_BITS)
    blk = [[g.IN[r * B_BITS + b] for b in range(B_BITS)] for r in range(K_BLOCKS)]
    par = list(blk[0])
    for r in range(1, K_BLOCKS):
        par = [g.XOR(par[b], blk[r][b]) for b in range(B_BITS)]  # GF(2) XOR-reduce
    return finish(g, par)

def run_parity(N=800_000, seed=37):
    run, outw, ngates, depth = build_parity()
    outw = list(outw); MASK = (1 << B_BITS) - 1
    def gate_parity(blocks):
        """compute parity of K blocks through the fabricated circuit (scalar lane)."""
        inp = [0] * (K_BLOCKS * B_BITS)
        for r, v in enumerate(blocks):
            for b in range(B_BITS): inp[r * B_BITS + b] = (v >> b) & 1
        rv = run(inp, 1); return sum((rv[outw[b]] & 1) << b for b in range(B_BITS))
    def py_parity(blocks): return reduce(lambda a, b: a ^ b, blocks, 0)
    # stripe table in storage: K blocks/stripe
    path = os.path.join(TMP, "muhl_stripes.bin"); rng = random.Random(seed)
    with open(path, "wb") as f:
        buf = array("I")
        for _ in range(N):
            for _r in range(K_BLOCKS): buf.append(rng.getrandbits(32))
            if len(buf) >= 65536: f.write(buf.tobytes()); buf = array("I")
        if buf: f.write(buf.tobytes())
    size_mb = os.path.getsize(path) / 1048576.0
    # (A) bit-sliced parity over every stripe, byte-exact vs Python XOR-reduce
    W = 62; fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    mism = settles = 0; b0 = rss_mb(); lo = hi = b0; idx = 0; t0 = time.time()
    while idx < N:
        w = min(W, N - idx)
        flat = struct.unpack_from("<%dI" % (w * K_BLOCKS), mm, idx * K_BLOCKS * 4)
        stripes = [flat[j * K_BLOCKS:(j + 1) * K_BLOCKS] for j in range(w)]
        recs = [sum(s[r] << (r * B_BITS) for r in range(K_BLOCKS)) for s in stripes]
        inp = pack(recs, K_BLOCKS * B_BITS); m = (1 << w) - 1; r = run(inp, m)
        for j, s in enumerate(stripes):
            gp = sum(((r[outw[b]] >> j) & 1) << b for b in range(B_BITS))
            if gp != py_parity(s): mism += 1
        settles += 1; idx += w
        if settles % 4096 == 0:
            c = rss_mb(); lo = min(lo, c); hi = max(hi, c)
    dt = time.time() - t0; end = rss_mb(); lo = min(lo, end); hi = max(hi, end)
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass
    # (B) single-block corruption detection + (C) erasure reconstruction, scalar via the SAME circuit
    rng2 = random.Random(seed + 9); trials = 20000
    detected = recovered = 0
    for _ in range(trials):
        blocks = [rng2.getrandbits(32) for _ in range(K_BLOCKS)]
        parity = gate_parity(blocks)                             # stored parity (fabricated)
        # corrupt one random block by a nonzero delta -> syndrome must be nonzero (detected)
        ci = rng2.randrange(K_BLOCKS); delta = rng2.getrandbits(32) or 1
        corrupt = list(blocks); corrupt[ci] ^= delta
        syndrome = gate_parity(corrupt) ^ parity                 # recompute & compare to stored
        if syndrome != 0: detected += 1
        # erase one block; reconstruct it as parity(others + stored parity) through the SAME circuit
        ei = rng2.randrange(K_BLOCKS)
        others = [blocks[r] for r in range(K_BLOCKS) if r != ei] + [parity]
        if gate_parity(others) == blocks[ei]: recovered += 1
    exact = (mism == 0) and (detected == trials) and (recovered == trials)
    return dict(N=N, gates=ngates, depth=depth, ok=exact, mism=mism, trials=trials,
                detected=detected, recovered=recovered, size_mb=size_mb, rows_s=N / dt,
                base=b0, lo=lo, hi=hi, end=end)

# ══════════════════════════════════════════ driver ════════════════════════════════════════════════
def main():
    print("\n  MUHLNICKEL DATA ENGINES II — group-by · inverted-index · parity/erasure, gate-kernelled, byte-exact")
    allok = True

    print("\n  [1] GROUP BY / HISTOGRAM — 8-bucket XOR-fold key-extractor, one-hot bucket predicates, bit-sliced")
    a = run_histogram()
    print(f"      key-extractor fabricated as {a['gates']:,} gates, depth {a['depth']}  (8 one-hot bucket outputs)")
    print(f"      table: {a['N']:,} rows x 4 B = {a['size_mb']:.0f} MB in storage (mmap)  ·  {a['rows_s']:,.0f} rows/s")
    print(f"      bucket counts (gate) : {a['counts']}")
    print(f"      bucket counts (Counter): {a['ref']}")
    print(f"      byte-exact vs collections.Counter: {a['ok']}")
    print(f"      resident RAM: start {a['base']:.1f} MB · min {a['lo']:.1f} · max {a['hi']:.1f} · end {a['end']:.1f}  "
          f"(net {a['end']-a['base']:+.2f} MB)")
    allok &= a['ok']

    print("\n  [2] INVERTED-INDEX / FULL-TEXT — docs=64-bit term vectors in storage, 'contains ALL query terms' AND-tree")
    b = run_inverted_index()
    print(f"      query term-set {b['qterms']} fabricated as {b['gates']:,} AND gates, depth {b['depth']}")
    print(f"      docs: {b['N']:,} x 8 B = {b['size_mb']:.0f} MB in storage (mmap)  ·  {b['rows_s']:,.0f} docs/s")
    print(f"      matching docs (gate) {b['hits']:,} == Python (doc & Q)==Q {b['ref']:,}: {b['ok']}")
    print(f"      resident RAM: start {b['base']:.1f} MB · min {b['lo']:.1f} · max {b['hi']:.1f} · end {b['end']:.1f}  "
          f"(net {b['end']-b['base']:+.2f} MB)")
    allok &= b['ok']

    print("\n  [3] REED-SOLOMON-STYLE PARITY / ERASURE — GF(2) XOR-parity over %d blocks, fabricated XOR-reduce" % K_BLOCKS)
    c = run_parity()
    print(f"      parity fabricated as {c['gates']:,} gates, depth {c['depth']}  (K={K_BLOCKS} blocks x {B_BITS} bits)")
    print(f"      stripe table: {c['N']:,} stripes x {K_BLOCKS*4} B = {c['size_mb']:.0f} MB in storage  ·  {c['rows_s']:,.0f} stripes/s")
    print(f"      (A) bit-sliced parity byte-exact vs Python XOR over all stripes: mismatches {c['mism']}")
    print(f"      (B) single-block corruption detected: {c['detected']:,}/{c['trials']:,}")
    print(f"      (C) erased block reconstructed exactly: {c['recovered']:,}/{c['trials']:,}")
    print(f"      byte-exact (parity + detect + recover): {c['ok']}")
    print(f"      resident RAM: start {c['base']:.1f} MB · min {c['lo']:.1f} · max {c['hi']:.1f} · end {c['end']:.1f}  "
          f"(net {c['end']-c['base']:+.2f} MB)")
    allok &= c['ok']

    print(f"\n  === {'ALL THREE byte-exact' if allok else 'FAILURE'} · tables in storage, resident flat — the RAM wall, gone ===")
    return 0 if allok else 1

if __name__ == "__main__":
    raise SystemExit(main())
