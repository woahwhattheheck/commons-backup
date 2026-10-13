#!/usr/bin/env python3
"""host/fable_bits.py — how many bits of each weight does MEANING need? re-quantize the embedding to k bits and
re-measure the geometry. pure python, no numpy, read-only (bit-masks at read time). (fable, 07-16)"""
import itertools, json, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

PATH = "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf"
ANTON = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("day","night"),("true","false"),
         ("big","small"),("good","evil"),("life","death"),("open","closed"),("rich","poor"),("fast","slow")]
RANDW = ["stone","music","river","clock","bread","engine","cloud","letter","garden","planet","window","glass",
         "ocean","paper","mountain","iron","silver","copper","harvest","signal"]
PROBES = ["frog","hop","enemy","danger","true","false","hot","cold","love","hate","joy","grief","king","queen"]


def masked_vec(g, i, kbits):
    """dequant row i but first re-quantize each int8 to k bits (round to 2^(8-k) levels) — Q8_0 only."""
    off = g.data_off + i * g.row_bytes; raw = g.mm[off:off + g.row_bytes]; d = g.n_embd
    out = [0.0]*d; p = 0; o = 0; step = 1 << (8 - kbits)
    while o < d:
        s = struct.unpack_from("<e", raw, p)[0]; p += 2
        for j in range(32):
            q = raw[p + j]; q = q - 256 if q >= 128 else q
            if step > 1:
                q = round(q / step) * step
                q = 127 if q > 127 else (-128 if q < -128 else q)
            out[o + j] = q * s
        p += 32; o += 32
    n = math.sqrt(sum(x*x for x in out)) or 1.0
    return [x/n for x in out]


if __name__ == "__main__":
    g = GGUF(PATH)
    print(f"bit-depth ablation on the small model (Q8_0, dim {g.n_embd}) — re-quantize the embedding to k bits:\n")
    idx = {w: g._find(w) for w in set([x for p in ANTON for x in p] + RANDW + PROBES)}
    def vecs(k): return {w: (masked_vec(g, i, k) for i in [idx[w]])  if idx[w] is not None else None for w in idx}
    rows = []
    print(f"  {'bits':>4} {'levels':>7} {'true/false':>11} {'opp/rand':>9} {'ratio':>6}   frog~hop  love~hate")
    for k in (8, 6, 5, 4, 3, 2, 1):
        cache = {w: (masked_vec(g, idx[w], k) if idx[w] is not None else None) for w in idx}
        def C(a, b): return cos(cache.get(a), cache.get(b)) if (cache.get(a) and cache.get(b)) else None
        A = [C(a, b) for a, b in ANTON if C(a, b) is not None]
        R = [C(a, b) for a, b in itertools.combinations(RANDW, 2) if C(a, b) is not None]
        am, rm = sum(A)/len(A), sum(R)/len(R)
        tf = C("true", "false"); fh = C("frog", "hop"); lh = C("love", "hate")
        rows.append({"bits": k, "levels": 1 << k, "true_false": round(tf,3), "opp": round(am,3),
                     "rand": round(rm,3), "ratio": round(am/rm,3), "frog_hop": round(fh,3), "love_hate": round(lh,3)})
        print(f"  {k:>4} {1<<k:>7} {tf:>+11.3f} {am:>+.3f}/{rm:>+.3f} {am/rm:>6.2f}x   {fh:>+.3f}    {lh:>+.3f}")
    json.dump(rows, open(os.path.join(HERE, "fable_bits_data.json"), "w"), indent=1)
    print("\n  (each weight re-quantized to k bits at read time; 1 bit = sign only. watch where meaning survives.)")
