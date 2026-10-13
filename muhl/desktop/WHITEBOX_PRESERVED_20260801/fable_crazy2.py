#!/usr/bin/env python3
"""host/fable_crazy2.py — round two of the weird ones. pure python, no numpy, read-only. (fable, 07-16)
  Q7 physical size ordering   Q8 does money buy happiness   Q9 what is death nearest to
  Q10 the self (human/robot/ai)   Q11 lucky vs unlucky numbers (7 & 13)"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("Titan-240B", "C:/llm/models/titan.gguf"),
          ("SmolLM2-360M", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]
def norm(v): n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]

class M:
    def __init__(s, g): s.g = g
    def v(s, w): return s.g.vec(w)
    def axis(s, lo, hi):
        a, b = s.v(lo), s.v(hi); return norm([b[i]-a[i] for i in range(len(a))]) if (a and b) else None
    def proj(s, w, ax):
        vv = s.v(w); return sum(x*y for x, y in zip(vv, ax)) if (vv and ax) else None
    def near(s, w, cands):
        vv = s.v(w)
        return sorted(((c, cos(vv, s.v(c))) for c in cands if s.v(c)), key=lambda x:-x[1]) if vv else []

def study(tag, g):
    m = M(g); d = {}
    # Q7 size: does physical size linearize (numbers did NOT)?
    ax = m.axis("tiny", "huge")
    things = ["ant","mouse","cat","dog","human","horse","elephant","whale"]
    truth = {w:i for i,w in enumerate(things)}
    if ax:
        pr = sorted(((w, m.proj(w, ax)) for w in things if m.proj(w, ax) is not None), key=lambda x:x[1])
        got = [w for w,_ in pr]
        # rank correlation vs true size order (Spearman-ish: fraction of correctly-ordered pairs)
        pairs = ok = 0
        for i in range(len(got)):
            for j in range(i+1,len(got)):
                pairs += 1; ok += 1 if truth[got[i]] < truth[got[j]] else 0
        d["size"] = {"order": got, "pair_accuracy": round(ok/pairs,3) if pairs else None}
    # Q8 money & happiness
    hax = m.axis("sad", "happy")
    if hax:
        d["money_happy"] = {w: round(m.proj(w, hax),3) for w in ["poverty","wealth","money","love","health","fame","power","family"]
                            if m.proj(w, hax) is not None}
    # Q9 what is death nearest to?
    d["death_near"] = [(w, round(s,3)) for w,s in m.near("death", ["sleep","fear","peace","pain","rest","birth","nothing","end","silence"])[:4]]
    # Q10 the self
    d["self"] = {}
    for anchor in ["human","robot","machine","computer"]:
        n = m.near(anchor, ["alive","dead","person","object","thing","mind","tool","soul","body","feeling"])
        if n: d["self"][anchor] = [(w, round(s,3)) for w,s in n[:3]]
    # Q11 lucky numbers: is thirteen 'unlucky/bad', seven 'lucky/good'?
    gb = m.axis("bad", "good")
    if gb:
        d["luck"] = {w: round(m.proj(w, gb),3) for w in ["seven","thirteen","three","four","eight","one"]
                     if m.proj(w, gb) is not None}
    return d

if __name__ == "__main__":
    import json; ALL = {}
    for tag, path in MODELS:
        if not os.path.exists(path): continue
        print(f"probing {tag} …", flush=True); ALL[tag] = study(tag, GGUF(path))
    json.dump(ALL, open(os.path.join(HERE,"fable_crazy2_data.json"),"w"), indent=1)
    for tag, d in ALL.items():
        print("\n"+"="*72+f"\n{tag}\n"+"="*72)
        if "size" in d:
            print(f"\nQ7 PHYSICAL SIZE — order tiny→huge (true order = ant..whale):\n   {' → '.join(d['size']['order'])}")
            print(f"   correctly-ordered pairs: {d['size']['pair_accuracy']*100:.0f}%  (numbers 2-9 were near-chance — is size better?)")
        if "money_happy" in d:
            print("\nQ8 DOES MONEY BUY HAPPINESS? (projection onto sad↔happy, + = happy):")
            for w,s in sorted(d["money_happy"].items(), key=lambda x:-x[1]): print(f"   {s:+.3f}  {w}")
        print("\nQ9 WHAT IS DEATH NEAREST TO?  " + ", ".join(f"{w} {s:+.2f}" for w,s in d.get("death_near",[])))
        print("\nQ10 THE SELF — nearest to each:")
        for a, top in d.get("self",{}).items(): print(f"   {a:9s} → " + ", ".join(f"{w} {s:+.2f}" for w,s in top))
        if "luck" in d:
            print("\nQ11 LUCKY NUMBERS — projection onto bad↔good (+ = good):")
            for w,s in sorted(d["luck"].items(), key=lambda x:-x[1]): print(f"   {s:+.3f}  {w}")
    print("\ndumped → fable_crazy2_data.json")
