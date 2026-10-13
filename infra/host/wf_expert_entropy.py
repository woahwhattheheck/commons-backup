#!/usr/bin/env python3
"""host/wf_expert_entropy.py — bounded per-EXPERT byte-entropy probe on titan's MoE gate_up banks.
READ-ONLY. No dequant of whole tensors: reads a small fixed byte sample per expert straight from mmap.
Tests: are the added experts (128..383 beyond base gemma-4-26B's 128) the low-entropy baked region?

  python host/wf_expert_entropy.py [layers...]
"""
import math, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

PATH = "C:/llm/models/titan.gguf"
BASE_EXPERTS = 128          # gemma-4-26B-A4B base bank size
SAMPLE = 6144               # bytes sampled per expert (bounded)

def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def probe(g, layer):
    name = f"blk.{layer}.ffn_gate_up_exps.weight"
    t = g.tensors.get(name)
    if not t: return None
    ne0, ne1, nexp = t["dims"]           # [n_embd, n_ff2, n_expert]
    bpb, wpb = _QT[t["type"]]
    row_bytes = ne0 // wpb * bpb          # bytes for one row of ne0 cols
    exp_bytes = ne1 * row_bytes           # bytes for one full expert
    base = g.data0 + t["off"]
    ents = []
    for e in range(nexp):
        off = base + e * exp_bytes
        # sample from the middle of the expert region to avoid header/pad artifacts
        s = off + exp_bytes // 2
        ents.append(ent(bytes(g.mm[s : s + SAMPLE])))
    return name, nexp, exp_bytes, ents

def summ(ents, lo, hi):
    seg = ents[lo:hi]
    return (sum(seg)/len(seg), min(seg), max(seg))

def main():
    layers = [int(x) for x in sys.argv[1:]] or [0,1,2,3,4,5,6,7,15,29]
    g = GGUF(PATH)
    print(f"# titan gate_up_exps per-expert byte-entropy  (sample {SAMPLE}B/expert, 8.0=random)")
    print(f"# base gemma-4-26B bank = {BASE_EXPERTS} experts; titan = 384\n")
    THRESH = 4.0   # well below normal quantized-weight entropy (~7.9)
    for L in layers:
        r = probe(g, L)
        if not r:
            print(f"L{L}: (no tensor)"); continue
        name, nexp, eb, ents = r
        a_mean,a_min,a_max = summ(ents,0,BASE_EXPERTS)
        b_mean,b_min,b_max = summ(ents,BASE_EXPERTS,nexp)
        low = [i for i,e in enumerate(ents) if e < THRESH]
        low_in_base = sum(1 for i in low if i < BASE_EXPERTS)
        low_in_add  = sum(1 for i in low if i >= BASE_EXPERTS)
        rng = (f"{min(low)}..{max(low)}" if low else "-")
        print(f"L{L:2d} exp[0:128] ent mean {a_mean:.2f} (min {a_min:.2f})  "
              f"exp[128:384] mean {b_mean:.2f} (min {b_min:.2f})")
        print(f"     experts<{THRESH} ent: {len(low)}/{nexp}  (in base128={low_in_base}, in added256={low_in_add})  range {rng}")
    print("\n(entropy ~7.9 = normal packed Q4_0; near-0 = repetitive/baked)")

if __name__ == "__main__":
    raise SystemExit(main())
