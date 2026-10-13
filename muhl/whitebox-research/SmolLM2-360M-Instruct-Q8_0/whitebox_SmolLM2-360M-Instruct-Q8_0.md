# White Box readout — SmolLM2-360M-Instruct-Q8_0.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 8 MB in 7.7s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **llama** · **0.36B** params · 0.39 GB on disk · 32 layers · hidden 960 · vocab 49152
- experts **None** (used None) · attention heads **15** over 5 KV lines · 290 tensors
- quant mix: Q8_0×225 · F32×65

## Precision map (mixed-quant recipe by role)
- ffn_down: **Q8_0** (~8.5 bpw · 79M params)
- ffn_gate: **Q8_0** (~8.5 bpw · 79M params)
- ffn_up: **Q8_0** (~8.5 bpw · 79M params)
- token_embd: **Q8_0** (~8.5 bpw · 47M params)
- attn_output: **Q8_0** (~8.5 bpw · 29M params)
- attn_q: **Q8_0** (~8.5 bpw · 29M params)
- attn_k: **Q8_0** (~8.5 bpw · 10M params)
- attn_v: **Q8_0** (~8.5 bpw · 10M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | 2560 | 265 | 284 | 0 | 6 | 4 | 0.03 |
| 16 | 2560 | 367 | 377 | 0 | 875 | 870 | 0.03 |
| 31 | 2560 | 491 | 457 | 0 | 541 | 546 | 0.031 |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 15 | 5 | ×3 | 64 | 411.837 | 1149.82 |
| 16 | 15 | 5 | ×3 | 64 | 1821.112 | 2388.76 |
| 31 | 15 | 5 | ×3 | 64 | 1829.329 | 2423.285 |

## Computer-in-the-weights (OS-primitive map)
- **PROCESSOR / ALU (compute)** ← FFN transistors (SwiGLU gate neurons) — 2560 transistors/block · 265 amplifiers · 284 inhibitors · 0 dead
- **MEMORY (registers / RAM cells)** ← latches — drain writes where the gate reads — 6 hold cells (memory) · 4 reset · λ̄=-0.0
- **SCHEDULER / ADDRESS DECODER** ← gate projection decodes input→neuron — decoder orthogonality 0.03 (lower = sharper one-of-many select)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 15 channels over 5 shared KV lines (GQA×3) · mean channel 411.837
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 0.36 B params · 0.39 GB on disk · 32 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 49152 × hidden 960 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

