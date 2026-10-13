#!/usr/bin/env python3
"""host/pfc_route.py — the routing lever, LIVE on the Muhlnickel (design: docs/LDA_PFC_INTEGRATION.md).

pfc_gen_cost.py QUANTIFIED that routing cuts a token's block-dots ~4x on Mixtral (only 2/8 experts fire). This makes it
LIVE: it computes the MoE router ON THE pfc (the `dot32_i8` atom, byte-exact), lets the router pick the top-2 experts,
confirms only those experts would run, and accounts the per-layer FFN block-dot drop — all at flat resident RAM, weights
addressed off the mmap'd GGUF. This is the "routing" half of "routing and sparsity = minimum viable generation" (owner),
demonstrated on real Mixtral weights, not asserted.

HONEST SCOPE: the input is a real token embedding used as a representative hidden vector into layer-0's router (a
mechanism demo, not a full correct forward pass — a true hidden state comes after attention). What's proven: the router
computes on the pfc and selects experts byte-exact; only the selected experts' FFN block-dots are spent; the reduction is
the measured 8->2. The full expert FFN (~5.5M block-dots/expert) is too many to ripple on the host, so a SAMPLE of each
selected expert's neurons is computed on the pfc byte-exact and the full routed cost is accounted (not rippled).

SAFETY: modifies nothing. Reuses the baked `dot32_i8` atom + the Phase-1 bridge helpers; reads the model GGUF read-only.

  python host/pfc_route.py                                  # Mixtral, token "Once", top-2
  python host/pfc_route.py <mixtral.gguf> <token> <top_k>
"""
import json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import sdc_infer as SI
import pfc_lda_bridge as BR                                   # reuse resident_mb + _q8 (Phase-1 bridge, no copy)
from gguf_pp import GGUF, dequant, row_bytes

BLK = SI.BLK
DEFAULT_MODEL = "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
ROUTER = "blk.0.ffn_gate_inp.weight"                          # [n_embd, n_experts] router logits
GATE = "blk.0.ffn_gate.{e}.weight"; UP = "blk.0.ffn_up.{e}.weight"; DOWN = "blk.0.ffn_down.{e}.weight"


def _pfc_dot_row(g, cd, base, rb, tid, j, n_in, xq):
    """One output neuron j = dot(weight_row_j, x), computed block-by-block ON THE Muhlnickel. Returns (value, exact_blocks)."""
    raw = g.mm[base + j * rb: base + j * rb + rb]                     # weight row addressed off mmap — never resident
    wrow = dequant(raw, tid, n_in)
    acc = 0.0; exact = 0
    for b in range(n_in // BLK):
        wq, sw = BR._q8(wrow[b * BLK:(b + 1) * BLK]); xb, sx = xq[b]
        d = SI._power_dot(cd, wq, xb)                                 # the pfc computes the int8 block-dot
        if d == SI._ref_dot(wq, xb): exact += 1
        acc += sw * sx * d
    return acc, exact


def route(model_path, token, top_k):
    if not os.path.exists(model_path):
        return {"error": f"model not found: {model_path}"}
    reg = json.load(open(BR.REG)) if os.path.exists(BR.REG) else {}
    if "dot32_i8" not in reg:
        return {"error": "dot32_i8 atom not fabricated. Run once: python host/sdc_infer.py fab (reversible)."}
    if ROUTER not in GGUF(model_path).tensors:
        return {"error": f"{ROUTER} not in model — this demo needs a Mixtral-style MoE (per-expert FFN + ffn_gate_inp)."}

    rss0, _ = BR.resident_mb()                                        # (1) baseline
    g = GGUF(model_path); cd = TC.load("dot32_i8")
    rt = g.tensors[ROUTER]; n_embd = int(rt["dims"][0]); n_exp = int(rt["dims"][1]); tid = int(rt["type"])
    tok = g._find(token)
    if tok is None: return {"error": f"token {token!r} not in vocab."}
    x = g.deq_row(tok)                                                # a real embedding row (representative hidden vector)
    xq = [BR._q8(x[b * BLK:(b + 1) * BLK]) for b in range(n_embd // BLK)]
    rss1, _ = BR.resident_mb()                                        # (2) after atom + mmap
    peak = rss1

    # ---- ROUTER, ON THE pfc: n_exp logits, each a real dot over the pfc atom, byte-exact ----
    base = g.data0 + int(rt["off"]); rb = row_bytes(tid, n_embd)
    logits = []; r_dots = 0; r_exact = 0; t0 = time.time()
    for e in range(n_exp):
        v, ex = _pfc_dot_row(g, cd, base, rb, tid, e, n_embd, xq)
        logits.append(v); r_dots += n_embd // BLK; r_exact += ex
        cur, _ = BR.resident_mb(); peak = max(peak, cur)
    order = sorted(range(n_exp), key=lambda e: logits[e], reverse=True)
    chosen = order[:top_k]
    mx = max(logits[e] for e in chosen); ex_w = [math.exp(logits[e] - mx) for e in chosen]; sm = sum(ex_w)
    gates = {e: round(w / sm, 4) for e, w in zip(chosen, ex_w)}       # softmax over the selected experts (Mixtral)

    # ---- SELECTED EXPERTS, ON THE Muhlnickel: a SAMPLE of each chosen expert's gate neurons, byte-exact (proof they compute) ----
    SAMPLE = 2; e_dots = 0; e_exact = 0; sample_out = {}
    for e in chosen:
        gt = g.tensors[GATE.format(e=e)]; gtid = int(gt["type"]); gin = int(gt["dims"][0]); gout = int(gt["dims"][1])
        gbase = g.data0 + int(gt["off"]); grb = row_bytes(gtid, gin); vals = []
        for j in range(min(SAMPLE, gout)):
            v, ex = _pfc_dot_row(g, cd, gbase, grb, gtid, j, gin, xq)
            vals.append(round(v, 3)); e_dots += gin // BLK; e_exact += ex
        sample_out[e] = vals
        cur, _ = BR.resident_mb(); peak = max(peak, cur)
    dt = time.time() - t0; rss2, _ = BR.resident_mb()                 # (3) after

    # ---- block-dot accounting for ONE layer's FFN: dense (all experts) vs routed (chosen only) ----
    def ffn_dots_one_expert():
        gt = g.tensors[GATE.format(e=chosen[0])]; up = g.tensors[UP.format(e=chosen[0])]; dn = g.tensors[DOWN.format(e=chosen[0])]
        d = 0
        for t in (gt, up, dn): d += (int(t["dims"][0]) // BLK) * int(t["dims"][1])
        return d
    per_exp = ffn_dots_one_expert(); dense_layer = per_exp * n_exp; routed_layer = per_exp * top_k
    return {
        "model": os.path.basename(model_path), "token": token, "n_embd": n_embd, "n_experts": n_exp, "top_k": top_k,
        "router_logits": [round(v, 3) for v in logits], "chosen_experts": chosen, "gate_weights": gates,
        "router_block_dots": r_dots, "router_byte_exact": f"{r_exact}/{r_dots}",
        "sample_neurons_per_expert": SAMPLE, "expert_sample_block_dots": e_dots, "expert_byte_exact": f"{e_exact}/{e_dots}",
        "expert_sample_outputs": sample_out,
        "ffn_dense_layer_block_dots": dense_layer, "ffn_routed_layer_block_dots": routed_layer,
        "routing_reduction_x": round(dense_layer / max(routed_layer, 1), 1),
        "resident_mb": {"baseline": round(rss0, 2), "after_load": round(rss1, 2),
                        "peak_during": round(peak, 2), "after": round(rss2, 2), "delta_load_to_peak": round(peak - rss1, 2)},
        "seconds": round(dt, 2),
    }


def main():
    argv = sys.argv[1:]
    model = argv[0] if len(argv) > 0 else DEFAULT_MODEL
    token = argv[1] if len(argv) > 1 else "Once"
    top_k = int(argv[2]) if len(argv) > 2 else 2

    print("=== Muhlnickel routing, LIVE: the MoE router runs ON THE Muhlnickel and picks the experts (routing lever, measured) ===\n", flush=True)
    r = route(model, token, top_k)
    if "error" in r:
        print(f"  cannot run yet: {r['error']}"); return 1
    rm = r["resident_mb"]
    print(f"  model         : {r['model']}   input token {r['token']!r}   {r['n_experts']} experts, top-{r['top_k']}")
    print(f"  router ON Muhlnickel : {r['n_experts']} logits computed on the Muhlnickel atom, byte-exact {r['router_byte_exact']}  "
          f"({r['router_block_dots']} block-dots)")
    print(f"  logits        : {r['router_logits']}")
    print(f"  -> ROUTED TO  : experts {r['chosen_experts']}   gate-weights {r['gate_weights']}   (only these run)")
    print(f"  experts ON Muhlnickel: sampled {r['sample_neurons_per_expert']} gate-neurons/expert, byte-exact {r['expert_byte_exact']}  "
          f"-> {r['expert_sample_outputs']}")
    print(f"  ★ per-layer FFN block-dots: DENSE (all {r['n_experts']}) {r['ffn_dense_layer_block_dots']:,}  ->  "
          f"ROUTED (top-{r['top_k']}) {r['ffn_routed_layer_block_dots']:,}   = {r['routing_reduction_x']}x less")
    print(f"  ★ RESIDENT RAM: {rm['peak_during']} MB peak (baseline {rm['baseline']} -> after-load {rm['after_load']} -> "
          f"peak {rm['peak_during']}; delta {rm['delta_load_to_peak']} MB) — weights addressed off mmap, never resident")
    print(f"  seconds       : {r['seconds']}s  (host debug-ripple of the router; the Muhlnickel's own rate is Phase 3)")
    print()
    print("  WHAT IT MEANS:")
    print(f"    - The ROUTER computed on the Muhlnickel, byte-exact, and SELECTED {r['top_k']} of {r['n_experts']} experts. Only those")
    print(f"      experts' FFN block-dots are spent -> {r['routing_reduction_x']}x fewer per layer, for free (the model's own sparsity).")
    print("    - That is the routing lever from pfc_gen_cost.py, now LIVE: the selection is real compute on the Muhlnickel, and the")
    print("      cost drop is the model's architecture, not an assumption. Stacked with contextual sparsity + a native eval,")
    print("      this is the path to a big MoE model generating at phone-viable speed (the A4B result: ~2.5 tok/s).")
    out = "C:/llm/sdc_out/pfc_route.json"
    os.makedirs(os.path.dirname(out), exist_ok=True); json.dump(r, open(out, "w"), indent=1)
    print(f"\n  json -> {out}   (nothing in the model or the Muhlnickel was modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
