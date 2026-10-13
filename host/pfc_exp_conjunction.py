#!/usr/bin/env python3
"""host/pfc_exp_conjunction.py — EXPERIMENTAL (owner 07-19): SLAM ALL (throughput) LEVERS IN CONJUNCTION.
Stack bit-slicing + minimization + MEMOIZE on a verification-style predicate (the winning-application type), over a
streaming input with a repeat factor R. Shows the compounding: raw bit-slice throughput × memoize(≈R) = effective rate.
Byte-exact verified. Safe: small circuit, W=8192 batches, single process, no numpy. Logs to docs/PFC_LEVER_DATADUMP.md.
  python host/pfc_exp_conjunction.py
"""
import json, os, random, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdc_cc as CC
from pfc_exp_levers import finish, bits, lane_val
OUT_DIR = "C:/llm/sdc_out"; os.makedirs(OUT_DIR, exist_ok=True)
M = 0xffffffff
def rotr_n(x, n): return ((x >> n) | (x << (32 - n))) & M
TARGET = 0x5a
def nat_pred(x):                                   # verification predicate: low byte of sigma0(x) == TARGET
    s = (rotr_n(x, 7) ^ rotr_n(x, 18) ^ (x >> 3)) & M
    return 1 if (s & 0xff) == TARGET else 0


def build_verifier():
    g = CC.CircuitCompiler(32); x = list(g.IN)
    s = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3))
    tb = [CC.cword(g, TARGET)[j] for j in range(8)]                       # match low 8 bits to TARGET
    eq = g.C1
    for j in range(8): eq = g.AND(eq, g.NOT(g.XOR(s[j], tb[j])))          # AND of XNORs
    return g, [eq]


def eval_batch(run, out_wire, cands, W):
    ins = [0] * 32
    for j, c in enumerate(cands):
        for b in range(32):
            if (c >> b) & 1: ins[b] |= (1 << j)
    v = run(ins, (1 << W) - 1)
    ov = v[out_wire] if out_wire >= 2 else out_wire
    return [(ov >> j) & 1 for j in range(len(cands))]


def raw_run(run, out_wire, stream, W):
    t = time.time(); res = []
    for i in range(0, len(stream), W):
        res += eval_batch(run, out_wire, stream[i:i + W], W)
    return res, time.time() - t


def memo_run(run, out_wire, stream, W):
    t = time.time(); cache = {}
    uniq = []
    for c in stream:
        if c not in cache:
            cache[c] = None; uniq.append(c)
    for i in range(0, len(uniq), W):
        b = uniq[i:i + W]; verd = eval_batch(run, out_wire, b, W)
        for c, r in zip(b, verd): cache[c] = r
    res = [cache[c] for c in stream]                                      # repeats = dict reads at ~0 compute
    return res, time.time() - t, len(uniq)


def main():
    print("Muhlnickel — SLAM ALL LEVERS IN CONJUNCTION (bit-slice + minimize + memoize, verification workload)\n", flush=True)
    g, outs = build_verifier(); run, out2, n_gate, n_wire, _ = finish(g, outs)
    ow = out2[0]
    ok = all((lane_val(run(bits(x, 32), 1), out2) == nat_pred(x)) for x in
             (0, 1, 0xdeadbeef, 0x0f1e2d3c, M, 0x1234, 0xabcdef01))
    print(f"  verifier circuit: {n_gate} gates (minimized), byte-exact vs native = {ok}", flush=True)
    if not ok:
        print("  VERIFY FAILED — abort."); return 1
    W = 8192; N = 8192 * 12
    rows = []
    print(f"\n  stream N={N:,}, batch W={W}. compounding memoize over repeat factor R:", flush=True)
    print(f"    {'R':>4s}{'unique':>10s}{'raw cand/s':>14s}{'memo cand/s':>14s}{'memo gain':>11s}", flush=True)
    for R in (1, 2, 4, 16, 64):
        U = max(1, N // R)
        pool = [random.getrandbits(32) for _ in range(U)]
        stream = [pool[random.randrange(U)] for _ in range(N)]
        r_raw, t_raw = raw_run(run, ow, stream, W)
        r_memo, t_memo, u = memo_run(run, ow, stream, W)
        assert r_raw == r_memo, "memoize changed the answer!"             # correctness under conjunction
        raw_cs = N / t_raw; memo_cs = N / t_memo
        rows.append({"R": R, "unique": u, "raw_cands_s": round(raw_cs), "memo_cands_s": round(memo_cs),
                     "memo_gain": round(memo_cs / raw_cs, 2)})
        print(f"    {R:>4d}{u:>10,}{raw_cs:>14,.0f}{memo_cs:>14,.0f}{memo_cs/raw_cs:>10.2f}x", flush=True)

    peak = max(r["memo_cands_s"] for r in rows)
    json.dump({"n_gate": n_gate, "W": W, "N": N, "rows": rows}, open(f"{OUT_DIR}/pfc_conjunction.json", "w"), indent=2)
    line = (f"- **07-19 (conjunction)** — bit-slice+minimize+**memoize** on a verification predicate ({n_gate} gates): raw "
            f"~{rows[0]['raw_cands_s']:,} cand/s; memoize multiplies by the repeat factor (R=64 → **{peak:,} cand/s**, "
            f"{rows[-1]['memo_gain']}× the raw rate) with byte-exact-identical answers. Levers COMPOUND. `pfc_conjunction.json`.\n")
    try:
        with open("docs/PFC_LEVER_DATADUMP.md", "a", encoding="utf-8") as f: f.write(line)
        print(f"\n  logged -> docs/PFC_LEVER_DATADUMP.md", flush=True)
    except Exception as e:
        print(f"  (log append failed: {e})", flush=True)
    print(f"  results -> {OUT_DIR}/pfc_conjunction.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
