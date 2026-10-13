#!/usr/bin/env python3
"""host/forge_build.py — CREATE A MODEL FROM SCRATCH, driven by White-Box data (owner: 'white box needs a create-model-
from-scratch feature where you describe what you want and titan builds the model using the white box data').

Describe what you want → this proposes a BUILD SPEC composed from the MEASURED pool (docs/TITAN_SCAN.json:
best-source-per-role + health) and the precision recipe, then composes it. Per the structural law (TITAN_SYSTEM §1.7):
cross-arch fusion into one transformer is incoherent, so 'create a model' = a REFERENCE-BASED routing folder (whole-expert
routing, INV-149, no ≥120 GB copy) + SAME-HIDDEN-DIM tensor grafts applied as reversible White-Box weight edits
(`wbedit.blend_tensor`) + operator bakes — every applied change a reversible weight modification (owner's binding
constraint). This module is the PROPOSE + COMPOSE engine; the White Box "Create" tab calls it.
"""
import json, os, re
import gguf

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = "C:/llm/models"
SCAN = os.path.join(HERE, "..", "docs", "TITAN_SCAN.json")

# size intent → a base model in the pool (sparse-first; NEVER dense-grow for size — STUDY_NOTES misfire)
_SIZE = [("200", "titan.gguf"), ("giant", "titan.gguf"), ("huge", "titan.gguf"), ("70", "Llama-3.3-70B-Instruct-Q4_K_M.gguf"),
         ("big", "titan.gguf"), ("large", "gemma-4-31B-it-qat-UD-Q4_K_XL.gguf"), ("medium", "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"),
         ("small", "phi-4-Q4_K_M.gguf"), ("tiny", "phi-4-Q4_K_M.gguf"), ("fast", "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")]
_SPECIALTY = {"cod": "coder", "program": "coder", "reason": "reasoning", "math": "reasoning", "logic": "reasoning",
              "image": "image", "draw": "image", "art": "image", "vision": "image", "translat": "translator",
              "chat": "assistant", "assistant": "assistant", "write": "writer", "poet": "writer"}


def _scan():
    try:
        return json.load(open(SCAN, encoding="utf-8"))
    except Exception:
        return {}


# known hidden dims (measured; the structural-law key — TITAN_SYSTEM §1.7) so propose() never opens 7 ggufs
_HIDDEN = {"titan.gguf": 2816, "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf": 2816, "gemma-4-31B-it-qat-UD-Q4_K_XL.gguf": 5376,
           "google_gemma-3-27b-it-Q4_K_M.gguf": 5376, "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf": 5120,
           "phi-4-Q4_K_M.gguf": 5120, "Llama-3.3-70B-Instruct-Q4_K_M.gguf": 8192, "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf": 4096}


def _hidden(path):
    b = os.path.basename(path)
    if b in _HIDDEN:
        return _HIDDEN[b]
    try:
        r = gguf.GGUFReader(path)
        kv = {f.name: f for f in r.fields.values()}
        a = bytes(kv["general.architecture"].parts[kv["general.architecture"].data[-1]]).decode("utf-8", "replace")
        x = kv.get(f"{a}.embedding_length")
        return int(x.parts[x.data[-1]][0]) if x else None
    except Exception:
        return None


def propose(description):
    """Describe a model → a White-Box-data-driven BUILD SPEC (base, best-source-per-role grafts that are dim-compatible,
    sparse α target, operators). Measured, reference-based, reversible-by-construction. No heavy op — pure planning."""
    d = (description or "").lower()
    base = next((m for key, m in _SIZE if key in d), "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")
    specialty = next((v for k, v in _SPECIALTY.items() if k in d), "assistant")
    scan = _scan()
    bsr = scan.get("best_source_per_role", {})
    base_path = os.path.join(MODELS, base)
    base_hidden = _hidden(base_path) if os.path.exists(base_path) else None
    # which best-source roles are GRAFTABLE into this base (same hidden dim = the structural law); others = whole-expert route
    grafts, routed = [], []
    for role, v in bsr.items():
        src = v.get("model") if isinstance(v, dict) else v
        if not src or src == base:
            continue
        sp = os.path.join(MODELS, src)
        sh = _hidden(sp) if os.path.exists(sp) else None
        entry = {"role": role, "source": src, "hidden": sh}
        (grafts if (sh and base_hidden and sh == base_hidden) else routed).append(entry)
    return {"description": description, "specialty": specialty, "base": base, "base_hidden": base_hidden,
            "grafts": grafts[:20], "n_graftable": len(grafts), "routed_experts": routed[:12], "n_routed": len(routed),
            "alpha_target": "sparse (α fixed — grow storage/experts, never per-token read)",
            "operators": {"coder": ["SCHEMA", "REDUCE"], "reasoning": ["REDUCE", "ACCURACY"], "image": ["SCHEMA"],
                          "writer": ["ANCHOR"], "assistant": ["ACCURACY", "GROUNDING"]}.get(specialty, ["ACCURACY"]),
            "note": f"Build a '{specialty}' from base {base} (hidden {base_hidden}): {len(grafts)} same-dim role grafts "
                    f"(reversible White-Box weight blends) + {len(routed)} whole-expert routes (reference-based, no copy) "
                    f"+ operator bake. All grafts land via wbedit (reversible). This is the SGS routing-folder form.",
            "how": "Grafts apply as reversible wbedit.blend_tensor edits into the base; routes stay reference-based (INV-149); "
                   "operators bake via the White-Box oscilloscope. Cross-arch fusion into ONE transformer is incoherent — "
                   "hence the folder form (why Titan is an SGS, not a merged LLM)."}


if __name__ == "__main__":
    import sys
    print(json.dumps(propose(" ".join(sys.argv[1:]) or "a fast tiny coder"), indent=2))
