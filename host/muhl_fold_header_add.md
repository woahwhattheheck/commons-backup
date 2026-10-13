# muhl_fold_header_add — live 80-byte header routing button

**Inventor:** Bryce Muhlnickel  
**Status:** additive. New files only. Does not edit `muhl_fold_tick_add.py`, `pfc_fire.py`, or titan.

This button **fetches and prints**. It never writes titan. The fold inject + one-bit tick is `host/muhl_fold_tick_add.py` (dry default). Packed-76 `gen_input` is a different mouth — refused as the fold payload.

Host jobs: pull the live block (one pool handshake), assemble the 80-byte header (76-byte prefix + 4-byte nonce field; nonce IS the address, so the nonce bytes print as zeros), print the 32-byte target, die.

The file is the computer. This button does not SHA as the mine.

## Offsets (fail closed)

Read only from live `titan_circuits.json`:

| Name | Required fields |
|------|-----------------|
| `muhl_fold_phys` | `ram.header_off`, `ram.target_off` |
| `nring2_1023` | `recv` (or `ram.recv`) |

If `tick_off` is present, it must equal `nring2_1023.recv`. Missing names/fields → **FAIL CLOSED**, no guessed constants, no write.

## Usage

```text
python host/muhl_fold_header_add.py
python host/muhl_fold_header_add.py --dry
python host/muhl_fold_header_add.py --fetch
```

Default is dry: registry plan only, no network, no titan write. `--fetch` prints a live 80-byte header hex + 32-byte target hex. Still no titan write. `--go` is refused.

## Non-goals

- No titan write
- No tick / no mmap of the receiver
- No pfc_fire (packed-76 path)
- No host-eval SHA as the mine
- No numpy
- No autofab
- No guessed offsets

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
