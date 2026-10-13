#!/usr/bin/env python3
"""host/fable_neurons.py — NEURON FINDER, fable's own white-box tool (fable, 2026-07-22; owner: "add whatever tools u want").

Finds the CLEANEST (most monosemantic) neurons of an FFN layer by projecting each neuron's stored weight vector onto the
token embedding and reading its top tokens — NO inference, read straight off the weights. High top-1 cosine = a clean,
near-monosemantic neuron (a 'font' neuron, a cross-lingual 'university' concept neuron); low = a superposed direction.
Streams the 262k x 2816 embedding in bounded windows (StreamE.chunks) so it never goes resident. Read-only.

  python host/fable_neurons.py [layer=29] [kind=down] [n=96] [model=titan]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import whitebox_app as wb

TITAN = "C:/llm/models/titan.gguf"


def main():
    layer = int(sys.argv[1]) if len(sys.argv) > 1 else 29
    kind = sys.argv[2] if len(sys.argv) > 2 else "down"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    model = sys.argv[4] if len(sys.argv) > 4 else TITAN
    k = 5

    wb.load_file(model)
    wb.start_embed_build()
    t0 = time.time()
    while wb.STATE.get("E_mm") is None and time.time() - t0 < 180:
        time.sleep(1)
    E = wb.STATE.get("E_mm")
    if E is None:
        print("embedding did not attach:", wb.EMBED); return 1
    vocab = wb.STATE.get("vocab")
    if vocab is None:
        import decompile; vocab = decompile.load_vocab(model)

    def tok(i):
        try: s = vocab[int(i)]
        except Exception: s = str(i)
        return (s or "").replace("▁", "·").replace("\n", "\\n")

    W, meta = wb._deq_cached(model, f"blk.{layer}.ffn_{kind}.weight")
    if W is None:
        print("no tensor:", meta); return 1
    if kind in ("gate", "up"):
        nff = W.shape[0]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[sel])
    else:
        nff = W.shape[1]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[:, sel].T)
    P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-8)
    N = P.shape[0]
    print(f"scanning {N} neurons of blk.{layer}.ffn_{kind} against {E.shape[0]:,} tokens…", flush=True)

    best_sim = np.full((N, k), -1e9, np.float32); best_idx = np.zeros((N, k), np.int64)
    for s, rows in E.chunks(ch=8192):                         # rows: normalized f32, bounded window
        sims = P @ rows.T                                     # (N, c) cosine (both sides unit-norm)
        c = rows.shape[0]
        cat_sim = np.concatenate([best_sim, sims], axis=1)
        span = np.broadcast_to(np.arange(s, s + c, dtype=np.int64), (N, c))
        cat_idx = np.concatenate([best_idx, span], axis=1)
        keep = np.argpartition(-cat_sim, k - 1, axis=1)[:, :k]
        best_sim = np.take_along_axis(cat_sim, keep, axis=1)
        best_idx = np.take_along_axis(cat_idx, keep, axis=1)

    out = []
    for a in range(N):
        o = np.argsort(-best_sim[a])
        toks = [tok(best_idx[a, i]) for i in o]
        out.append((int(sel[a]), float(best_sim[a, o[0]]), toks))
    out.sort(key=lambda r: -r[1])

    print(f"\nFABLE NEURON FINDER — {os.path.basename(model)} · layer {layer} {kind} · {N} neurons · "
          f"{int((time.time()-t0)*1000)}ms")
    print("the CLEANEST (highest top-1 cosine to token space) first:\n", flush=True)
    for j, top, toks in out[:44]:
        print(f"  n{j:<5}  {top:.3f}  ->  " + ", ".join(toks), flush=True)
    tops = sorted((t for _, t, _ in out), reverse=True)
    clean15 = sum(tops[:15]) / min(15, len(tops)); meanall = sum(tops) / len(tops)
    print(f"\nSUMMARY  model={os.path.basename(model)}  layer={layer}  n={N}  "
          f"clean_top15={clean15:.3f}  mean_all={meanall:.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
