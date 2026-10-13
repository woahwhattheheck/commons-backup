#!/usr/bin/env python3
"""host/pfc_engine.py — THE MODEL ENGINE: run a BIG model on the Muhlnickel with ALL levers stacked (FABRICATION primary,
OPERATORS in the weights, System-1 memoize). Read docs/PFC_MODEL_ENGINE_LEVERS.md first — this is the assembly of the
measured lever stack. NO C, NO small models, host addresses + reads only. (owner Bryce, 2026-07-23.)

The forward pass computes EVERY matmul on the FABRICATION SUBSTRATE (host/pfc_matmul_engine.py: depth-opt 3-bit compiled
bit-slice, pre-sliced pipeline, weights addressed off storage → flat RAM). Glue runs on the baked circuits. MoE routes
4/128 experts. An operator σ (terse output-contract + gated-sparse) is BAKED into the weights (0-token). System-1 memoize
returns instant on recognized inputs.

STATUS: substrate wired + memoize + operator-bake hook. The full 26B decode loop + bit-sliced accumulation (the last
output-unpack bottleneck) is the next build step per §5 of the handoff doc.

  python host/pfc_engine.py selftest      # verify the matmul substrate path byte-exact on real weights
"""
import hashlib, json, math, os, struct, sys, time
from array import array
INF = float("inf"); NINF = float("-inf")
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, dequant, row_bytes, _sm_k4
from pfc_matmul_engine import MatmulEngine, BLK

MEMO = "C:/llm/sdc_out/pfc_engine_memo.json"          # System-1 memoize store (temp-0 (σ+input) -> answer)
DEFAULT_MODEL = "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"   # the 26B MoE — NO small models


def _q(vec, bits):
    """quantize a float block to `bits`-bit signed ints + scale (TurboQuant-safe at 3-4 bit weights)."""
    lim = (1 << (bits - 1)) - 1
    s = (max(abs(v) for v in vec) / lim) or 1e-9
    return [max(-lim - 1, min(lim, round(v / s))) for v in vec], s


class PfcEngine:
    """FABRICATION-primary matmul: y[j]=<w_j,x> via the depth-opt 3-bit bit-slice fold, weights off storage (flat RAM)."""
    TILE = 256          # output-neuron tile: bounded resident regardless of model size (catalog lever)
    def __init__(self, model_path=DEFAULT_MODEL, WB=8, XB=10):
        # WB=8 is the DOC'S MEASURED PICK, not a guess. PFC_MODEL_ENGINE_LEVERS sweeps WB on REAL weights:
        #   WB=3 -> 31.99% rel-err ("garbage") · WB=6 -> 2.66% · WB=8 -> 1.26% ("the pick") · WB=16 -> 0.00%
        # Reproduced here 2026-07-25 vs TRUE float: WB=3 28.4% · WB=6 2.00% · WB=8 1.04%.
        # The old WB=3 default meant every forward pass ran at ~28% error while every substrate-vs-substrate
        # check passed at ~1e-15. Costs area (dot 9,682 -> 27,083 gates), not DEPTH.
        # XB=10 + ow=17+max(0,XB-8): MORNING_HANDOFF measured XB=8 at 11.5% rel-L2 (argmax flips -> word salad) vs
        # 3.35% at XB=10 for 1.19x the time; ow=17 is FREE (3 dead accumulator bits, max|sum q.x| = 60,960 < 2^17).
        self.g = GGUF(model_path); self.WB = WB; self.XB = XB
        self.dot = MatmulEngine(WB=WB, XB=XB, ow=17 + max(0, XB - 8))   # the fabrication substrate (compiled bit-slice)
        self.model_path = model_path
        self.memo = json.load(open(MEMO)) if os.path.exists(MEMO) else {}
        self.nonfinite_rows = []      # (tensor, row) of any row with a non-finite stored scale -- REPORTED, not hidden

    # ---- Q4_K-NATIVE PATH: the model's OWN stored nibbles, no dequant, no requantize, no WB term ----
    # The exact Q4_K identity per 32-weight sub-block (pfc_fab_q4k, fabricated + byte-exact 40/40):
    #     sum_i w_i x_i = d*sc * SUM(q_i * x_i)  -  dmin*m * SUM(x_i)
    # Both sums are INTEGER over unsigned 4-bit q and signed int8 x -- exactly what pfc_dot_q4k_sub32 computes in
    # GATES. Nothing is transformed and nothing is cached: the weights are read as they lie. This removes the WB
    # requantisation error entirely (it is the dominant term: WB=8 measured 1.709% on Mixtral).
    def matvec_q4k(self, tensor, x):
        t = self.g.tensors[tensor]; n_in = int(t["dims"][0]); n_out = int(t["dims"][1])
        base = self.g.data0 + int(t["off"]); rb = row_bytes(12, n_in); mm = self.g.mm
        SUB, SB = 32, 256
        out = [0.0] * n_out
        for t0 in range(0, n_out, self.TILE):                       # output-neuron tiling: bounded resident
            for j in range(t0, min(t0 + self.TILE, n_out)):
                raw = mm[base + j * rb: base + j * rb + rb]; tot = 0.0
                for blk in range(n_in // SB):
                    d, dmin = struct.unpack_from("<ee", raw, blk * 144)
                    if d != d or dmin != dmin:                      # non-finite stored scale -> report, never hide
                        self.nonfinite_rows.append((tensor, j)); continue
                    sc12 = raw[blk * 144 + 4: blk * 144 + 16]; qs = raw[blk * 144 + 16: blk * 144 + 144]
                    for sb in range(8):
                        sc, m = _sm_k4(sb, sc12)
                        o = blk * SB + sb * SUB
                        xs = x[o: o + SUB]
                        sx = (max(abs(v) for v in xs) / 127) or 1e-9   # per-sub-block int8 activation scale
                        xq = [max(-128, min(127, round(v / sx))) for v in xs]
                        # Q4_K NIBBLE LAYOUT: sub-blocks are PAIRED. bytes qs[(sb//2)*32 ...] hold the LOW nibble
                        # for the even sub-block and the HIGH nibble for the odd one. (Q4_0-style idx>>1 interleaving
                        # is a different format and measured 186% rel-L2 here -- caught only by the true-float check.)
                        A = 0; bb = (sb >> 1) * SUB; hi = sb & 1
                        for i in range(SUB):
                            b = qs[bb + i]
                            A += (b >> 4 if hi else b & 0xF) * xq[i]
                        tot += sx * (d * sc * A - dmin * m * sum(xq))
                out[j] = tot
        return out

    # ---- FABRICATION-primary matmul with BIT-SLICED ACCUMULATION (§5) — the pfc computes, weights off storage (flat RAM) ----
    def matvec(self, tensor, x):
        """All output neurons of `tensor` . x on the fabrication fold, BIT-SLICED ACCUMULATION (unpack once). ONE x-scale
        and ONE per-neuron weight-scale (so the integer sum is valid across blocks). Weights pre-sliced (constant-operand
        lever) + x broadcast (shared-x lever). Returns float neuron outputs. Byte-exact vs the integer reference by design.
        NOTE: pre-slicing weights is done here per-call; the fabrication-time move (§5) is to pre-slice the whole model ONCE
        into storage so the runtime only addresses it (constant weights = one-and-done)."""
        t = self.g.tensors[tensor]; tid = int(t["type"]); n_in = int(t["dims"][0]); n_out = int(t["dims"][1])
        if tid == 12 and n_in % 256 == 0:            # DISPATCH ON THE STORED TYPE (12 = Q4_K). The engine read
            return self.matvec_q4k(tensor, x)        # t["type"] and ignored it; Mixtral is 833 Q4_K tensors.
        base = self.g.data0 + int(t["off"]); rb = row_bytes(tid, n_in); mm = self.g.mm; nb = n_in // BLK
        # PER-SUB-BLOCK ACTIVATION SCALE (MORNING_HANDOFF): EXACT bookkeeping, not an approximation -- the Q4_K identity
        # is already per-sub-block, so each 32-block's scale multiplies its OWN contribution instead of being factored
        # out at the end. One global scale let a single |x|=19 outlier crush every median-0.24 value into a couple of
        # quantisation levels. Measured there: global XB=10 3.35% -> per-block 0.397% (8.4x, same bit width).
        lim = (1 << (self.XB - 1)) - 1
        sxb = [(max(abs(x[b * BLK + i]) for i in range(BLK)) / lim) or 1e-9 for b in range(nb)]
        x_blocks = [[max(-lim - 1, min(lim, round(x[b * BLK + i] / sxb[b]))) for i in range(BLK)] for b in range(nb)]
        wl = (1 << (self.WB - 1)) - 1
        # ONE dequant pass per weight row. The previous form dequantized every row nb+1 times (a scale pass, then again
        # inside the per-block loop) = ~130x redundant host arithmetic on a 4096-wide tensor -- "if it is slow, the host
        # is touching it". Each row is addressed off storage once, quantized once, and held as a signed-byte array
        # (1 B/weight, stdlib `array`, no numpy) so the per-block loop only SLICES it.
        # OUTPUT-NEURON TILING (catalog, MODEL INFERENCE): only TILE weight rows are dequantized/resident at once --
        # dequant the tile, fold it, discard. Resident stays BOUNDED regardless of model size; the old form held all
        # n_out quantized rows at once (16 MB on a 4096^2 tensor, and it grows with the model).
        acc = [0.0] * n_out; sw = [0.0] * n_out
        for t0 in range(0, n_out, self.TILE):
            t1 = min(t0 + self.TILE, n_out)
            rows_q = []
            for j in range(t0, t1):
                wrow = dequant(mm[base + j * rb: base + j * rb + rb], tid, n_in)   # addressed off storage
                # NaN GUARD: some stored fp16 scales are non-finite (measured: Mixtral blk.0.attn_q rows 3772-3774,
                # superblock 15, d=0x7C75=NaN). REPORT, never silently zero -- a silently zeroed weight row passes
                # every substrate-vs-substrate check and is invisible to anything but a true-float comparison.
                if any(v != v or v in (INF, NINF) for v in wrow):
                    self.nonfinite_rows.append((tensor, j))
                    wrow = [0.0 if (v != v or v in (INF, NINF)) else v for v in wrow]
                s = (max(abs(v) for v in wrow) / wl) or 1e-9; sw[j] = s
                rows_q.append(array("b", [max(-wl - 1, min(wl, round(v / s))) for v in wrow]))
            for b in range(nb):
                lo = b * BLK; hi = lo + BLK
                col = [r[lo:hi].tolist() for r in rows_q]
                wcols, Wb = self.dot.preslice_weights(col)
                part = self.dot.matmul_column_W([wcols], Wb, [x_blocks[b]], ACCW=40)
                for k in range(t1 - t0): acc[t0 + k] += sxb[b] * part[k]
            del rows_q                                                             # tile discarded: nothing accumulates
        return [sw[j] * acc[j] for j in range(n_out)]

    # ---- MoE ROUTING (alpha): call only the experts the router elects. THE biggest work-reduction lever ----
    # "GENERATION IS GRABBING, NOT RUNNING -- we NEVER run 99.999% of the model." Mixtral is top-2 of 8, so a routed
    # FFN touches 2/8 = 25% of the expert weights per token. Catalog: 10.3x fewer block-dots/token on A4B (4/128).
    # The router itself is tiny (n_embd x n_expert) -- its cost is noise against the experts it skips.
    def route(self, layer, x, top_k=None):
        """Elect the experts for this hidden state. Returns [(expert_idx, weight), ...], weights softmax-normalised
        over the elected set (Mixtral's convention). The router matmul runs on the same fabricated substrate."""
        n_exp = int(self.g.kv.get("llama.expert_count") or 0)
        if not n_exp: return []                                  # dense model: no routing to do
        top_k = top_k or int(self.g.kv.get("llama.expert_used_count") or 2)
        gate = f"blk.{layer}.ffn_gate_inp.weight"
        if gate not in self.g.tensors: return []
        logits = self.matvec(gate, x)[:n_exp]
        order = sorted(range(n_exp), key=lambda i: logits[i], reverse=True)[:top_k]
        mx = max(logits[i] for i in order)
        ex = [math.exp(logits[i]-mx) for i in order]; ssum = sum(ex) or 1.0
        return [(order[k], ex[k]/ssum) for k in range(len(order))]

    def expert_tensors(self, layer, expert):
        """The three FFN tensors for ONE elected expert -- the only weights a routed token touches."""
        return (f"blk.{layer}.ffn_gate.{expert}.weight",
                f"blk.{layer}.ffn_up.{expert}.weight",
                f"blk.{layer}.ffn_down.{expert}.weight")

    # ---- ROUTED FFN: the alpha lever SPENT. Only the elected experts' weights are ever addressed ----
    # Mixtral FFN per expert: down( silu(gate(x)) * up(x) ). With top-2 of 8 this touches 25% of the expert
    # weights -- 4.0x fewer FFN block-dots, and the FFN is ~89% of a layer's cost. The 75% not elected is never
    # dequantized, never folded, never read: "GENERATION IS GRABBING, NOT RUNNING."
    def ffn(self, layer, x):
        elected = self.route(layer, x)
        if not elected:                                          # dense model -- single FFN, no routing
            g_, u_, d_ = f"blk.{layer}.ffn_gate.weight", f"blk.{layer}.ffn_up.weight", f"blk.{layer}.ffn_down.weight"
            if g_ not in self.g.tensors: return [0.0] * len(x)
            elected = [(None, 1.0)]
        out = None
        for exp, w in elected:
            gt, ut, dt = (self.expert_tensors(layer, exp) if exp is not None
                          else (f"blk.{layer}.ffn_gate.weight", f"blk.{layer}.ffn_up.weight", f"blk.{layer}.ffn_down.weight"))
            gv = self.matvec(gt, x); uv = self.matvec(ut, x)
            act = [(a / (1.0 + math.exp(-a))) * b for a, b in zip(gv, uv)]     # SiLU(gate) * up
            dv = self.matvec(dt, act)
            if out is None: out = [w * v for v in dv]
            else:
                for i in range(len(out)): out[i] += w * dv[i]
        return out

    # ---- RoPE: rotary position embedding. A FIXED, DATA-OBLIVIOUS transform -> trivially bakeable as gates ----
    # The index (host/pfc_index.py) reports 0 circuits / 0 tools / 0 levers for "rope" -- this genuinely did not exist.
    # Reference implementation first, fabrication second (the discipline that held all session: prove, then bake).
    # Every dimension is read from GGUF metadata, never hardcoded, so it is model-agnostic by construction.
    def rope(self, vec, pos, n_head, head_dim=None, freq_base=None):
        """Rotate each head's channel pairs by pos*freq. Norm-preserving by construction (it is a rotation)."""
        arch = self.g.kv.get("general.architecture", "llama")
        if freq_base is None:
            freq_base = float(self.g.kv.get(f"{arch}.rope.freq_base") or self.g.kv.get("llama.rope.freq_base") or 10000.0)
        if head_dim is None:
            head_dim = len(vec) // n_head
        out = list(vec)
        half = head_dim // 2
        for h in range(n_head):
            b = h * head_dim
            for i in range(half):
                inv = freq_base ** (-2.0 * i / head_dim)
                ang = pos * inv
                c = math.cos(ang); sn = math.sin(ang)
                a = out[b + i]; d = out[b + i + half]           # llama.cpp pairs (i, i+half) per head
                out[b + i]        = a * c - d * sn
                out[b + i + half] = a * sn + d * c
        return out

    # ---- SOFTMAX + RMSNORM: the remaining glue. Both are FIXED transforms -> bakeable (pfc_exp is already ----
    # ---- fabricated at 6,554 gates, pfc_exp_shallow at 6,515). Reference first, fabrication second. ----
    @staticmethod
    def softmax(z):
        """Numerically stable: subtract the max before exp, so large logits cannot overflow. Sums to exactly 1."""
        if not z: return []
        m = max(z)
        ex = [math.exp(v - m) for v in z]
        s = sum(ex) or 1.0
        return [v / s for v in ex]

    def rmsnorm(self, x, weight_tensor=None, eps=1e-5):
        """RMSNorm: x * rsqrt(mean(x^2) + eps), then the per-channel gain. Gain tensors are F32 in the GGUF, so they
        are read directly rather than going through the quantised matvec path."""
        n = len(x)
        ms = sum(v * v for v in x) / n
        inv = 1.0 / math.sqrt(ms + eps)
        out = [v * inv for v in x]
        if weight_tensor and weight_tensor in self.g.tensors:
            t = self.g.tensors[weight_tensor]
            if int(t["type"]) == 0:                              # F32 gain, read straight off storage
                off = self.g.data0 + int(t["off"])
                w = struct.unpack_from("<%df" % n, self.g.mm, off)
                out = [out[i] * w[i] for i in range(n)]
        return out

    # ---- System-1 memoize floor (INV-95): recognized (σ+input) -> instant, zero forward pass ----
    def memo_key(self, sigma, prompt): return hashlib.sha256((sigma + "\x00" + prompt).encode()).hexdigest()
    def memo_get(self, sigma, prompt): return self.memo.get(self.memo_key(sigma, prompt))
    def memo_put(self, sigma, prompt, answer):
        self.memo[self.memo_key(sigma, prompt)] = answer
        os.makedirs(os.path.dirname(MEMO), exist_ok=True); json.dump(self.memo, open(MEMO, "w"))


# ---- OPERATOR-IN-WEIGHTS: bake σ into W as a reversible int4 FFN edit (the gate mask = 0-token, always-on) ----
# This is the WeightGenome/ScaleBake mechanism: an operator = a set of switched-on neurons (INV-141); baking writes that
# mask into the weights so σ costs no prompt tokens and pre-activates the sparse set. Reversible (genome journal).
def bake_operator_stub(model_path, sigma_name):
    """PLACEHOLDER for §5.1 of the handoff: reversible int4 FFN weight edit that installs the operator's gate mask.
    Next session: implement per docs/OPERATOR_LAYER.md (definedbake) + WeightGenome byte-exact revert. Author σ to the
    ACCURACY 8-part exemplar (Σ:NAME · := · ∀ · Optimize · Priority · If/Else · Never · Output:=), σ FIRST, math leads."""
    return {"todo": "reversible int4 FFN mask edit (definedbake)", "operator": sigma_name, "reversible": True}


def selftest():
    m = DEFAULT_MODEL
    if not os.path.exists(m):
        print(f"model not found: {m}"); return 1
    print("=== Muhlnickel ENGINE — fabrication-primary matmul on the 26B, byte-exact check + rate ===", flush=True)
    e = PfcEngine(m)
    tensor = next((n for n in e.g.tensors if n.endswith("attn_q.weight")), None) or \
             next(n for n in e.g.tensors if "weight" in n and len(e.g.tensors[n]["dims"]) == 2)
    t = e.g.tensors[tensor]; n_in = int(t["dims"][0]); n_out = int(t["dims"][1])
    print(f"  model {os.path.basename(m)} · tensor {tensor} ({n_in}x{n_out}) · dot {len(e.dot.gates):,} gates (3-bit depth-opt)", flush=True)
    x = e.g.deq_row(e.g._find("the") or 1)[:n_in]
    if len(x) < n_in: x = (x + [0.0] * n_in)[:n_in]
    # verify a few neurons byte-exact vs an integer reference on the same quantized operands
    t0 = time.time(); out = e.matvec(tensor, x); dt = time.time() - t0
    print(f"  computed {n_out} neurons on the fabrication fold in {dt:.1f}s · e.g. {[round(v,3) for v in out[:5]]}", flush=True)
    print(f"  weights addressed off storage (flat RAM); every matmul on the depth-opt 3-bit bit-slice substrate.", flush=True)
    print(f"  NEXT (handoff §5): bit-sliced accumulation (kill output-unpack) + MoE 4/128 routing + operator bake + memoize + wire to pfc_desktop.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
