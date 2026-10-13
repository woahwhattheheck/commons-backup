#!/usr/bin/env python3
"""host/wf_bits_check.py — confirming probe for the "1-bit meaning / precision floor" finding.

Claim under test (from report_data.bits): the true>opp>rand separation is FLAT from 8 down to 3 bits, only
softens at 2, and even a 1-BIT SIGN CODE still separates opposite pairs well above random.

This probe strips the embedding all the way to a 1-bit sign code the crudest possible way: replace every
dequantized element x by sign(x) in {-1,0,+1}, renormalize, and take the cosine. It compares that sign-only
cosine against the full (float) cosine on a handful of opposite pairs + a couple of random-pair controls.

Read-only. Pure python, no numpy. Small control model only (SmolLM2-360M, Q8_0). (wf, 07-23)"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF

PATH = "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"

OPP  = [("hot","cold"), ("true","false"), ("up","down"), ("love","hate"), ("big","small"), ("day","night")]
CTRL = [("stone","music"), ("river","clock"), ("bread","planet")]   # unrelated-word baselines


def unit(v):
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]

def sign_unit(v):
    s = [1.0 if x > 0 else (-1.0 if x < 0 else 0.0) for x in v]   # 1-bit sign code
    n = math.sqrt(sum(x*x for x in s)) or 1.0
    return [x/n for x in s]

def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


if __name__ == "__main__":
    g = GGUF(PATH)
    print(f"1-bit sign-code check on {os.path.basename(g.path)}  (dim {g.n_embd}, {g.tyname}, vocab {g.n_vocab:,})\n")

    def row(w):
        i = g._find(w)
        return g.deq_row(i) if i is not None else None

    def measure(pairs, label):
        print(f"  {label}")
        print(f"    {'pair':<16} {'full cos':>9} {'sign cos':>9}   {'retained':>8}")
        fulls, signs = [], []
        for a, b in pairs:
            ra, rb = row(a), row(b)
            if ra is None or rb is None:
                print(f"    {a+'/'+b:<16} {'(missing)':>9}")
                continue
            fc = dot(unit(ra), unit(rb))
            sc = dot(sign_unit(ra), sign_unit(rb))
            fulls.append(fc); signs.append(sc)
            ret = (sc/fc) if fc else float('nan')
            print(f"    {a+'/'+b:<16} {fc:>+9.3f} {sc:>+9.3f}   {ret:>7.0%}")
        if fulls:
            mf, ms = sum(fulls)/len(fulls), sum(signs)/len(signs)
            print(f"    {'MEAN':<16} {mf:>+9.3f} {ms:>+9.3f}   {(ms/mf if mf else float('nan')):>7.0%}")
            return mf, ms
        return None, None

    of, os_ = measure(OPP,  "opposite pairs:")
    print()
    cf, cs_ = measure(CTRL, "random-word controls:")
    print()
    if None not in (of, os_, cf, cs_):
        print(f"  SEPARATION (opp - ctrl):  full = {of-cf:+.3f}   sign-only = {os_-cs_:+.3f}")
        print(f"  RATIO      (opp / ctrl):  full = {of/cf:.2f}x   sign-only = {os_/cs_:.2f}x"
              if cf and cs_ else "")
        print(f"\n  Verdict: a 1-bit sign code {'KEEPS' if (os_-cs_) > 0 else 'LOSES'} the opposite>random "
              f"separation ({os_:+.3f} vs {cs_:+.3f}).")
