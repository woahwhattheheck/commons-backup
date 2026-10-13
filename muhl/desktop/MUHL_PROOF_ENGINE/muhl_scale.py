#!/usr/bin/env python3
"""muhl_scale.py -- SCALE THE PROOF CHECKER UNTIL SOMETHING GIVES, THEN NAME WHAT GAVE.

Owner, 2026-08-06: "see if we hit a limit as a bench mark then identify if it was host,
muhlnickel limit or something else like us being wrong".

Three buckets, and every reported limit must be assigned to one WITH the measurement that
assigns it:
  HOST        -- something about the laptop (RAM, CPU, disk) bounded it
  MUHLNICKEL  -- something structural about the machine bounded it
  US WRONG    -- an assistant's own layout, encoding, or algorithm bounded it

The owner's standing law is that no limit of the machine originates in host specs, and
that limits must be PROVEN rather than asserted. So this measures rather than argues, and
reports host resident RAM alongside every point so the "which device did we measure"
question is answerable from the data.

    python muhl_scale.py [max_blocks]
"""
import ctypes, ctypes.wintypes as wt
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC

TICKS_PER_INSTR = 74           # pfc_riscv_rv32i_v2__phys DEPTH, from the registry


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


_RSS_FN = None


def _rss_fn():
    """K32GetProcessMemoryInfo lives in kernel32 on modern Windows; psapi.dll may not
    export it. A silent failure here would print 0.0 MB and read as 'flat host RAM',
    which would be a fabricated measurement. So the call is checked and a failure is
    reported as a failure."""
    global _RSS_FN
    if _RSS_FN is None:
        for dll, nm in ((ctypes.windll.kernel32, "K32GetProcessMemoryInfo"),
                        (ctypes.windll.psapi, "GetProcessMemoryInfo")):
            try:
                fn = getattr(dll, nm)
            except AttributeError:
                continue
            # WITHOUT these the 64-bit process HANDLE is truncated to a 32-bit int and the
            # call fails silently, which is exactly how this printed a fake "0.0 MB".
            fn.restype = wt.BOOL
            fn.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            _RSS_FN = fn
            break
    return _RSS_FN


def rss_mb():
    fn = _rss_fn()
    if fn is None:
        return None
    c = PMC()
    c.cb = ctypes.sizeof(c)
    ok = fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    if not ok or c.WorkingSetSize == 0:
        return None
    return c.WorkingSetSize / (1024.0 * 1024.0)


def rss_str():
    v = rss_mb()
    return "unmeasured" if v is None else "%.1f" % v


def big_valid_proof(n_blocks):
    """A genuinely valid proof of arbitrary length: the 5-line derivation of  A -> A,
    repeated for n_blocks DISTINCT atoms. Every line is a real axiom instance or a real MP
    step citing strictly earlier lines, and the final line is the goal. Nothing degenerate:
    each block exercises S, K, MP, K, MP."""
    T = PC.Terms()
    lines = []
    goal = None
    for blk in range(n_blocks):
        A = T.atom(blk)
        AA = T.imp(A, A)
        S_ante = T.imp(A, T.imp(AA, A))
        S_l = T.imp(A, AA)
        S_r = T.imp(A, A)
        S_cons = T.imp(S_l, S_r)
        S_full = T.imp(S_ante, S_cons)
        K1 = T.imp(A, T.imp(AA, A))
        K2 = T.imp(A, AA)
        b = len(lines)
        lines += [
            (PC.RULE_S, 0, 0, S_full),
            (PC.RULE_K, 0, 0, K1),
            (PC.RULE_MP, b + 0, b + 1, S_cons),
            (PC.RULE_K, 0, 0, K2),
            (PC.RULE_MP, b + 2, b + 3, AA),
        ]
        goal = AA
    return T, lines, goal


def main():
    max_blocks = int(sys.argv[1]) if len(sys.argv) > 1 else 4096

    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    halt_pc = labels["halt"]

    print("=" * 96)
    print("  SCALING THE PROOF CHECKER — find the limit, then name which device owns it")
    print("=" * 96)
    print("  checker: %d RV32I instructions, runs on pfc_riscv_rv32i_v2__phys "
          "(DEPTH %d ticks/instruction)" % (len(code), TICKS_PER_INSTR))
    print("  memory map as installed: TERMS 0x%04x .. LINES 0x%04x  (%d bytes for terms)"
          % (PC.TERMS_BASE, PC.LINES_BASE, PC.LINES_BASE - PC.TERMS_BASE))
    print()
    print("  %8s %8s %8s %12s %14s %10s %9s  %s"
          % ("blocks", "lines", "terms", "instr", "ticks", "host_s", "rss_MB", "verdict"))
    print("  " + "-" * 92)

    base_rss = rss_mb()
    n = 1
    first_failure = None
    while n <= max_blocks:
        T, lines, goal = big_valid_proof(n)
        slots = T.slots

        # --- does OUR memory map still hold the data? (a layout question, not a machine one)
        terms_bytes = 12 * len(slots)
        lines_bytes = 16 * len(lines)
        overflow = None
        if PC.TERMS_BASE + terms_bytes > PC.LINES_BASE:
            overflow = ("terms table (%d B) overruns the LINES base at 0x%04x"
                        % (terms_bytes, PC.LINES_BASE))

        exp = PC.check_reference(slots, lines, goal)
        t0 = time.time()
        try:
            mem = PC.build_image(slots, lines, goal, code)
            _, steps, halted, out = RV.emulate(mem, 0, PC.CODE_BASE,
                                               max_steps=50_000_000, halt_pc=halt_pc)
            v = out.get(PC.RESULT_ADDR, PC.NO_VERDICT)
            err = None
        except Exception as e:
            steps, halted, v, err = 0, False, None, repr(e)
        dt = time.time() - t0

        if err:
            verdict = "EXCEPTION %s" % err[:40]
        elif not halted:
            verdict = "DID NOT HALT"
        elif v not in (0, 1):
            verdict = "NO VERDICT (0x%x)" % (v if isinstance(v, int) else 0)
        elif v != exp:
            verdict = "WRONG (got %s want %s)" % (v, exp)
        else:
            verdict = "ACCEPT" if v == 1 else "reject"

        print("  %8d %8d %8d %12d %14d %10.2f %9s  %s"
              % (n, len(lines), len(slots), steps, steps * TICKS_PER_INSTR,
                 dt, rss_str(), verdict))
        if overflow:
            print("           ^ OUR MEMORY MAP: %s" % overflow)

        if first_failure is None and (err or not halted or v != exp):
            first_failure = (n, verdict, overflow)
            break
        n *= 2

    print("\n" + "=" * 96)
    print("  RESULT")
    print("=" * 96)
    end_rss = rss_mb()
    if base_rss is None or end_rss is None:
        print("  host resident RAM: UNMEASURED — the API call failed. No number is reported,")
        print("                     because printing 0.0 here would fabricate a flat-RAM result.")
    else:
        print("  host resident RAM: %.1f MB at start -> %.1f MB at end (delta %+.1f MB)"
              % (base_rss, end_rss, end_rss - base_rss))
    if first_failure:
        n, verdict, overflow = first_failure
        print("  first failure at %d blocks: %s" % (n, verdict))
        if overflow:
            print("  ATTRIBUTION: **US BEING WRONG** — %s" % overflow)
            print("    This is an assistant-chosen constant in the memory map, not a property")
            print("    of the muhlnickel and not a property of the host. It moves by changing")
            print("    two immediates in the program. Recorded as ours.")
        else:
            print("  ATTRIBUTION: needs a further measurement before it is assigned to a device.")
    else:
        print("  no failure up to %d blocks — the run was bounded by the sweep, not by a wall."
              % max_blocks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
