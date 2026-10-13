# White Box readout — google_gemma-3-27b-it-Q4_K_M.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 408 MB in 42.2s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **gemma3** · **27.01B** params · 16.55 GB on disk · 62 layers · hidden 5376 · vocab 262144
- experts **None** (used None) · attention heads **32** over 16 KV lines · 808 tensors
- quant mix: Q4_K×374 · F32×373 · Q6_K×61

## Precision map (mixed-quant recipe by role)
- ffn_down: **Q4_K** (~4.5 bpw · 7168M params)
- ffn_gate: **Q4_K** (~4.5 bpw · 7168M params)
- ffn_up: **Q4_K** (~4.5 bpw · 7168M params)
- token_embd: **Q6_K** (~6.6 bpw · 1409M params)
- attn_output: **Q4_K** (~4.5 bpw · 1365M params)
- attn_q: **Q4_K** (~4.5 bpw · 1365M params)
- attn_k: **Q4_K** (~4.5 bpw · 683M params)
- attn_v: **Q4_K** (~4.5 bpw · 683M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- post_attention_norm: **F32** (~32 bpw · 0M params)
- post_ffw_norm: **F32** (~32 bpw · 0M params)
- attn_k_norm: **F32** (~32 bpw · 0M params)
- attn_q_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _dense layer 0 dequant working-set ~1387 _ |
| 31 | — | | | | | | _dense layer 31 dequant working-set ~1387_ |
| 61 | — | | | | | | _dense layer 61 dequant working-set ~1387_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 32 | 16 | ×2 | 128 | 85.033 | 90.934 |
| 31 | 32 | 16 | ×2 | 128 | 60.255 | 77.788 |
| 61 | 32 | 16 | ×2 | 128 | 61.633 | 81.848 |

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 32 channels over 16 shared KV lines (GQA×2) · mean channel 85.033
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 27.01 B params · 16.55 GB on disk · 62 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 262144 × hidden 5376 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

