# White Box readout — pfc_mix.gguf

> Read from stored bits, **no inference, no model load**. system free-RAM drop 520 MB in 61.1s (Titan addressed via mmap; the rest is the Python skin + bounded windows).

## Structure
- arch **llama** · **4.61B** params · 4.53 GB on disk · 12 layers · hidden 5120 · vocab 100352
- experts **6** (used 2) · attention heads **40** over 8 KV lines · 303 tensors
- quant mix: Q8_0×276 · F32×25 · Q4_K×1 · Q6_K×1

## Precision map (mixed-quant recipe by role)
- token_embd: **Q4_K** (~4.5 bpw · 514M params)
- output: **Q6_K** (~6.6 bpw · 514M params)
- attn_q: **Q8_0** (~8.5 bpw · 315M params)
- attn_output: **Q8_0** (~8.5 bpw · 315M params)
- ffn_gate.0: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.0: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.0: **Q8_0** (~8.5 bpw · 157M params)
- ffn_gate.1: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.1: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.1: **Q8_0** (~8.5 bpw · 157M params)
- ffn_gate.2: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.2: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.2: **Q8_0** (~8.5 bpw · 157M params)
- ffn_gate.3: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.3: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.3: **Q8_0** (~8.5 bpw · 157M params)
- ffn_gate.4: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.4: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.4: **Q8_0** (~8.5 bpw · 157M params)
- ffn_gate.5: **Q8_0** (~8.5 bpw · 157M params)
- ffn_up.5: **Q8_0** (~8.5 bpw · 157M params)
- ffn_down.5: **Q8_0** (~8.5 bpw · 157M params)
- attn_k: **Q8_0** (~8.5 bpw · 63M params)
- attn_v: **Q8_0** (~8.5 bpw · 63M params)
- ffn_gate_inp: **Q8_0** (~8.5 bpw · 0M params)
- attn_norm: **F32** (~32 bpw · 0M params)
- ffn_norm: **F32** (~32 bpw · 0M params)
- output_norm: **F32** (~32 bpw · 0M params)

## Captured circuit across depth (transistors / latches / decoder)
| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0 | — | | | | | | _layer 0 has no dense ffn_gate/up/down (p_ |
| 1 | — | | | | | | _layer 1 has no dense ffn_gate/up/down (p_ |
| 2 | — | | | | | | _layer 2 has no dense ffn_gate/up/down (p_ |
| 3 | — | | | | | | _layer 3 has no dense ffn_gate/up/down (p_ |
| 4 | — | | | | | | _layer 4 has no dense ffn_gate/up/down (p_ |
| 5 | — | | | | | | _layer 5 has no dense ffn_gate/up/down (p_ |
| 6 | — | | | | | | _layer 6 has no dense ffn_gate/up/down (p_ |
| 7 | — | | | | | | _layer 7 has no dense ffn_gate/up/down (p_ |
| 8 | — | | | | | | _layer 8 has no dense ffn_gate/up/down (p_ |
| 9 | — | | | | | | _layer 9 has no dense ffn_gate/up/down (p_ |
| 10 | — | | | | | | _layer 10 has no dense ffn_gate/up/down (_ |
| 11 | — | | | | | | _layer 11 has no dense ffn_gate/up/down (_ |

## IPC bus (attention) — per sampled layer
| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |
|--:|--:|--:|--:|--:|--:|--:|
| 0 | 40 | 8 | ×5 | 128 | 4.012 | 6.478 |
| 1 | 40 | 8 | ×5 | 128 | 8.333 | 10.731 |
| 2 | 40 | 8 | ×5 | 128 | 10.443 | 13.758 |
| 3 | 40 | 8 | ×5 | 128 | 11.862 | 15.514 |
| 4 | 40 | 8 | ×5 | 128 | 13.907 | 19.703 |
| 5 | 40 | 8 | ×5 | 128 | 17.476 | 21.438 |
| 6 | 40 | 8 | ×5 | 128 | 15.643 | 20.176 |
| 7 | 40 | 8 | ×5 | 128 | 16.369 | 21.729 |
| 8 | 40 | 8 | ×5 | 128 | 18.419 | 22.285 |
| 9 | 40 | 8 | ×5 | 128 | 19.245 | 23.463 |
| 10 | 40 | 8 | ×5 | 128 | 19.522 | 25.19 |
| 11 | 40 | 8 | ×5 | 128 | 25.49 | 37.702 |

## Decompiler (bits → meaning)
- **king** → King, ked, Ġking, ĠKing, ĠKING, kin, ks, ker
- **queen** → ĠQueen, queen, Ġqueen, King, ĠKing, Ġqueens, Prince, ĠQueens
- **bitcoin** → ĠBitcoin, Ġbitcoin, bitcoin, ĠBitcoins, Ġbitcoins, ĠLitecoin, BTC, ĠBTC

## Computer-in-the-weights (OS-primitive map)
- **IPC BUS (interprocess comm.)** ← attention routes data between positions — 40 channels over 8 shared KV lines (GQA×5) · mean channel 4.012
- **STORAGE (disk / DRAM cells)** ← the parameter file (weights = stored charge) — 4.61 B params · 4.53 GB on disk · 12 layers
- **I/O CODEC (in / out)** ← token_embd (decode-in) + output head (encode-out) — vocab 100352 × hidden 5120 (the tokenizer bus)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
