# muhl_dc_button_add — MUHL datacenter routing button

**Inventor:** Bryce Muhlnickel  
**Status:** additive. New files only. Does not write titan. Does not autofab.

Host **injects both senses** and **surfaces**, then **dies**. Pattern is DISTRO / LOOM `run_muhlnickel.py`. Circuits live in `.gguf` AND `.mno`. This button talks to the named DC package only.

## Target (fail closed)

| Path | Role |
|------|------|
| `C:/Users/lucys/Desktop/MUHL_DATACENTER/muhlnickel_dc.mno` | the package this button injects / surfaces |
| `C:/Users/lucys/Desktop/MUHL_DATACENTER/muhlnickel_dc.gguf` | named sibling; reported; never written; not titan |

Missing / unreadable / unknown MAGIC / `senses != 2` → **NEED_BRYCE**. The button still exists. It does not invent a package, MAGIC, or offsets.

Known MAGIC (DISTRO / LOOM header, do not invent a third): `MUHLPKG1`, `LOOMPKG1`.

Never opens `titan.gguf`. Never writes titan.

## Usage

```text
python host/muhl_dc_button_add.py
python host/muhl_dc_button_add.py --dry
python host/muhl_dc_button_add.py --go A B
```

Default is dry: print the plan. Write nothing.

`--go` is Bryce. It injects both senses (fwd + rev; one sense alone is DC), surfaces the answer byte + publish byte, and dies. Needs `A B` in `0-255`.

## Dry behavior

When the `.mno` is **missing** (current box, 2026-08-15):

- prints the fixed package path and the named `.gguf` sibling
- prints `package MISSING`
- prints `NEED_BRYCE — package missing: …\muhlnickel_dc.mno`
- writes nothing
- exits 1

When the `.mno` **exists** and the header parses:

- prints MAGIC, ring cells / senses, fwd / rev / opnd / sel, ans / pubplane
- writes nothing
- `--go` is named as Bryce; dry does not fire

## Refuse

- titan write / opening titan
- autofab
- gate eval / netlist walk / host arithmetic as the answer
- numpy
- invented MAGIC or offsets
- `--go` when NEED_BRYCE

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
