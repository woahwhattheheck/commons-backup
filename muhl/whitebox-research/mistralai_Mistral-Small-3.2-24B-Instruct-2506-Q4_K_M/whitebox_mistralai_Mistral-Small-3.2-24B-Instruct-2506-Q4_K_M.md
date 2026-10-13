# White Box readout — mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 632 MB in 36.6s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **llama** · **23.57B** params · 14.33 GB on disk · 40 layers · hidden 5120 · vocab 131072
- experts **None** (used None) · attention heads **32** over 8 KV lines · 363 tensors
- quant mix: Q4_K×241 · F32×81 · Q6_K×41

## Precision map (mixed-quant recipe by role)
- ffn_down: **Q6_K** (~6.6 bpw · 6711M params)
- ffn_gate: **Q4_K** (~4.5 bpw · 6711M params)
- ffn_up: **Q4_K** (~4.5 bpw · 6711M params)
- attn_output: **Q4_K** (~4.5 bpw · 839M params)
- attn_q: **Q4_K** (~4.5 bpw · 839M params)
- output: **Q6_K** (~6.6 bpw · 671M params)
- token_embd: **Q4_K** (~4.5 bpw · 671M params)
- attn_k: **Q4_K** (~4.5 bpw · 210M params)
- attn_v: **Q6_K** (~6.6 bpw · 210M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _dense layer 0 dequant working-set ~2013 _ |
| 20 | — | | | | | | _dense layer 20 dequant working-set ~2013_ |
| 39 | — | | | | | | _dense layer 39 dequant working-set ~2013_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 32 | 8 | ×4 | 128 | 8.804 | 25.496 |
| 20 | 32 | 8 | ×4 | 128 | 8.265 | 10.45 |
| 39 | 32 | 8 | ×4 | 128 | 10.924 | 18.427 |

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 32 channels over 8 shared KV lines (GQA×4) · mean channel 8.804
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 23.57 B params · 14.33 GB on disk · 40 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 131072 × hidden 5120 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

