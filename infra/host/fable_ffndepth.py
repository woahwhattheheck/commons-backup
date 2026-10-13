#!/usr/bin/env python3
"""host/fable_ffndepth.py — FULL-DEPTH FFN gate census: run the White Box circuitry() classifier on EVERY layer
(the archive only sampled 3), so you get the whole compute depth-profile, not 3 dots. Per layer: amp/inh/pass/dead
transistor counts + rho + latch cells. Reuses whitebox_app.circuitry so numbers match the archive exactly.

Small dense-FFN models only (bounded ~70 MB working set/layer) — safe to run beside the big sweep on the 8 GB box.
The headline pair is titan vs its base gemma-4-26B: identical curve except where titan was modified. (fable 2026-07-23)
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from whitebox_app import circuitry

OUT = os.path.join(HERE, "fable_ffndepth_data.json")
MODELS = [
    ("SmolLM2-360M (clean control)", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf", 32),
    ("gemma-4-26B-A4B (titan base)", "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf", 30),
    ("titan (modified)", "C:/llm/models/titan.gguf", 30),
]


def run(tag, path, nl):
    rows = []
    for L in range(nl):
        try:
            c = circuitry(path, L)
        except Exception as e:
            c = {"error": str(e)}
        if "error" in c:
            rows.append({"layer": L, "error": c["error"][:90]})
            print(f"  {tag} L{L}: {c['error'][:70]}", flush=True); continue
        cc = c["counts"]; ag = c["agg"]; lo = c["logic"]
        rows.append({"layer": L, "n_ff": c["n_ff"], **cc,
                     "rho_mean": ag["rho_mean"], "rho_pos_frac": ag["rho_pos_frac"],
                     "top5_gate_energy": ag["top5_gate_energy"],
                     "latch_hold": lo["latch_hold"], "latch_reset": lo["latch_reset"],
                     "decode_orth": lo["decode_orth"]})
        print(f"  {tag} L{L:>2}: amp {cc['amp']:>5} inh {cc['inh']:>5} pass {cc['pass']:>6} "
              f"dead {cc['dead']}  rho {ag['rho_mean']:+.3f}  hold {lo['latch_hold']}", flush=True)
    return rows


def main():
    data = {}
    if os.path.exists(OUT):
        try: data = json.load(open(OUT, encoding="utf-8"))
        except Exception: data = {}
    for tag, path, nl in MODELS:
        if not os.path.exists(path):
            print(f"### {tag}: NOT FOUND {path}", flush=True); continue
        print(f"\n### {tag} — full-depth census ({nl} layers) ...", flush=True)
        t0 = time.time(); data[tag] = run(tag, path, nl)
        json.dump(data, open(OUT, "w", encoding="utf-8"), indent=1)
        print(f"### {tag} done in {time.time()-t0:.0f}s", flush=True)
    print(f"\n==> {OUT}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
