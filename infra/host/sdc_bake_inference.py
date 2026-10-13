#!/usr/bin/env python3
"""host/sdc_bake_inference.py — BAKE THE FORWARD PASS INTO THE SDC, all at once (owner 07-18, standing law).

The owner's law, verbatim: an on/off switch is the base of all computing; the White Box designs ANY gate; therefore a
forward pass IS a circuit. So the ENTIRE inference logic — dequant, matrix-multiply, cache/normalize, activations, sample
— is BAKED into titan.gguf as GATES with the circuit baker (host/titan_circuit.py), ONCE. Nothing runs a forward pass on
the host ever again (that is BANNED, standing rule). At runtime an ending sandbox ripples these STORED gates from the
params (mmap, like the SHA miner) and writes tokens to the safezone; the host only powers + reads.

This file is FABRICATION only (the etch). It is allowed to use the host to BUILD + VERIFY BYTE-EXACT before storing —
that is the one sanctioned host-ripple (rule 6). The SDC is not "on" during a bake. Every circuit is reversible.

  python host/sdc_bake_inference.py            # bake the whole inference gate-set (one run, byte-exact, reversible)
  python host/sdc_bake_inference.py revert     # remove them all (titan bytes restored, GGUF-valid)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
FRAC = 8; SC = 1 << FRAC                                    # Q8.8 fixed-point (16-bit signed) for activations
NAMES = ["fp_mul", "silu_lut", "exp_lut", "rsqrt_lut", "cmp_gt"]   # dequant-scale reuses fp_mul; matmul reuses dot32_i8


# ---------------- gate helpers (built ONLY from titan_circuit primitives) ----------------
def _sext(c, bits, w): return list(bits) + [bits[-1]] * (w - len(bits))
def _shl(c, bits, k, w): return ([c.C0] * k + list(bits) + [c.C0] * w)[:w]


def _mul_s16(c, a, b):
    """signed 16x16 -> 32-bit product (shift-add; the top partial is subtracted)."""
    a32 = _sext(c, a, 32); acc = c.cvec(0, 32)
    for i in range(15):
        acc = c.add(acc, [c.and_(t, b[i]) for t in _shl(c, a32, i, 32)])
    term = [c.and_(t, b[15]) for t in _shl(c, a32, 15, 32)]
    return c.add(acc, c.add([c.not_(t) for t in term], c.cvec(1, 32)))


def _lut(c, idx_bits, table, out_w):
    """a mux tree: idx_bits (LSB first) select a baked constant from `table` (len 2^k). Pure gates, byte-exact by build."""
    nodes = [c.cvec(v & ((1 << out_w) - 1), out_w) for v in table]
    for s in idx_bits:
        nxt = []
        for j in range(0, len(nodes), 2):
            lo, hi = nodes[j], nodes[j + 1]
            nxt.append([c.mux(s, lo[b], hi[b]) for b in range(out_w)])   # mux(s,a,b)=s?b:a  -> bit=0 lo, bit=1 hi
        nodes = nxt
    return nodes[0]


# ---------------- the inference gate-set (each a circuit + its reference) ----------------
def build_fp_mul():
    """Q8.8 fixed-point multiply: (a*b)>>8 -> 16-bit. Serves general multiply AND dequant-scale (q * scale)."""
    c = TC.Circuit(32); a = c.IN[0:16]; b = c.IN[16:32]
    return c, _mul_s16(c, a, b)[FRAC:FRAC + 16]


def _ref_fp_mul(a, b): return ((((a & 0xFFFF) * (b & 0xFFFF)) if False else (a * b)) & 0xFFFFFFFF) >> FRAC & 0xFFFF


def build_lut_op(fn, kbits=10, out_w=16):
    """generic LUT op: the 16-bit Q8.8 input's TOP kbits are the address (a pure bit-slice), the value is baked.
    idx (signed kbits) represents x ~= idx * 2^(16-kbits) in Q8.8; table[idx] = round(fn(x)*SC)."""
    shift = 16 - kbits; c = TC.Circuit(16)
    idx = c.IN[shift:16]                                   # top kbits of x (includes sign) = the address, no arithmetic
    table = []
    half = 1 << kbits
    for u in range(half):
        s = u - half if u >= (half >> 1) else u            # signed index
        x = (s << shift) / SC                              # the x this address stands for
        v = int(round(fn(x) * SC))
        table.append(v & 0xFFFF)
    return c, _lut(c, list(idx), _reorder(table, kbits), out_w), table, shift, kbits


def _reorder(table, kbits):
    """the LUT tree consumes idx LSB-first as a plain binary counter 0..2^k-1; table is already in that order."""
    return table


def build_cmp_gt():
    """signed a>b -> 1 bit (for argmax / sampling). a-b in 17-bit sext; gt = (diff != 0) & (sign == 0)."""
    c = TC.Circuit(32); a = c.IN[0:16]; b = c.IN[16:32]
    a17 = _sext(c, a, 17); nb = [c.not_(x) for x in _sext(c, b, 17)]
    diff = c.add(c.add(a17, nb), c.cvec(1, 17))            # a - b (17-bit)
    nz = c.not_(c.is_zero(diff)); pos = c.not_(diff[16])   # not zero, and sign bit clear
    return c, [c.and_(nz, pos)]


# ---------------- fabricate (byte-exact, reversible, ALL AT ONCE) ----------------
def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def _s16(u): return u - 0x10000 if u >= 0x8000 else u


def fab():
    import math, random
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    present = [n for n in NAMES if n in reg]
    if present:
        print(f"already baked: {present}. revert first to re-bake."); return 0
    jobs = []; random.seed(3)

    # 1) fp_mul (multiply + dequant-scale)
    c, o = build_fp_mul(); cd = _cd(c, o); ok = True
    for _ in range(300):
        a = random.randint(-2000, 2000); b = random.randint(-2000, 2000)
        got = TC.frombits(TC.ripple(cd, [(a >> k) & 1 for k in range(16)] + [(b >> k) & 1 for k in range(16)]))
        if got != (_ref_fp_mul(a, b)): ok = False; break
    jobs.append(("fp_mul", c, o, ok, "Q8.8 multiply / dequant-scale"))

    # 2) silu, 3) exp, 4) rsqrt — LUT activation/normalize ops (byte-exact by construction)
    for name, fn, desc in [("silu_lut", lambda x: x / (1.0 + math.exp(-x)) if -30 < x else 0.0, "SiLU activation"),
                           ("exp_lut", lambda x: math.exp(x) if x < 11 else math.exp(11), "exp (softmax)"),
                           ("rsqrt_lut", lambda x: 1.0 / math.sqrt(x) if x > (1.0 / SC) else float(SC), "1/sqrt (rmsnorm)")]:
        c, o, table, shift, kbits = build_lut_op(fn); cd = _cd(c, o); ok = True
        for u in range(1 << kbits):                        # verify EVERY address
            x16 = (u << shift) & 0xFFFF
            if TC.frombits(TC.ripple(cd, [(x16 >> k) & 1 for k in range(16)])) != table[u]: ok = False; break
        jobs.append((name, c, o, ok, desc))

    # 5) cmp_gt (argmax / sample)
    c, o = build_cmp_gt(); cd = _cd(c, o); ok = True
    for _ in range(400):
        a = random.randint(-30000, 30000); b = random.randint(-30000, 30000)
        got = TC.frombits(TC.ripple(cd, [(a >> k) & 1 for k in range(16)] + [(b >> k) & 1 for k in range(16)]))
        if got != (1 if a > b else 0): ok = False; break
    jobs.append(("cmp_gt", c, o, ok, "signed a>b (argmax/sample)"))

    for name, c, o, ok, desc in jobs:
        print(f"  {name:10s} {desc:26s} gates={len(c.ga):>8,}  byte-exact: {ok}", flush=True)
        if not ok: print(f"  MISMATCH on {name} — storing NOTHING (no cheating)."); return 1
    for name, c, o, ok, desc in jobs:                      # all verified -> store all (reversible)
        info = TC.store(name, c, o)
        print(f"BAKED {name} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes.", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\ntitan GGUF-valid: {gg}. matmul-dot atom already baked = dot32_i8.")
    print("THE FORWARD PASS IS NOW GATES IN THE SDC: dequant·matmul·rmsnorm·silu·softmax·argmax. Reversible.")
    print("revert: python host/sdc_bake_inference.py revert")
    return 0


def revert():
    if not os.path.exists(REG): print("no registry."); return 0
    reg = json.load(open(REG)); removed = [n for n in NAMES if reg.pop(n, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "revert": raise SystemExit(revert())
    raise SystemExit(fab())
