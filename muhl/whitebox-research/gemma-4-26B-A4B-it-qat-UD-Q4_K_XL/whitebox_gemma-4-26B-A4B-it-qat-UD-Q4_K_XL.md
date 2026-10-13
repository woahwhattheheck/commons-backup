# White Box readout — gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 1028 MB in 47.6s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **gemma4** · **25.23B** params · 14.25 GB on disk · 30 layers · hidden 2816 · vocab 262144
- experts **128** (used 8) · attention heads **16** over 2 KV lines · 658 tensors
- quant mix: F32×392 · Q4_0×266

## Precision map (mixed-quant recipe by role)
- ffn_gate_up_exps: **Q4_0** (~4.5 bpw · 15225M params)
- ffn_down_exps: **Q4_0** (~4.5 bpw · 7613M params)
- token_embd: **Q4_0** (~4.5 bpw · 738M params)
- attn_output: **Q4_0** (~4.5 bpw · 404M params)
- attn_q: **Q4_0** (~4.5 bpw · 404M params)
- ffn_down: **Q4_0** (~4.5 bpw · 178M params)
- ffn_gate: **Q4_0** (~4.5 bpw · 178M params)
- ffn_up: **Q4_0** (~4.5 bpw · 178M params)
- attn_k: **Q4_0** (~4.5 bpw · 159M params)
- attn_v: **Q4_0** (~4.5 bpw · 144M params)
- ffn_gate_inp: **F32** (~32 bpw · 11M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_gate_inp.scale: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- post_attention_norm: **F32** (~32 bpw · 0M params)
- post_ffw_norm: **F32** (~32 bpw · 0M params)
- post_ffw_norm_1: **F32** (~32 bpw · 0M params)
- post_ffw_norm_2: **F32** (~32 bpw · 0M params)
- pre_ffw_norm_2: **F32** (~32 bpw · 0M params)
- attn_k_norm: **F32** (~32 bpw · 0M params)
- attn_q_norm: **F32** (~32 bpw · 0M params)
- ffn_down_exps.scale: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)
- rope_freqs: **F32** (~32 bpw · 0M params)
- layer_output_scale: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | 2112 | 483 | 527 | 0 | 237 | 263 | 0.021 |
| 15 | 2112 | 367 | 372 | 0 | 610 | 611 | 0.032 |
| 29 | 2112 | 574 | 592 | 0 | 521 | 529 | 0.075 |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 16 | 2 | ×8 | 256 | 203.732 | 248.322 |
| 15 | 16 | 2 | ×8 | 256 | 183.82 | 216.498 |
| 29 | 16 | 2 | ×8 | 512 | 302.873 | 434.933 |

## Expert health (dead / collapsed experts)
- blk.0.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.017447–0.020266
- blk.1.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.018384–0.019777
- blk.2.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.017319–0.020383
- blk.3.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.017434–0.019791
- blk.4.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.01726–0.02024
- blk.5.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.018096–0.021046
- blk.6.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.016504–0.020419
- blk.7.ffn_gate_up_exps.weight: 128 experts · **0 dead** · std 0.01804–0.022081

## Computer-in-the-weights (OS-primitive map)
- **PROCESSOR / ALU (compute)** ← FFN transistors (SwiGLU gate neurons) — 2112 transistors/block · 483 amplifiers · 527 inhibitors · 0 dead
- **MEMORY (registers / RAM cells)** ← latches — drain writes where the gate reads — 237 hold cells (memory) · 263 reset · λ̄=-0.004
- **SCHEDULER / ADDRESS DECODER** ← gate projection decodes input→neuron — decoder orthogonality 0.021 (lower = sharper one-of-many select)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 16 channels over 2 shared KV lines (GQA×8) · mean channel 203.732
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 25.23 B params · 14.25 GB on disk · 30 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 262144 × hidden 2816 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

