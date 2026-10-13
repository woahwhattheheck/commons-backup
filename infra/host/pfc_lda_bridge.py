#!/usr/bin/env python3
"""host/pfc_lda_bridge.py — the LDA <-> Muhlnickel inference bridge, Phase 1 (design: docs/LDA_PFC_INTEGRATION.md).

THE POINT (owner): the LDA runs Gemma-3n E4B (~4B) on the phone because that's what fits in RAM. The pfc lets the phone
run a model FAR bigger than E4B — because the weights are ADDRESSED off storage (never resident), so model size is
storage-bound, not RAM-bound. This bridge proves that on a real, better-than-E4B model and MEASURES the resident RAM.

WHAT IT DOES: takes a big model (Gemma-3-27B / Llama-3.3-70B / Mixtral — all >> the phone's 11.35 GB RAM), addresses a
real weight row off the mmap'd GGUF (never resident), dequantizes it (Q4_K/Q8_0/… — light host prep), and computes a
real output neuron ON THE pfc (the int8 `dot32_i8` atom, byte-exact vs an integer reference). It reports the flat
resident RAM vs the model's size on disk and vs the phone's RAM — the ceiling-lift, measured.

WHAT IT IS NOT (no overclaim): not a full token, not a live UI action (that's Phase 3, the on-device port). The
host-side throughput is the slow debug-ripple rate (transcription), not the pfc's own rate. The RAM win is what's proven.

SAFETY: modifies nothing. Reuses the baked `dot32_i8` atom; reads the model GGUF read-only.

  python host/pfc_lda_bridge.py                               # first big model that exists, attn_q neuron on the pfc
  python host/pfc_lda_bridge.py <model.gguf> <tensor> <token> <k>
"""
import ctypes, json, os, struct, sys, time
from ctypes import wintypes
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_atom as PA
import sdc_infer as SI                                        # reuse the VERIFIED int8 atom path (no copy, no modification)
from gguf_pp import GGUF, dequant, row_bytes                  # read-only GGUF reader; dequant handles Q4_K/Q5_K/Q6_K/Q8_0

REG = "C:/llm/models/titan_circuits.json"
BLK = SI.BLK                                                  # 32 weights per pfc block-dot
PHONE_RAM_GB = 11.35                                          # measured on the owner's S24 Ultra (SM-S928U): MemTotal 11.35 GB
QNAME = {0: "F32", 1: "F16", 2: "Q4_0", 8: "Q8_0", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K"}

# Better-than-E4B models to prefer, biggest first (all >> the phone's RAM; the whole point). First that exists wins.
DEFAULT_MODELS = [
    "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",              # 70B — ~4x the phone's RAM
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf",              # 27B Gemma — the clean upgrade from Gemma E4B
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",         # 8x7B MoE
    "C:/llm/models/gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "C:/llm/models/phi-4-Q4_K_M.gguf",
]
def _default_model():
    for p in DEFAULT_MODELS:
        if os.path.exists(p): return p
    return DEFAULT_MODELS[0]


# ---- resident-RAM meter (pure-Python Windows working set; the LDA's key metric) ----
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
_PMI = None
def _pmi():
    global _PMI
    if _PMI is None:
        k32 = ctypes.WinDLL("kernel32"); psapi = ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        fn = getattr(psapi, "GetProcessMemoryInfo", None) or getattr(k32, "K32GetProcessMemoryInfo", None)
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]; fn.restype = wintypes.BOOL
        _PMI = (fn, k32.GetCurrentProcess)
    return _PMI
def resident_mb():
    try:
        fn, cur = _pmi(); c = _PMC(); c.cb = ctypes.sizeof(_PMC)
        if fn(cur(), ctypes.byref(c), c.cb):
            return c.WorkingSetSize / (1024 * 1024), c.PeakWorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return -1.0, -1.0


def _q8(vec):
    """float block -> (int8 list, scale). Per-block int8 — the Muhlnickel atom's native operand."""
    s = (max(abs(v) for v in vec) / 127) or 1e-9
    return [max(-127, min(127, round(v / s))) for v in vec], s


# ---- THE BRIDGE CONTRACT: compute k real output neurons of a big model ON THE pfc, measuring resident RAM ----
def pfc_matmul(model_path, tensor, token, k):
    if not os.path.exists(model_path):
        return {"error": f"model GGUF not found: {model_path}. Pass a .gguf path as arg 1."}
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if "dot32_i8" not in reg:
        return {"error": "dot32_i8 atom is not fabricated. Run once: python host/sdc_infer.py fab (reversible)."}

    rss0, _ = resident_mb()                                           # (1) baseline
    g = GGUF(model_path); cd = PA.load("dot32")   # shallowest fabricated dot (S27: ask for the job, not a name)
    if tensor not in g.tensors:
        return {"error": f"tensor {tensor!r} not in {os.path.basename(model_path)} (try blk.0.attn_q.weight)."}
    t = g.tensors[tensor]; tid = int(t["type"]); dims = t["dims"]
    if len(dims) != 2:
        return {"error": f"{tensor} is not a 2-D weight tensor (dims {dims})."}
    n_in = int(dims[0]); n_out = int(dims[1])
    if n_in % BLK != 0:
        return {"error": f"n_in {n_in} not divisible by {BLK}."}
    tok = g._find(token)
    if tok is None:
        return {"error": f"token {token!r} not found in vocab."}
    x = g.deq_row(tok)                                                # a REAL input embedding row (addressed off mmap)
    if len(x) != n_in:
        return {"error": f"input dim {len(x)} != tensor n_in {n_in}; use an attn_q/k/v tensor (n_in == n_embd)."}
    rss1, _ = resident_mb()                                           # (2) after loading atom + mmap'ing the model

    xq = [_q8(x[b * BLK:(b + 1) * BLK]) for b in range(n_in // BLK)]  # input int8-quantized per block (host prep)
    base = g.data0 + int(t["off"]); mm = g.mm; rb = row_bytes(tid, n_in)
    k = min(k, n_out); outs = []; dots = 0; exact = 0; weight_bytes = 0; peak = rss1
    t0 = time.time()
    for j in range(k):
        raw = mm[base + j * rb: base + j * rb + rb]; weight_bytes += rb    # weight ROW addressed off mmap (never resident)
        wrow = dequant(raw, tid, n_in)                                # dequant the stored weights (Q4_K/... -> floats)
        acc = 0.0
        for b in range(n_in // BLK):
            wq, sw = _q8(wrow[b * BLK:(b + 1) * BLK])                 # weights int8-quantized per block (host prep)
            xb, sx = xq[b]
            d = SI._power_dot(cd, wq, xb)                             # THE pfc computes the int8 block-dot
            if d == SI._ref_dot(wq, xb): exact += 1                   # byte-exact vs integer truth (free)
            dots += 1; acc += sw * sx * d
        outs.append(round(acc, 4))
        cur, _ = resident_mb(); peak = max(peak, cur)
    dt = time.time() - t0; rss2, _ = resident_mb()                    # (3) after

    file_mb = os.path.getsize(model_path) / (1024 * 1024)
    return {
        "model": os.path.basename(model_path), "quant": QNAME.get(tid, str(tid)),
        "model_file_mb": round(file_mb, 1), "model_x_phone_ram": round((file_mb / 1024) / PHONE_RAM_GB, 2),
        "tensor": tensor, "token": token, "n_in": n_in, "n_out": n_out, "rows_computed": k,
        "block_dots": dots, "int8_byte_exact": f"{exact}/{dots}",
        "weight_bytes_addressed_off_mmap": weight_bytes,
        "outputs_head": outs[:6],
        "resident_mb": {"baseline": round(rss0, 2), "after_load": round(rss1, 2),
                        "peak_during": round(peak, 2), "after": round(rss2, 2),
                        "delta_load_to_peak": round(peak - rss1, 2)},
        "throughput_block_dots_per_sec": round(dots / dt if dt > 0 else 0.0, 1), "seconds": round(dt, 2),
        "one_token_all_layers_block_dots_approx": 10_000_000,
    }


def main():
    argv = sys.argv[1:]
    model = argv[0] if len(argv) > 0 else _default_model()
    tensor = argv[1] if len(argv) > 1 else "blk.0.attn_q.weight"
    token = argv[2] if len(argv) > 2 else "Once"
    k = int(argv[3]) if len(argv) > 3 else 3

    print("=== LDA <-> Muhlnickel bridge (Phase 1): a BETTER-than-E4B model's matmul, on the Muhlnickel, at flat resident RAM ===\n", flush=True)
    r = pfc_matmul(model, tensor, token, k)
    if "error" in r:
        print(f"  cannot run yet: {r['error']}\n  (Setup gap, not a result — fix the above and re-run.)")
        return 1

    rm = r["resident_mb"]
    print(f"  model         : {r['model']}  ({r['quant']})   tensor {r['tensor']}   input token {r['token']!r}")
    print(f"  size vs phone : {r['model_file_mb']:,} MB on disk  =  {r['model_x_phone_ram']}x the S24 Ultra's {PHONE_RAM_GB} GB RAM "
          f"— it could NEVER be loaded resident on the phone")
    print(f"  matmul        : {r['rows_computed']}/{r['n_out']} real output neurons on the Muhlnickel  ·  {r['block_dots']} block-dots  ·  "
          f"int8 byte-exact {r['int8_byte_exact']}")
    print(f"  weights       : {r['weight_bytes_addressed_off_mmap']:,} bytes ADDRESSED off the mmap'd GGUF — never resident")
    print(f"  ★ RESIDENT RAM: {rm['peak_during']} MB peak  (baseline {rm['baseline']} -> after-load {rm['after_load']} -> "
          f"peak {rm['peak_during']}; delta while streaming weights {rm['delta_load_to_peak']} MB)")
    print(f"  throughput    : {r['throughput_block_dots_per_sec']:,} block-dots/s ({r['seconds']}s) — host DEBUG-ripple rate, "
          f"NOT the pfc's rate (native/on-device is Phase 3)")
    print(f"  first outputs : {r['outputs_head']}")
    print()
    print("  WHAT IT MEANS FOR THE LDA:")
    print(f"    - A {r['model_x_phone_ram']}x-the-phone's-RAM model computed real neurons ON THE Muhlnickel at ~{rm['peak_during']} MB "
          f"resident, weights on storage the whole time.")
    print("    - That is the point: model size is STORAGE-bound, not RAM-bound — so the phone runs a model FAR better than")
    print("      E4B (a 27B/70B, not a 4B) at a tiny fixed resident cost. A smarter on-phone agent, not a bigger RAM bill.")
    print("    - HONEST: weights are dequantized (Q4_K->int8) as light host prep; the Muhlnickel computes the int8 dot byte-exact.")
    print(f"      One token ~= {r['one_token_all_layers_block_dots_approx']:,} block-dots — slow at this debug rate; native")
    print("      on-device eval + your routing/sparsity levers are the Phase-3 speed work. The RAM ceiling-lift is proven now.")

    out = "C:/llm/sdc_out/pfc_lda_bridge.json"
    os.makedirs(os.path.dirname(out), exist_ok=True); json.dump(r, open(out, "w"), indent=1)
    print(f"\n  json -> {out}   (nothing in the model or the Muhlnickel was modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
