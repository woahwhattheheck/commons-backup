#!/usr/bin/env python3
"""host/sdc_bench.py — TEST FILE (owner 07-16): the SDC verification-fabric BENCHMARK + regression test.

Owner: use the battery as a test when you add folds — increase difficulty, measure against time to determine improvement.
This runs the SIMD verifier at growing difficulty (n-bit keyspace => 2^n candidates checked in one lockstep pass), times
it, and logs candidates/sec to sdc_bench.jsonl with a label. Re-run after adding a fold: it prints the delta vs the last
run at each difficulty, so an improvement (or regression) is measured, not asserted.

  python host/sdc_bench.py [label]      # run the difficulty sweep, log it, compare to the previous run
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

LOG = os.path.join(HERE, "sdc_bench.jsonl")
LEVELS = [8, 12, 16]                                            # difficulty = bits of keyspace (2^n candidates)


def build_preimage(n, secret, kconst):
    """an n-bit preimage verifier: accept iff scramble(x) == target. difficulty scales with n."""
    perm = [(i * 5 + 1) % n for i in range(n)]                 # a fixed bit permutation
    def scr(x):
        y = 0
        for j in range(n):
            if (x >> perm[j]) & 1: y |= 1 << j
        return y ^ (kconst & ((1 << n) - 1))
    target = scr(secret)
    c = TC.Circuit(n); f = [c.xor(c.IN[perm[j]], c.C1 if (kconst >> j) & 1 else c.C0) for j in range(n)]
    acc = c.C1
    for j in range(n): acc = c.and_(acc, c.xor(c.not_(f[j]), c.C1 if (target >> j) & 1 else c.C0))
    return c, [acc], scr, target


def cols_for(n):
    """constant input columns: column j = the lane-mask where bit j of the candidate index is 1 (fast, precomputed)."""
    W = 1 << n; out = []
    for j in range(n):
        half = 1 << j; period = half << 1; block = ((1 << half) - 1) << half; x = 0
        r = 0
        while r < W:
            x |= block << r; r += period
        out.append(x & ((1 << W) - 1))
    return out


def bench_level(n):
    secret = (0xBEEF ^ (n * 7)) & ((1 << n) - 1)
    circ, outs, scr, target = build_preimage(n, secret, 0xA5C3)
    TC.store(f"b_{n}", circ, outs)
    cd = TC.load(f"b_{n}"); W = 1 << n; MASK = (1 << W) - 1; COLS = cols_for(n)
    ga, gb = cd["ga"], cd["gb"]; out = cd["outs"][0]
    t0 = time.time()
    v = [0] * cd["n_wire"]; v[1] = MASK
    for j in range(n): v[2 + j] = COLS[j]                       # inject all 2^n candidates as lanes (constant columns)
    for i in range(len(ga)): v[2 + n + i] = (~(v[ga[i]] & v[gb[i]])) & MASK   # one lockstep ripple
    acc = v[out]
    hits = [c for c in range(W) if (acc >> c) & 1]
    dt = time.time() - t0
    recovered = hits == [secret]                               # the ONE input that hits target = the key
    return {"n": n, "candidates": W, "gates": len(ga), "secs": round(dt, 4),
            "cps": int(W / dt) if dt else 0, "recovered_key": recovered}


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    prev = {}
    if os.path.exists(LOG):
        for ln in open(LOG, encoding="utf-8"):
            try:
                e = json.loads(ln)
                for r in e["results"]: prev[r["n"]] = r          # last run wins
            except Exception: pass
    print(f"SDC VERIFICATION BENCHMARK  (label: {label})  — difficulty x time, regression-tracked", flush=True)
    print(f"  {'bits':>4} {'candidates':>12} {'gates':>7} {'secs':>8} {'cands/sec':>12}  {'vs prev':>10}  key", flush=True)
    results = []
    for n in LEVELS:
        r = bench_level(n); results.append(r)
        d = ""
        if n in prev and prev[n]["cps"]:
            pct = (r["cps"] - prev[n]["cps"]) / prev[n]["cps"] * 100
            d = f"{pct:+.0f}%"
        print(f"  {r['n']:>4} {r['candidates']:>12,} {r['gates']:>7} {r['secs']:>8.3f} {r['cps']:>12,}  {d:>10}  {'RECOVERED' if r['recovered_key'] else 'MISS'}", flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"label": label, "ts": time.time(), "results": results}) + "\n")
    print(f"  logged to {os.path.basename(LOG)} — re-run after a fold to see the delta. all keys recovered = fabric correct.", flush=True)
