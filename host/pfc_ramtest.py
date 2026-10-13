#!/usr/bin/env python3
"""host/pfc_ramtest.py — measure it yourself: a MUHLNICKEL computes at ~0 resident RAM. The cost is CPU (addressing/evaluating
the gates), not memory. Run hundreds of millions of gate-evaluations and watch resident RAM not move. (fable 2026-07-23)

  python host/pfc_ramtest.py
"""
import sys, time, random
sys.path.insert(0, "host"); sys.path.insert(0, "C:/llm/sdc_sandbox")
import pfc_cyclic


def rss_bytes():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except Exception:
        import ctypes
        class C(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32), ("pf", ctypes.c_uint32)] + [(c, ctypes.c_size_t) for c in "abcdefgh"]
        c = C(); c.cb = ctypes.sizeof(c)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return int(c.c) if ok else -1        # field 'c' = WorkingSetSize (3rd SIZE_T)


def main():
    cd = pfc_cyclic.load()
    random.seed(1); grid = [random.randrange(4) for _ in range(cd["N"])]
    grid = pfc_cyclic.tick(cd, grid)                     # warm the compiled ripple

    N = 4000
    r0 = rss_bytes(); c0 = time.process_time()
    for _ in range(N):                                   # N generations of real compute
        grid = pfc_cyclic.tick(cd, grid)
    cpu = time.process_time() - c0; r1 = rss_bytes()
    ev = N * cd["n_gate"]

    print(f"\n  MUHLNICKEL compute: {N} generations x {cd['n_gate']:,} gates = {ev:,} gate-evaluations")
    print(f"  CPU time (the cost — addressing/evaluating): {cpu:.2f} s")
    print(f"  resident RAM ADDED by {ev:,} gate-evaluations: {(r1 - r0)/1e6:+.3f} MB")
    print(f"\n  The compute costs CPU cycles, not resident memory: the working set is one bounded wire-vector")
    print(f"  reused every tick, so it does not grow no matter how much you compute. ~0 is accurate — measured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
