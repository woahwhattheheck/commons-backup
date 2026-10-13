#!/usr/bin/env python3
"""host/fable_direction.py — MANIFOLD-RESIDUAL + VALUE-SANITY detector (owner's "direction stream" idea, fable 07-22).

Two signals a baked row trips that a learned row never does:
  VALUE-SANITY : legit dequantized weights are finite and bounded; circuit rows often dequant to NaN/Inf/huge values.
  MANIFOLD     : learned rows live in the low-dim subspace the model actually learned; inserted rows carry energy
                 OFF that manifold (residual sticks out) even when entropy-matched.
Estimates the learned directions robustly (Gram-eigh, no fragile SVD), scores every row, flags the outliers. Read-only.

  python host/fable_direction.py model.gguf blk.2.ffn_gate.weight [k=64]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from gguf_pp import GGUF, _QT, dequant


def topk_dirs(S, k):
    """robust top-k learned directions via the small Gram matrix — no SVD convergence issues."""
    mu = S.mean(0); Sc = S - mu
    G = Sc @ Sc.T                                    # (ns, ns) small + symmetric
    w, U = np.linalg.eigh(G)
    sel = np.argsort(-w)[:k]
    V = Sc.T @ U[:, sel]                             # (ncol, k) right singular directions
    V /= (np.linalg.norm(V, axis=0) + 1e-9)
    return mu, V.T                                   # (k, ncol), orthonormal-ish


def main():
    path, tname = sys.argv[1], sys.argv[2]
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 64
    if not os.path.exists(path):
        alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
        if os.path.exists(alt): path = alt
    g = GGUF(path); t = g.tensors.get(tname)
    if not t: print(f"no tensor {tname}"); return 1
    tid = t["type"]; bpb, wpb = _QT[tid]; ncol = t["dims"][0]
    nrow = 1
    for d in t["dims"][1:]: nrow *= d
    rb = ncol // wpb * bpb; base = g.data0 + t["off"]

    def raw(i):
        return np.asarray(dequant(g.mm[base + i * rb: base + i * rb + rb], tid, ncol), np.float32)

    # SIGNAL 1 — value sanity: NaN/Inf/extreme rows (finite-clip for the geometry below)
    insane = []
    rows = np.empty((nrow, ncol), np.float32)
    for i in range(nrow):
        r = raw(i)
        finite = np.isfinite(r)
        if (not finite.all()) or (np.abs(r[finite]).max(initial=0.0) > 1e4):
            insane.append(i)
        rows[i] = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
    rows = np.clip(rows, -1e4, 1e4)

    # SIGNAL 2 — manifold residual: learn directions from a robust sample (drop worst 10% first, then re-fit)
    ns = min(3000, nrow); samp = np.linspace(0, nrow - 1, ns).astype(int)
    S = rows[samp]
    mu, V = topk_dirs(S, k)
    r0 = np.linalg.norm((S - mu) - ((S - mu) @ V.T) @ V, axis=1) / (np.linalg.norm(S - mu, axis=1) + 1e-9)
    keep = r0 <= np.quantile(r0, 0.90)
    mu, V = topk_dirs(S[keep], k)
    clean = np.linalg.norm((S[keep] - mu) - ((S[keep] - mu) @ V.T) @ V, axis=1) / (np.linalg.norm(S[keep] - mu, axis=1) + 1e-9)
    med, mad = float(np.median(clean)), float(np.median(np.abs(clean - np.median(clean)))) or 1e-9

    Rc = rows - mu
    resid = np.linalg.norm(Rc - (Rc @ V.T) @ V, axis=1) / (np.linalg.norm(Rc, axis=1) + 1e-9)
    thr = med + 8 * mad
    manifold = np.where(resid > thr)[0]

    print(f"\n{os.path.basename(path)}  {tname}  ({nrow:,} rows x {ncol}, {g.tyname})", flush=True)
    print(f"  value-sanity:  {len(insane):,} rows dequant to NaN/Inf/huge", flush=True)
    print(f"  manifold:      learned residual med {med:.3f}±{mad:.3f}, threshold {thr:.3f}; "
          f"flagged-row residual ≈ {float(np.median(resid[manifold])) if len(manifold) else float('nan'):.3f}", flush=True)

    flagged = sorted(set(insane) | set(manifold.tolist()))
    if not flagged:
        print("  ✓ nothing sticks out — clean tensor.")
        return 0
    blk, s, p = [], flagged[0], flagged[0]
    for i in flagged[1:]:
        if i == p + 1: p = i
        else: blk.append((s, p)); s = p = i
    blk.append((s, p))
    print(f"  ◆ FLAGGED: {len(flagged):,} rows in {len(blk)} block(s):", flush=True)
    for a, b in sorted(blk, key=lambda x: -(x[1] - x[0]))[:8]:
        why = "NaN/Inf" if a in set(insane) else "off-manifold"
        print(f"      rows {a:,}..{b:,} ({b - a + 1})  [{why}]  residual≈{float(np.median(resid[a:b+1])):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
