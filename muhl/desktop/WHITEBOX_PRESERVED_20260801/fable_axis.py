#!/usr/bin/env python3
"""host/fable_axis.py — STEERING-AXIS BUILDER + POLE READOUT (fable, 2026-07-22; owner: "make new tools").

Give +/- example pairs (neg:pos). Builds the concept direction (a steering vector), measures its PURITY (are the
example directions consistent = a real axis, or noise?), then scans the vocab to show the tokens at each POLE — what
the axis actually MEANS, read straight off the weights. A steering vector, with its meaning made visible. No inference.

  python host/fable_axis.py "cold:warm, low:high, dark:bright, sad:happy, slow:fast" [place_word]
"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import whitebox_app as wb

TITAN = "C:/llm/models/titan.gguf"


def _topk(E, R, k=14):
    """single streamed pass: top-k tokens by projection onto R (+ pole) and by -projection (- pole)."""
    bp = np.full(k, -1e9, np.float32); ip = np.zeros(k, np.int64)
    bn = np.full(k, -1e9, np.float32); ineg = np.zeros(k, np.int64)
    for s, rows in E.chunks(ch=8192):
        proj = rows @ R
        span = np.arange(s, s + rows.shape[0], dtype=np.int64)
        cat = np.concatenate([bp, proj]); csp = np.concatenate([ip, span])
        keep = np.argpartition(-cat, k - 1)[:k]; bp, ip = cat[keep], csp[keep]
        cat = np.concatenate([bn, -proj]); csp = np.concatenate([ineg, span])
        keep = np.argpartition(-cat, k - 1)[:k]; bn, ineg = cat[keep], csp[keep]
    return (ip, bp), (ineg, -bn)


def main():
    pairs = sys.argv[1] if len(sys.argv) > 1 else "cold:warm, low:high, dark:bright, sad:happy, slow:fast"
    place = sys.argv[2] if len(sys.argv) > 2 else None
    wb.load_file(TITAN); wb.start_embed_build()
    t0 = time.time()
    while wb.STATE.get("E_mm") is None and time.time() - t0 < 180: time.sleep(1)
    E, vocab = wb.STATE.get("E_mm"), wb.STATE.get("vocab")
    if E is None: print("embedding did not attach"); return 1

    dirs, used = [], []
    for p in re.split(r"[,\n]+", pairs):
        p = p.strip()
        if ":" not in p: continue
        a, b = [x.strip() for x in p.split(":", 1)]
        va, vb = wb._str_vec_row(a), wb._str_vec_row(b)
        if va is not None and vb is not None:
            dirs.append(np.asarray(vb, np.float32) - np.asarray(va, np.float32)); used.append((a, b))
    if len(dirs) < 2: print("need >= 2 embeddable a:b pairs"); return 1
    Dn = [d / (np.linalg.norm(d) + 1e-9) for d in dirs]
    purity = float(np.mean([Dn[i] @ Dn[j] for i in range(len(Dn)) for j in range(i + 1, len(Dn))]))
    R = np.mean(np.stack(dirs), axis=0); R = R / (np.linalg.norm(R) + 1e-9)

    (ip, vp), (ineg, vn) = _topk(E, R)
    tok = lambda i: vocab[int(i)].replace("▁", "·")
    verdict = "CLEAN AXIS" if purity > 0.25 else "weak / noisy" if purity > 0.1 else "NOT an axis"
    print(f"\nFABLE STEERING AXIS — {len(used)} pairs · purity {purity:+.3f}  ({verdict})")
    print("  " + ", ".join(f"{a}->{b}" for a, b in used))
    op = np.argsort(-vp); on = np.argsort(-vn)
    print("\n  + POLE  (toward the second word of each pair):")
    for i in op[:12]: print(f"     {vp[i]:+.3f}  {tok(ip[i])}")
    print("\n  - POLE  (toward the first word):")
    for i in on[:12]: print(f"     {-vn[i]:+.3f}  {tok(ineg[i])}")
    if place:
        pv = wb._str_vec_row(place)
        if pv is not None:
            print(f"\n  '{place}' projects to {float(np.asarray(pv, np.float32) @ R):+.3f} on this axis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
