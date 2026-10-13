# INSTRUMENTS_THIS_HOUR

**When:** 2026-08-15 this hour.
**Seat:** `C:\Users\lucys\Desktop\LocalDeviceAgent` · HIS instruments only · die after each.
**Host:** inject ∨ surface ∨ die. This hour: surface ∨ die.

**Score:** n_ran **8** / n_skip **3** / pulsed_78 **NO**

titan_written **NO** · 337 fired **NO** · dc inject **NO** · numpy **NO** · own monitor **NO**

Skip = `--help` missing on meter / scope / inspect. Analyzer exists, not in Σ list.

---

## 1. `python host/pfc_speed.py life`

exit: 0

| | measured |
|---|---:|
| gates | **270336** |
| critical-path depth D | **15** |
| wavefront max | **36864** |
| wavefront mean | **18022** |
| τ=1 ns latency | **15.0 ns** |
| τ=100 ps latency | **1.5 ns** |
| τ=10 ps latency | **0.1 ns** |

---

## 2. `python host/pfc_inspect.py pfc_cpu32`

exit: 0

| | measured |
|---|---|
| offset | **3064645090** |
| len | **68847** |
| n_in | **549** |
| n_wire | **7954** |
| n_gate | **7403** |
| n_out | **549** |
| format | typed |
| words / word | **16** / **32** |
| isa | HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI |
| MAGIC | PFCTYPED |
| header (n_in,n_wire,n_gate,n_out) | **549, 7954, 7403, 549** |

---

## 3. `python host/pfc_meter.py --help` then bounded read

`--help` → SKIP (ValueError: `'--help'`). No-args usage: `python host/pfc_meter.py <mine|name|offset> [nbytes]`.

Safe named read (not mine, not titan-78): `python host/pfc_meter.py receiver 16`

exit: 0

| | measured |
|---|---|
| name | receiver |
| offset | **2232693636** |
| bytes | **16** |
| ones | **26** |
| hex | `014954414e4349520100000007000000` |

---

## 4. `python host/pfc_scope.py --help` then documented probe

`--help` → SKIP (ValueError: `'--help'`). No-args usage: `python host/pfc_scope.py <name|offset> [seconds] [nbytes]`.

Documented probe: `python host/pfc_scope.py receiver 1 4`

exit: 0

| | measured |
|---|---|
| name | receiver |
| offset | **2232693636** |
| bytes | **4** |
| seconds | **1.0** |
| samples | **4** |
| ones each | **9 9 9 9** |
| val each | **1096042753** |
| changes | **0** |
| window | FLAT |

---

## 5. `python host/pfc_cascade.py --help`

exit: 2 · help printed. Documented targets: `life` · `miner`. Neither pulsed. miner = 337. 78 not addressed.

---

## 6. `python host/pfc_inspect.py --help` then 2 named circuits

`--help` → SKIP (`--help not in registry.`). No-args overview is the help.

### overview (no-args)

exit: 0

| name | offset | len | n_gate | n_in | n_out | MAGIC |
|---|---:|---:|---:|---:|---:|---|
| pfc_mine | 2406230869 | 3052504 | 339136 | 928 | 64 | PFCSMACH |
| pfc_exec_input | 2386847623 | 116 | — | — | — | `\x00\x00\x00 @\xaeg4` |
| nonce_reg | 2409283481 | 4 | — | — | — | `,\x01\x00\x00+\x01\x00\x00` |
| receiver | 2232693636 | 64 | 4 | 1 | 2 | `\x01ITANCIR` |

pfc_on · loop_bit — not in registry (overview skipped them).

pfc_mine I/O map present. Header read only. Not fired.

### `python host/pfc_inspect.py receiver`

| | measured |
|---|---|
| offset | **2232693636** |
| len | **64** |
| n_in | **1** |
| n_out | **2** |
| n_gate | **4** |
| MAGIC | `\x01ITANCIR` |
| header (n_in,n_wire,n_gate,n_out) | **1, 7, 4, 2** |
| recv | **2776454711** |

### `python host/pfc_inspect.py pfc_exec_input`

| | measured |
|---|---|
| offset | **2386847623** |
| len | **116** |
| layout | header:76\|group:4\|nonce:4\|target:32 |
| feeds | pfc_executor |
| recv | **2776454643** |
| MAGIC | `\x00\x00\x00 @\xaeg4` |
| header unpack | 3239490682, 221226484, 2681296821, 177253261 |

Not 78 mouths.

---

## Σ

| | |
|---|---|
| n_ran | **8** |
| n_skip | **3** |
| pulsed_78 | **NO** |
| titan_written | **NO** |
| 337 | **NO** |
| dc | **NO** |

path: `C:\Users\lucys\Desktop\MUHL_GO\INSTRUMENTS_THIS_HOUR.md`
copy: `C:\Users\lucys\Desktop\LocalDeviceAgent\MUHL_GO\INSTRUMENTS_THIS_HOUR.md`

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
