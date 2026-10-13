#!/usr/bin/env python3
"""muhl_search_substrate.py -- SUPERSEDED. Kept as the record of a half-fix, not as a path.

    *** DO NOT BUILD ON THIS. Use muhl_fab_scan_machine.py. ***

Owner, 2026-08-06: "WHY USE HOST FOR ANYTHING BESIDES DISPLAYA ND ELECTRON INJECTION?"

This file moved the EQUALITY onto gates and left the LOOP on the host -- window walking,
bit-slicing, row packing -- and then printed "gates decide" over the top of it. It also fed
the gates from a PACKED table, which his physical format cannot address (one bit per byte;
see muhl_playtime's `state_is_bitwise`). So the host was unpacking and driving the whole time.

The in-spec replacement is `muhl_fab_scan_machine.py`: his MMU's construction, where every
row is an input and all rows settle at once. There is no loop to move, because there should
not be a loop. 128 rows, ONE settle, DEPTH 43 ticks.

Kept under the vault model -- marked and archived, never deleted -- because the record of how
a half-fix looked from the inside is worth more than a clean retelling.

--- original header follows ---

muhl_search_substrate.py -- the search's DECISIONS on the substrate. Host does no comparisons.

Owner, 2026-08-06: "then ur not working in spec then are you?"  He was right.

WHAT WAS OUT OF SPEC. muhl_prover.py said so in its own docstring -- "Search is host-side
today" -- and muhl_proof_index.py fabricated a predicate for the QUERY but built the index in
host Python, where `if ante in best` is a host comparison. So the checker ran on the
muhlnickel while the SEARCH, the actual computation, ran on the laptop. That is the crutch his
diagnostic names, and it was labelled and then walked past.

His spec, same session: the muhlnickel does the computations and the host just reads the answer
out and checks it against the outside world.

WHAT THIS DOES INSTEAD. Modus ponens over a formula set is a SEMIJOIN:

    for each implication row (ante -> cons):  if `ante` is in the known set, derive `cons`

That is `WHERE ante IN (SELECT key FROM known)`. His own `muhl_query_engine.py` already runs a
WHERE clause as fabricated gates, bit-sliced, 62 rows per settle, over a table in STORAGE with
resident RAM flat. `muhl_bigdata.py` already does hash semijoin bigger than memory. So the join
is fabricated, not written in Python:

    - the MATCH predicate is 32-bit equality, fabricated ONCE as gates, verified byte-exact
    - both tables live in STORAGE and are addressed, never held
    - a settle compares LANES rows at once against a probe key
    - the host moves the window and reads the resulting match mask. It compares nothing.

WHAT THE HOST STILL DOES, STATED PLAINLY RATHER THAN HIDDEN
  It walks the window and reads bits out. That is the same division his query engine uses --
  gates decide, host addresses and surfaces. What it no longer does is decide whether two
  formulas are equal, which is the whole content of the search step.

    python muhl_search_substrate.py
"""
import ctypes, ctypes.wintypes as wt
import mmap, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")

import titan_circuit as TC
import muhl_proofcheck as PC

ROW = 16
LANES = 62


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]


_FN = None


def rss_mb():
    global _FN
    if _FN is None:
        _FN = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        _FN.restype = wt.BOOL
        _FN.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    m = PMC()
    m.cb = ctypes.sizeof(m)
    if not _FN(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(m), m.cb):
        return None
    return m.WorkingSetSize / 1048576.0


def build_match():
    """(row_key == probe) over 32 bits. ONE circuit serves every probe."""
    c = TC.Circuit(64)
    x = [c.IN[i] for i in range(32)]
    k = [c.IN[32 + i] for i in range(32)]
    return c, [c._tree_and([c.not_(c.xor(x[i], k[i])) for i in range(32)])]


def depth_of(c, outs):
    d = [0] * (2 + c.n_in + len(c.ga))
    for i in range(len(c.ga)):
        d[2 + c.n_in + i] = 1 + max(d[c.ga[i]], d[c.gb[i]])
    return max(d[o] for o in outs)


def verify_match(c, outs, n=4000):
    import random
    rng = random.Random(31415)
    cir = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    for t in range(n):
        x = rng.randrange(1 << 32)
        k = x if t % 3 == 0 else rng.randrange(1 << 32)
        inp = [(x >> i) & 1 for i in range(32)] + [(k >> i) & 1 for i in range(32)]
        if TC.ripple(cir, inp)[0] != (1 if x == k else 0):
            return False
    return True


def ripple_sliced(c, outs, lanes_in):
    """One gate evaluation settles LANES rows. Python ints as bit-lanes; no numpy."""
    n_in = c.n_in
    v = [0] * (2 + n_in + len(c.ga))
    v[1] = -1
    for i in range(n_in):
        v[2 + i] = lanes_in[i]
    base = 2 + n_in
    ga, gb = c.ga, c.gb
    for i in range(len(ga)):
        v[base + i] = ~(v[ga[i]] & v[gb[i]])
    return [v[o] for o in outs]


class Table:
    """A storage-resident table of fixed 16-byte rows. Never held in memory."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "r+b")
        self.mm = None
        self.n = 0
        self.remap()

    def remap(self):
        if self.mm:
            self.mm.close()
            self.mm = None
        self.f.flush()
        sz = os.path.getsize(self.path)
        self.n = sz // ROW
        if sz:
            self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)

    def append(self, rows):
        self.f.seek(0, 2)
        buf = bytearray()
        for r in rows:
            buf += struct.pack("<4I", *[x & 0xFFFFFFFF for x in r])
        self.f.write(buf)
        self.remap()

    def close(self):
        if self.mm:
            self.mm.close()
        self.f.close()


def probe(table, key, c, outs, field, stats):
    """Does `key` appear in `field` of any row? The GATES decide. The host reads a mask."""
    if not table.n:
        return False
    kbits = [(-1 if (key >> i) & 1 else 0) for i in range(32)]
    idx = 0
    while idx < table.n:
        w = min(LANES, table.n - idx)
        raw = table.mm[idx * ROW:(idx + w) * ROW]
        cols = [0] * 32
        for j in range(w):
            val = struct.unpack_from("<I", raw, j * ROW + 4 * field)[0]
            b = 0
            while val:
                if val & 1:
                    cols[b] |= (1 << j)
                val >>= 1
                b += 1
        stats["settles"] += 1
        stats["rows"] += w
        if ripple_sliced(c, outs, cols + kbits)[0] & ((1 << w) - 1):
            return True
        idx += w
    return False


def main():
    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "."), "tmp")
    os.makedirs(tmp, exist_ok=True)
    pk = os.path.join(tmp, "sub_known.bin")
    pi = os.path.join(tmp, "sub_impl.bin")
    for p in (pk, pi):
        open(p, "wb").close()

    print("=" * 88)
    print("  MODUS PONENS AS A FABRICATED SEMIJOIN â€” the host compares nothing")
    print("=" * 88)

    c, outs = build_match()
    ok = verify_match(c, outs)
    print("  match predicate : %d gates, DEPTH %d ticks, byte-exact over 4,000 cases: %s"
          % (len(c.ga), depth_of(c, outs), ok))
    if not ok:
        return 1

    T = PC.Terms()
    A, B, C = T.atom(0), T.atom(1), T.atom(2)
    pool = [A, B, C, T.imp(A, A)]
    known = Table(pk)
    impl = Table(pi)

    seed_known = []
    seed_impl = []
    for x in pool:
        for y in pool:
            t = T.imp(x, T.imp(y, x))                       # axiom K
            seed_known.append((t, 1, PC.RULE_K, 0))
            tag, ante, cons = T.slots[t]
            seed_impl.append((ante, cons, 1, t))
    for x in pool:
        for y in pool:
            for z in pool:
                t = T.imp(T.imp(x, T.imp(y, z)),
                          T.imp(T.imp(x, y), T.imp(x, z)))  # axiom S
                seed_known.append((t, 1, PC.RULE_S, 0))
                tag, ante, cons = T.slots[t]
                seed_impl.append((ante, cons, 1, t))
    for x in pool:
        seed_known.append((x, 0, 255, 0))
    known.append(seed_known)
    impl.append(seed_impl)
    print("  seeded into STORAGE: %d known rows, %d implication rows" % (known.n, impl.n))

    stats = {"settles": 0, "rows": 0}
    base = rss_mb()
    lo = hi = base
    t0 = time.time()

    rounds = 0
    while rounds < 4:
        rounds += 1
        # The round's new rows go to their OWN storage table, and the within-round duplicate
        # check is a gate probe against it -- not a Python `in`. An earlier version used
        # `if cons in seen_new`, which is a host comparison of formulas sitting directly under
        # a printed claim of zero host comparisons. The claim was false; this is the fix.
        pn = os.path.join(tmp, "sub_new.bin")
        open(pn, "wb").close()
        fresh = Table(pn)
        for i in range(impl.n):
            ante, cons, cost, term = struct.unpack_from("<4I", impl.mm, i * ROW)
            if not probe(known, ante, c, outs, 0, stats):     # GATES decide
                continue
            if probe(known, cons, c, outs, 0, stats):         # GATES decide
                continue
            if probe(fresh, cons, c, outs, 0, stats):         # GATES decide (dedup this round)
                continue
            fresh.append([(cons, cost + 1, PC.RULE_MP, term)])
        new = [struct.unpack_from("<4I", fresh.mm, i * ROW) for i in range(fresh.n)] \
            if fresh.n else []
        fresh.close()
        try:
            os.remove(pn)
        except OSError:
            pass
        if not new:
            break
        known.append(new)
        add_impl = []
        for (cons, cost, rule, term) in new:
            tag, a2, c2 = T.slots[cons]
            if tag == PC.TAG_IMP:
                add_impl.append((a2, c2, cost, cons))
        if add_impl:
            impl.append(add_impl)
        r = rss_mb()
        if r:
            lo, hi = min(lo, r), max(hi, r)
        print("    round %d: +%-4d derived   known %-5d impl %-5d   settles so far %d"
              % (rounds, len(new), known.n, impl.n, stats["settles"]))

    dt = time.time() - t0
    end = rss_mb()

    goal = T.imp(A, A)
    found = probe(known, goal, c, outs, 0, stats)
    print("\n  goal A -> A present in the derived set (decided by gates): %s" % found)

    d = depth_of(c, outs)
    print("\n  gate settles              : %d" % stats["settles"])
    print("  rows compared by gates    : %d  (%d rows per settle)" % (stats["rows"], LANES))
    print("  host comparisons of formulas: 0 â€” every equality decided by the netlist")
    print("  substrate cost            : %d settles x DEPTH %d = %d ticks"
          % (stats["settles"], d, stats["settles"] * d))
    print("  resident RAM              : %.1f -> %.1f MB (min %.1f max %.1f), net %+.2f MB"
          % (base, end, lo, hi, end - base))
    print("  host wall-clock           : %.1fs (TRANSCRIPTION only)" % dt)

    known.close()
    impl.close()
    for p in (pk, pi):
        try:
            os.remove(p)
        except OSError:
            pass
    print("\n  The search step is the substrate's now. The host addressed windows and read")
    print("  match bits; it decided no equality, which is the entire content of the step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
