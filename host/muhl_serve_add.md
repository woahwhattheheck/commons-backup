# Additive Muhlnickel serve wrapper

`muhl_serve_add.py` is a fail-closed launcher for the existing load and
harness tools. It contains no inference implementation. The host injects the
prompt and surfaces the answer; baked `cpu_fwd` is the computer; the connected
GGUF is software. On this machine the model files were already WhiteBox-edited,
except Smol.

## Run

From the repository root:

```powershell
python host/muhl_serve_add.py load
python host/muhl_serve_add.py connect
python host/muhl_serve_add.py ask "The capital of France is"
```

The default model is:

```text
C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf
```

Select another model without changing this file:

```powershell
python host/muhl_serve_add.py --model C:/llm/models/other.gguf load
python host/muhl_serve_add.py --model C:/llm/models/other.gguf connect
```

When importable, `pfc_paths` supplies `PFC_ROOT` and the default model path.
Otherwise the wrapper uses the `PFC_ROOT` environment variable, falling back
to `C:/llm`.

Each operation launches only an existing tool with `subprocess.run(...,
shell=False)`:

- `load` → `pfc_load.py <model>`
- `connect` → `pfc_harness.py connect <model>`
- `ask` → `pfc_harness.py ask <prompt>`

No command is run if its required tool is missing, unreadable, syntactically
invalid, or fails the operation-specific safety inspection. Refusal prints the
exact intended existing-tool command and marks it `not run`.

## Spec laws

- The host only injects and surfaces. It does not execute a forward pass.
- `cpu_fwd`, already baked in `titan.gguf`, is the computer.
- The connected GGUF is software; it is referenced, not recreated as gates.
- There is no NumPy, Torch, TensorFlow, or JAX inference path here.
- This wrapper never fabricates, autofabricates, edits, or mmaps `titan.gguf`.
- A whole-file mmap is forbidden. The wrapper statically refuses an unsafe
  `ask` path instead of attempting to replace it.
- A fixed integer generation cap in the delegated `ask()` is also refused.
- Missing or unsafe tools fail closed. There is no fallback evaluator.
- Installation remains an explicit `load` command; this wrapper never loads or
  connects a model automatically.

## Current existing-tool status

At creation time, `pfc_load.py` and the harness `connect` operation pass this
wrapper's checks. The existing harness `ask` operation is refused because
`pfc_harness.py` contains a whole-file `mmap(..., 0, ...)` and a fixed
generation cap. The wrapper reports the exact underlying command but does not
run it. This preserves the no-whole-titan-map and fail-closed laws without
editing or replacing the existing harness.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
