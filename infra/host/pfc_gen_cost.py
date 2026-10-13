#!/usr/bin/env python3
"""host/pfc_gen_cost.py — per-token generation cost + the routing/sparsity lever, for Muhlnickel inference (design: docs/LDA_PFC_INTEGRATION.md).

THE QUESTION (owner): the pfc + memmapping removes the RAM wall (proven in pfc_lda_bridge.py) so a big model FITS on the
phone. The remaining question is SPEED: "routing and sparsity = minimum viable generation." This tool answers it with
real numbers — it reads a model's actual architecture from the GGUF and computes:
  * DENSE  block-dots per token  (every weight matmul, all experts) — the honest full cost.
  * ROUTED block-dots per token  (MoE: only the active experts) — architectural sparsity, real, from the file.
  * + an optional contextual-sparsity factor for the dense FFN (PowerInfer/Deja-Vu style: only the neurons that fire).
Then it shows tok/s at a few block-dot evaluation rates, so you can see exactly what eval speed x sparsity makes Llama
(or an MoE) viable on the Ultra. A block-dot = the pfc `dot32_i8` atom (32 int8 MACs).

Honest: the sparsity FACTORS are labelled (MoE active-expert count is real from the file; contextual sparsity is a target
you set). The point is the SHAPE — dense cost is fixed by the model; routing+sparsity is the lever; eval-rate is the port.

  python host/pfc_gen_cost.py                         # first big model on the box
  python host/pfc_gen_cost.py <model.gguf> [n_active_experts] [contextual_ffn_keep]
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF

BLK = 32
PHONE_RAM_GB = 11.35                                          # measured S24 Ultra (SM-S928U)
DEFAULT_MODELS = [
    "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf",
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
    "C:/llm/models/phi-4-Q4_K_M.gguf",
]
# block-dot evaluation rates to illustrate (block-dots/sec):
#  56          = the CURRENT pure-python gate-ripple of the 93k-gate atom (the debug transcription rate)
#  1e6, 1e8    = native int8 evaluation targets (a block-dot is 32 int8 MACs — trivial natively); the on-device port
RATES = [("python gate-ripple (now)", 56.0), ("native ~1e6/s", 1e6), ("native ~1e8/s", 1e8)]
MATMUL_HINTS = ("attn_q", "attn_k", "attn_v", "attn_qkv", "attn_output", "attn_o",
                "ffn_gate", "ffn_up", "ffn_down", "output.weight", "lm_head")
EXP_RE = re.compile(r"ffn_(?:gate|up|down)\.(\d+)\.weight")  # Mixtral-style per-expert FFN (one 2-D tensor per expert)


def _is_matmul(name):
    if name.endswith("_norm.weight") or "token_embd" in name or name.endswith(".bias"):
        return False
    return any(h in name for h in MATMUL_HINTS)


def analyze(model_path, n_active, ffn_keep):
    g = GGUF(model_path)
    pe_ids = set()                                           # pre-scan for Mixtral-style per-expert FFN tensors
    for name in g.tensors:
        m = EXP_RE.search(name)
        if m: pe_ids.add(int(m.group(1)))
    n_exp_pe = (max(pe_ids) + 1) if pe_ids else 0
    layers = set(); dense = 0; routed = 0; is_moe = False; n_exp = 0; ffn_dense = 0; ffn_routed = 0
    for name, t in g.tensors.items():
        dims = [int(d) for d in t["dims"]]
        if name.startswith("blk."):
            layers.add(name.split(".")[1])
        if not _is_matmul(name):
            continue
        if EXP_RE.search(name) and len(dims) == 2:           # per-expert FFN (Mixtral): one 2-D tensor per expert
            is_moe = True; n_exp = max(n_exp, n_exp_pe)
            n_in, n_out = dims; bd = (n_in // BLK) * n_out
            frac = min(n_active, n_exp_pe) / max(n_exp_pe, 1) # only the top-k experts fire per token
            dense += bd; routed += int(bd * frac)
            ffn_dense += bd; ffn_routed += int(bd * frac)
        elif len(dims) == 2:                                 # standard weight [n_in, n_out]
            n_in, n_out = dims; bd = (n_in // BLK) * n_out
            dense += bd; routed += bd
            if "ffn_" in name: ffn_dense += bd; ffn_routed += bd
        elif len(dims) == 3:                                 # _exps MoE [n_in, n_out, n_experts] (A4B-style)
            is_moe = True; n_in, n_out, ne = dims; n_exp = max(n_exp, ne)
            bd1 = (n_in // BLK) * n_out
            dense += bd1 * ne                                 # dense would compute ALL experts
            act = min(n_active, ne)
            routed += bd1 * act                               # routed computes only the active experts
            ffn_dense += bd1 * ne; ffn_routed += bd1 * act
    n_layers = len(layers) or 1
    # contextual FFN sparsity (optional target): keep only `ffn_keep` fraction of the dense-FFN block-dots
    sparse = routed - ffn_routed + int(ffn_routed * ffn_keep)
    file_gb = os.path.getsize(model_path) / (1024 ** 3)
    return {"model": os.path.basename(model_path), "file_gb": round(file_gb, 1),
            "x_phone_ram": round(file_gb / PHONE_RAM_GB, 2), "n_layers": n_layers,
            "is_moe": is_moe, "n_experts": n_exp, "n_active": min(n_active, n_exp) if is_moe else None,
            "dense_block_dots_per_token": dense, "routed_block_dots_per_token": routed,
            "sparse_block_dots_per_token": sparse, "ffn_keep": ffn_keep}


def main():
    argv = sys.argv[1:]
    model = argv[0] if len(argv) > 0 else next((p for p in DEFAULT_MODELS if os.path.exists(p)), DEFAULT_MODELS[0])
    n_active = int(argv[1]) if len(argv) > 1 else 2          # MoE active experts (Mixtral top-2; set per model)
    ffn_keep = float(argv[2]) if len(argv) > 2 else 0.15     # contextual FFN keep-fraction (target; PowerInfer ~ a fifth fire)
    if not os.path.exists(model):
        print(f"model not found: {model}"); return 1

    r = analyze(model, n_active, ffn_keep)
    print(f"=== Muhlnickel generation cost — {r['model']} ===\n", flush=True)
    print(f"  size          : {r['file_gb']} GB on disk = {r['x_phone_ram']}x the S24 Ultra's {PHONE_RAM_GB} GB RAM "
          f"(memmapped: resident ~flat, from pfc_lda_bridge.py)")
    moe = f"MoE {r['n_experts']} experts, {r['n_active']} active/token" if r["is_moe"] else "dense (no MoE experts)"
    print(f"  architecture  : {r['n_layers']} layers · {moe}")
    dpt = r["dense_block_dots_per_token"]; rpt = r["routed_block_dots_per_token"]; spt = r["sparse_block_dots_per_token"]
    print(f"\n  block-dots / token (a block-dot = the Muhlnickel dot32_i8 atom = 32 int8 MACs):")
    print(f"    DENSE  (all weights, all experts)        : {dpt:,}")
    if r["is_moe"]:
        print(f"    ROUTED (MoE: only {r['n_active']}/{r['n_experts']} experts)          : {rpt:,}   "
              f"({dpt/max(rpt,1):.1f}x less)")
    print(f"    + contextual FFN sparsity (keep {int(r['ffn_keep']*100)}%)  : {spt:,}   ({dpt/max(spt,1):.1f}x less than dense)")
    print(f"\n  tok/s at various block-dot evaluation rates (this is the Phase-3 'port' variable):")
    print(f"    {'rate':<28}{'DENSE':>14}{'ROUTED+SPARSE':>18}")
    for label, rate in RATES:
        td = rate / dpt if dpt else 0; ts = rate / spt if spt else 0
        def fmt(x): return f"{x:,.2f} tok/s" if x >= 0.01 else f"1 tok / {1/x/60:,.0f} min" if x > 0 else "-"
        print(f"    {label:<28}{fmt(td):>14}{fmt(ts):>18}")
    print(f"\n  READ-OUT:")
    print(f"    - RAM is solved (memmapped, ~flat resident — proven). Cost/token is FIXED by the model ({dpt:,} dense).")
    print(f"    - Routing + sparsity is the lever: it cuts the work ~{dpt/max(spt,1):.0f}x here. Eval-rate is the port.")
    if r["is_moe"]:
        print(f"    - This is an MoE — architectural sparsity is FREE (only active experts run). Good 'viable' candidate.")
    else:
        print(f"    - Dense model: the sparsity is contextual (only firing neurons) — the target keep-fraction is set by you.")
    print(f"    - To beat resident LiteRT-LM (~2 tok/s on the phone), routed+sparse needs a native/on-device eval rate")
    print(f"      in the ~1e6-1e8 block-dots/s band. That band + the sparsity above is the 'minimum viable generation' line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
