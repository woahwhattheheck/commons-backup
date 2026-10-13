#!/usr/bin/env python3
"""host/wf_norm_probe.py — profile RMSNorm/LayerNorm GAIN vectors by depth on the SmolLM2 control.

READ-ONLY. Reads every 1-D *_norm.weight gain vector (attn_norm, ffn_norm, output_norm) out of the GGUF,
computes mean/std/min/max + a spike count per layer, and prints a depth profile + outlier layers.
Norm gains are tiny (960 floats each, F32), so this is fast and bounded. numpy allowed; working set = one
960-vector at a time. (wf, 07-23)
"""
import math, os, sys, statistics as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gguf_pp import GGUF

PATH = sys.argv[1] if len(sys.argv) > 1 else "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"


def profile(vec):
    n = len(vec)
    mean = sum(vec) / n
    var = sum((x - mean) ** 2 for x in vec) / n
    sd = math.sqrt(var)
    mn, mx = min(vec), max(vec)
    amx = max(vec, key=abs)                       # largest-magnitude channel (signed)
    ai = vec.index(amx)
    # spike channels: |x - mean| > 6 std  (heavy-tail steering channels)
    thr = mean + 6 * sd
    spikes = [(i, x) for i, x in enumerate(vec) if x > thr or x < mean - 6 * sd]
    neg = sum(1 for x in vec if x < 0)
    return dict(n=n, mean=mean, sd=sd, mn=mn, mx=mx, amx=amx, ai=ai,
                nspike=len(spikes), spikes=spikes[:5], neg=neg)


def main():
    g = GGUF(PATH)
    nblk = int(g.kv.get("llama.block_count", 0))
    print(f"model: {os.path.basename(PATH)}  blocks={nblk}  dim={g.n_embd}")
    print()

    rows = []   # (label, depth_index, kind, stats)
    for L in range(nblk):
        for kind in ("attn_norm", "ffn_norm"):
            name = f"blk.{L}.{kind}.weight"
            if name not in g.tensors:
                continue
            vec = g.tensor(name)
            s = profile(vec)
            rows.append((name, L, kind, s))
    # final output norm
    for onm in ("output_norm.weight", "norm.weight"):
        if onm in g.tensors:
            rows.append((onm, nblk, "output_norm", profile(g.tensor(onm))))
            break

    hdr = f"{'tensor':22s} {'mean':>8s} {'std':>7s} {'min':>8s} {'max':>8s} {'|max|ch':>10s} {'#>6sd':>6s} {'#neg':>5s}"
    print(hdr); print("-" * len(hdr))
    for name, L, kind, s in rows:
        print(f"{name:22s} {s['mean']:8.4f} {s['sd']:7.4f} {s['mn']:8.4f} {s['mx']:8.4f} "
              f"{s['amx']:7.3f}@{s['ai']:<3d} {s['nspike']:6d} {s['neg']:5d}")

    # ---- depth trend of the mean gain, split by kind ----
    print("\nDEPTH TREND (mean gain):")
    for kind in ("attn_norm", "ffn_norm"):
        seq = [(L, s['mean']) for name, L, k, s in rows if k == kind]
        if not seq:
            continue
        means = [m for _, m in seq]
        print(f"  {kind:10s} L0={means[0]:.3f}  Lmid={means[len(means)//2]:.3f}  "
              f"Llast={means[-1]:.3f}  range=[{min(means):.3f},{max(means):.3f}]  "
              f"grand_mean={sum(means)/len(means):.3f}")

    # ---- outlier layers: by max gain, by spike count, by std ----
    print("\nOUTLIERS:")
    by_max = sorted(rows, key=lambda r: r[3]['mx'], reverse=True)[:5]
    print("  top max-gain layers:")
    for name, L, kind, s in by_max:
        print(f"    {name:22s} max={s['mx']:.3f} (ch {s['ai']})  mean={s['mean']:.3f}")
    by_spk = sorted(rows, key=lambda r: r[3]['nspike'], reverse=True)[:5]
    print("  most spike channels (>6 std):")
    for name, L, kind, s in by_spk:
        ch = ", ".join(f"ch{i}={x:.2f}" for i, x in s['spikes'])
        print(f"    {name:22s} n={s['nspike']:3d}  [{ch}]")
    by_sd = sorted(rows, key=lambda r: r[3]['sd'], reverse=True)[:5]
    print("  highest-variance layers:")
    for name, L, kind, s in by_sd:
        print(f"    {name:22s} std={s['sd']:.3f}  mean={s['mean']:.3f}  max={s['mx']:.3f}")

    # negative-gain channels (sign flips) are unusual for RMSNorm
    negrows = [(name, s['neg']) for name, L, k, s in rows if s['neg'] > 0]
    print(f"\n  layers with any negative gain channel: {len(negrows)} / {len(rows)}")
    for name, nn in sorted(negrows, key=lambda x: x[1], reverse=True)[:6]:
        print(f"    {name:22s} {nn} negative channels")


if __name__ == "__main__":
    main()
