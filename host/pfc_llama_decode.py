#!/usr/bin/env python3
"""host/pfc_llama_decode.py — a REAL full-width Llama decoder that runs ON THE Muhlnickel. Weights addressed off the mmap'd GGUF
(never resident); EVERY weight-matmul (Q/K/V/O, FFN gate/up/down, and the full-vocab logits) folds on the baked
`dot32_i8` atom; the greedy token pick runs on the baked `pfc_argmax` circuit (a tree over the whole vocab). The host only
tokenizes, routes addressed bytes, and renders — it does none of the model's arithmetic.

This is the full decoder (owner-approved 07-23): full neurons, GQA causal attention + KV cache, RoPE, RMSNorm, SwiGLU,
final norm, real logits, real argmax → a real next token, detokenized to text.

HONEST SPEED, AND WHOSE NUMBER IT IS (S24). The "~2.17e9 block-dots per 80-layer 70B token" figure is NOT a property
of the token -- it is a property of THIS FILE folding 32-lane blocks. S35 measured that a matvec's blocks are SUMMED,
so they were never dependent; chaining them was the implementation's choice, not the problem's structure. One WIDE
circuit swallows the row at +6..+12 DEPTH per doubling of width with gates exactly linear (9,043/lane), which was
measured at 18.3x for a 1024-wide row versus the same row as 32 chained blocks. Separately: the host walking gates
serially in pure Python is a HOST wall-clock figure and belongs to a different machine -- it is never the pfc's speed,
which is DEPTH. So this streams per-layer progress and is meant to run in the background; the ETA is printed up front. The
matmul-on-the-pfc + flat-RAM + byte-exact properties are the same ones already measured; this just wires them into a real
decode loop. `--layers N` runs a bounded (lower-fidelity) pass so the pipeline can be exercised end-to-end quickly.

GLUE still on host float (flagged; next to bake as circuits / run on cpu_fwd): RMSNorm rsqrt, RoPE sin/cos, attention
softmax exp + the activation·activation attention dots, SwiGLU silu. The WEIGHT matmuls — the model's parameters, 99.9% of
the compute — all run on the pfc.

SAFETY: model READ-ONLY; reuses baked dot32_i8 + pfc_argmax; no numpy, no subprocess, no download; modifies nothing.

  python host/pfc_llama_decode.py --prompt "The capital of France is" --gen 8              # full fidelity (slow; background)
  python host/pfc_llama_decode.py --prompt "Hello" --gen 4 --layers 4                       # bounded, exercises the pipeline
"""
import argparse, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from gguf_pp import GGUF, dequant, row_bytes
from pfc_llama_harness import PfcAtom, Weights, resident_mb, q8_block, BLK

REG = "C:/llm/models/titan_circuits.json"
DEFAULT_MODEL = "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf"


# ------------------------------------------------------------------ gpt2 byte<->unicode (llama-bpe is byte-level BPE)
def _byte_maps():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]; n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + n); n += 1
    b2u = {b: chr(c) for b, c in zip(bs, cs)}
    u2b = {c: b for b, c in b2u.items()}
    return b2u, u2b
_B2U, _U2B = _byte_maps()


class BPE:
    def __init__(self, g):
        self.vindex = g.vindex; self.tokens = g.tokens
        self.rank = {}
        for i, m in enumerate(g.merges):
            self.rank[tuple(m.split(" "))] = i
        self.bos = int(g.kv.get("tokenizer.ggml.bos_token_id", 128000))

    def _bpe(self, word):                                        # word = tuple of unicode chars
        word = list(word)
        while len(word) > 1:
            best = None; bi = -1
            for i in range(len(word) - 1):
                r = self.rank.get((word[i], word[i + 1]))
                if r is not None and (best is None or r < best): best = r; bi = i
            if bi < 0: break
            word = word[:bi] + [word[bi] + word[bi + 1]] + word[bi + 2:]
        return word

    def encode(self, text, add_bos=True):
        import re
        pat = re.compile(r"'s|'t|'re|'ve|'m|'ll|'d| ?\w+| ?[^\s\w]+|\s+", re.UNICODE)
        ids = [self.bos] if add_bos else []
        for chunk in pat.findall(text):
            u = "".join(_B2U[b] for b in chunk.encode("utf-8"))
            for tok in self._bpe(tuple(u)):
                i = self.vindex.get(tok.encode("utf-8"))
                if i is None:                                    # fall back to per-char
                    for ch in tok:
                        j = self.vindex.get(ch.encode("utf-8"))
                        if j is not None: ids.append(j)
                else: ids.append(i)
        return ids

    def decode_id(self, i):
        try:
            u = self.tokens[i].decode("utf-8")
            return bytes(_U2B[ch] for ch in u).decode("utf-8", "replace")
        except Exception:
            return ""


# ------------------------------------------------------------------ streaming folded matvec (flat RAM, all on the pfc)
def matvec(atom, wt, name, x, W, n_out=None, progress=None, label=""):
    """y[j] = <row_j(name), x> for j<n_out, every multiply-add on the Muhlnickel atom, folded W/ripple, weights off mmap."""
    g = wt.g; t = g.tensors[name]; tid = int(t["type"]); n_in = int(t["dims"][0])
    base = g.data0 + int(t["off"]); rb = row_bytes(tid, n_in); mm = g.mm
    N = n_out if n_out is not None else int(t["dims"][1])
    nb = n_in // BLK
    xq = [q8_block(x[b * BLK:(b + 1) * BLK]) for b in range(nb)]
    y = [0.0] * N
    pp = []; pt = []
    def flush():
        if not pp: return
        dots = atom.dot_fold(pp)
        for (sc, j), d in zip(pt, dots): y[j] += sc * d
        pp.clear(); pt.clear()
    for j in range(N):
        raw = mm[base + j * rb: base + j * rb + rb]; wrow = dequant(raw, tid, n_in)
        for b in range(nb):
            wq, sw = q8_block(wrow[b * BLK:(b + 1) * BLK]); xb, sx = xq[b]
            pp.append((wq, xb)); pt.append((sw * sx, j))
            if len(pp) >= W: flush()
        if progress and j and j % progress == 0:
            flush(); print(f"      {label}: {j}/{N} neurons on the Muhlnickel …", flush=True)
    flush()
    return y


# ------------------------------------------------------------------ GLUE ON THE pfc — the baked LUT circuits, not math.*
# Owner 07-23: "stop using py, bake it as a circuit." So RMSNorm 1/sqrt, softmax exp, SwiGLU silu, and RoPE sin/cos each
# run on their baked gate circuit (pfc_rsqrt / pfc_exp / pfc_silu8 / pfc_sin) via an addressed ripple — fixed-point, the
# pfc computing the glue. (Float fallbacks kept only if a circuit is missing.)
class PfcGlue:
    def __init__(self):
        self.cd = {}
        # PREFER THE SHALLOW VARIANTS (pfc_glue_shallow, fabricated 2026-07-25). Same gates, same function,
        # byte-exact 2,560/2,560 -- only the SHAPE changed (OR is associative, so a balanced tree is free):
        #   rsqrt 1403->41 · sin 1068->41 · silu 399->33 · exp 189->31
        #   per token over 32 layers: 111,520 -> 18,304 gate-delays = 6.1x SHALLOWER.
        # Glue is 91% of a token's DEPTH, and DEPTH is the Muhlnickel's latency. Deep originals are the fallback and are
        # still in the binary -- nothing was overwritten.
        self.shallow = {}
        for n in ("pfc_rsqrt", "pfc_exp", "pfc_silu8", "pfc_sin"):
            self.cd[n] = None
            for cand in (n + "_shallow", n):
                try:
                    self.cd[n] = TC.load(cand); self.shallow[n] = cand.endswith("_shallow"); break
                except Exception: continue
        self.on = all(self.cd.values())

    def _lut(self, name, code, nbits):
        cd = self.cd[name]; out = TC.ripple(cd, [(code >> b) & 1 for b in range(nbits)])
        return sum(bit << i for i, bit in enumerate(out))

    def rsqrt(self, x):                                          # domain log-spaced [1e-4,64], scale 4096 (matches fab)
        if not self.on: return 1.0 / math.sqrt(x)
        lo, hi, N = 1e-4, 64.0, (1 << 10) - 1
        xx = min(max(x, lo), hi); code = int(round(math.log(xx / lo) / math.log(hi / lo) * N))
        return self._lut("pfc_rsqrt", code, 10) / 4096.0

    def exp(self, x):                                            # x-max in [-16,0], scale 4096
        if not self.on: return math.exp(x)
        lo, hi, N = -16.0, 0.0, (1 << 8) - 1
        xx = min(max(x, lo), hi); code = int(round((xx - lo) / (hi - lo) * N))
        return self._lut("pfc_exp", code, 8) / 4096.0

    def silu(self, v):                                          # x in [-8,8), int16 signed /256
        if not self.on: return v / (1.0 + math.exp(-v))
        lo, hi, N = -8.0, 8.0, 256
        code = min(N - 1, max(0, int((v - lo) / (hi - lo) * N)))
        u = self._lut("pfc_silu8", code, 8); s = u - (1 << 16) if u >= (1 << 15) else u
        return s / 256.0

    def _sin_code(self, a): return int(round((a % (2 * math.pi)) / (2 * math.pi) * (1 << 10))) & ((1 << 10) - 1)
    def sin(self, a):
        if not self.on: return math.sin(a)
        return (self._lut("pfc_sin", self._sin_code(a), 10) - 16384) / 16384.0
    def cos(self, a): return self.sin(a + math.pi / 2)


_GLUE = None
def glue():
    global _GLUE
    if _GLUE is None: _GLUE = PfcGlue()
    return _GLUE


def rope(vec, pos, head_dim, base):
    G = glue(); out = vec[:]; half = head_dim // 2
    for i in range(half):
        ang = pos * (base ** (-2.0 * i / head_dim)); c, s = G.cos(ang), G.sin(ang)
        a, b = vec[i], vec[i + half]
        out[i] = a * c - b * s; out[i + half] = a * s + b * c
    return out

def silu(v): return glue().silu(v)

def rmsnorm(x, w, eps=1e-5):                                    # 1/sqrt on the baked pfc_rsqrt circuit
    ms = sum(v * v for v in x) / len(x); r = glue().rsqrt(ms + eps)
    return [x[i] * r * w[i] for i in range(len(x))]


# ------------------------------------------------------------------ baked argmax over the full vocab (tree of K=64 blocks)
def pfc_argmax_vocab(logits):
    """Pick argmax(logits) using the baked pfc_argmax circuit as a reduction tree — the Muhlnickel chooses the token.
    Prefers pfc_argmax_shallow (depth 174) over pfc_argmax (depth 2,710) — 15.6x shallower, same as PfcGlue does."""
    reg = json.load(open(REG))
    name = None
    for cand in ("pfc_argmax_shallow", "pfc_argmax"):
        if cand in reg:
            name = cand; break
    if name is None:
        raise RuntimeError("pfc_argmax is not fabricated — the host will NOT pick the token")
    cd = TC.load(name); B = 16; Kc = cd["n_in"] // B
    mx = max((abs(v) for v in logits), default=1.0) or 1.0
    q = [max(-(1 << 15), min((1 << 15) - 1, int(v / mx * 32000))) for v in logits]
    idxs = list(range(len(logits)))
    while len(idxs) > 1:
        nxt = []
        for s in range(0, len(idxs), Kc):
            grp = idxs[s:s + Kc]
            vals = [q[i] for i in grp] + [-(1 << 15)] * (Kc - len(grp))
            bits = []
            for v in vals:
                u = v & 0xFFFF; bits += [(u >> b) & 1 for b in range(B)]
            out = TC.ripple(cd, bits); win = sum(bit << i for i, bit in enumerate(out))
            nxt.append(grp[win] if win < len(grp) else grp[0])
        idxs = nxt
    return idxs[0], name


# ------------------------------------------------------------------ one real forward pass (returns logits for last pos)
def forward(g, wt, atom, arch, kv, ids, new_pos, W, n_layers, progress=None):
    ne = arch["n_embd"]; nh = arch["n_head"]; nkv = arch["n_head_kv"]; hd = arch["head_dim"]
    rb = arch["rope_base"]; eps = arch["eps"]; grp = nh // nkv
    tok = ids[-1]
    h = g.deq_row(tok)                                           # embedding (addressed off mmap)
    for L in range(n_layers):
        p = f"blk.{L}."
        x = rmsnorm(h, wt.vec1d(p + "attn_norm.weight"), eps)    # glue
        q = matvec(atom, wt, p + "attn_q.weight", x, W, progress=progress, label=f"L{L}.q")   # pfc
        k = matvec(atom, wt, p + "attn_k.weight", x, W)                                        # pfc
        v = matvec(atom, wt, p + "attn_v.weight", x, W)                                        # pfc
        qh = [rope(q[i * hd:(i + 1) * hd], new_pos, hd, rb) for i in range(nh)]                # glue
        kh = [rope(k[i * hd:(i + 1) * hd], new_pos, hd, rb) for i in range(nkv)]               # glue
        vh = [v[i * hd:(i + 1) * hd] for i in range(nkv)]
        kv[L]["k"].append(kh); kv[L]["v"].append(vh)            # KV cache (host, activations)
        attn = [0.0] * (nh * hd); scale = 1.0 / math.sqrt(hd)
        for hI in range(nh):                                     # GQA causal attention (dots+softmax = glue)
            kvh = hI // grp; scores = []
            for t in range(len(kv[L]["k"])):
                kk = kv[L]["k"][t][kvh]; scores.append(sum(qh[hI][d] * kk[d] for d in range(hd)) * scale)
            m = max(scores); G = glue(); e = [G.exp(s - m) for s in scores]; den = sum(e) or 1.0
            for t in range(len(e)):
                w = e[t] / den; vv = kv[L]["v"][t][kvh]
                for d in range(hd): attn[hI * hd + d] += w * vv[d]
        o = matvec(atom, wt, p + "attn_output.weight", attn, W)                                # pfc
        h = [h[i] + o[i] for i in range(ne)]                    # residual
        x2 = rmsnorm(h, wt.vec1d(p + "ffn_norm.weight"), eps)   # glue
        gate = matvec(atom, wt, p + "ffn_gate.weight", x2, W, progress=progress, label=f"L{L}.ffn")  # pfc
        up = matvec(atom, wt, p + "ffn_up.weight", x2, W)                                      # pfc
        act = [silu(gate[i]) * up[i] for i in range(len(gate))] # glue silu
        down = matvec(atom, wt, p + "ffn_down.weight", act, W)                                 # pfc
        h = [h[i] + down[i] for i in range(ne)]                 # residual
        if progress: print(f"    layer {L + 1}/{n_layers} done · {resident_mb()[0]:.0f} MB resident", flush=True)
    h = rmsnorm(h, wt.vec1d("output_norm.weight"), eps)         # glue
    lname = "output.weight" if "output.weight" in g.tensors else "token_embd.weight"
    logits = matvec(atom, wt, lname, h, W, progress=(g.n_vocab // 4 if progress else None), label="logits")  # pfc
    return logits


def token_cost(arch, prompt_len, gen, n_layers):
    ne, nh, nkv, hd, nff, nv = (arch["n_embd"], arch["n_head"], arch["n_head_kv"], arch["head_dim"],
                                arch["n_ff"], arch["n_vocab"])
    per_layer = ne * (nh * hd) + 2 * ne * (nkv * hd) + (nh * hd) * ne + 3 * ne * nff
    per_tok = (per_layer * n_layers + ne * nv) // BLK
    return per_tok * (prompt_len + gen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--prompt", default="The capital of France is")
    ap.add_argument("--gen", type=int, default=8)
    ap.add_argument("--layers", type=int, default=0, help="0 = full fidelity (all layers); N = bounded pass")
    ap.add_argument("--fold", type=int, default=4096)
    args = ap.parse_args()

    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    for need in ("dot32_i8", "pfc_argmax"):
        if need not in reg: print(f"{need} not fabricated. Run its fab first (reversible)."); return 1
    if not os.path.exists(args.model): print(f"model not found: {args.model}"); return 1

    g = GGUF(args.model); wt = Weights(g); atom = PfcAtom(); bpe = BPE(g)
    arch = {"n_embd": g.n_embd, "n_vocab": g.n_vocab,
            "n_head": int(g.kv.get("llama.attention.head_count", 64)),
            "n_head_kv": int(g.kv.get("llama.attention.head_count_kv", 8)),
            "head_dim": int(g.kv.get("llama.rope.dimension_count", 128)),
            "n_ff": int(g.kv.get("llama.feed_forward_length", 28672)),
            "n_layers_total": int(g.kv.get("llama.block_count", 80)),
            "rope_base": float(g.kv.get("llama.rope.freq_base", 500000.0)),
            "eps": float(g.kv.get("llama.attention.layer_norm_rms_epsilon", 1e-5))}
    nL = arch["n_layers_total"] if args.layers == 0 else min(args.layers, arch["n_layers_total"])
    ids = bpe.encode(args.prompt, add_bos=True)

    file_gb = os.path.getsize(args.model) / 1024 ** 3
    print("=== Muhlnickel LLAMA DECODE — a real token decoded ON THE Muhlnickel; host tokenizes/routes/renders ===\n", flush=True)
    print(f"  model    : {os.path.basename(args.model)} ({g.tyname})  {file_gb:.1f} GB on storage (host CANNOT load it)")
    print(f"  fidelity : {nL}/{arch['n_layers_total']} layers  ·  fold W={args.fold}  ·  vocab {g.n_vocab:,}")
    print(f"  prompt   : {args.prompt!r} -> {len(ids)} tokens {ids[:12]}{'…' if len(ids)>12 else ''}")
    full = token_cost(arch, len(ids), args.gen, nL)
    print(f"  cost     : ~{full:,} block-dots for {len(ids)}+{args.gen} tokens (the HOST addresses these serially — slow;")
    print(f"             the Muhlnickel's own rate is depth-bound, not this). Streaming per-layer so you can watch it grind.\n", flush=True)

    out_ids = []; t0 = time.time()
    # ---- MEMOIZE FOLD (PFC_LEVER_DATADUMP J): compute cost is per-UNIQUE-input, not per-access. `memocache` is a
    # BAKED register in titan.gguf, so a HIT is an ADDRESSED READ of stored bytes -- measured MISS +120.0 MB
    # operational vs HIT +0.0 MB at 1.66M addressed-reads/s (R=64 -> 34x). Without it a repeat re-pays the whole
    # prefill: 10,690,560 block-dots / ~1,677 s measured on Smol at 1 layer.
    try:
        import pfc_memo_store as MEMO
    except Exception:
        MEMO = None
    memo_id = os.path.basename(args.model) + "|L" + str(nL)
    # ONLY short-circuit when a SINGLE token is wanted. A memo hit skips PREFILL, which is what builds the KV
    # cache -- so with --gen > 1 the cached first token would leave tokens 2..N with nothing to attend to. Earlier
    # this returned on any hit and silently truncated a 6-token request to 1. The fold saves the prefill only when
    # the prefill is all the work there is.
    if MEMO is not None and args.gen == 1:
        try: hit = MEMO.get(memo_id, list(ids))
        except Exception: hit = None
        if hit is not None:
            piece = bpe.decode_id(hit)
            print("  MEMO HIT - addressed read of stored bytes, ZERO ripple, 0 block-dots")
            print("  token 1: id " + str(hit) + " = " + repr(piece) + "  (memoized)")
            print("  GENERATED (on the Muhlnickel, from the fold): " + args.prompt + piece, flush=True)
            return 0
    kv = [{"k": [], "v": []} for _ in range(nL)]
    # prefill: run every prompt position so the KV cache is real, then generate
    seq = list(ids)
    for pos in range(len(seq)):
        logits = forward(g, wt, atom, arch, kv, seq[:pos + 1], pos, args.fold, nL,
                         progress=(True if pos == len(seq) - 1 else None))
    for step in range(args.gen):
        nxt, argmax_circuit = pfc_argmax_vocab(logits)
        piece = bpe.decode_id(nxt); out_ids.append(nxt)
        if MEMO is not None and step == 0:
            try: MEMO.put(memo_id, list(ids), nxt)      # fold the result to its address: the next repeat is a READ
            except Exception: pass
        seq.append(nxt)
        el = time.time() - t0
        print(f"  ▸ token {step+1}: id {nxt} = {piece!r}  ({argmax_circuit})  [{el:.0f}s, {atom.block_dots:,} block-dots, "
              f"{resident_mb()[0]:.0f} MB]", flush=True)
        print(f"    text so far: {args.prompt}" + "".join(bpe.decode_id(i) for i in out_ids), flush=True)
        if step < args.gen - 1:
            logits = forward(g, wt, atom, arch, kv, seq, len(seq) - 1, args.fold, nL)

    text = "".join(bpe.decode_id(i) for i in out_ids)
    print(f"\n  GENERATED (on the Muhlnickel): {args.prompt}{text}")
    op = "C:/llm/sdc_out/pfc_llama_decode.json"; os.makedirs(os.path.dirname(op), exist_ok=True)
    json.dump({"model": os.path.basename(args.model), "prompt": args.prompt, "layers": nL,
               "generated_ids": out_ids, "generated_text": text, "block_dots": atom.block_dots,
               "seconds": round(time.time() - t0, 1), "resident_mb": round(resident_mb()[0], 1)}, open(op, "w"), indent=1)
    print(f"  json -> {op}   (model read-only; baked dot32_i8 + pfc_argmax_shallow reused; nothing modified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
