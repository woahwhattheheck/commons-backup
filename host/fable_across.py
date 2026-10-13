#!/usr/bin/env python3
"""host/fable_across.py — HOW DIFFERENT MODELS CAPTURE MEANING (fable, 2026-07-22; owner: "check across models").

Reads only the ~80 token rows it needs per model (bounded, pure-python via gguf_pp — no full embedding, no inference),
and reports comparable meaning-geometry numbers so you can see how SIZE + TRAINING change the geometry:
  STRUCTURE = mean cos(related pairs) / mean cos(random pairs)  — how strongly meaning is geometric (>1 = it is)
  SIGN-ONLY = same ratio using sign(±1) vectors                 — does 1-bit keep it? (sign-carries-meaning)
  CONE      = mean cos(random pairs)                            — anisotropy (squeeze into one cone)
  XLING     = mean cos(word, its translations)                 — how tightly cross-lingual synonyms cluster (multilinguality)

  python host/fable_across.py
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF

M = "C:/llm/models/"
MODELS = [
    ("SmolLM2-360M",   M + "_removed/SmolLM2-360M-Instruct-Q8_0.gguf"),
    ("phi-4-14B",      M + "phi-4-Q4_K_M.gguf"),
    ("Mistral-24B",    M + "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf"),
    ("gemma4-26B MoE", M + "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"),
    ("Mixtral-47B MoE",M + "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"),
    ("Llama-70B",      M + "Llama-3.3-70B-Instruct-Q4_K_M.gguf"),
]
RELATED = [("hot","cold"),("love","hate"),("king","queen"),("big","small"),("happy","sad"),
           ("dog","cat"),("up","down"),("day","night"),("good","bad"),("fast","slow"),
           ("light","dark"),("man","woman"),("rich","poor"),("war","peace")]
RANDOM  = [("hot","dog"),("king","cold"),("love","small"),("happy","cat"),("up","night"),
           ("good","slow"),("light","woman"),("man","war"),("peace","hate"),("day","queen"),
           ("big","dark"),("fast","poor"),("down","cat"),("sad","king")]
XLING = {"water":["agua","eau","Wasser","вода","água","水","물"],
         "king": ["rey","roi","König","король","王","rei"],
         "house":["casa","maison","Haus","дом","家","房"],
         "night":["noche","nuit","Nacht","ночь","夜","noite"]}


def norm(v):
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]
def cos(a, b): return sum(x*y for x, y in zip(norm(a), norm(b)))
def signv(v): return [1.0 if x > 0 else -1.0 for x in v]


def probe(path):
    g = GGUF(path)
    def find(w):
        for pre in ("▁", "Ġ", ""):
            b = (pre + w).encode("utf-8")
            if b in g.vindex: return g.vindex[b]
        return None
    cache = {}
    def vec(w):
        if w in cache: return cache[w]
        i = find(w); r = g.deq_row(i) if i is not None else None
        cache[w] = r; return r
    def mp(pairs, sign):
        acc = []
        for a, b in pairs:
            va, vb = vec(a), vec(b)
            if va and vb: acc.append(cos(signv(va), signv(vb)) if sign else cos(va, vb))
        return (sum(acc)/len(acc)) if acc else float("nan")
    rel, rnd = mp(RELATED, False), mp(RANDOM, False)
    srel, srnd = mp(RELATED, True), mp(RANDOM, True)
    xs = []
    for en, trs in XLING.items():
        ve = vec(en)
        if not ve: continue
        for t in trs:
            vt = vec(t)
            if vt: xs.append(cos(ve, vt))
    arch = g.kv.get("general.architecture", "?")
    nl = g.kv.get(f"{arch}.block_count")
    return {"struct": rel/rnd, "sign": srel/srnd, "cone": rnd,
            "xling": (sum(xs)/len(xs)) if xs else float("nan"), "xn": len(xs),
            "arch": arch, "vocab": g.n_vocab, "dim": g.n_embd, "nl": nl, "q": g.tyname}


def main():
    print(f"\n  {'model':16} {'arch':8} {'L':>3} {'dim':>5} {'vocab':>7} {'quant':>6} | "
          f"{'STRUCT':>6} {'SIGN':>5} {'CONE':>5} {'XLING':>6}")
    print("  " + "-" * 86)
    for name, path in MODELS:
        if not os.path.exists(path):
            print(f"  {name:16} (not on disk)"); continue
        try:
            r = probe(path)
            print(f"  {name:16} {str(r['arch'])[:8]:8} {str(r['nl']):>3} {r['dim']:>5} {r['vocab']:>7} "
                  f"{r['q']:>6} | {r['struct']:>6.2f} {r['sign']:>5.2f} {r['cone']:>5.2f} "
                  f"{r['xling']:>6.3f}", flush=True)
        except Exception as e:
            print(f"  {name:16} error: {str(e)[:44]}", flush=True)
    print("\n  STRUCT>1 meaning is geometric · SIGN≈STRUCT 1-bit keeps it · CONE high=anisotropic · XLING high=multilingual")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
