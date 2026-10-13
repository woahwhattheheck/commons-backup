#!/usr/bin/env python3
"""host/specs.py — the CHIP SPEC SHEET builder: a datasheet per pool model, from WHITE BOX data (owner 07-14).

Titan is a library of chips (the pool models); the router elects one. To route well you need each chip's SPEC SHEET —
like a silicon datasheet: what it is (arch/params/dims/experts), its precision recipe (from the White Box precision map),
its health (from the pool scan: junk %, dead experts), and whether its ffn is byte-editable in place. This reuses the
White Box's OWN analysis code (`whitebox_app.anatomy` + `precision_map`) + `docs/TITAN_SCAN.json`, and caches to
`docs/TITAN_SPECS.json` for the lab's Specs tab. RAM-safe (metadata + the scan JSON; no model loaded whole).

Run:  python host/specs.py     (build/refresh the spec sheets)
"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import whitebox_app as wb      # the White Box's own analyzers — "using data from whitebox"

POOL = "C:/llm/models/*.gguf"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECS = os.path.join(ROOT, "docs", "TITAN_SPECS.json")
SCAN = os.path.join(ROOT, "docs", "TITAN_SCAN.json")


def _health_index():
    if not os.path.exists(SCAN):
        return {}
    try:
        d = json.load(open(SCAN, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for m in d.get("models", []):
        de = sum(len(v.get("dead", [])) for v in m.get("dead_experts", {}).values())
        out[m["file"]] = {"n_junk": m.get("n_junk", 0),
                          "junk_pct": round(100 * m.get("junk_params", 0) / max(m.get("total_params", 1), 1), 2),
                          "dead_experts": de}
    return out


def build_specs(progress=lambda s: None):
    files = [f for f in sorted(glob.glob(POOL)) if not f.endswith(".genome") and "titan" not in os.path.basename(f).lower()]
    health = _health_index()
    sheets = []
    for f in files:
        name = os.path.basename(f)
        progress(f"spec: {name}")
        try:
            a = wb.anatomy(f)
            pm = wb.precision_map(f)
        except Exception as e:
            sheets.append({"file": name, "error": f"{type(e).__name__}: {e}"})
            continue
        recipe = [{"role": r["role"], "main": r["main"], "bpw": r["bpw"], "params_M": round(r["params"] / 1e6, 1)}
                  for r in pm["roles"][:10]]
        ffn = next((r for r in pm["roles"] if r["role"] in ("ffn_down", "ffn_down_exps")), None)
        sheets.append({
            "file": name, "arch": a["arch"], "params_B": a["params_B"], "size_GB": a["size_GB"],
            "hidden": a["hidden"], "layers": a["layers"], "experts": a["experts"], "expert_used": a["expert_used"],
            "vocab": a["vocab"], "n_tensors": a["n_tensors"], "quant_types": a["types"],
            "recipe": recipe, "ffn_type": (ffn["main"] if ffn else None),
            "ffn_editable_inplace": bool(ffn and ffn["main"] in ("Q4_0", "Q8_0")),
            "health": health.get(name)})
    rep = {"note": "per-chip spec sheets for Titan's router — from White Box anatomy + precision map + the pool scan.",
           "has_scan": bool(health), "chips": sheets}
    os.makedirs(os.path.dirname(SPECS), exist_ok=True)
    json.dump(rep, open(SPECS, "w"), indent=1)
    progress(f"done — {len(sheets)} chip spec sheets -> {SPECS}")
    return rep


if __name__ == "__main__":
    r = build_specs(lambda s: print("[specs]", s, flush=True))
    for c in r["chips"]:
        if "error" in c:
            print(f"  {c['file'][:34]:34} FAILED {c['error']}")
        else:
            h = c.get("health") or {}
            print(f"  {c['file'][:34]:34} {c['arch']:7} {c['params_B']:6.1f}B ffn={c['ffn_type']} "
                  f"editable={c['ffn_editable_inplace']} junk={h.get('junk_pct','?')}% dead_exp={h.get('dead_experts','?')}")
