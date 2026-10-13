#!/usr/bin/env python3
"""host/pfc_model.py — host routing that hooks a model up to the Muhlnickel.

Host only ADDRESSES weight/prompt windows, records the reflector connection, and
READS published answers. Host does not import titan_circuit or pfc_llama_harness
and does not ripple, fold, or run forward-pass arithmetic. Fire/read of a
fabricated slice: host/pfc_model_fire.py. Offline bake: infra/host/pfc_model.py.

  python host/pfc_model.py connect <model.gguf>   # reflector: reference, no copy
  python host/pfc_model.py run "<prompt>"         # address published windows
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

REG = "C:/llm/models/titan_circuits.json"
SBX = "C:/llm/sdc_sandbox/infer"
CONN = "C:/llm/sdc_sandbox/connection.json"
SAFEZONE = "C:/llm/sdc_out/pfc_model_safezone.bin"
PUBLISHED = ("pfc_mac", "pfc_silu8", "mdl_meta", "mdl_wires", "mdl_input", "mdl_receiver", "mdl_answer")


def _reg():
    if not os.path.exists(REG):
        return {}
    return json.load(open(REG))


def connect(model_path):
    if not os.path.exists(model_path):
        print(f"model not found: {model_path}"); return 1
    os.makedirs(os.path.dirname(CONN), exist_ok=True)
    json.dump(
        {
            "series": [
                {"model": model_path, "ref": True},
                {"pfc": ["pfc_mac", "pfc_silu8", "pfc_rsqrt", "pfc_exp", "pfc_argmax"]},
                {"safezone": SAFEZONE},
            ],
            "note": "reflector: model referenced in storage, never copied; host addresses only",
        },
        open(CONN, "w"),
        indent=1,
    )
    print(f"connected (reflector): {os.path.basename(model_path)} — referenced, not copied.")
    print(f"  series wired: model -> Muhlnickel baked circuits -> safezone.  {CONN}")
    return 0


def run(prompt, n_neurons="full"):
    """Address published model windows. Host does not compute the forward pass."""
    if not os.path.exists(CONN):
        print("no model connected — run: python host/pfc_model.py connect <model.gguf>"); return 1
    conn = json.load(open(CONN))
    model_path = conn["series"][0]["model"]
    reg = _reg()
    print("=== Muhlnickel MODEL — host addresses + reads; the Muhlnickel computes ===")
    print(f"  prompt  : {prompt!r}")
    print(f"  model   : {os.path.basename(model_path)}  neurons={n_neurons}")
    print(f"  conn    : {CONN}")
    missing = [k for k in PUBLISHED if k not in reg]
    if missing:
        print("  unpublished:", ", ".join(missing))
        print("  fire/read of a fabricated slice: python host/pfc_model_fire.py")
        print("  offline bake: infra/host/pfc_model.py")
        return 0
    for k in PUBLISHED:
        row = reg[k]
        if isinstance(row, dict):
            print(f"  {k}: offset={row.get('offset')} len={row.get('len')} n_gate={row.get('n_gate')}")
        else:
            print(f"  {k}: {row}")
    print(f"  safezone: {SAFEZONE}")
    print("  host arithmetic performed: NONE.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "connect":
        raise SystemExit(connect(sys.argv[2] if len(sys.argv) > 2 else "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf"))
    if cmd == "bake":
        print("host bake of weight tiles is offline: infra/host/pfc_model.py")
        print("host fire/read of a fabricated slice: python host/pfc_model_fire.py")
        raise SystemExit(0)
    prompt = sys.argv[2] if len(sys.argv) > 2 else "The capital of France is"
    n = sys.argv[3] if len(sys.argv) > 3 else "full"
    raise SystemExit(run(prompt, n))
