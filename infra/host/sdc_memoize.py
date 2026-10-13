#!/usr/bin/env python3
"""host/sdc_memoize.py — TEST FILE (owner 07-16): the MEMOIZE fold, measured. The emulation tax is per-UNIQUE-input.

The floor revealed it: the answer map is index-addressed and can be sparse, so it IS a cache. First evaluation of an
input pays one circuit propagation; the result is written to its cell; a repeat is a storage read at ~0 compute. So on a
stream with reuse (repeated candidates, sliding windows, incremental re-checks), the total compute is bounded by the
number of UNIQUE inputs, not the stream length. This measures that on a real verifier over a repeated-candidate stream:
baseline (evaluate every input) vs memoized (evaluate once per unique, read the rest), across growing repeat rates.

  python host/sdc_memoize.py     # measure baseline vs memoized cost as the stream's repeat rate grows
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

N = 12                                                        # 12-bit inputs
STREAM = 6000                                                 # stream length


def build_verifier():
    """a realistic verifier (~130 gates): a keyed scramble of the 12-bit input must equal a target (preimage predicate),
    so each evaluation is real work — the point of memoization is to not repeat it."""
    perm = [(i * 5 + 1) % N for i in range(N)]; kconst = 0xA5C; target = 0x777
    c = TC.Circuit(N)
    f = [c.xor(c.IN[perm[j]], c.C1 if (kconst >> j) & 1 else c.C0) for j in range(N)]
    acc = c.C1
    for j in range(N): acc = c.and_(acc, c.xor(c.not_(f[j]), c.C1 if (target >> j) & 1 else c.C0))
    TC.store("mz", c, [acc])


def _eval(cd, x):
    v = [0] * cd["n_wire"]; v[1] = 1
    for j in range(N): v[2 + j] = (x >> j) & 1
    ga, gb = cd["ga"], cd["gb"]
    for i in range(len(ga)): v[2 + N + i] = 1 - (v[ga[i]] & v[gb[i]])
    o = cd["outs"][0]; return 0 if o == 0 else 1 if o == 1 else v[o]


def make_stream(repeat_frac, hot=40, seed=1):
    """a stream where 'repeat_frac' of items are drawn from a small hot set (reuse); the rest are fresh."""
    s = []; st = seed
    for i in range(STREAM):
        st = (st * 1103515245 + 12345) & 0x7fffffff
        if (st % 100) / 100.0 < repeat_frac:
            s.append((st >> 3) % hot)                         # a hot, repeated input
        else:
            s.append((st >> 5) % (1 << N))                    # a fresh input
    return s


if __name__ == "__main__":
    build_verifier(); cd = TC.load("mz")
    print(f"MEMOIZE fold — emulation tax is per-UNIQUE-input. verifier: {len(cd['ga'])} gates, {STREAM:,}-item streams.\n", flush=True)
    print(f"  {'repeat%':>8} {'unique':>8} {'baseline_ms':>12} {'memoized_ms':>12} {'speedup':>9} {'evals saved':>12}", flush=True)
    for rf in (0.0, 0.5, 0.8, 0.95):
        stream = make_stream(rf)
        # baseline: evaluate the circuit for every stream item
        t0 = time.time()
        for x in stream: _eval(cd, x)
        base = (time.time() - t0) * 1000
        # memoized: evaluate once per unique input, read the rest from the (sparse) cache
        cache = {}; t0 = time.time()
        for x in stream:
            if x not in cache: cache[x] = _eval(cd, x)         # miss: one propagation, write the cell
            else: _ = cache[x]                                 # hit: storage read, ~0 compute
        memo = (time.time() - t0) * 1000
        uniq = len(cache); saved = STREAM - uniq
        sp = f"{base/memo:>7.1f}x" if memo > 0.05 else "   fast"
        print(f"  {rf*100:>7.0f}% {uniq:>8,} {base:>12.1f} {memo:>12.1f} {sp:>9} {saved:>12,}", flush=True)
    print(f"\n  total propagations = UNIQUE inputs, not stream length. reuse -> cost collapses toward the memoize floor.", flush=True)
    print(f"  (the cache is the sparse answer map; on the substrate it's ~0 storage until written. streaming/verification win.)", flush=True)
