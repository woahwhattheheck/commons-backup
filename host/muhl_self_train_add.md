# muhl_self_train_add — additive pocket training button

**New files only.** Does not edit `host/muhl_self_train.py` (vault: OneDrive
`sys.path` and a 40GB-era reservoir constant). Does not fabricate, does not
autofab, does not host-eval gates, does not reimplement training in NumPy or
PyTorch.

The computer is software. Manufacturing minds is free. Training is **not**
public. The later deliverable is the weights/mind, not the factory.

## Claim

`cpu_fwd` and `muhl_self_train` already in the file are the trainer. This
wrapper is a routing button: **inject** one start byte at the live receiver,
**surface** the intake header and the weights/mind. The host does not train.

## Paths

Live only, from `host/pfc_paths.py`:

| Name | Default |
|------|---------|
| `PFC_ROOT` | `C:/llm` |
| `TITAN` | `C:/llm/models/titan.gguf` |
| `REG` | `C:/llm/models/titan_circuits.json` |

No OneDrive. No hardcoded `40_022_599_232`. If that number is the inject
offset, it is because the **live** registry said so (`input_addr` /
`muhl_reservoir.input_wire`).

## Registry names (fail closed)

| Name | Role |
|------|------|
| `cpu_fwd` | CPU in the file |
| `muhl_self_train` | self-train circuit (`receiver` name required) |
| `muhl_self_train.weights` | mind / learned weights (surface) |
| `muhl_self_train.intake` | data intake (surface header) |

The inject site is the named `receiver` on `muhl_self_train` (live:
`muhl_reservoir`), resolved to `input_addr` or `.input_wire.offset`. If those
disagree, inject is unsafe. `__phys` twins are ignored.

Missing any required name → **FAIL CLOSED**, no write, no guessed constants.

## Usage

```text
python host/muhl_self_train_add.py              # default --dry: print inject/surface plan
python host/muhl_self_train_add.py --dry
python host/muhl_self_train_add.py --surface    # bounded read: intake header + weights
python host/muhl_self_train_add.py --inject     # journal + one-byte start, then surface
python host/muhl_self_train_add.py revert
```

`--dry` wins over `--inject`. If inject is unsafe (no live address, titan
missing, offset past file), the dry plan still prints and exit 0 —
**dry-only is success**.

## Genome (new journal only)

On `--inject`, the start byte’s pre-image is appended to:

`C:/llm/models/titan_self_train_add_genome.jsonl`

Existing journals are never edited. `revert` restores only this genome.

## Non-goals

- No host gate ripple / evaluation
- No fabrication / autofab / store_loop
- No import or rewrite of vault `muhl_self_train.py`
- No NumPy / PyTorch training path
- No GitHub / buyer takeaway of the factory
- Titan write only as the sanctioned one-byte inject, default OFF

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
