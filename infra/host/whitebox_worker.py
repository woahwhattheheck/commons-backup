#!/usr/bin/env python3
"""whitebox_worker.py — the GATED SANDBOX (docs/WHITEBOX_SANDBOX.md, owner spec).

Every White Box model-operation runs HERE, in an isolated child process: input comes in ONE-WAY via argv (no channel
back to the server), the op reads the model's STORED BITS via mmap (sandboxed in storage — no model load, no inference),
FREEZES its result to --result, and this process EXITS (a dead process draws zero compute). The server reads the static
frozen file only AFTER this process ends, then renders. Reuses the existing whitebox_app functions verbatim — it only
relocates WHERE they run (an ending child, never the live server).

  python whitebox_worker.py --op <name> --path <model.gguf> --kw <json> --result <file>
"""
import json, os, sys
HOST = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOST)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import whitebox_app as wb


def _b(v):
    return v in (True, "1", "true", "True", 1)


# op name -> how to call the existing whitebox_app function with the request's kw dict.
# Functions that read wb.STATE["path"] internally are covered because the worker sets it below; embed-family functions
# self-attach the streaming decompiler on demand (start_embed_build → StreamE, ~0). No function is reimplemented here.
OPS = {
    "anatomy":     lambda p, k: wb.anatomy(p),
    "precision":   lambda p, k: wb.precision_map(p),
    "layerroles":  lambda p, k: {"roles": wb._layer_roles(p)},
    "layerscan":   lambda p, k: wb.layer_scan(p, k.get("role")),
    "tensor":      lambda p, k: wb.tensor_stats(k.get("name")),
    "experts":     lambda p, k: wb.do_experts(k.get("name")),
    "circuitry":   lambda p, k: wb.circuitry(p, int(k.get("layer", "0") or 0)),
    "interconnect": lambda p, k: wb.interconnect(p, int(k.get("layer", "0") or 0)),
    "osmap":       lambda p, k: wb.os_map(p),
    "decompile":   lambda p, k: wb.do_decompile(k.get("word", "king")),
    "meaning":     lambda p, k: wb.do_meaning_search(k.get("q", "king")),
    "analogy":     lambda p, k: wb.do_analogy(k.get("a"), k.get("b"), k.get("c")),
    "vec":         lambda p, k: wb.do_vec(k.get("text", "")),
    "editpreview": lambda p, k: wb.do_edit_preview(k.get("a", "king"), k.get("b", "queen")),
    "edittoken":   lambda p, k: wb.do_edit_token(k.get("word"), k.get("toward"), float(k.get("amount", "0.6") or 0.6), _b(k.get("zero"))),
    "align_axis":  lambda p, k: wb.do_align_axis(k.get("pos"), k.get("neg")),
    "align_edit":  lambda p, k: wb.do_align_edit(k.get("word"), float(k.get("strength", "0.3") or 0.3)),
    "direction":   lambda p, k: wb.do_direction(k.get("right"), k.get("wrong"), k.get("layer", "24"), k.get("kind", "down"),
                                                k.get("k", "14"), norm=k.get("norm", "0"), strip=k.get("strip", "0")),
    "param_decode": lambda p, k: wb.param_decode(k.get("layer", "0"), k.get("kind", "gate"), k.get("j", "0")),
    "param_scan":  lambda p, k: wb.param_scan(k.get("layer", "0"), k.get("kind", "down"), int(k.get("n", "48") or 48)),
    "token_neurons": lambda p, k: wb.token_neurons(k.get("word", "king"), k.get("layer", "29"), k.get("kind", "down")),
    "search":      lambda p, k: wb.do_search(k.get("kind", "tensor"), k.get("q"), k.get("rx", "0")),
    "destroy":     lambda p, k: wb.do_destroy(k.get("name"), k.get("expert")),
    "scale":       lambda p, k: wb.do_scale(k.get("name"), float(k.get("factor", "1") or 1)),
    "paste":       lambda p, k: wb.do_paste(k.get("dst"), k.get("src"), k.get("srcname")),
    "genome":      lambda p, k: wb.do_genome(),
    "revert":      lambda p, k: wb.do_revert(k.get("n", "1")),
    "create":      lambda p, k: (wb._fb.propose(k.get("desc", "")) if wb._fb else {"error": "forge unavailable"}),
    "export":      lambda p, k: wb.export_all(p, full_circuit=_b(k.get("full")), all_experts=_b(k.get("allexp")),
                                              decompile=_b(k.get("decompile"))),
    "archive":     lambda p, k: wb.research_archive(p, full=_b(k.get("full")), all_experts=_b(k.get("allexp")),
                                                    decompile=_b(k.get("decompile"))),
}


def main():
    args = sys.argv[1:]
    op = path = result = None
    kw = {}
    for i, a in enumerate(args):
        if a == "--op" and i + 1 < len(args):
            op = args[i + 1]
        elif a == "--path" and i + 1 < len(args):
            path = args[i + 1].replace("\\", "/") or None
        elif a == "--result" and i + 1 < len(args):
            result = args[i + 1]
        elif a == "--kw" and i + 1 < len(args):
            try:
                kw = json.loads(args[i + 1]) or {}
            except Exception:
                kw = {}
    if path:
        wb.STATE["path"] = path                                   # so functions that read STATE["path"] see the file
    try:
        fn = OPS.get(op)
        out = fn(path, kw) if fn else {"error": f"unknown op {op}"}
    except Exception as e:
        out = {"error": f"{type(e).__name__}: {e}"}
    if result:                                                    # FREEZE the static result, then this process EXITS
        try:
            with open(result, "w", encoding="utf-8") as f:
                json.dump(out, f)
        except Exception as e:
            try:
                with open(result, "w", encoding="utf-8") as f:
                    json.dump({"error": f"result-write failed: {e}"}, f)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
