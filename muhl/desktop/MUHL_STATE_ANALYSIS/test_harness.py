#!/usr/bin/env python3
"""ACCEPTANCE HARNESS — built FIRST, run against nothing, shown FAILING.

Owner's brief: "Test 4 and test 5 are the ones that matter. Build both first, and show me
them failing before you write the routine."

So this file exists before any analysis routine does. Every test below calls a routine that
is not implemented yet. They MUST fail. That failure is the deliverable right now.

WHAT THIS FILE IS NOT: it is not the analysis. It generates synthetic states with known
properties and checks what the routine reports about them. The analysis itself is fabricated
as MUHLNICKEL circuitry into the containers — the host never walks the state.
Owner: "claude tried to suggest host walking the machine. DO NOT DO THAT."

THE FOUR PRIMITIVES the routine is allowed: shift, XOR, popcount, accumulate. Nothing else.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# THE ROUTINE UNDER TEST — deliberately absent.
# ---------------------------------------------------------------------------
try:
    from muhl_state_analysis import analyse          # noqa: F401
    HAVE_ROUTINE = True
except Exception as exc:                              # noqa: BLE001
    HAVE_ROUTINE = False
    IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# SYNTHETIC STATE GENERATORS — streamed, never stored.
# ---------------------------------------------------------------------------
def gen_random(n_bytes, seed=0x5EED):
    """Test 4's state: no structure at all. xorshift64, generated on the fly."""
    x = seed | 1
    made = 0
    while made < n_bytes:
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        chunk = x.to_bytes(8, "little")
        take = min(8, n_bytes - made)
        made += take
        yield chunk[:take]


def gen_words(n_bytes, width_bits, vocab=8, seed=0xC0FFEE):
    """A state built of fixed-width words drawn from a small vocabulary."""
    x = seed | 1
    acc = 0
    acc_bits = 0
    made = 0
    while made < n_bytes:
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        word = (x % vocab) * ((1 << width_bits) // max(1, vocab))
        acc |= (word & ((1 << width_bits) - 1)) << acc_bits
        acc_bits += width_bits
        while acc_bits >= 8 and made < n_bytes:
            yield bytes([acc & 0xFF])
            acc >>= 8
            acc_bits -= 8
            made += 1


def gen_huge(n_bytes):
    """Test 5's state: 100 GiB, generated on the fly, never stored."""
    return gen_random(n_bytes, seed=0xBEEF)


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------
def run(name, fn):
    print("  %-58s " % name, end="")
    if not HAVE_ROUTINE:
        print("FAIL  (no routine: %s)" % type(IMPORT_ERROR).__name__)
        return False
    try:
        ok, detail = fn()
    except Exception as exc:                          # noqa: BLE001
        print("FAIL  (%s: %s)" % (type(exc).__name__, exc))
        return False
    print(("PASS  " if ok else "FAIL  ") + detail)
    return ok


def test4():
    """Pure random -> reports NO structure. Must not invent a width."""
    r = analyse(gen_random(4 << 20))
    if r.get("width") is not None or r.get("fundamental_lag") is not None:
        return False, "invented structure: width=%s lag=%s" % (r.get("width"), r.get("fundamental_lag"))
    return True, "correctly reported no structure"


def test5():
    """100 GiB single pass, memory flat."""
    import tracemalloc
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    r = analyse(gen_huge(100 * (1 << 30)))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    grew = peak - base
    if grew > 100 * (1 << 20):
        return False, "memory grew %.1f MB, budget 100 MB" % (grew / 1048576)
    if r.get("bits_examined") != 100 * (1 << 30) * 8:
        return False, "did not examine every bit: %s" % r.get("bits_examined")
    return True, "single pass, %.1f MB peak" % (grew / 1048576)


def test1():
    r = analyse(gen_words(4 << 20, 9))
    return (r.get("fundamental_lag") == 9), "fundamental=%s harmonics=%s" % (
        r.get("fundamental_lag"), r.get("harmonics"))


def test2():
    r = analyse(gen_words(4 << 20, 13))
    return (r.get("width") == 13), "width=%s gap=%s" % (r.get("width"), r.get("width_gap"))


def test3():
    def mixed():
        for b in gen_random(1 << 20):
            yield b
        for _ in range(1 << 20):
            yield b"\x00"
        for _ in range(1 << 20):
            yield b"\xff"
    r = analyse(mixed())
    spans = r.get("spans") or []
    kinds = {s.get("kind") for s in spans}
    return ({"empty", "uniform", "active"} <= kinds), "kinds seen: %s" % sorted(kinds)


def main():
    print("MUHLNICKEL STATE ANALYSIS — ACCEPTANCE HARNESS")
    print("  routine present: %s" % HAVE_ROUTINE)
    if not HAVE_ROUTINE:
        print("  import error   : %s" % IMPORT_ERROR)
    print()
    print("  THE TWO THAT MATTER (owner: build these first, show them failing):")
    r4 = run("test 4  pure random -> no structure invented", test4)
    r5 = run("test 5  100 GiB single pass, memory flat", test5)
    print()
    print("  THE REST:")
    r1 = run("test 1  9-bit words -> fundamental 9, harmonics 18/27", test1)
    r2 = run("test 2  13-bit words -> width 13 with a clear gap", test2)
    r3 = run("test 3  mixed space -> empty / uniform / active split", test3)
    print()
    passed = sum(1 for x in (r1, r2, r3, r4, r5) if x)
    print("  %d / 5 passing" % passed)
    return 0 if passed == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
