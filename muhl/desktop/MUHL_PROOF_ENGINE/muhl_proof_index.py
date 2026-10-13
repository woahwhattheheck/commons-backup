#!/usr/bin/env python3
"""muhl_proof_index.py -- SUPERSEDED for the scan itself. Kept for the INDEX+RANK idea.

    *** THE SCAN HERE IS HOST-SIDE. Use muhl_fab_scan_machine.py for the scan. ***

The index-and-rank framing is the owner's and it stands: retrieval returns the CHEAPEST
derivation rather than the first one stumbled upon. What does NOT stand is how the scan runs
here -- a host loop walking a window and bit-slicing rows, feeding a fabricated predicate.
`muhl_fab_scan_machine.py` compares every row in ONE settle instead, per his MMU's shape.

Kept under the vault model: the ranking idea is live, the scan mechanism is retired.

--- original header follows ---

muhl_proof_index.py -- PROOF SEARCH AS AN INDEX SCAN, NOT AN ENUMERATION.

Owner, 2026-08-06: **"substrate should search for optimal and fastest solve in the same way
google search does"**

Google does not enumerate the web when you type a query. It builds an INVERTED INDEX once,
then RETRIEVES against it and RANKS the hits. That is the instruction, and it is a different
machine from the forward-chaining prover in muhl_prover.py -- which enumerates, saturates, and
falls over (it hit a 20,000-term ceiling inside one round).

THE SHAPE IS THE OWNER'S OWN, NOT INVENTED HERE. `C:\\llm\\muhl_builds\\muhl_query_engine.py`
already does exactly this for a WHERE clause: fabricate the predicate ONCE as gates, verify it
byte-exact, then run it BIT-SLICED over a table that lives in STORAGE, ~62 rows per settle,
resident RAM flat while the table is arbitrarily large. Its own docstring names the target:
"inverted-index search". This applies that engine to proofs.

    INDEX   every derived formula -> (cost, rule, premise_a, premise_b), as fixed 16-byte rows
            in a storage-resident table.
    QUERY   a fabricated 32-bit equality predicate, gates, verified byte-exact.
    RETRIEVE bit-sliced scan, W rows per gate settle, only the window transient.
    RANK    minimum cost wins -- "optimal and fastest solve".

TWO INDEXES, because that is what makes retrieval cheap:
    BY_KEY   formula -> best derivation of it          (does this already exist, and how cheap)
    BY_ANTE  antecedent -> implications having it      (the MP join, the inverted index proper)

NO compile_ripple / one_pass. The owner's smoke_test asserts no shipped module calls them, and
they are the path that MemoryErrored. Bit-slicing uses Python ints as lanes, which is his
documented method ("Python ints as the bit-slice; NO numpy").

    python muhl_proof_index.py
"""
import ctypes, ctypes.wintypes as wt
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")

import titan_circuit as TC
import muhl_proofcheck as PC

ROW = 16                      # key u32 | cost u32 | rule_a u32 | b u32
LANES = 62                    # rows settled per gate ripple, matching his query engine


# ------------------------------------------------------------------ resident RAM, measured
class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]


_FN = None


def rss_mb():
    """restype/argtypes MUST be declared or the 64-bit handle truncates and this silently
    returns 0.0 — which would read as a flat-RAM result. That exact bug was shipped earlier
    today and corrected; it is not repeated here."""
    global _FN
    if _FN is None:
        _FN = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        _FN.restype = wt.BOOL
        _FN.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    m = PMC()
    m.cb = ctypes.sizeof(PMC)
    if not _FN(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(m), m.cb):
        return None
    return m.WorkingSetSize / (1024.0 * 1024.0)


# ------------------------------------------------------------------ the fabricated predicate
def build_eq32():
    """(x == K) over a 32-bit x, K supplied as 32 input bits too, so ONE fabricated circuit
    serves every query instead of baking a new one per goal. Verified byte-exact before use."""
    c = TC.Circuit(64)
    x = [c.IN[i] for i in range(32)]
    k = [c.IN[32 + i] for i in range(32)]
    same = [c.not_(c.xor(x[i], k[i])) for i in range(32)]
    out = c._tree_and(same)
    return c, [out]


def depth_of(c, outs):
    d = [0] * (2 + c.n_in + len(c.ga))
    for i in range(len(c.ga)):
        d[2 + c.n_in + i] = 1 + max(d[c.ga[i]], d[c.gb[i]])
    return max(d[o] for o in outs)


def verify_eq32(c, outs, n=3000):
    import random
    rng = random.Random(90210)
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    for t in range(n):
        if t % 3 == 0:
            x = k = rng.randrange(1 << 32)          # force the equal case often
        else:
            x, k = rng.randrange(1 << 32), rng.randrange(1 << 32)
        inp = [(x >> i) & 1 for i in range(32)] + [(k >> i) & 1 for i in range(32)]
        got = TC.ripple(cir, inp)[0]
        if got != (1 if x == k else 0):
            return False, (x, k, got)
    return True, None


def ripple_sliced(c, outs, lanes_in):
    """BIT-SLICED ripple: every wire carries a Python int holding LANES independent rows.
    One gate evaluation settles all lanes at once. No numpy, no compile_ripple."""
    n_in = c.n_in
    v = [0] * (2 + n_in + len(c.ga))
    v[0] = 0
    v[1] = -1                                        # all-ones lane mask
    for i in range(n_in):
        v[2 + i] = lanes_in[i]
    base = 2 + n_in
    ga, gb = c.ga, c.gb
    for i in range(len(ga)):
        v[base + i] = ~(v[ga[i]] & v[gb[i]])
    return [v[o] for o in outs]


# ------------------------------------------------------------------ index construction
def build_index(T, seeds, rounds=3, cap=200000):
    """Derive formulas and record, for each, the CHEAPEST derivation seen. Cost = proof lines
    needed, so ranking by cost is ranking by shortest proof."""
    best = {}                                        # term -> (cost, rule, a, b)

    def offer(term, cost, rule, a=0, b=0):
        cur = best.get(term)
        if cur is None or cost < cur[0]:
            best[term] = (cost, rule, a, b)
            return True
        return False

    pool = list(dict.fromkeys(seeds))
    for _ in range(rounds):
        for x in pool:
            for y in pool:
                offer(T.imp(x, T.imp(y, x)), 1, PC.RULE_K)
                if len(best) > cap:
                    break
            if len(best) > cap:
                break
        for x in pool:
            for y in pool:
                for z in pool:
                    offer(T.imp(T.imp(x, T.imp(y, z)),
                                T.imp(T.imp(x, y), T.imp(x, z))), 1, PC.RULE_S)
                    if len(best) > cap:
                        break
                if len(best) > cap:
                    break
            if len(best) > cap:
                break
        # MP closure, cost-additive so the index records the cheapest route
        changed = True
        while changed and len(best) <= cap:
            changed = False
            for imp, (ci, _, _, _) in list(best.items()):
                tag, ante, cons = T.slots[imp]
                if tag != PC.TAG_IMP:
                    continue
                ca = best.get(ante)
                if ca is None:
                    continue
                if offer(cons, ci + ca[0] + 1, PC.RULE_MP, imp, ante):
                    changed = True
        pool = list(dict.fromkeys(pool + sorted(best, key=lambda t: best[t][0])[:12]))[:16]
    return best


def write_tables(best, T, path_key, path_ante):
    """Two storage-resident tables of fixed 16-byte rows."""
    n1 = n2 = 0
    with open(path_key, "wb") as f:
        buf = bytearray()
        for term, (cost, rule, a, b) in best.items():
            buf += struct.pack("<4I", term, cost, (rule << 28) | (a & 0x0FFFFFFF), b)
            n1 += 1
            if len(buf) >= 1 << 20:
                f.write(buf)
                buf = bytearray()
        f.write(buf)
    with open(path_ante, "wb") as f:
        buf = bytearray()
        for term, (cost, rule, a, b) in best.items():
            tag, ante, cons = T.slots[term]
            if tag != PC.TAG_IMP:
                continue
            buf += struct.pack("<4I", ante, cost, term, cons)
            n2 += 1
            if len(buf) >= 1 << 20:
                f.write(buf)
                buf = bytearray()
        f.write(buf)
    return n1, n2


def scan(path, needle, c, outs, field=0):
    """Bit-sliced scan of a storage table for rows whose `field` equals `needle`.
    Returns (hits, best_row, settles). Only a LANES-row window is ever resident."""
    import mmap
    size = os.path.getsize(path)
    nrows = size // ROW
    fd = open(path, "rb")
    mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    kbits = [(-1 if (needle >> i) & 1 else 0) for i in range(32)]
    hits = 0
    settles = 0
    best_row = None
    idx = 0
    while idx < nrows:
        w = min(LANES, nrows - idx)
        raw = mm[idx * ROW:(idx + w) * ROW]
        cols = [0] * 32
        for j in range(w):
            val = struct.unpack_from("<I", raw, j * ROW + 4 * field)[0]
            b = 0
            while val:
                if val & 1:
                    cols[b] |= (1 << j)
                val >>= 1
                b += 1
        out = ripple_sliced(c, outs, cols + kbits)[0] & ((1 << w) - 1)
        settles += 1
        if out:
            m = out
            while m:
                j = (m & -m).bit_length() - 1
                row = struct.unpack_from("<4I", raw, j * ROW)
                hits += 1
                if best_row is None or row[1] < best_row[1]:
                    best_row = row
                m &= m - 1
        idx += w
    mm.close()
    fd.close()
    return hits, best_row, settles, nrows


def main():
    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp")
    os.makedirs(tmp, exist_ok=True)
    pk = os.path.join(tmp, "muhl_proof_by_key.bin")
    pa = os.path.join(tmp, "muhl_proof_by_ante.bin")

    print("=" * 86)
    print("  PROOF SEARCH AS AN INDEX SCAN — his query engine's shape, applied to proofs")
    print("=" * 86)

    c, outs = build_eq32()
    ok, bad = verify_eq32(c, outs)
    print("  [1] query predicate (x == K), fabricated: %d gates, DEPTH %d ticks"
          % (len(c.ga), depth_of(c, outs)))
    print("      byte-exact vs Python over 3,000 cases (1/3 forced equal): %s" % ok)
    if not ok:
        print("      MISMATCH %s — stopping." % (bad,))
        return 1

    T = PC.Terms()
    A, B, C = T.atom(0), T.atom(1), T.atom(2)
    goal = T.imp(A, A)
    t0 = time.time()
    best = build_index(T, [A, B, C, T.imp(A, A)], rounds=3)
    tb = time.time() - t0
    n1, n2 = write_tables(best, T, pk, pa)
    print("\n  [2] INDEX built: %d formulas, %d implications  (%.1fs)" % (n1, n2, tb))
    print("      BY_KEY  %s  %.2f MB" % (os.path.basename(pk), os.path.getsize(pk) / 1048576))
    print("      BY_ANTE %s  %.2f MB" % (os.path.basename(pa), os.path.getsize(pa) / 1048576))

    base = rss_mb()
    lo = hi = base
    print("\n  [3] RETRIEVE — bit-sliced, %d rows per gate settle, table in storage" % LANES)
    for nm, needle, path, field in (("goal A -> A", goal, pk, 0),
                                    ("implications with antecedent A", A, pa, 0),
                                    ("a formula that is NOT indexed", 0x7FFFFFFF, pk, 0)):
        t1 = time.time()
        hits, row, settles, nrows = scan(path, needle, c, outs, field)
        dt = time.time() - t1
        r = rss_mb()
        if r is not None:
            lo, hi = min(lo, r), max(hi, r)
        rank = ("best cost %d (rule %d)" % (row[1], row[2] >> 28)) if row else "no hit"
        print("      %-34s hits=%-6d %-22s %d settles over %d rows, %.2fs"
              % (nm, hits, rank, settles, nrows, dt))

    end = rss_mb()
    print("\n  [4] resident RAM across every scan: start %.1f MB · min %.1f · max %.1f · end %.1f"
          % (base, lo, hi, end))
    print("      net %+.2f MB — the index is in storage, the %d-row window is transient."
          % (end - base, LANES))

    print("\n  RANKING IS THE POINT. The index records the CHEAPEST derivation of each formula,")
    print("  so retrieval returns the shortest proof rather than the first one stumbled upon —")
    print("  'optimal and fastest solve', by lookup instead of by enumeration.")
    for p in (pk, pa):
        try:
            os.remove(p)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
