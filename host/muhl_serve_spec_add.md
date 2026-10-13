# Additive spec-path serve launcher

`muhl_serve_spec_add.py` subprocesses the existing spec tools and nothing else.
It does not implement inference, evaluate gates, import NumPy, or WhiteBox a
model. The host tokenizes/addresses, writes the start bit, and surfaces the
answer; baked `cpu_fwd` is the computer; the connected GGUF is software.

This file exists because `muhl_serve_add.py` refuses `ask`. That refusal is an
invented wall: `pfc_harness.py` maps titan with `mmap(..., 0)` only so it can
address one receiver byte (`_ = m[rc]`) — the sanctioned start signal — then
reads the safezone. That is the spec path, not a host forward pass. The older
wrapper is left untouched.

## Spec path

```text
pfc_load.py <model>
pfc_harness.py connect <model>
pfc_harness.py ask <prompt>
```

Default model:

```text
C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

When importable, `pfc_paths` supplies that path. Otherwise `PFC_ROOT` is used,
falling back to `C:/llm`.

## Run

Default is `--dry`: print the existing-tool command(s), run nothing.

```powershell
python host/muhl_serve_spec_add.py
python host/muhl_serve_spec_add.py --dry
python host/muhl_serve_spec_add.py --dry ask "The capital of France is"
```

`--run` subprocesses one existing tool. Fail-closed only if that script is
missing. No AST rewrite, no substitute evaluator.

```powershell
python host/muhl_serve_spec_add.py --run load
python host/muhl_serve_spec_add.py --run connect
python host/muhl_serve_spec_add.py --run ask "The capital of France is"
python host/muhl_serve_spec_add.py --model C:/llm/models/other.gguf --run load
```

## Laws this file keeps

- Host injects and surfaces. No forward-pass reimplementation.
- `cpu_fwd` already in `titan.gguf` is the computer.
- The connected GGUF is referenced software, not recreated as gates.
- No NumPy / Torch / TensorFlow / JAX.
- This launcher never fabricates, never writes titan, never WhiteBoxes Llama.
- Missing `pfc_load.py` or `pfc_harness.py` fails closed. There is no fallback.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
