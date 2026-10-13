#!/usr/bin/env python3
"""host/fable_concept.py — CROSS-LINGUAL CONCEPT EXPLORER (fable, 2026-07-22; owner: "make new tools").

Given a word, finds its nearest embedding neighbors and flags the ones in other scripts/languages — showing that the
CONCEPT sits below language (the model files 'university' right next to 대학, université, universidad, …). Weight-only.

  python host/fable_concept.py university [k=30]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import whitebox_app as wb

TITAN = "C:/llm/models/titan.gguf"


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "university"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    wb.load_file(TITAN); wb.start_embed_build()
    t0 = time.time()
    while wb.STATE.get("E_mm") is None and time.time() - t0 < 180: time.sleep(1)
    E, vocab = wb.STATE.get("E_mm"), wb.STATE.get("vocab")
    if E is None: print("embedding did not attach"); return 1
    v = wb._str_vec_row(word)
    if v is None: print(f"'{word}' is not a single embeddable token"); return 1
    q = np.asarray(v, np.float32); q = q / (np.linalg.norm(q) + 1e-9)
    ai = wb._dc.find_tok(vocab, word)

    K = k + 5
    best = np.full(K, -1e9, np.float32); idx = np.zeros(K, np.int64)
    for s, rows in E.chunks(ch=8192):
        sims = rows @ q
        span = np.arange(s, s + rows.shape[0], dtype=np.int64)
        cat = np.concatenate([best, sims]); csp = np.concatenate([idx, span])
        keep = np.argpartition(-cat, K - 1)[:K]; best, idx = cat[keep], csp[keep]

    latin = lambda t: all(ord(c) < 0x0250 or c in "▁· \t" for c in t)
    o = np.argsort(-best)
    print(f"\nFABLE CONCEPT EXPLORER — nearest to '{word}'  (◆ = other script / language):\n")
    shown = xling = 0
    for i in o:
        ti = int(idx[i])
        if ai is not None and ti == ai: continue
        t = vocab[ti].replace("▁", "·")
        cross = not latin(t)
        xling += cross
        print(f"  {'◆ ' if cross else '  '}{best[i]:+.3f}  {t}")
        shown += 1
        if shown >= k: break
    print(f"\n  {xling}/{shown} of the nearest neighbours are in other scripts — the concept, not the English word.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
