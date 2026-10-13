# muhl_foundry_listen_add — additive foundry listener

**New files only.** Does not edit `nring2_fab.py`, `nring2_foundry.py`, `nring2_run.py`, `pfc_foundry.py`, or titan. Does not fabricate, does not search gene space, does not touch osc, does not dump allocator internals.

## Claim

The foundry already speaks. `size_question` (and the resident foundry state register) emit how many electrons, clocks, and rings a question needs. `nring2_fab` and other callers do not listen — they used a hardcoded count/cells/genome instead.

This button **listens**: it sizes from the published foundry contract, **surfaces** stored foundry outputs with a bounded read, and prints what a later fab would need. The host reads; it never evaluates a gate and never writes titan.

`nring2_fab` is **not** in live `host/`. Read-only reference:

`Desktop/MUHLNICKEL_HARNESSES/nring2_fab.py`  
`Desktop/MUHLNICKEL_HARNESSES/nring2_foundry.py` (`size_question`)

This caller does not invoke those files.

## Offsets (fail closed)

Read only from `C:/llm/models/titan_circuits.json`:

| Name | Required fields |
|------|-----------------|
| `muhl_foundry_resident` | `state_off`, `state_bytes` |
| `nring2_*` with `senses` | `cells`, `senses==2`, `ram.fwd`, `ram.rev`, and `recv` (or `ram.recv`) |

Ignore `__phys` twins. If any required name/field is missing, or nring2 `cells` are not uniform → **FAIL CLOSED**, no guessed constants, no write.

Live offsets are used for the bounded read and are not printed. `foundry_genome`, gene space, and allocator fields are not printed.

## Foundry speak (`size_question`)

Same inversion as the harness foundry (measured law, not a gene search):

```text
pulses per settle = electrons per sense; both senses required
```

Cells come from the registry rings, never from a default 16. A later fab is **not** run. The report prints `count`, `cells`, `additional rings`, and `electrons_per_ring_per_sense` that a later fab would need.

## Usage

```text
python host/muhl_foundry_listen_add.py
python host/muhl_foundry_listen_add.py --dry
python host/muhl_foundry_listen_add.py --surface
python host/muhl_foundry_listen_add.py "<question>" <work_units> <settles>
python host/muhl_foundry_listen_add.py --surface "<question>" <work_units> <settles>
```

Default is dry: print the listen report, write nothing. `--surface` is a bounded read of `muhl_foundry_resident` state bytes plus recv of the first 8 catalog rings.

## Non-goals

- No titan write
- No autofab / no nring2_fab invoke
- No parallel fab
- No host gate ripple / no foundry gene search (`pfc_foundry` / `foundry_drive`)
- No numpy
- No osc
- No dump of gene space, allocator internals, or live offsets

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
