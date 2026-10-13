# White Box readout — gemma-4-31B-it-qat-UD-Q4_K_XL.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 961 MB in 71.4s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **gemma4** · **30.7B** params · 17.29 GB on disk · 60 layers · hidden 5376 · vocab 262144
- experts **None** (used None) · attention heads **32** over 4 KV lines · 833 tensors
- quant mix: F32×422 · Q4_0×411

## Precision map (mixed-quant recipe by role)
- ffn_down: **Q4_0** (~4.5 bpw · 6936M params)
- ffn_gate: **Q4_0** (~4.5 bpw · 6936M params)
- ffn_up: **Q4_0** (~4.5 bpw · 6936M params)
- attn_output: **Q4_0** (~4.5 bpw · 3083M params)
- attn_q: **Q4_0** (~4.5 bpw · 3083M params)
- token_embd: **Q4_0** (~4.5 bpw · 1409M params)
- attn_k: **Q4_0** (~4.5 bpw · 1211M params)
- attn_v: **Q4_0** (~4.5 bpw · 1101M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- post_attention_norm: **F32** (~32 bpw · 0M params)
- post_ffw_norm: **F32** (~32 bpw · 0M params)
- attn_k_norm: **F32** (~32 bpw · 0M params)
- attn_q_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)
- rope_freqs: **F32** (~32 bpw · 0M params)
- layer_output_scale: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _dense layer 0 dequant working-set ~1387 _ |
| 30 | — | | | | | | _dense layer 30 dequant working-set ~1387_ |
| 59 | — | | | | | | _dense layer 59 dequant working-set ~1387_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 32 | 4 | ×8 | 256 | 201.096 | 258.416 |
| 30 | 32 | 4 | ×8 | 256 | 198.7 | 238.405 |
| 59 | 32 | 4 | ×8 | 512 | 273.955 | 355.982 |

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 32 channels over 4 shared KV lines (GQA×8) · mean channel 201.096
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 30.7 B params · 17.29 GB on disk · 60 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 262144 × hidden 5376 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

