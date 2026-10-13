#!/usr/bin/env python3
"""host/pfc_exp_levers.py — EXPERIMENTAL (owner-directed 07-19): test two levers the barrage hadn't isolated —
   (1) AMOUNT of pfc (scale the same circuit up) and (2) TYPE of circuitry (different circuit kinds).

Question (measured, not asserted): does throughput depend on amount / type, or is the real invariant a roughly fixed
**gates-evaluated-per-second** host rate — so amount/type just change how many gates a useful op costs?

For each circuit: build via the real compiler (sdc_cc), DCE, compile the ripple, VERIFY byte-exact vs a numeric
reference (no cheating), then measure single-lane ops/sec, gates/sec (= n_gate x ops/sec), and resident RAM.
  TYPE   : parity32 (XOR-only, shallow)  ·  add32  ·  one SHA-256 block  ·  full double-SHA miner  (spans ~31 .. 213k gates)
  AMOUNT : chained 32-bit adders, N = 1,2,4,8,16 (same TYPE, growing AMOUNT)

Safe: small circuits, single lane (low RAM), single process, foreground, RAM-guarded, no numpy, titan.gguf not opened.
  python host/pfc_exp_levers.py
"""
import hashlib, json, os, struct, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, PFCP.SBX)
import sdc_cc as CC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_exp_bench import rss, free_mb, rate           # reuse the fixed RAM probe + timer

OUT_DIR = PFCP.OUT; os.makedirs(OUT_DIR, exist_ok=True)


def lane_val(v, wires):
    """single-lane integer value of a wire-list (LSB-first), honoring const wires 0/1."""
    x = 0
    for j, w in enumerate(wires):
        b = 0 if w == 0 else (1 if w == 1 else (v[w] & 1))
        x |= b << j
    return x


def finish(g, outs):
    """DCE + compile the ripple; return (run, out2_wires, n_gate, n_wire, flash_s)."""
    gates, out2 = g.dce(outs); n_gate = len(gates); n_wire = 2 + g.n_in + n_gate
    t = time.time(); run = g.compile_ripple(gates, n_wire); flash_s = time.time() - t
    return run, out2, n_gate, n_wire, flash_s


def bits(x, n):  # LSB-first bit list
    return [(x >> i) & 1 for i in range(n)]


# ------------------------------------------------------------------ circuit builders (each returns g, outs, checker) --
def build_parity():
    g = CC.CircuitCompiler(32); acc = g.IN[0]
    for i in range(1, 32): acc = g.XOR(acc, g.IN[i])
    outs = [acc]
    def check(run, out2):
        for x in (0, 1, 0x0f0f0f0f, 0xffffffff, 0x12345678):
            v = run(bits(x, 32), 1)
            if lane_val(v, out2) != (bin(x).count("1") & 1): return False
        return True
    return g, outs, check, (lambda: bits(0x12345678, 32))


def build_add32():
    g = CC.CircuitCompiler(64); a = list(g.IN[:32]); b = list(g.IN[32:64])
    outs = CC.add32(g, a, b)
    def check(run, out2):
        for (x, y) in ((0, 0), (1, 1), (0xffffffff, 1), (0x89abcdef, 0x12345678)):
            v = run(bits(x, 32) + bits(y, 32), 1)
            if lane_val(v, out2) != ((x + y) & 0xffffffff): return False
        return True
    return g, outs, check, (lambda: bits(0x89abcdef, 32) + bits(0x12345678, 32))


def build_chain_add(N):
    g = CC.CircuitCompiler(32 * N)
    words = [list(g.IN[32 * k:32 * k + 32]) for k in range(N)]
    acc = words[0]
    for k in range(1, N): acc = CC.add32(g, acc, words[k])
    outs = acc
    def check(run, out2):
        import random
        for _ in range(4):
            xs = [random.getrandbits(32) for _ in range(N)]
            inp = []
            for x in xs: inp += bits(x, 32)
            v = run(inp, 1)
            if lane_val(v, out2) != (sum(xs) & 0xffffffff): return False
        return True
    return g, outs, check, (lambda: bits(0x11111111, 32) * N)


def build_sha_block():
    # hash a single 32-bit message word in ONE SHA-256 block (msg | 0x80.. | len=32)
    g = CC.CircuitCompiler(32); inw = list(g.IN)
    in16 = [inw, CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 13 + [CC.cword(g, 32)]
    H0w = [CC.cword(g, h) for h in CC.H0]
    d = CC.sha_block(g, H0w, in16)
    outs = [w for word in d for w in word]
    def ref(x): return hashlib.sha256(struct.pack(">I", x)).digest()
    def dig(v, o2):
        out = b""
        for wi in range(8): out += struct.pack(">I", lane_val(v, o2[wi * 32:wi * 32 + 32]))
        return out
    def check(run, out2):
        for x in (0, 1, 0xdeadbeef, 0x0f1e2d3c):
            if dig(run(bits(x, 32), 1), out2) != ref(x): return False
        return True
    return g, outs, check, (lambda: bits(0xdeadbeef, 32))


def build_miner():
    g, d2 = CC.compile_miner(); outs = [w for word in d2 for w in word]
    d2shape = None
    def check(run, out2):
        d2c = [out2[i * 32:(i + 1) * 32] for i in range(8)]
        for nc in (0, 1, 0xcafebabe):
            if CC.digest_from(run(bits(nc, 32), 1), d2c) != CC.ref(nc): return False
        return True
    return g, outs, check, (lambda: bits(0, 32))


def measure(name, builder, secs=2.0):
    t = time.time(); g, outs, check, mkinp = builder(); build_s = time.time() - t
    run, out2, n_gate, n_wire, flash_s = finish(g, outs)
    ok = check(run, out2)
    if not ok:
        print(f"  {name:<16s}  VERIFY FAILED — skipping (no cheating).", flush=True)
        return {"name": name, "verified": False, "n_gate": n_gate}
    inp = mkinp()
    n, s = rate(lambda: run(inp, 1), secs); ops = n / s
    r_now, _ = rss()
    row = {"name": name, "verified": True, "n_gate": n_gate, "ops_per_s": round(ops, 1),
           "gates_per_s": round(n_gate * ops), "rss_mb": round(r_now, 1),
           "build_s": round(build_s, 2), "flash_s": round(flash_s, 2)}
    print(f"  {name:<16s}  gates={n_gate:>8,}  ops/s={ops:>12,.1f}  gates/s={n_gate*ops:>14,.0f}  RSS={r_now:6.1f}MB", flush=True)
    return row


def main():
    R = {"type": [], "amount": []}
    print(f"Muhlnickel LEVER TEST — amount + type of circuitry (single lane, byte-exact, free RAM {free_mb():.0f} MB)\n", flush=True)

    print("  === TYPE of circuitry (different kinds, one lane) ===", flush=True)
    for name, b in [("parity32", build_parity), ("add32", build_add32),
                    ("sha256_1block", build_sha_block), ("double_sha_miner", build_miner)]:
        R["type"].append(measure(name, b))

    print("\n  === AMOUNT of Muhlnickel (chained 32-bit adders, same TYPE, growing size) ===", flush=True)
    for N in (1, 2, 4, 8, 16):
        R["amount"].append(measure(f"chain_add x{N}", lambda N=N: build_chain_add(N)))

    # the invariant check: is gates/sec roughly constant across all verified circuits?
    gps = [r["gates_per_s"] for r in (R["type"] + R["amount"]) if r.get("verified")]
    if gps:
        lo, hi, mean = min(gps), max(gps), sum(gps) / len(gps)
        R["gates_per_s_summary"] = {"min": lo, "max": hi, "mean": round(mean), "spread_x": round(hi / max(lo, 1), 2)}
        print(f"\n  gates/sec across ALL circuits: min {lo:,} · mean {mean:,.0f} · max {hi:,}  (spread {hi/max(lo,1):.2f}x)", flush=True)
        print(f"  => if that spread is small, gates/sec is the invariant: amount & type only change gates-per-op,", flush=True)
        print(f"     not the host's gate-rate. throughput(ops/s) = gates/s / gates-per-op.", flush=True)

    json.dump(R, open(f"{OUT_DIR}/pfc_levers.json", "w"), indent=2)
    print(f"\n  results -> {OUT_DIR}/pfc_levers.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
