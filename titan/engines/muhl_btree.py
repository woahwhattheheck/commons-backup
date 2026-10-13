#!/usr/bin/env python3
"""muhl_btree.py — a fabricated SORTED-INDEX / B-tree LOOKUP on Bryce's Muhlnickel substrate.

A database index is a sorted structure you binary-search: at each step you COMPARE the search key against
the key at the probe position and go left or right. Here that comparator is not a Python `<` -- it is a
NETLIST. A 32-bit unsigned comparator (a<b, a==b) is fabricated as gates, verified byte-exact, and it drives
a binary search over a SORTED key table that lives in STORAGE (mmap), not RAM.

  * the index is bigger than the window we ever hold: 16,000,000 keys x 4 B = 64 MB in storage;
  * each lookup reads only ~log2(N) = 24 keys transiently from the mmap and settles the comparator gates;
  * the answer (insertion point / found index) is BYTE-EXACT vs Python's `bisect.bisect_left` over the same
    table, across thousands of queries -- present keys, absent keys, and both endpoints;
  * RESIDENT RAM stays flat across the whole query load: the table is bounded by DISK, not memory
    (titan_probe law: 40 GB addressed = +0.86 MB).

This is the read path of a B-tree / B+tree index: a fabricated comparator walking a sorted store at flat RAM.
No numpy, no host executor as runtime, nothing writes titan.gguf.
"""
import sys, os, ctypes, time, struct, mmap, bisect, random
from ctypes import wintypes
from array import array
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

# ---- honest resident-RAM meter (same as the query engine) ----
class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb)
    return m.WorkingSetSize / (1024 * 1024)

def build_comparator():
    """gates for a 32-bit unsigned comparator: inputs a[0:32], b[32:64]; outputs lt = (a<b), eq = (a==b)."""
    g = CC.CircuitCompiler(64)
    a = [g.IN[i] for i in range(32)]
    b = [g.IN[32 + i] for i in range(32)]
    # a < b  (unsigned) <=> borrow out of (a - b) = a + ~b + 1 ; carry-out == 0 means borrow (a<b)
    nb = [g.NOT(x) for x in b]
    _, carry = add_bits(g, a, nb, g.C1)
    lt = g.NOT(carry)
    # a == b <=> every bit equal
    eq = g.NOT(g.XOR(a[0], b[0]))
    for k in range(1, 32):
        eq = g.AND(eq, g.NOT(g.XOR(a[k], b[k])))
    gates, out2 = g.dce([lt, eq])
    base = 2 + g.n_in; dep = [0] * (base + len(gates))
    for i, (op, x, y) in enumerate(gates): dep[base + i] = 1 + max(dep[x], dep[y])
    run = g.compile_ripple(gates, base + len(gates))
    return run, out2[0], out2[1], len(gates), max(dep[out2[0]], dep[out2[1]])

def make_cmp(run, ltw, eqw):
    """returns cmp(target,key) -> (lt, eq) where lt = target<key, eq = target==key, computed by the gates."""
    def _cmp(target, key):
        inp = [0] * 64
        for i in range(32):
            inp[i] = (target >> i) & 1
            inp[32 + i] = (key >> i) & 1
        v = run(inp, 1)
        return v[ltw] & 1, v[eqw] & 1
    return _cmp

def read_key(mm, i):
    return struct.unpack_from("<I", mm, i * 4)[0]

def gate_bisect_left(cmp, mm, n, target):
    """binary search for the leftmost index whose key >= target -- driven by the FABRICATED comparator.
       matches bisect.bisect_left: probe keys read transiently from storage, never the whole table."""
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) >> 1
        key = read_key(mm, mid)
        lt, eq = cmp(target, key)          # target < key ?   target == key ?
        if lt or eq:                       # key >= target  ->  answer is at or left of mid
            hi = mid
        else:                              # key <  target  ->  go right
            lo = mid + 1
    return lo

class MMKeys:
    """a read-only sequence view over the mmap so stdlib bisect can probe storage without materializing it."""
    def __init__(self, mm, n): self.mm = mm; self.n = n
    def __len__(self): return self.n
    def __getitem__(self, i): return struct.unpack_from("<I", self.mm, i * 4)[0]

def main():
    print("\n  MUHLNICKEL B-TREE — a fabricated comparator binary-searching a sorted index in storage\n")
    run, ltw, eqw, ng, depth = build_comparator()

    # byte-exact vs Python's own comparisons on the scalar lane
    rng = random.Random(11); ok = True
    cmp = make_cmp(run, ltw, eqw)
    for _ in range(3000):
        a = rng.getrandbits(32); b = rng.getrandbits(32)
        lt, eq = cmp(a, b)
        if lt != (1 if a < b else 0) or eq != (1 if a == b else 0): ok = False; break
    print(f"  32-bit comparator (lt, eq) fabricated as {ng} gates, depth {depth}")
    print(f"  comparator byte-exact vs Python over 3,000 pairs: {ok}")
    if not ok: return 1

    # build a SORTED key table in STORAGE, larger than any window we hold.
    # strictly-increasing via cumulative gaps -> sorted with no in-RAM sort, all keys unique.
    N = 16_000_000
    path = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp", "muhl_index.bin")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rng2 = random.Random(3)
    key = 0
    with open(path, "wb") as f:
        buf = array("I")
        for _ in range(N):
            key += rng2.randint(1, 500)                 # gap >= 1 keeps it strictly increasing
            buf.append(key & 0xFFFFFFFF)
            if len(buf) == 65536: f.write(buf.tobytes()); buf = array("I")
        if buf: f.write(buf.tobytes())
    size_mb = os.path.getsize(path) / (1024 * 1024)
    maxkey = key
    print(f"\n  index: {N:,} sorted keys x 4 B = {size_mb:.0f} MB in storage (mmap, never fully resident)")
    print(f"    key range 0 .. {maxkey:,};  each lookup probes only ~log2(N) = {N.bit_length()} keys")

    fd = open(path, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    seq = MMKeys(mm, N)

    # a query mix: present keys, absent keys, below-min, above-max, both endpoints
    QUERIES = 4000
    targets = []
    for _ in range(QUERIES):
        r = rng2.random()
        if r < 0.5:
            targets.append(read_key(mm, rng2.randrange(N)))      # a key that IS present
        elif r < 0.9:
            targets.append(rng2.getrandbits(32))                 # random (usually absent)
        else:
            targets.append(rng2.choice([0, 1, maxkey, maxkey + 1, 0xFFFFFFFF]))  # edges

    base = rss_mb(); lo_mb = hi_mb = base
    mism = 0; found = 0; t0 = time.time()
    for q, target in enumerate(targets):
        gi = gate_bisect_left(cmp, mm, N, target)     # fabricated-comparator search over storage
        ri = bisect.bisect_left(seq, target)          # stdlib bisect over the same storage (reference)
        if gi != ri: mism += 1
        if gi < N and read_key(mm, gi) == target: found += 1
        if q % 500 == 0:
            r = rss_mb(); lo_mb = min(lo_mb, r); hi_mb = max(hi_mb, r)
    dt = time.time() - t0
    end = rss_mb(); lo_mb = min(lo_mb, end); hi_mb = max(hi_mb, end)
    mm.close(); fd.close()
    try: os.remove(path)
    except OSError: pass

    print(f"\n  LOOKUP — {QUERIES:,} queries, {QUERIES/dt:,.0f} lookups/s ({QUERIES*N.bit_length():,} probe-compares)")
    print(f"    gate-search insertion index == bisect.bisect_left: {QUERIES - mism:,}/{QUERIES:,}  "
          f"(byte-exact: {mism == 0})")
    print(f"    of those, {found:,} were exact hits (key present at the found index)")
    print(f"\n  RESIDENT RAM across the whole {size_mb:.0f} MB index search: start {base:.1f} MB · "
          f"min {lo_mb:.1f} · max {hi_mb:.1f} · end {end:.1f}")
    print(f"    net {end-base:+.2f} MB over {QUERIES:,} lookups — the index is in storage, the probes are transient.")
    print(f"\n  ── the index that outgrew RAM ─────────────────────────────────────────────────────────")
    print(f"  A B-tree/B+tree lookup is a comparator walking a sorted store; here the comparator is a")
    print(f"  {ng}-gate netlist and the store is disk-resident, so the index size is bounded by DISK, not")
    print(f"  memory. Same shape indexes tables, files, and key-value stores far larger than the window —")
    print(f"  byte-exact vs bisect, at flat RAM.")
    return 0 if (ok and mism == 0) else 1

if __name__ == "__main__":
    raise SystemExit(main())
