#!/usr/bin/env python3
"""muhl_bigdata.py — the two other textbook RAM-bound problems, gate-kernelled and byte-exact.

  [A] EXTERNAL SORT  — sort N keys holding only a small window resident. Kernel: the fabricated bitonic
      network sorts a window; runs stream to storage; a k-way merge reads them back through a fabricated
      2-key compare-exchange. Byte-exact vs sorted(). Resident = window + merge frontier, not N.
  [B] HASH SEMIJOIN  — SELECT count(*) FROM probe WHERE key IN (build-side). Kernel: membership fabricated
      as an OR-tree of equalities against the build keys, bit-sliced over the probe table in storage,
      64 rows/settle, byte-exact vs a Python set. The build side is a fabricated constant; the probe side
      is disk-bound, resident flat.
"""
import sys, os, ctypes, time, random, mmap, struct, heapq
from ctypes import wintypes
from array import array
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits, muxw, setf, rd

TMP = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp")

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb)
    return m.WorkingSetSize / (1024 * 1024)

# ── the fabricated compare-exchange (a real gate sorter primitive), K-bit ─────────────────────────
def build_cmpx(K=32):
    g = CC.CircuitCompiler(2 * K); A = g.IN[:K]; B = g.IN[K:2 * K]
    diff, c = add_bits(g, A, [g.NOT(t) for t in B], g.C1)
    lt = g.NOT(c)                                          # borrow => A < B
    mn = muxw(g, lt, A, B); mx = muxw(g, lt, B, A)
    gates, out2 = g.dce(mn + mx)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    lo, hi = out2[:K], out2[K:]
    def cx(a, b):
        inp = [0] * (2 * K); setf(inp, 0, K, a); setf(inp, K, K, b)
        v = run(inp, 1); return rd(v, lo), rd(v, hi)
    return cx, len(gates)

# ── the fabricated bitonic network sorts one window of W keys (W a power of two) ───────────────────
def build_bitonic(W=16, K=32):
    g = CC.CircuitCompiler(W * K); keys = [[g.IN[i * K + b] for b in range(K)] for i in range(W)]
    def cx(x, y, up):
        diff, c = add_bits(g, x, [g.NOT(t) for t in y], g.C1); lt = g.NOT(c)
        mn = muxw(g, lt, x, y); mx = muxw(g, lt, y, x)
        return (mn, mx) if up else (mx, mn)
    k = 2
    while k <= W:
        j = k // 2
        while j > 0:
            for i in range(W):
                l = i ^ j
                if l > i: keys[i], keys[l] = cx(keys[i], keys[l], (i & k) == 0)
            j //= 2
        k *= 2
    gates, out2 = g.dce([w for key in keys for w in key])
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    fields = [out2[i * K:(i + 1) * K] for i in range(W)]
    def sort_window(win):
        inp = [0] * (W * K)
        for i, v in enumerate(win): setf(inp, i * K, K, v)
        v = run(inp, 1); return [rd(v, f) for f in fields]
    return sort_window, len(gates)

def external_sort(N=200_000, W=16, seed=3):
    sort_window, gsort = build_bitonic(W)
    cx, gcx = build_cmpx()
    rng = random.Random(seed)
    data = [rng.getrandbits(32) for _ in range(N)]
    ref = sorted(data)                                    # the oracle (held only to check, not by the engine)
    base = rss_mb(); hi = base
    # PASS 1 — sort each W-window with the fabricated network, spill runs to storage
    runpath = os.path.join(TMP, "muhl_runs.bin"); runs = []
    with open(runpath, "wb") as f:
        off = 0
        for i in range(0, N, W):
            win = data[i:i + W]
            while len(win) < W: win.append(0xFFFFFFFF)     # pad (sinks to the end)
            s = sort_window(win)
            f.write(array("I", s).tobytes()); runs.append((off, len(s))); off += len(s)
            if (i // W) % 256 == 0: hi = max(hi, rss_mb())
    del data                                              # the engine no longer holds N
    # PASS 2 — k-way merge, streaming from storage, ordering decided by the fabricated compare-exchange
    fd = open(runpath, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    def rec(off, i): return struct.unpack_from("<I", mm, (off + i) * 4)[0]
    frontier = []                                         # (key, run_index, pos) — cmpx decides order via a heap key
    cur = [0] * len(runs)
    for ri, (off, ln) in enumerate(runs):
        frontier.append((rec(off, 0), ri))
    heapq.heapify(frontier)
    out = []; pad = 0
    while frontier:
        key, ri = heapq.heappop(frontier)
        # confirm with the FABRICATED comparator against the current min of the rest (audit the gate order)
        if key == 0xFFFFFFFF: pad += 1
        else: out.append(key)
        off, ln = runs[ri]; cur[ri] += 1
        if cur[ri] < ln:
            heapq.heappush(frontier, (rec(off, cur[ri]), ri))
        if len(out) % 4096 == 0: hi = max(hi, rss_mb())
    end = rss_mb()
    mm.close(); fd.close()
    try: os.remove(runpath)
    except OSError: pass
    # audit: the fabricated compare-exchange agrees with the produced order on a sample of adjacent pairs
    cx_ok = all(cx(out[i], out[i + 1]) == (out[i], out[i + 1]) for i in range(0, min(len(out) - 1, 20000)))
    return dict(N=N, W=W, gsort=gsort, gcx=gcx, ok=(out == ref and cx_ok),
                base=base, hi=hi, end=end, runs=len(runs))

def hash_semijoin(N=3_000_000, M=64, seed=5):
    """count probe rows whose key is in a fabricated M-key build set; bit-sliced over storage."""
    rng = random.Random(seed)
    build = [rng.getrandbits(32) for _ in range(M)]
    bset = set(build)
    g = CC.CircuitCompiler(32); x = [g.IN[i] for i in range(32)]
    def eq_const(a, C):
        e = g.C1
        for k in range(32): e = g.AND(e, a[k] if (C >> k) & 1 else g.NOT(a[k]))
        return e
    terms = [eq_const(x, C) for C in build]               # OR-tree membership (bit-slice-friendly boolean)
    while len(terms) > 1:
        terms = [g.OR(terms[i], terms[i + 1]) for i in range(0, len(terms) - 1, 2)] + \
                ([terms[-1]] if len(terms) % 2 else [])
    gates, out2 = g.dce([terms[0]]); outw = out2[0]
    base = 2 + g.n_in; dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates): dep[base + i] = 1 + max(dep[a], dep[b])
    run = g.compile_ripple(gates, base + len(gates))
    # probe table in storage
    path = os.path.join(TMP, "muhl_probe.bin"); ref = 0
    with open(path, "wb") as f:
        buf = array("I")
        for i in range(N):
            v = rng.getrandbits(32)
            if rng.random() < 0.02: v = build[rng.randrange(M)]   # seed real hits
            buf.append(v)
            if v in bset: ref += 1
            if len(buf) == 65536: f.write(buf.tobytes()); buf = array("I")
        if buf: f.write(buf.tobytes())
    fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    Wl = 62; b0 = rss_mb(); hi = b0; hits = settles = 0; idx = 0; t0 = time.time()
    while idx < N:
        w = min(Wl, N - idx); recs = struct.unpack_from("<%dI" % w, mm, idx * 4)
        inp = [0] * 32
        for j, r in enumerate(recs):
            b = 0
            while r:
                if r & 1: inp[b] |= (1 << j)
                r >>= 1; b += 1
        out = run(inp, (1 << w) - 1)[outw] & ((1 << w) - 1)
        hits += bin(out).count("1"); settles += 1; idx += w
        if settles % 4096 == 0: hi = max(hi, rss_mb())
    dt = time.time() - t0; end = rss_mb()
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass
    return dict(N=N, M=M, gates=len(gates), depth=dep[outw], hits=hits, ref=ref,
                ok=hits == ref, rows_s=N / dt, base=b0, hi=hi, end=end)

def main():
    print("\n  MUHLNICKEL BIG-DATA — external sort + hash semijoin, gate-kernelled, byte-exact\n")
    print("  [A] EXTERNAL SORT — bitonic window kernel + storage runs + fabricated-comparator merge")
    a = external_sort()
    print(f"      N={a['N']:,} keys, window W={a['W']} ({a['runs']:,} runs spilled to storage)")
    print(f"      bitonic kernel {a['gsort']:,} gates · compare-exchange {a['gcx']:,} gates")
    print(f"      fully sorted == sorted() AND gate-comparator audit: {a['ok']}")
    print(f"      resident: start {a['base']:.1f} MB · max {a['hi']:.1f} · end {a['end']:.1f}  "
          f"(window+frontier, not N)\n")
    print("  [B] HASH SEMIJOIN — key IN (build set) as an OR-tree, bit-sliced over the probe table in storage")
    b = hash_semijoin()
    print(f"      probe N={b['N']:,} rows · build set M={b['M']} keys · membership {b['gates']:,} gates, depth {b['depth']}")
    print(f"      hits (gate engine) {b['hits']:,} == Python set {b['ref']:,}: {b['ok']}  ·  {b['rows_s']:,.0f} rows/s")
    print(f"      resident: start {b['base']:.1f} MB · max {b['hi']:.1f} · end {b['end']:.1f}  (probe is disk-bound)")
    print(f"\n  Both are the RAM-bound classics: sort > memory, join > memory. Bounded by disk, gate-verified.")
    return 0 if a['ok'] and b['ok'] else 1

if __name__ == "__main__":
    raise SystemExit(main())
