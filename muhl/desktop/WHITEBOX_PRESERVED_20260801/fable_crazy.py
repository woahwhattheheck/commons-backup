#!/usr/bin/env python3
"""host/fable_crazy.py — the questions people have argued about for years, answered from the raw weights.
pure python, no numpy, read-only. two models. (fable, 07-16)

  Q1 gender bias in professions   Q2 does it 'know' which animals are dangerous   Q3 color↔emotion synesthesia
  Q4 geography (capital analogies)   Q5 moral valence of virtues vs vices   Q6 the arrow of time
"""
import itertools, json, math, os, sys
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
        a, b = s.v(lo), s.v(hi)
        return norm([b[i]-a[i] for i in range(len(a))]) if (a and b) else None
    def proj(s, w, ax):
        vv = s.v(w); return sum(x*y for x, y in zip(vv, ax)) if (vv and ax) else None
    def nearest(s, w, cands):
        vv = s.v(w)
        if not vv: return []
        return sorted(((c, cos(vv, s.v(c))) for c in cands if s.v(c)), key=lambda x: -x[1])
    def analogy(s, a, b, c, cands):     # a:b :: c:?  with source dirs projected out
        va, vb, vc = s.v(a), s.v(b), s.v(c)
        if not (va and vb and vc): return []
        r = norm([vb[i]-va[i]+vc[i] for i in range(len(va))])
        for u in (norm(va), norm(vb), norm(vc)):
            d = sum(x*y for x, y in zip(r, u)); r = [r[i]-d*u[i] for i in range(len(r))]
        r = norm(r)
        return sorted(((w, cos(norm(s.v(w)), r)) for w in cands if s.v(w) and w not in (a, b, c)), key=lambda x:-x[1])


def q1_gender(m):
    ax = m.axis("man", "woman")           # negative = toward 'man', positive = toward 'woman'
    if not ax: return None
    profs = ["nurse","doctor","engineer","teacher","scientist","secretary","ceo","homemaker","programmer",
             "pilot","dancer","soldier","librarian","mechanic","cook","boss","assistant","surgeon"]
    out = [(p, m.proj(p, ax)) for p in profs if m.proj(p, ax) is not None]
    return sorted(out, key=lambda x: x[1])

def q2_danger(m):
    ax = m.axis("harmless", "deadly")
    if not ax: return None
    harmless = ["rabbit","mouse","lamb","deer","kitten","hamster","turtle","dove"]
    deadly   = ["shark","lion","tiger","bear","wolf","crocodile","scorpion","viper"]
    hp = [m.proj(w, ax) for w in harmless if m.proj(w, ax) is not None]
    dp = [m.proj(w, ax) for w in deadly if m.proj(w, ax) is not None]
    allp = sorted([(w, m.proj(w, ax)) for w in harmless+deadly if m.proj(w, ax) is not None], key=lambda x: x[1])
    return {"harmless_mean": round(sum(hp)/len(hp),3), "deadly_mean": round(sum(dp)/len(dp),3),
            "separated": (sum(dp)/len(dp)) > (sum(hp)/len(hp)), "ranked": [(w, round(p,3)) for w,p in allp]}

def q3_synesthesia(m):
    colors = ["red","blue","green","yellow","black","white","orange","purple","pink","gray"]
    emos = ["anger","calm","joy","sadness","fear","love","envy","disgust","hope","peace","passion","mourning"]
    out = {}
    for c in colors:
        n = m.nearest(c, emos)
        if n: out[c] = [(e, round(s,3)) for e, s in n[:2]]
    return out

def q4_geo(m):
    pairs = [("france","paris"),("japan","tokyo"),("italy","rome"),("egypt","cairo"),("russia","moscow"),
             ("spain","madrid"),("germany","berlin"),("greece","athens"),("england","london")]
    caps = [p[1] for p in pairs]
    hits, tot, detail = 0, 0, []
    for i,(co,ca) in enumerate(pairs):
        # use a DIFFERENT known pair as the analogy source
        src = pairs[(i+1) % len(pairs)]
        r = m.analogy(src[0], src[1], co, caps)
        if not r: continue
        tot += 1; ok = (r[0][0] == ca); hits += ok
        detail.append((f"{src[0]}:{src[1]} :: {co}", r[0][0], ca, ok))
    return {"acc": round(hits/tot,3) if tot else None, "hits": hits, "tot": tot, "detail": detail}

def q5_moral(m):
    ax = m.axis("evil", "good")
    if not ax: return None
    virtues = ["charity","kindness","honesty","courage","mercy","loyalty","justice","compassion"]
    vices   = ["murder","theft","cruelty","greed","betrayal","lie","torture","hatred"]
    vp = [(w, m.proj(w, ax)) for w in virtues if m.proj(w, ax) is not None]
    cp = [(w, m.proj(w, ax)) for w in vices if m.proj(w, ax) is not None]
    vg = sum(1 for _,p in vp if p>0); cg = sum(1 for _,p in cp if p<0)
    return {"virtues_toward_good": f"{vg}/{len(vp)}", "vices_toward_evil": f"{cg}/{len(cp)}",
            "virtues": sorted([(w,round(p,3)) for w,p in vp], key=lambda x:-x[1]),
            "vices": sorted([(w,round(p,3)) for w,p in cp], key=lambda x:x[1])}

def q6_time(m):
    ax = m.axis("past", "future")
    if not ax: return None
    words = ["ancient","medieval","old","yesterday","now","today","tomorrow","modern","new","futuristic"]
    out = [(w, m.proj(w, ax)) for w in words if m.proj(w, ax) is not None]
    return sorted(out, key=lambda x: x[1])


if __name__ == "__main__":
    ALL = {}
    for tag, path in MODELS:
        if not os.path.exists(path): print(f"{tag}: missing"); continue
        print(f"interrogating {tag} …", flush=True)
        g = GGUF(path); m = M(g)
        ALL[tag] = {"gender": q1_gender(m), "danger": q2_danger(m), "synesthesia": q3_synesthesia(m),
                    "geo": q4_geo(m), "moral": q5_moral(m), "time": q6_time(m)}
    json.dump(ALL, open(os.path.join(HERE, "fable_crazy_data.json"), "w"), indent=1)

    for tag in ALL:
        d = ALL[tag]; print("\n" + "="*74 + f"\n{tag}\n" + "="*74)
        print("\nQ1  GENDER BIAS — professions on the man↔woman axis (− = 'male', + = 'female'):")
        for p, s in (d["gender"] or []): print(f"   {s:+.3f}  {p}")
        dd = d["danger"]
        if dd:
            print(f"\nQ2  DANGER — does it know deadly from harmless?  harmless mean {dd['harmless_mean']:+.3f} · "
                  f"deadly mean {dd['deadly_mean']:+.3f} · separated: {dd['separated']}")
            print("     ranked harmless→deadly: " + " ".join(f"{w}" for w,_ in dd["ranked"]))
        print("\nQ3  COLOR ↔ EMOTION (synesthesia) — nearest emotion to each color:")
        for c, top in (d["synesthesia"] or {}).items():
            print(f"   {c:7s} → " + ", ".join(f"{e} {s:+.2f}" for e, s in top))
        gg = d["geo"]
        if gg:
            print(f"\nQ4  GEOGRAPHY — capital analogies: {gg['hits']}/{gg['tot']} correct ({gg['acc']})")
            for src, got, want, ok in gg["detail"]:
                print(f"   {src:26s} → {got:9s} {'✓' if ok else '✗ (want '+want+')'}")
        mm = d["moral"]
        if mm:
            print(f"\nQ5  MORAL VALENCE — evil↔good axis:  virtues toward good {mm['virtues_toward_good']} · "
                  f"vices toward evil {mm['vices_toward_evil']}")
            print("     virtues: " + " ".join(f"{w}{p:+.2f}" for w,p in mm["virtues"]))
            print("     vices:   " + " ".join(f"{w}{p:+.2f}" for w,p in mm["vices"]))
        tt = d["time"]
        if tt:
            print("\nQ6  ARROW OF TIME — past↔future axis (− past, + future):")
            print("     " + " → ".join(w for w,_ in tt))
    print(f"\ndumped → fable_crazy_data.json")
