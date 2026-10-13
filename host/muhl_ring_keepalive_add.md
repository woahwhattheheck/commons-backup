# muhl_ring_keepalive_add — additive ring keepalive

**New files only.** Does not edit `nring2_run.py`, does not fabricate gates, does not touch osc, does not modify existing genomes.

## Claim

Electrons in a two-way ring do not deplete; they traverse. Keepalive **injects both senses** into the ring state wires (bounded writes) and **surfaces** with bounded reads. The host places or reads bytes; it never evaluates a gate.

Reference harness (read-only): `Desktop/MUHLNICKEL_HARNESSES/nring2_run.py` — same place-both-senses / journal-preimage pattern, separate genome.

## Offsets (fail closed)

Read only from `C:/llm/models/titan_circuits.json`:

| Ring | Required fields |
|------|-----------------|
| `nring2_000` … `nring2_003` | `ram.fwd`, `ram.rev`, `cells`, `senses==2`, and `recv` (or `ram.recv` / `junction.address` / int `junctioned_to`) |

If any field is missing → **FAIL CLOSED**, no write, no guessed constants.

## Genome (new journal only)

On `--inject`, every byte’s pre-image is appended to:

`C:/llm/models/titan_keepalive_add_genome.jsonl`

Existing journals are never edited. `revert` restores only this genome’s placements.

## Usage

```text
python host/muhl_ring_keepalive_add.py              # default --dry: print inject plan, write nothing
python host/muhl_ring_keepalive_add.py --dry
python host/muhl_ring_keepalive_add.py --surface    # bounded read: fwd/rev rails + 1-byte recv
python host/muhl_ring_keepalive_add.py --inject     # journal + write state wires, then surface
python host/muhl_ring_keepalive_add.py revert
```

## Dose

Default `K_PER_SENSE = 1`: one electron in `fwd`, one in `rev` (half-ring offset), matching `nring2_run.place_electrons` spacing. Both senses required for contact.

## Non-goals

- No host gate ripple / evaluation
- No fabrication / gate bake
- No osc tooling
- No parallel titan structure edits; inject is the sanctioned state-byte verb only when `--inject` is passed

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
