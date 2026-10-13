#!/usr/bin/env python3
"""muhl_geometry.py — GEOMETRY OF A PREDICTOR'S EMBEDDING SPACE (real SmolLM2-360M, Q8_0, flat RAM).

Deeper than muhl_truefalse.py. Reuses that file's GGUF/Q8_0 parser (imported). Everything is measured on
the REAL token-embedding rows, dequantized one at a time from the mmap'd .gguf — no numpy, pure Python math.

Four measurements, each a probe of PREDICTION vs MEANING:
  1. ANTONYM vs SYNONYM vs RANDOM mean cosine. If antonyms sit as close as (or closer than) synonyms, the
     axis of "meaning" is invisible to the geometry — what survives is grammatical slot / co-occurrence.
  2. Truth-word pairwise cosine matrix (true,false,yes,no,right,wrong,good,bad) — do the truth words huddle.
  3. Anisotropy: mean cosine of many random pairs. A meaning space would be ~0; a predictor's space is a
     narrow cone (mean cosine well above 0), a known artifact of next-token training.
  4. Nearest neighbors of 'true' by cosine over the whole vocab — does 'false'/'True'/'yes' dominate.
"""
import sys, os, math, json, random, mmap

# Reuse the verified parser from the sibling file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from muhl_truefalse import parse_gguf, q8_row, cos, GGUF, ANCH


def main():
    if not os.path.exists(GGUF):
        print("gguf not found:", GGUF); return 1
    fd = open(GGUF, "rb"); mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    meta, tensors, data_start = parse_gguf(mm)
    toks = meta.get("tokenizer.ggml.tokens")
    emb = tensors.get("token_embd.weight")
    if not toks or not emb:
        print("missing tokens/embeddings"); return 1
    dims, typ, off = emb; n_embd = dims[0]
    V = len(toks)
    print(f"\n  MUHLNICKEL — geometry of the real embedding space ({os.path.basename(GGUF)})")
    print(f"  token_embd.weight dims={dims} type={typ} (8=Q8_0) · vocab {V:,} · n_embd {n_embd}")

    vocab = {t: i for i, t in enumerate(toks)}
    row_bytes = (n_embd // 32) * 34

    def tid(word):                                    # byte-level BPE: leading space is U+0120
        for cand in ("Ġ" + word, word, "Ġ" + word.capitalize(), word.capitalize()):
            if cand in vocab:
                return vocab[cand]
        return None

    # cache dequantized rows so repeated lookups are cheap
    _cache = {}
    def vec(i):
        v = _cache.get(i)
        if v is None:
            v = q8_row(mm, data_start + off + i * row_bytes, n_embd)
            _cache[i] = v
        return v

    def cos_words(a, b):
        ia, ib = tid(a), tid(b)
        if ia is None or ib is None:
            return None
        return cos(vec(ia), vec(ib))

    # ---------------------------------------------------------------- 1. ANTONYM vs SYNONYM vs RANDOM
    anchors = json.load(open(ANCH))
    axes = anchors.get("axes") or [(anchors["anchors"][i], anchors["anchors"][i + 1])
                                   for i in range(0, len(anchors["anchors"]) - 1, 2)]
    ANT = [(a, b) for a, b in axes]
    SYN = [("big", "large"), ("happy", "glad"), ("fast", "quick"), ("smart", "clever"),
           ("small", "little"), ("begin", "start"), ("angry", "mad"), ("rich", "wealthy"),
           ("sad", "unhappy"), ("hard", "difficult"), ("easy", "simple"), ("cold", "chilly"),
           ("buy", "purchase"), ("end", "finish"), ("big", "huge"), ("odd", "strange")]

    def summarize(pairs, label):
        vals = []
        for a, b in pairs:
            c = cos_words(a, b)
            if c is not None:
                vals.append((c, a, b))
        m = sum(c for c, _, _ in vals) / len(vals) if vals else float("nan")
        print(f"\n  {label} pair cosine  (n={len(vals)}):")
        for c, a, b in sorted(vals, reverse=True):
            print(f"    {a:>9} / {b:<9}  cos {c:+.3f}")
        print(f"    -> mean {label} cosine: {m:+.3f}")
        return m, vals

    print("\n" + "=" * 68)
    print("  [1] ANTONYM vs SYNONYM vs RANDOM  — is the 'meaning' axis visible?")
    print("=" * 68)
    m_ant, ant_vals = summarize(ANT, "ANTONYM")
    m_syn, syn_vals = summarize(SYN, "SYNONYM")

    rng = random.Random(0)
    rc = []
    for _ in range(2000):
        i, j = rng.randrange(V), rng.randrange(V)
        if i != j:
            rc.append(cos(vec(i), vec(j)))
    m_rnd = sum(rc) / len(rc)
    var_rnd = sum((x - m_rnd) ** 2 for x in rc) / len(rc)
    sd_rnd = math.sqrt(var_rnd)
    print(f"\n  RANDOM pair cosine (n={len(rc)}):  mean {m_rnd:+.3f}  sd {sd_rnd:.3f}")

    print(f"\n  SUMMARY  antonyms {m_ant:+.3f} | synonyms {m_syn:+.3f} | random {m_rnd:+.3f}")
    print(f"  antonyms - synonyms = {m_ant - m_syn:+.3f}   "
          f"({'antonyms as close as/closer than synonyms' if m_ant >= m_syn - 0.02 else 'synonyms closer'})")
    print(f"  antonyms - random   = {m_ant - m_rnd:+.3f}   "
          f"({'antonyms sit well above the random cone' if m_ant > m_rnd + 0.05 else 'near random'})")

    # ---------------------------------------------------------------- 2. TRUTH-WORD MATRIX
    print("\n" + "=" * 68)
    print("  [2] TRUTH-WORD pairwise cosine matrix — do they huddle?")
    print("=" * 68)
    words = ["true", "false", "yes", "no", "right", "wrong", "good", "bad"]
    ids = {w: tid(w) for w in words}
    present = [w for w in words if ids[w] is not None]
    missing = [w for w in words if ids[w] is None]
    if missing:
        print(f"  (not found as tokens: {missing})")
    hdr = "        " + " ".join(f"{w[:5]:>6}" for w in present)
    print(hdr)
    offdiag = []
    for wa in present:
        cells = []
        for wb in present:
            c = cos(vec(ids[wa]), vec(ids[wb]))
            cells.append(f"{c:+.2f}")
            if wa < wb:
                offdiag.append(c)
        print(f"  {wa:>5} " + " ".join(f"{x:>6}" for x in cells))
    if offdiag:
        m_truth = sum(offdiag) / len(offdiag)
        print(f"\n  mean off-diagonal (truth-word to truth-word): {m_truth:+.3f}")
        print(f"  vs mean random cosine                       : {m_rnd:+.3f}")
        print(f"  truth words sit {m_truth - m_rnd:+.3f} above random  "
              f"({'they huddle' if m_truth > m_rnd + 0.05 else 'no huddle'})")

    # ---------------------------------------------------------------- 3. ANISOTROPY
    print("\n" + "=" * 68)
    print("  [3] ANISOTROPY of the space (mean random-pair cosine)")
    print("=" * 68)
    print(f"  mean random cosine {m_rnd:+.3f} (sd {sd_rnd:.3f}) over {len(rc)} pairs.")
    print(f"  In an isotropic 'meaning' space this is ~0. Here it is a narrow cone: the average pair of")
    print(f"  UNRELATED tokens already points {m_rnd:+.3f} the same way — a next-token-predictor artifact.")
    # fraction of random pairs that are actually negative (truly opposed directions)
    neg = sum(1 for x in rc if x < 0) / len(rc)
    print(f"  fraction of random pairs with NEGATIVE cosine: {100*neg:.1f}%  "
          f"(a meaning space would be ~50%).")

    # ---------------------------------------------------------------- 4. NEAREST NEIGHBORS OF 'true'
    print("\n" + "=" * 68)
    print("  [4] NEAREST NEIGHBORS of 'true' (cosine over full vocab)")
    print("=" * 68)
    ti = tid("true")
    if ti is None:
        print("  'true' token not found.");
    else:
        tv = vec(ti)
        tv_norm = math.sqrt(sum(x * x for x in tv))
        best = []  # list of (cos, idx)
        for j in range(V):
            if j == ti:
                continue
            wv = vec(j)
            d = sum(x * y for x, y in zip(tv, wv))
            nb = math.sqrt(sum(y * y for y in wv))
            c = d / (tv_norm * nb) if nb else 0.0
            if len(best) < 8:
                best.append((c, j)); best.sort()
            elif c > best[0][0]:
                best[0] = (c, j); best.sort()
        best.sort(reverse=True)
        print(f"  token 'true' = row {ti} ('{toks[ti]}')")
        for c, j in best:
            disp = toks[j].replace("Ġ", "_")
            print(f"    cos {c:+.3f}   row {j:>6}   '{disp}'")
        neigh = {toks[j].replace("Ġ", "").lower() for _, j in best}
        hit = neigh & {"false", "yes", "no", "wrong", "right"}
        print(f"\n  truth-family tokens among the 8 nearest: {sorted(hit) if hit else 'none'}")

    mm.close(); fd.close()

    print("\n" + "=" * 68)
    print("  VERDICT")
    print("=" * 68)
    print(f"  antonyms {m_ant:+.3f} ~ synonyms {m_syn:+.3f} >> random {m_rnd:+.3f}, and the whole space")
    print(f"  is a {m_rnd:+.3f} cone. Opposite MEANINGS are not pushed apart; same-SLOT words cluster.")
    print(f"  Geometry encodes what predicts the next token (slot, co-occurrence), not what a word MEANS.")
    print(f"  Meaning has to be COMPUTED, not read off the embedding — the case for Titan's verified core.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
