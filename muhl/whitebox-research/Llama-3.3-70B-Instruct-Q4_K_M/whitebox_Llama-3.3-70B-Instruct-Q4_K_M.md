# White Box readout — Llama-3.3-70B-Instruct-Q4_K_M.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 872 MB in 70.9s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **llama** · **70.55B** params · 42.52 GB on disk · 80 layers · hidden 8192 · vocab 128256
- experts **None** (used None) · attention heads **64** over 8 KV lines · 724 tensors
- quant mix: Q4_K×441 · F32×162 · Q6_K×81 · Q5_K×40

## Precision map (mixed-quant recipe by role)
- ffn_down: **Q6_K** (~6.6 bpw · 18790M params)
- ffn_gate: **Q4_K** (~4.5 bpw · 18790M params)
- ffn_up: **Q4_K** (~4.5 bpw · 18790M params)
- attn_output: **Q4_K** (~4.5 bpw · 5369M params)
- attn_q: **Q4_K** (~4.5 bpw · 5369M params)
- output: **Q6_K** (~6.6 bpw · 1051M params)
- token_embd: **Q4_K** (~4.5 bpw · 1051M params)
- attn_k: **Q4_K** (~4.5 bpw · 671M params)
- attn_v: **Q6_K** (~6.6 bpw · 671M params)
- attn_norm: **F32** (~32 bpw · 1M params)
- ffn_norm: **F32** (~32 bpw · 1M params)
- output_norm: **F32** (~32 bpw · 0M params)
- rope_freqs: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _dense layer 0 dequant working-set ~2819 _ |
| 40 | — | | | | | | _dense layer 40 dequant working-set ~2819_ |
| 79 | — | | | | | | _dense layer 79 dequant working-set ~2819_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 64 | 8 | ×8 | 128 | 542.464 | 3027.276 |
| 40 | 64 | 8 | ×8 | 128 | 165.136 | 291.945 |
| 79 | 64 | 8 | ×8 | 128 | 150.574 | 338.6 |

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 64 channels over 8 shared KV lines (GQA×8) · mean channel 542.464
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 70.55 B params · 42.52 GB on disk · 80 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 128256 × hidden 8192 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

