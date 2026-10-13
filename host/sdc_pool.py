#!/usr/bin/env python3
"""host/sdc_pool.py — THE POOL INDEX / ROUTING FOLDER over the WHOLE parameter reservoir (Phase 0 of the SDC OS).

FINALREADME §1/§8 (the parameter pool as a browsable, reference-based routing folder — no copy) + §7B (the pool is a
configurable circuit substrate). This indexes EVERY .gguf on the box (~206 GB across ~10 diverse models — not just titan)
AND the exact circuit bank (titan_circuits.json) into ONE reference-based folder the router selects over. Two kinds of
"expert" live in the folder: FUZZY (a model's params, role spine/fast/specialist) and EXACT (a stored circuit — add8,
dot32_i8, cpu_fwd, a verifier). Bits stay where they are (paths, never copied). Pure python (numpy BANNED) via gguf_pp;
read-only; ~0 RAM (header + tensor-index off the mmap).

  python host/sdc_pool.py            # build/refresh the routing folder -> C:/llm/pool/
  python host/sdc_pool.py show       # print the folder without rewriting
"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import gguf_pp

MODELS = "C:/llm/models/*.gguf"
REG = "C:/llm/models/titan_circuits.json"
POOL = "C:/llm/pool"                                          # the routing folder (outside OneDrive; references the models)


def _kv(g, *keys, default=None):
    for k in keys:
        if k in g.kv: return g.kv[k]
    return default


def anat(path):
    """model metadata off the stored bits — pure python, ~0 RAM (gguf_pp reads the header + tensor index only)."""
    g = gguf_pp.GGUF(path)
    arch = _kv(g, "general.architecture", default="?")
    params = _kv(g, "general.parameter_count")
    if params is None:                                       # sum tensor element counts (pure python, no numpy)
        params = 0
        for t in g.tensors.values():
            n = 1
            for d in t["dims"]: n *= int(d)
            params += n
    hidden = _kv(g, f"{arch}.embedding_length", f"{arch}.hidden_size", f"{arch}.d_model")
    layers = _kv(g, f"{arch}.block_count")
    experts = _kv(g, f"{arch}.expert_count") or 0
    ffn_ty = None
    for name, t in g.tensors.items():
        if name.endswith("ffn_down.weight") or name.endswith("ffn_down_exps.weight"):
            ffn_ty = gguf_pp._TYNAME.get(int(t["type"]), str(t["type"])); break
    g.mm.close(); g.f.close()
    return {"file": os.path.basename(path), "path": path.replace("\\", "/"), "arch": arch,
            "params_B": round(int(params) / 1e9, 2), "hidden": hidden, "layers": layers, "experts": int(experts),
            "vocab": g.n_vocab, "embd_type": g.tyname, "size_GB": round(os.path.getsize(path) / 1e9, 2),
            "ffn_type": ffn_ty, "ffn_editable_inplace": ffn_ty in ("Q4_0", "Q8_0")}


def exact_experts():
    """the exact circuit bank (titan_circuits.json) as EXACT experts — addressable stored functions, reference-based."""
    if not os.path.exists(REG): return []
    reg = json.load(open(REG))
    out = []
    for name, e in reg.items():
        if not isinstance(e, dict) or "n_gate" not in e: continue          # only real gate-nets
        out.append({"name": name, "kind": "exact", "gates": int(e["n_gate"]), "offset": int(e.get("offset", 0)),
                    "n_in": e.get("n_in"), "n_out": e.get("n_out"), "in": "titan.gguf (params)"})
    return out


def build(write=True):
    files = sorted(f for f in glob.glob(MODELS) if not f.endswith(".genome"))
    fuzzy = []
    print(f"[pool] indexing {len(files)} model files as reference-based experts (no copy) …\n", flush=True)
    for f in files:
        try:
            a = anat(f); fuzzy.append(a)
            print(f"  {a['file'][:40]:40} {a['arch']:8} {a['params_B']:6.1f}B  hid={str(a['hidden']):>5} "
                  f"exp={a['experts']:>3} ffn={a['ffn_type']} editable={a['ffn_editable_inplace']}", flush=True)
        except Exception as ex:
            print(f"  {os.path.basename(f)[:40]:40} SKIP ({type(ex).__name__}: {str(ex)[:44]})", flush=True)
    ranked = sorted(fuzzy, key=lambda a: a["params_B"], reverse=True)

    def role(a, i):
        return "spine" if i == 0 else ("fast" if a["experts"] else "specialist")
    for i, a in enumerate(ranked):
        a["role"] = role(a, i); a["kind"] = "fuzzy"
        a["fallback"] = ranked[i + 1]["file"] if i + 1 < len(ranked) else ranked[0]["file"]

    exact = exact_experts()
    total_B = round(sum(a["params_B"] for a in fuzzy), 1)
    total_GB = round(sum(a["size_GB"] for a in fuzzy), 1)
    manifest = {
        "note": "the SDC routing folder — the WHOLE reservoir + the exact circuit bank as ONE reference-based pool. "
                "Bits stay in their files (paths, no copy). FINALREADME §1/§7B/§8.",
        "reservoir_GB": total_GB, "reservoir_params_B": total_B, "n_models": len(fuzzy), "n_exact_circuits": len(exact),
        "roles": {r: [a["file"] for a in ranked if a["role"] == r] for r in ("spine", "fast", "specialist")},
        "fuzzy_experts": ranked, "exact_experts": exact,
        "spine": ranked[0]["file"] if ranked else None,
    }
    if write:
        os.makedirs(os.path.join(POOL, "experts"), exist_ok=True)
        for a in ranked:
            json.dump(a, open(os.path.join(POOL, "experts", a["file"].split(".gguf")[0] + ".json"), "w"), indent=1)
        for e in exact:
            json.dump(e, open(os.path.join(POOL, "experts", "exact_" + e["name"] + ".json"), "w"), indent=1)
        json.dump({"roles": manifest["roles"], "note": "role -> models; exact circuits are addressed by name"},
                  open(os.path.join(POOL, "routing.json"), "w"), indent=1)
        json.dump(manifest, open(os.path.join(POOL, "pool.json"), "w"), indent=1)
    print(f"\n[pool] RESERVOIR = {total_GB} GB / {total_B}B across {len(fuzzy)} models + {len(exact)} exact circuits.")
    print(f"  spine    : {manifest['roles']['spine']}")
    print(f"  fast(MoE): {manifest['roles']['fast']}")
    print(f"  exact    : {len(exact)} stored circuits (cpu_fwd, dot32_i8, the lib_* functions, verifiers, …)")
    if write: print(f"  routing folder -> {POOL}/  (pool.json · routing.json · experts/*.json — all references, no copy)")
    return manifest


if __name__ == "__main__":
    raise SystemExit(0 if build(write=(len(sys.argv) < 2 or sys.argv[1] != "show")) is not None else 1)
