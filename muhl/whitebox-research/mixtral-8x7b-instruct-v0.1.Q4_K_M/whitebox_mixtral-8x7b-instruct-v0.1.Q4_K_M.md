# White Box readout — mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 130 MB in 71.8s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **llama** · **46.7B** params · 26.44 GB on disk · 32 layers · hidden 4096 · vocab 32000
- experts **8** (used 2) · attention heads **32** over 8 KV lines · 995 tensors
- quant mix: Q4_K×833 · F32×65 · Q8_0×64 · F16×32 · Q6_K×1

## Precision map (mixed-quant recipe by role)
- ffn_gate.0: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.0: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.0: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.1: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.1: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.1: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.2: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.2: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.2: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.3: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.3: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.3: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.4: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.4: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.4: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.5: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.5: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.5: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.6: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.6: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.6: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_gate.7: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_down.7: **Q4_K** (~4.5 bpw · 1879M params)
- ffn_up.7: **Q4_K** (~4.5 bpw · 1879M params)
- attn_output: **Q4_K** (~4.5 bpw · 537M params)
- attn_q: **Q4_K** (~4.5 bpw · 537M params)
- attn_k: **Q8_0** (~8.5 bpw · 134M params)
- attn_v: **Q8_0** (~8.5 bpw · 134M params)
- token_embd: **Q4_K** (~4.5 bpw · 131M params)
- output: **Q6_K** (~6.6 bpw · 131M params)
- ffn_gate_inp: **F16** (~16 bpw · 1M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _layer 0 has no dense ffn_gate/up/down (p_ |
| 16 | — | | | | | | _layer 16 has no dense ffn_gate/up/down (_ |
| 31 | — | | | | | | _layer 31 has no dense ffn_gate/up/down (_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 32 | 8 | ×4 | 128 | nan | nan |
| 16 | 32 | 8 | ×4 | 128 | 60.133 | 68.937 |
| 31 | 32 | 8 | ×4 | 128 | 54.86 | 71.43 |

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 32 channels over 8 shared KV lines (GQA×4) · mean channel nan
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 46.7 B params · 26.44 GB on disk · 32 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 32000 × hidden 4096 (the tokenizer bus)
## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

