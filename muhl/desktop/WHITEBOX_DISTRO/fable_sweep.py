#!/usr/bin/env python3
"""host/fable_sweep.py — FULL per-tensor sweep of a model: EVERY weight tensor (the archive only sampled a subset),
rich per-tensor stats + the validated anomaly signals. Completes the tensor-data coverage. (fable, 2026-07-23)

Per tensor: byte-entropy crater scan (baked-circuit signal, reuse of the audit), float stats (mean/std/absmean/min/max/
sparsity), row-L2-norm mean+cv, and a NaN/Inf value-sanity count. For token_embd it also measures the anisotropy
"cone" (mean-vector norm + random-pair cosine). numpy for reductions, gguf_pp for correct dequant, read-only mmap.
Incremental: merges into fable_sweep_data.json per model, so partial results survive an interrupt.

  python host/fable_sweep.py model1.gguf model2.gguf ...
"""
import json, math, os, statistics, sys, time
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
from gguf_pp import GGUF, _QT, _TYNAME, dequant

STAT_ROWS = 160          # rows to dequant per tensor for float stats (bounded work even on 40GB titan)
ENT_ROWS  = 256          # strided rows for the byte-entropy anomaly scan (raw bytes, cheap)
ABS_DROP  = 0.7          # entropy crater threshold (matches fable_audit's validated detector)
EMB_ROWS  = 1200         # rows sampled for the token_embd anisotropy metrics
OUT = os.path.join(HERE, "fable_sweep_data.json")


def ent(b):
    if not b: return 0.0
    c = Counter(b); n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def rows_of(dims):
    if len(dims) < 2: return None
    ncol, nrow = dims[0], 1
    for d in dims[1:]: nrow *= d          # flatten experts/heads -> (rows, ncol); catches MoE bakes
    return ncol, nrow


def kind_of(name):
    n = name.lower()
    for k in ("token_embd", "ffn_gate_up_exps", "ffn_down_exps", "ffn_gate_inp",
              "attn_q", "attn_k", "attn_v", "attn_output", "attn_norm",
              "ffn_gate", "ffn_up", "ffn_down", "ffn_norm", "output_norm", "output"):
        if k in n: return k
    return "other"


def layer_of(name):
    import re
    m = re.search(r"blk\.(\d+)\.", name)
    return int(m.group(1)) if m else -1


def strided(n, k):
    if n <= k: return list(range(n))
    step = max(1, n // k)
    return list(range(0, n, step))


def deq_rows(mm, base, rb, tid, ncol, idxs):
    R = []
    for i in idxs:
        try:
            R.append(dequant(mm[base + i * rb: base + i * rb + rb], tid, ncol))
        except Exception:
            pass
    return np.asarray(R, dtype=np.float64) if R else np.zeros((0, ncol))


def sweep_tensor(mm, base, tid, ncol, nrow):
    bpb, wpb = _QT[tid]; rb = ncol // wpb * bpb
    # --- entropy anomaly (raw bytes) ---
    samp = min(rb, 384)
    es = [(i, ent(mm[base + i * rb: base + i * rb + samp])) for i in strided(nrow, ENT_ROWS)]
    emed = statistics.median(e for _, e in es); emin = min(e for _, e in es)
    bad = [i for i, e in es if e < emed - ABS_DROP]
    band = [int(min(bad)), int(max(bad))] if bad else None
    # --- float stats ---
    A = deq_rows(mm, base, rb, tid, ncol, strided(nrow, STAT_ROWS))
    if A.shape[0] == 0:
        return dict(ent_med=round(emed, 3), ent_min=round(emin, 3), n_ent_anom=len(bad),
                    anom_band=band, n_valinsane=0, sampled=0)
    fin = np.isfinite(A)
    rowmax = np.where(fin, np.abs(A), 0.0).max(axis=1)
    n_insane = int(np.sum((~fin.all(axis=1)) | (rowmax > 1e4)))
    Af = np.where(fin, A, 0.0)
    rn = np.linalg.norm(Af, axis=1)
    return dict(
        ent_med=round(emed, 3), ent_min=round(emin, 3), n_ent_anom=len(bad), anom_band=band,
        n_valinsane=n_insane, sampled=int(A.shape[0]),
        mean=round(float(Af.mean()), 6), std=round(float(Af.std()), 6),
        absmean=round(float(np.abs(Af).mean()), 6),
        vmin=round(float(Af.min()), 5), vmax=round(float(Af.max()), 5),
        sparsity=round(float(np.mean(np.abs(Af) < 1e-8)), 4),
        rownorm_mean=round(float(rn.mean()), 5),
        rownorm_cv=round(float(rn.std() / (rn.mean() + 1e-12)), 4),
    )


def embed_metrics(mm, base, tid, ncol, nrow):
    bpb, wpb = _QT[tid]; rb = ncol // wpb * bpb
    M = deq_rows(mm, base, rb, tid, ncol, strided(nrow, EMB_ROWS))
    if M.shape[0] < 50: return None
    mu = M.mean(axis=0)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)
    S = Mn[:300]
    C = S @ S.T
    iu = np.triu_indices(C.shape[0], k=1)
    cc = C[iu]
    return dict(dim=int(ncol), vocab=int(nrow),
                mean_vec_norm=round(float(np.linalg.norm(mu)), 4),
                rand_pair_cos_mean=round(float(cc.mean()), 4),
                rand_pair_cos_p95=round(float(np.percentile(cc, 95)), 4))


def sweep_model(path):
    g = GGUF(path); mm = g.mm
    name = os.path.basename(path)
    size_gb = round(os.path.getsize(g.path) / 1e9, 2)
    qcount = Counter()
    tensors = []; embed = None; flagged = []
    items = list(g.tensors.items())
    t0 = time.time()
    for j, (tn, t) in enumerate(items):
        tid = t["type"]
        if tid not in _QT: continue
        ro = rows_of(t["dims"])
        if not ro: continue
        ncol, nrow = ro
        bpb, wpb = _QT[tid]
        if nrow < 8 or ncol % wpb: continue
        base = g.data0 + t["off"]
        qcount[_TYNAME.get(tid, tid)] += 1
        try:
            s = sweep_tensor(mm, base, tid, ncol, nrow)
        except Exception as e:
            print(f"    ! {tn}: {e}", flush=True); continue
        rec = dict(name=tn, kind=kind_of(tn), layer=layer_of(tn), type=_TYNAME.get(tid, tid),
                   shape=list(t["dims"]), nrow=int(nrow), ncol=int(ncol), **s)
        tensors.append(rec)
        if s.get("n_ent_anom", 0) or s.get("n_valinsane", 0):
            flagged.append(dict(name=tn, kind=rec["kind"], layer=rec["layer"], nrow=int(nrow),
                                ent_med=s["ent_med"], ent_min=s["ent_min"],
                                n_ent_anom=s["n_ent_anom"], anom_band=s.get("anom_band"),
                                n_valinsane=s.get("n_valinsane", 0)))
        if kind_of(tn) == "token_embd" and embed is None:
            try: embed = embed_metrics(mm, base, tid, ncol, nrow)
            except Exception as e: print(f"    ! embed {tn}: {e}", flush=True)
        if (j + 1) % 60 == 0:
            print(f"    .. {j+1}/{len(items)} tensors ({time.time()-t0:.0f}s)", flush=True)
    out = dict(file=name, size_GB=size_gb, n_tensors_swept=len(tensors),
               quant_types=dict(qcount), embed=embed,
               anomaly_summary=dict(n_tensors_flagged=len(flagged),
                                    total_anom_rows=sum(f["n_ent_anom"] for f in flagged),
                                    total_insane_rows=sum(f["n_valinsane"] for f in flagged),
                                    flagged=sorted(flagged, key=lambda f: (f["ent_min"], -f["n_ent_anom"]))),
               tensors=tensors, sweep_seconds=round(time.time() - t0, 1))
    return name, out


def main():
    paths = sys.argv[1:]
    if not paths:
        print("usage: fable_sweep.py model.gguf ..."); return 1
    data = {}
    if os.path.exists(OUT):
        try: data = json.load(open(OUT, encoding="utf-8"))
        except Exception: data = {}
    for p in paths:
        if not os.path.exists(p):
            alt = os.path.join(os.path.dirname(p), "_removed", os.path.basename(p))
            p = alt if os.path.exists(alt) else p
        if not os.path.exists(p):
            print(f"### {os.path.basename(p)}: NOT FOUND", flush=True); continue
        print(f"\n### sweeping {os.path.basename(p)} ({os.path.getsize(p)/1e9:.1f} GB) ...", flush=True)
        try:
            name, out = sweep_model(p)
        except Exception as e:
            print(f"### {os.path.basename(p)}: ERROR {e}", flush=True); continue
        data[name] = out
        json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)   # incremental: survive interrupts
        a = out["anomaly_summary"]
        print(f"### done {name}: {out['n_tensors_swept']} tensors, {a['n_tensors_flagged']} flagged, "
              f"{a['total_anom_rows']} anom rows, {a['total_insane_rows']} NaN/Inf rows, {out['sweep_seconds']}s", flush=True)
    print(f"\n==> {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
