# White Box readout — phi-4-Q4_K_M.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 1 MB in 11.8s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **phi3** · **14.66B** params · 9.05 GB on disk · 40 layers · hidden 5120 · vocab 100352
- experts **None** (used None) · attention heads **40** over 10 KV lines · 243 tensors
- quant mix: Q4_K×101 · F32×81 · Q5_K×40 · Q6_K×21

## Precision map (mixed-quant recipe by role)
- ffn_up: **Q4_K** (~4.5 bpw · 7340M params)
- ffn_down: **Q6_K** (~6.6 bpw · 3670M params)
- attn_qkv: **Q5_K** (~5.5 bpw · 1573M params)
- attn_output: **Q4_K** (~4.5 bpw · 1049M params)
- output: **Q6_K** (~6.6 bpw · 514M params)
- token_embd: **Q4_K** (~4.5 bpw · 514M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _layer 0 has no dense ffn_gate/up/down (p_ |
| 20 | — | | | | | | _layer 20 has no dense ffn_gate/up/down (_ |
| 39 | — | | | | | | _layer 39 has no dense ffn_gate/up/down (_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|

## Computer-in-the-weights (OS-primitive map)
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 14.66 B params · 9.05 GB on disk · 40 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 100352 × hidden 5120 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

