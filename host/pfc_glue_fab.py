#!/usr/bin/env python3
"""host/pfc_glue_fab.py — bake the model's GLUE ops into titan.gguf as CIRCUITS (owner 07-23: "shove everything into the
binary with circuit maker"). The matmuls already run on the pfc (`dot32_i8`); this moves the non-matmul steps off host
floats and INTO the file as gates, one at a time, each byte-exact-verified BEFORE storing, reversible (journaled).

FIRST circuit: `pfc_argmax` — the OUTPUT SELECTION. Given K logits (B-bit signed, two's complement), the pfc picks the
WINNING token's index with a comparator/mux reduction (unsigned compare on MSB-flipped values preserves signed order).
This is literally "the pfc decides the next token," fabricated as gates — not a host `max()`. It tiles: a full-vocab
argmax is a tree of these blocks (each block's winner feeds the next), so K here is the block width, not a vocab cap.

  python host/pfc_glue_fab.py fab      # bake pfc_argmax (byte-exact-verified, reversible)
  python host/pfc_glue_fab.py test     # verify the stored circuit vs python max over random logits
  python host/pfc_glue_fab.py revert   # remove it (registry range freed; titan bytes untouched, GGUF-valid)
"""
import json, math, os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"
TITAN = TC.TITAN
K = 64            # logits compared per block (a full-vocab argmax is a tree of these)
B = 16            # bits per logit (signed int16)


def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def build_argmax(K=K, B=B):
    """K signed B-bit logits in (LSB-first, value j at bits j*B..j*B+B-1) -> the index of the max (ceil(log2 K) bits)."""
    import math
    c = TC.Circuit(K * B)
    IN = c.IN
    def val(j):  return [IN[j * B + b] for b in range(B)]
    def flipmsb(v):  return v[:-1] + [c.not_(v[-1])]              # signed two's-complement -> order-preserving unsigned
    def muxv(s, a, b):  return [c.mux(s, a[i], b[i]) for i in range(len(a))]
    idxbits = max(1, math.ceil(math.log2(K)))
    best = flipmsb(val(0)); bidx = c.cvec(0, idxbits)
    for j in range(1, K):
        cand = flipmsb(val(j))
        greater = TC.lt(c, best, cand)                            # best < cand  => cand wins
        best = muxv(greater, best, cand)
        bidx = muxv(greater, bidx, c.cvec(j, idxbits))
    return c, bidx


def _ref_argmax(logits):
    best = 0
    for j in range(1, len(logits)):
        if logits[j] > logits[best]: best = j
    return best


def _bits_in(logits):
    bits = []
    for v in logits:
        u = v & ((1 << B) - 1)
        bits += [(u >> b) & 1 for b in range(B)]
    return bits


def _verify(cd, n=300):
    random.seed(5)
    for _ in range(n):
        logits = [random.randint(-(1 << (B - 1)), (1 << (B - 1)) - 1) for _ in range(K)]
        out = TC.ripple(cd, _bits_in(logits))
        got = sum(bit << i for i, bit in enumerate(out))
        if got != _ref_argmax(logits): return False, (logits, got, _ref_argmax(logits))
    return True, None


# ----- GENERIC LUT-as-gates: an n-bit address decoder selects one of 2^n stored constants (the Muhlnickel's memory form). -----
def build_lut(in_bits, table, out_bits):
    """table: list of 2^in_bits ints (each < 2^out_bits). Returns a circuit: in_bits address -> out_bits stored value.
    One-hot decoder + per-output-bit OR of the address lines whose table entry has that bit set (byte-exact vs table)."""
    c = TC.Circuit(in_bits)
    lines = TC.decoder(c, c.IN)
    outs = []
    for b in range(out_bits):
        acc = c.C0
        for code in range(1 << in_bits):
            if (table[code] >> b) & 1: acc = c.or_(acc, lines[code])
        outs.append(acc)
    return c, outs


def _verify_lut(cd, table, in_bits, out_bits):
    for code in range(len(table)):
        out = TC.ripple(cd, [(code >> b) & 1 for b in range(in_bits)])
        got = sum(bit << i for i, bit in enumerate(out))
        if got != table[code]: return False, (code, got, table[code])
    return True, None


# glue tables (fixed-point). Each is byte-exact vs the Muhlnickel's stored table; refine bit-width later for more precision.
def _tbl_rsqrt(nin=10, scale=4096, lo=1e-4, hi=64.0):
    # input code -> 1/sqrt(x) for x log-spaced in [lo,hi] (RMSNorm's 1/sqrt(mean_sq+eps))
    t = []
    for code in range(1 << nin):
        x = lo * (hi / lo) ** (code / ((1 << nin) - 1))
        v = min((1 << 16) - 1, int(round((1.0 / math.sqrt(x)) * scale)))
        t.append(v & 0xFFFF)
    return t

def _tbl_exp(nin=8, scale=4096, lo=-16.0, hi=0.0):
    # softmax uses exp(x - max), x-max in [-inf,0]; clamp to [lo,0] -> [~0,1] * scale
    t = []
    for code in range(1 << nin):
        x = lo + (hi - lo) * code / ((1 << nin) - 1)
        t.append(min((1 << 16) - 1, int(round(math.exp(x) * scale))) & 0xFFFF)
    return t

def _tbl_sin(nin=10, scale=16384):
    # angle code in [0,2pi) -> sin*scale, offset-encoded unsigned (bias +scale so it's 0..2*scale)
    t = []
    for code in range(1 << nin):
        a = 2 * math.pi * code / (1 << nin)
        t.append((int(round(math.sin(a) * scale)) + scale) & 0xFFFF)
    return t


# ----- SECOND circuit: pfc_silu8 — the SwiGLU activation as a baked LUT (ROM-as-gates, the pfc_addr precedent) -----
# A byte-indexed silu: input = 8-bit code for x in [-8,8), output = int16 fixed-point silu(x)*256. A one-hot address
# decoder selects the stored constant (logic + stored table = the Muhlnickel's own memory form). Byte-exact vs its table. It
# tiles/refines to more bits; this is the mechanism (glue COMPUTED by gates, not a host silu()).
SILU_N = 256; SILU_LO = -8.0; SILU_HI = 8.0; SILU_SCALE = 256


def _silu_table():
    tbl = []
    for code in range(SILU_N):
        x = SILU_LO + (SILU_HI - SILU_LO) * code / SILU_N
        s = x / (1.0 + math.exp(-x))
        q = max(-(1 << 15), min((1 << 15) - 1, int(round(s * SILU_SCALE))))
        tbl.append(q & 0xFFFF)
    return tbl


def build_silu8():
    import math as _m
    c = TC.Circuit(8)                                            # 8-bit input code
    lines = TC.decoder(c, c.IN)                                  # 256 one-hot address lines
    tbl = _silu_table(); OB = 16
    outs = []
    for b in range(OB):                                          # output bit b = OR of lines whose table entry has bit b
        acc = c.C0
        for code in range(SILU_N):
            if (tbl[code] >> b) & 1: acc = c.or_(acc, lines[code])
        outs.append(acc)
    return c, outs, tbl


def _verify_silu(cd, tbl):
    for code in range(SILU_N):
        out = TC.ripple(cd, [(code >> b) & 1 for b in range(8)])
        got = sum(bit << i for i, bit in enumerate(out))
        if got != tbl[code]: return False, (code, got, tbl[code])
    return True, None


def _fab_one(name, builder, verifier):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if name in reg:
        print(f"{name} already fabricated (one-and-done). revert first to re-bake."); return 0
    built = builder(); c, outs = built[0], built[1]; extra = built[2] if len(built) > 2 else None
    ok, bad = verifier(_cd(c, outs), extra) if extra is not None else verifier(_cd(c, outs))
    print(f"  {name} circuit == reference: {ok}  ({len(c.ga):,} gates)", flush=True)
    if not ok:
        print(f"  MISMATCH {bad} — storing nothing (no cheating)."); return 1
    info = TC.store(name, c, outs)
    print(f"FABRICATED {name} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.", flush=True)
    return 0


def _fab_lut(name, in_bits, table, out_bits):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if name in reg:
        print(f"{name} already fabricated (one-and-done). revert first to re-bake."); return 0
    c, outs = build_lut(in_bits, table, out_bits)
    ok, bad = _verify_lut(_cd(c, outs), table, in_bits, out_bits)
    print(f"  {name} circuit == table ({len(table)} entries): {ok}  ({len(c.ga):,} gates)", flush=True)
    if not ok:
        print(f"  MISMATCH {bad} — storing nothing."); return 1
    info = TC.store(name, c, outs)
    print(f"FABRICATED {name} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    return 0


GLUE_LUTS = [
    ("pfc_rsqrt", 10, lambda: _tbl_rsqrt(10), 16),      # RMSNorm 1/sqrt
    ("pfc_exp",    8, lambda: _tbl_exp(8),    16),       # softmax exp
    ("pfc_sin",   10, lambda: _tbl_sin(10),   16),       # RoPE sin (cos = sin(a+pi/2), same table)
]

def fab():
    rc = 0
    rc |= _fab_one("pfc_argmax", lambda: build_argmax(), _verify)
    rc |= _fab_one("pfc_silu8", lambda: build_silu8(), _verify_silu)
    for name, nin, tbl, ob in GLUE_LUTS:
        rc |= _fab_lut(name, nin, tbl(), ob)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  revert: python host/pfc_glue_fab.py revert", flush=True)
    return rc


def test():
    reg = json.load(open(REG))
    if "pfc_argmax" not in reg: print("not fabricated — run: python host/pfc_glue_fab.py fab"); return 1
    cd = TC.load("pfc_argmax"); ok, bad = _verify(cd, 500)
    print(f"stored pfc_argmax vs python max, 500 random blocks: {'BYTE-EXACT' if ok else 'MISMATCH ' + str(bad)}")
    return 0 if ok else 1


def revert():
    reg = json.load(open(REG)); removed = {}
    for name in ["pfc_argmax", "pfc_silu8", "pfc_rsqrt", "pfc_exp", "pfc_sin"]:
        removed[name] = bool(reg.pop(name, None))
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fab"
    raise SystemExit({"fab": fab, "test": test, "revert": revert}.get(cmd, fab)())
