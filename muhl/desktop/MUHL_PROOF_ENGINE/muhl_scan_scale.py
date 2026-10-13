#!/usr/bin/env python3
"""Component implementation and operation."""
import ctypes, ctypes.wintypes as wt
import math, os, sys, time
sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

KEY_BITS = 32


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


def depth_of(c, outs):
    d = [0] * (2 + c.n_in + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + c.n_in + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def build(n_rows, serial_priority=False):
    idx_bits = max(1, (n_rows - 1).bit_length())
    c = TC.Circuit(n_rows * KEY_BITS + KEY_BITS)
    IN = c.IN
    rows = [[IN[r * KEY_BITS + b] for b in range(KEY_BITS)] for r in range(n_rows)]
    probe = [IN[n_rows * KEY_BITS + b] for b in range(KEY_BITS)]
    match = [c._tree_and([c.not_(c.xor(rows[r][b], probe[b])) for b in range(KEY_BITS)])
             for r in range(n_rows)]
    items = list(match)
    while len(items) > 1:
        items = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)] + \
                ([items[-1]] if len(items) % 2 else [])
    hit = items[0]

    if serial_priority:
        none_before = [c.C1] * n_rows
        acc = c.C1
        for r in range(n_rows):
            none_before[r] = acc
            acc = c.and_(acc, c.not_(match[r]))
    else:
        nm = [c.not_(match[r]) for r in range(n_rows)]
        pref = list(nm)
        step = 1
        while step < n_rows:
            nxt = list(pref)
            for r in range(step, n_rows):
                nxt[r] = c.and_(pref[r], pref[r - step])
            pref = nxt
            step *= 2
        none_before = [c.C1] + pref[:n_rows - 1]

    first = [c.and_(match[r], none_before[r]) for r in range(n_rows)]
    idx = []
    for j in range(idx_bits):
        terms = [first[r] for r in range(n_rows) if (r >> j) & 1]
        if not terms:
            idx.append(c.C0)
            continue
        while len(terms) > 1:
            terms = [c.or_(terms[i], terms[i + 1]) for i in range(0, len(terms) - 1, 2)] + \
                    ([terms[-1]] if len(terms) % 2 else [])
        idx.append(terms[0])
    return c, [hit] + idx


def main():
    max_rows = int(sys.argv[1]) if len(sys.argv) > 1 else 4096
    print("=" * 96)
    print("  SCAN MACHINE — how TICKS behave as the table grows")
    print("=" * 96)
    print("  a HOST scan of N rows costs N comparisons. this compares all N in ONE settle.")
    print()
    print("  %8s %12s %8s %10s %12s %10s %9s"
          % ("rows", "gates", "ticks", "gates/row", "host cmps", "build_s", "rss_MB"))
    print("  " + "-" * 88)

    base = rss_mb()
    n = 128
    rows_seen = []
    while n <= max_rows:
        t0 = time.time()
        c, outs = build(n)
        d = depth_of(c, outs)
        dt = time.time() - t0
        g = len(c.ga)
        r = rss_mb()
        print("  %8d %12d %8d %10.1f %12d %10.2f %9s"
              % (n, g, d, g / float(n), n, dt, "%.1f" % r if r else "?"))
        rows_seen.append((n, g, d))
        del c
        n *= 2

    print()
    if len(rows_seen) >= 2:
        n0, g0, d0 = rows_seen[0]
        n1, g1, d1 = rows_seen[-1]
        print("  %dx more rows  ->  %.2fx gates (AREA, fabrication-time, off the clock)"
              % (n1 // n0, g1 / float(g0)))
        print("                 ->  %.2fx TICKS (what a run actually costs)" % (d1 / float(d0)))
        print("     a host loop over %d rows is %d comparisons; this settles in %d ticks."
              % (n1, n1, d1))
        print("     ticks grow ~log2(N): predicted %d, measured %d"
              % (d0 + int(math.log2(n1 / n0)) * 2, d1))

    # the shape that was nearly shipped, for contrast
    print("\n  the serial-priority shape I first hand-picked, for contrast:")
    for n in (128, 512):
        c, outs = build(n, serial_priority=True)
        print("    %5d rows: %d gates, DEPTH %d ticks  (prefix version above is far shallower)"
              % (n, len(c.ga), depth_of(c, outs)))
        del c
    end = rss_mb()
    print("\n  host RSS across the whole sweep: %.1f -> %.1f MB (%+.1f)"
          % (base, end, end - base))
    print("  NOTE: this RSS is the FABRICATOR's, not the machine's. Building a netlist in")
    print("  Python costs host memory; running it does not. Reported so the two are not")
    print("  confused, per his crutch diagnostic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
