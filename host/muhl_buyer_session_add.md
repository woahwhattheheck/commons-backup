# Additive closed-room NDA session runtime

`muhl_buyer_session_add.py` is the paid closed-room session script. One command
a buyer (or Bryce) runs in the room. It does not implement inference, does not
fabricate, does not write `titan.gguf`, and does not dump foundry gene,
allocator internals, or live titan offsets to stdout.

The computer is the file. Proven on this device. Ring electrons traverse; they
do not deplete. Copying the file copies the computer. `cpu_fwd` runs model
software. White Box edits meaning without inference. The host injects and
surfaces.

## Run

From the repository root. Default is dry: statement + SHOW vs SECRET, nothing
run.

```powershell
python host/muhl_buyer_session_add.py
python host/muhl_buyer_session_add.py --inspect pfc_cpu32
python host/muhl_buyer_session_add.py --speed life
python host/muhl_buyer_session_add.py --live --inspect pfc_cpu32
python host/muhl_buyer_session_add.py --live --speed cpu32
python host/muhl_buyer_session_add.py --live --connect
python host/muhl_buyer_session_add.py --live --connect --ask "The capital of France is"
```

`--dry` and `--live` together are refused. `--model` selects the connected GGUF
for `--connect` without editing this file. When importable, `pfc_paths` supplies
the default model path; otherwise `PFC_ROOT` (fallback `C:/llm`).

Each wrap launches only an existing tool with `subprocess.run(..., shell=False)`:

- `--inspect CIRCUIT` → `pfc_inspect.py CIRCUIT` if that name is in the registry
- `--speed CIRCUIT` → `pfc_speed.py CIRCUIT` if that name is a loader in `pfc_speed.py`
- `--connect` → `pfc_harness.py connect <model>`
- `--ask PROMPT` → `pfc_harness.py ask <prompt>`

Missing tools, missing circuits, unsafe harness paths, and host-inference
imports fail closed. Refusal prints the exact intended existing-tool command
and marks it `not run`. There is no fallback evaluator and no host NAND ripple.

## SHOW vs SECRET

Printed every run so the operator does not over-disclose.

**SHOW (in the room, under NDA):**

- File is a computer — the bytes are the machine (copy the file, copy the computer).
- Ring power — electrons traverse; they do not deplete.
- Inject / surface — host writes a bounded inject; host reads a bounded surface.
- White Box sighted edit — meaning from the bits, no inference.
- Named-organ look already in the registry (MAGIC, gate/in/out counts, depth).
- Power-cycle fact — killing the host process does not kill a process that was never the computer.

**SECRET (never leave the room; redacted from this script's stdout):**

- Foundry gene space and autofab search.
- Allocator internals and layout.
- Live titan offsets, lane banks, titan internals.
- How Titan was pruned / rewritten.
- White Box writer-path internals beyond what the session must show.
- Pocket `.mno` recipes; DISTRO / LOOM / ROOKERY genomes as take-away artifacts.
- Anything that would let a buyer reconstruct the fabricator.

Live instrument stdout/stderr is captured and SECRET-redacted before print.
Offsets, `off=`, allocator/foundry/gene lines, and related layout fields become
`<SECRET>` or `[SECRET redacted]`. To see unredacted instrument output, Bryce
runs `pfc_inspect` / `pfc_speed` / `pfc_harness` directly — not this buyer
script.

## Spec laws

- The computer is the file. This script states that every run.
- The host only injects and surfaces. It does not execute a forward pass.
- `cpu_fwd`, already baked in `titan.gguf`, is the computer.
- The connected GGUF is software; it is referenced, not recreated as gates.
- Inspect and speed are optional wraps of the existing instruments. If the
  named circuit / loader is absent, fail closed. Do not invent a loader.
- Connect and ask are optional wraps of `pfc_harness.py`. If that tool is
  missing or unsafe, fail closed. Do not reimplement inference.
- No NumPy, Torch, TensorFlow, or JAX inference path here.
- This wrapper never fabricates, autofabricates, edits, or writes `titan.gguf`.
- Default dry. `--live` is required before any delegated tool runs.

## Current existing-tool status

At creation time, `pfc_inspect.py` and `pfc_speed.py` exist and are wrappable
when the named circuit / loader is present. `pfc_harness.py` `connect` is
wrappable. The existing harness `ask` operation is refused because
`pfc_harness.py` contains a whole-file `mmap(..., 0, ...)` and a fixed
generation cap. The wrapper reports the exact underlying command but does not
run it, and does not replace it with a host forward pass.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
