#!/usr/bin/env python3
"""host/pfc_modelbuild.py — THE Muhlnickel-NATIVE MODEL FOUNDRY (owner 2026-07-23: "stop fighting the model — build one that
synergizes with the levers, from the ground up, using our param pool + the White Box").

It fabricates a model into the pfc's OWN format ONCE, offline, at BOUNDED / flat RAM: every 2D weight tensor is streamed
row-by-row → int16 single-scale → PRE-SLICED bit-planes on disk (.wc), tiled to the fold knee. At RUNTIME the forward
engine (`host/pfc_forward.py`) then only FOLDS — no dequant, no re-preslice — so resident RAM is FLAT by construction and
there is no build-time spike to black-screen the box. This is "fabrication is upfront, one-and-done" taken to the whole
model, and it is how performance is controlled from the substrate up:
  - weights ship ALREADY PRE-SLICED (int16 bit-planes)  → runtime = fold only, flat RAM
  - output-neuron tiles sized to the fold KNEE (W≈2560) → every fold fills the SIMD lanes (max block-dots/s)
  - MoE-native when the source is MoE (each routed expert folds independently) → the biggest COUNT lever, built in
  - real weights from the param pool                    → it SPEAKS (a faithful repack, not a random tiny net)

RAM SAFETY (the box is 8 GB — a spike is the one failure that disproves flat-RAM): one tile in flight, freed + gc'd before
the next; int16 array('h') storage (never Python float lists); a hard RSS ceiling that aborts rather than crash. Resumable
(skips tiles already fabricated). Run ONE foundry process at a time.

  python host/pfc_modelbuild.py <src.gguf> [name]              # fabricate (resumable); prints flat peak RAM + progress
  python host/pfc_modelbuild.py <src.gguf> --status            # tiles fabricated / remaining, disk used
  python host/pfc_modelbuild.py <src.gguf> --limit 40          # fabricate only the first N tiles (safe smoke test)
"""
import os, sys, json, gc, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from pfc_forward import Forward, resident_mb, BLK

MODELS_DIR = "C:/llm/models/pfc"                                # where pfc-native model manifests live


def _tensors_2d(f):
    """the 2D weight tensors to pre-slice (attention + ffn + MoE experts + lm_head); 1D norms stay live (tiny)."""
    out = []
    for n, t in f.g.tensors.items():
        if len(t["dims"]) == 2 and n.endswith(".weight") and n != "token_embd.weight":
            out.append((n, int(t["dims"][1])))                 # (name, n_out)
    out.sort()
    return out


def _tiles(f, tensors):
    for name, n_out in tensors:
        for j0 in range(0, n_out, f.tile):
            yield name, j0, min(f.tile, n_out - j0)


def status(src, tile=2560):
    f = Forward(src, substrate=True, tile=tile, memo=False)
    tensors = _tensors_2d(f); done = 0; total = 0; bytes_ = 0
    for name, j0, W in _tiles(f, tensors):
        total += 1; cp = f.wc_path(name, j0, W)
        if os.path.exists(cp): done += 1; bytes_ += os.path.getsize(cp)
    print(f"{os.path.basename(src)}: {done}/{total} tiles fabricated · {bytes_/1e9:.2f} GB on disk · cache {f.cache_dir}")
    return done, total


def fabricate(src, name=None, tile=2560, rss_ceiling_mb=1400, limit=None):
    f = Forward(src, substrate=True, tile=tile, memo=False)
    name = name or os.path.basename(src)
    a = f.arch; kv = f.g.kv
    tensors = _tensors_2d(f)
    all_tiles = list(_tiles(f, tensors)); total = len(all_tiles)
    base = resident_mb(); peak = base
    print(f"=== Muhlnickel FOUNDRY: fabricating {name} → Muhlnickel-native (pre-sliced, knee-tiled W={tile}, WB={f.WB}) ===", flush=True)
    print(f"  arch={a} L={f.L} d_model={f.ne} heads={f.nh}/{f.nkv} ff={f.n_ff} experts={f.n_expert} · "
          f"{len(tensors)} tensors → {total} tiles · baseline RSS {base:.0f} MB", flush=True)
    built = 0; skipped = 0; t0 = time.time()
    for i, (tname, j0, W) in enumerate(all_tiles):
        if limit is not None and built >= limit: break
        cp = f.wc_path(tname, j0, W)
        if os.path.exists(cp): skipped += 1; continue          # resumable
        f._tile(tname, j0, W)                                  # builds + writes .wc; returns wcb (dropped below)
        r = resident_mb(); peak = max(peak, r)
        gc.collect()
        built += 1
        if built % 25 == 0 or r > rss_ceiling_mb:
            print(f"  [{i+1}/{total}] {tname} j0={j0} W={W} · RSS {r:.0f} MB (peak {peak:.0f}) · "
                  f"built {built} skipped {skipped} · {time.time()-t0:.0f}s", flush=True)
        if r > rss_ceiling_mb:
            print(f"  ✗ RSS {r:.0f} MB exceeded ceiling {rss_ceiling_mb} MB — ABORTING to protect the box. "
                  f"Lower --tile or free memory, then re-run (resumes).", flush=True)
            return 1
    # manifest: a first-class pfc-native model artifact (arch + source + tokenizer provenance)
    os.makedirs(MODELS_DIR, exist_ok=True)
    man = {"name": name, "source_gguf": src, "arch": a, "format": "pfc-native-presliced-int16", "tile": tile, "WB": f.WB,
           "n_layers": f.L, "d_model": f.ne, "n_head": f.nh, "n_kv_head": f.nkv, "head_dim": f.hd, "n_ff": f.n_ff,
           "n_expert": f.n_expert, "n_expert_used": f.n_expert_used, "rope_base": f.rope_base, "eps": f.eps,
           "vocab": f.g.n_vocab, "tokenizer": f.bpe.model, "cache_dir": f.cache_dir,
           "tiles_total": total, "tiles_built_this_run": built, "peak_rss_mb": round(peak, 1)}
    mp = os.path.join(MODELS_DIR, name + ".pfcmodel.json"); json.dump(man, open(mp, "w"), indent=1)
    print(f"\n  ✓ fabricated {built} tiles (skipped {skipped} already-done) · manifest {mp}", flush=True)
    if Forward._nan_seen: print(f"  · zeroed/clipped {Forward._nan_seen:,} non-finite source weights (robust quantize)", flush=True)
    print(f"  ★ FLAT PEAK RSS during fabrication: {peak:.0f} MB (baseline {base:.0f}) — bounded, does NOT scale with model "
          f"size. Runtime is now fold-only. Run: python host/pfc_forward.py --new 1 --model {src!r} \"<prompt>\"", flush=True)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    src = sys.argv[1]; rest = sys.argv[2:]
    tile = 2560; limit = None; name = None
    if "--status" in rest: return 0 if status(src, tile)[0] >= 0 else 1
    i = 0
    while i < len(rest):
        if rest[i] == "--tile": tile = int(rest[i+1]); i += 2
        elif rest[i] == "--limit": limit = int(rest[i+1]); i += 2
        else: name = rest[i]; i += 1
    return fabricate(src, name=name, tile=tile, limit=limit)


if __name__ == "__main__":
    raise SystemExit(main())
