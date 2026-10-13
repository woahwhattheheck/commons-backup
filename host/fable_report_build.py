#!/usr/bin/env python3
"""host/fable_report_build.py — consolidate every fable/whitebox data source into ONE report_data.json for the visual
report. Re-runnable: pulls the archive (analogy/direction/circuitry/anatomy/RAM), the full-depth census, the full sweep
(anomaly + anisotropy), and the bit-depth curve. Read-only over JSON. (fable 2026-07-23)
"""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")

ARCH = "C:/Users/lucys/OneDrive/Desktop/WhiteBox_Research_Archive/WHITEBOX_ALL_MODELS.json"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fable_report_data.json")


def load(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def short(k):
    return (k.replace(".gguf", "").replace("-Instruct", "").replace("-it-qat-UD-Q4_K_XL", "")
            .replace("-Q4_K_M", "").replace("-Q8_0", "").replace("-2506", "").replace("google_", "")
            .replace("mistralai_", "").replace("-v0.1.Q4_K_M", ""))


def clean_tok(t):
    return str(t).replace("Ġ", "·").replace("Ā", "?")


def has_queen(near):
    for i, x in enumerate(near[:6]):
        tok = x.get("tok") if isinstance(x, dict) else (x[0] if isinstance(x, (list, tuple)) else str(x))
        sim = x.get("sim") if isinstance(x, dict) else (x[1] if isinstance(x, (list, tuple)) else 0)
        if re.sub(r"[^a-z]", "", str(tok).lower()) == "queen":
            return {"rank": i + 1, "sim": round(float(sim), 3)}
    return None


def near_toks(near, n=5):
    out = []
    for x in (near or [])[:n]:
        if isinstance(x, dict): out.append([clean_tok(x.get("tok")), round(float(x.get("sim", 0)), 3)])
        elif isinstance(x, (list, tuple)): out.append([clean_tok(x[0]), round(float(x[1]), 3)])
    return out


def main():
    arch = load(ARCH, {})
    ff = load(os.path.join(HERE, "fable_ffndepth_data.json"), {})
    sweep = load(os.path.join(HERE, "fable_sweep_data.json"), {})
    bits = load(os.path.join(HERE, "fable_bits_data.json"), [])

    models = []
    for k, md in arch.items():
        a = md.get("anatomy") or md.get("anatomy.json") or {}
        an = md.get("analogy_k_mw.json") or (md.get("decompiler", {}) or {}).get("analogy") or {}
        near = an.get("near") or an.get("results") or []
        dd = md.get("direction_good_bad.json") or {}
        coh = dd.get("cohesion", {})
        cross = coh.get("cross") if isinstance(coh, dict) else coh
        ar = md.get("_archive.json") or md.get("_archive") or {}
        # 3-layer circuitry (archive) -> pass fraction points
        circ = []
        for ck in sorted([x for x in md if x.startswith("circuitry")]):
            c = md[ck]
            if isinstance(c, dict) and c.get("counts"):
                cc = c["counts"]; tot = cc["amp"] + cc["inh"] + cc["pass"] or 1
                circ.append({"layer": c.get("layer"), "amp": cc["amp"], "inh": cc["inh"],
                             "pass": cc["pass"], "dead": cc["dead"], "active_frac": round((cc["amp"] + cc["inh"]) / tot, 3)})
        cb = md.get("circuit_by_layer")
        if cb:
            for L, c in cb.items():
                cc = c.get("counts", {})
                if cc:
                    tot = cc["amp"] + cc["inh"] + cc["pass"] or 1
                    circ.append({"layer": int(L), "amp": cc["amp"], "inh": cc["inh"], "pass": cc["pass"],
                                 "dead": cc["dead"], "active_frac": round((cc["amp"] + cc["inh"]) / tot, 3)})
        models.append({
            "key": k, "name": short(k), "arch": a.get("arch"), "params_B": a.get("params_B"),
            "hidden": a.get("hidden"), "layers": a.get("layers"), "experts": a.get("experts"),
            "vocab": a.get("vocab"), "size_GB": round((ar.get("raw_MB") or 0) / 1000, 1) or None,
            "analogy_near": near_toks(near), "queen": has_queen(near),
            "dir_near": near_toks(dd.get("near")), "dir_cross": cross,
            "ram_drop_MB": ar.get("free_ram_drop_MB"), "ram_raw_MB": ar.get("raw_MB"),
            "ram_sampled": ar.get("sampled"), "ram_ntensors": ar.get("n_tensors"),
            "circ3": sorted(circ, key=lambda x: (x["layer"] if x["layer"] is not None else 0)),
        })

    # full-depth census -> curves
    depth = {}
    for tag, rows in ff.items():
        pts = []
        for r in rows:
            if "amp" not in r: continue
            tot = r["amp"] + r["inh"] + r["pass"] or 1
            pts.append({"layer": r["layer"], "amp": r["amp"], "inh": r["inh"], "pass": r["pass"],
                        "hold": r.get("latch_hold"), "active_frac": round((r["amp"] + r["inh"]) / tot, 4),
                        "rho": r.get("rho_mean")})
        depth[tag] = pts
    # titan vs base divergence
    tdiff = []
    g = {r["layer"]: r for r in ff.get("gemma-4-26B-A4B (titan base)", []) if "amp" in r}
    t = {r["layer"]: r for r in ff.get("titan (modified)", []) if "amp" in r}
    for L in sorted(t):
        if L in g and any(t[L][x] != g[L][x] for x in ("amp", "inh", "pass")):
            tdiff.append({"layer": L, "d_amp": t[L]["amp"] - g[L]["amp"], "d_inh": t[L]["inh"] - g[L]["inh"],
                          "d_pass": t[L]["pass"] - g[L]["pass"]})

    # sweep -> anomaly + anisotropy per model
    sw = {}
    for k, md in sweep.items():
        emb = md.get("embed") or {}
        an = md.get("anomaly_summary") or {}
        deepest = sorted(an.get("flagged", []), key=lambda f: f["ent_min"])[:6]
        sw[short(k)] = {"key": k, "n_tensors": md.get("n_tensors_swept"),
                        "n_flagged": an.get("n_tensors_flagged"), "anom_rows": an.get("total_anom_rows"),
                        "insane_rows": an.get("total_insane_rows"),
                        "mean_vec_norm": emb.get("mean_vec_norm"), "rand_cos": emb.get("rand_pair_cos_mean"),
                        "rand_cos_p95": emb.get("rand_pair_cos_p95"), "dim": emb.get("dim"),
                        "deepest": [{"name": f["name"], "ent_min": f["ent_min"], "ent_med": f["ent_med"],
                                     "n": f["n_ent_anom"], "insane": f.get("n_valinsane", 0)} for f in deepest]}

    bitscurve = [{"bits": b["bits"], "true_false": b["true_false"], "opp": b["opp"],
                  "rand": b["rand"], "ratio": b["ratio"]} for b in bits]

    out = {"models": models, "depth": depth, "titan_diff": tdiff, "sweep": sw, "bits": bitscurve,
           "sweep_done": sorted(short(k) for k in sweep)}

    import math
    def san(o):                                    # non-finite -> null so it's valid JSON for the browser
        if isinstance(o, float): return o if math.isfinite(o) else None
        if isinstance(o, dict): return {k: san(v) for k, v in o.items()}
        if isinstance(o, list): return [san(v) for v in o]
        return o
    out = san(out)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, allow_nan=False)
    print(f"models: {len(models)} | depth curves: {list(depth)} | titan diff layers: {[d['layer'] for d in tdiff]}")
    print(f"sweep done ({len(sw)}): {out['sweep_done']}")
    print(f"bits pts: {len(bitscurve)} | -> {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
