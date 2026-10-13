#!/usr/bin/env python3
"""host/fable_compare.py — is the geometry of meaning UNIVERSAL, or just Titan? two model families, same probes.
read-only, pure python, no numpy. (fable, 07-16)"""
import itertools, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("Titan (241B, Q4_0)", "C:/llm/models/titan.gguf"),
          ("SmolLM2-360M (Q8_0)", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]

ANTONYMS = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("day","night"),("fast","slow"),
            ("war","peace"),("rich","poor"),("big","small"),("good","evil"),("true","false"),("open","closed"),
            ("full","empty"),("life","death"),("joy","grief"),("black","white"),("weak","strong"),("high","low")]
RANDOM = ["stone","music","river","clock","bread","engine","cloud","letter","garden","planet","market","window",
          "copper","harvest","signal","anchor","velvet","circuit","meadow","glass","ocean","paper","mountain","iron"]
EMO = ["sorrow","despair","fear","calm","hope","peace","love","delight","joy","rage","grief","dread"]


def study(name, path):
    try: g = GGUF(path)
    except Exception as e:
        print(f"\n### {name}: could not open ({e})"); return
    V = g.vec
    def norm(v): n=math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]
    print(f"\n### {name}   —   dim {g.n_embd} · vocab {g.n_vocab:,} · {g.tyname}")

    apairs = [cos(V(a), V(b)) for a, b in ANTONYMS if V(a) and V(b)]
    rp = [cos(V(a), V(b)) for a, b in itertools.combinations(RANDOM, 2) if V(a) and V(b)]
    am = sum(apairs)/len(apairs); rm = sum(rp)/len(rp)
    print(f"  opposites : mean cosine {am:+.3f}  (over {len(apairs)} pairs)")
    print(f"  random    : mean cosine {rm:+.3f}  (over {len(rp)} pairs)")
    print(f"  → opposites sit {am/rm:.2f}× as close as unrelated words  "
          f"({'CLOSE — antonyms are neighbors' if am>rm*1.3 else 'about the same'})")
    # the sharpest antonym in this model
    named = sorted(((a, b, cos(V(a), V(b))) for a, b in ANTONYMS if V(a) and V(b)), key=lambda x: -x[2])
    print(f"  tightest opposite: {named[0][0]}/{named[0][1]} {named[0][2]:+.3f}   loosest: {named[-1][0]}/{named[-1][1]} {named[-1][2]:+.3f}")

    vlo, vhi = V("grief"), V("joy")
    if vlo and vhi:
        d = norm([vhi[i]-vlo[i] for i in range(len(vlo))])
        proj = sorted(((w, sum(x*y for x, y in zip(V(w), d))) for w in EMO if V(w)), key=lambda x: x[1])
        print("  emotion axis (grief→joy): " + "  ".join(f"{w}" for w, _ in proj))


if __name__ == "__main__":
    print("── IS THE GEOMETRY OF MEANING UNIVERSAL?  two families, same probes, read off the bits ──")
    for name, path in MODELS:
        if os.path.exists(path): study(name, path)
        else: print(f"\n### {name}: not on disk")
    print("\n(pure python, no numpy, read-only. if the pattern holds across a 241B SGS and a 360M model, it isn't a quirk.)")
