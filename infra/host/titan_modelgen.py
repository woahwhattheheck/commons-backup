#!/usr/bin/env python3
"""host/titan_modelgen.py — THE MODEL GENERATOR: describe a model, get a build spec from the MEASURED pool (owner 07-15).

"making a model generator, where i can make specialized models like for my phone agent — that would be soooo cool."
The White-Box upshot: because the White Box READS every model in the pool from its stored bits (no inference), it knows
each model's real anatomy (arch, hidden dim, layers, params). So "make me a model for X" becomes a concrete, measured
build spec: a base + same-hidden-dim role grafts (reversible White-Box weight blends) + whole-expert reference routes
(no copy) + the operators to bake for that specialty. Cross-arch fusion into one transformer is incoherent, so the
deliverable is a routing folder (an SGS), not a merged blob. Pure planning off real pool data — no heavy op, no inference.

  python host/titan_modelgen.py a fast on-device phone-agent decision model
"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forge_build as fb

MODELS = "C:/llm/models"


def pool_table():
    rows = []
    for gg in sorted(glob.glob(os.path.join(MODELS, "*.gguf"))):
        idx = gg + ".wbindex.json"
        if not os.path.exists(idx):
            continue
        try:
            a = json.load(open(idx, encoding="utf-8"))
            rows.append((os.path.basename(gg)[:44], str(a.get("arch", "?")), str(a.get("params_B", "?")),
                         str(a.get("hidden", "?")), str(a.get("layers", "?"))))
        except Exception:
            pass
    return rows


if __name__ == "__main__":
    desc = " ".join(sys.argv[1:]) or "a fast on-device phone-agent decision model"
    print(f"MODEL GENERATOR — request: \"{desc}\"\n", flush=True)

    rows = pool_table()
    if rows:
        print("the MEASURED pool it draws from (read from stored bits, no inference):", flush=True)
        print("   %-44s %-8s %8s %7s %6s" % ("model", "arch", "paramsB", "hidden", "layers"), flush=True)
        for r in rows:
            print("   %-44s %-8s %8s %7s %6s" % r, flush=True)
        print(flush=True)

    spec = fb.propose(desc)
    print("PROPOSED BUILD SPEC (measured, reference-based, reversible-by-construction):", flush=True)
    print(f"   specialty      : {spec['specialty']}", flush=True)
    print(f"   base           : {spec['base']}  (hidden {spec['base_hidden']})", flush=True)
    print(f"   operators to bake: {', '.join(spec['operators'])}", flush=True)
    print(f"   same-dim grafts (reversible White-Box weight blends): {spec['n_graftable']}", flush=True)
    for g in spec["grafts"][:8]:
        print(f"       {g['role']:16s} <- {g['source']}  (hidden {g['hidden']})", flush=True)
    print(f"   whole-expert routes (reference, no copy): {spec['n_routed']}", flush=True)
    print(f"\n   {spec['note']}", flush=True)
    print("\n=> a specialized model composed from real measured pool anatomy — the phone-agent brain, forged not trained.", flush=True)
