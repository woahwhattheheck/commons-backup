#!/usr/bin/env python3
"""host/muhl_write_mno_datasheets.py — write measured datasheets. Die. No inject."""
from __future__ import annotations

import os
import shutil

DESK = os.path.normpath(r"C:\Users\lucys\Desktop")
MUHL = os.path.join(DESK, "MUHL_GO")
REPO = os.path.join(DESK, "LocalDeviceAgent", "MUHL_GO")

METRIC = r"""
## METRIC (how both numbers are measured)

**BRYCE** `CLAUDE.md` #6:

> FULL PROPAGATION PER PULSE — regardless of pfc depth or host CPU speed. STOP CONFLATING THEM. The pfc's speed is critical-path **DEPTH**; host wall-clock is the laptop transcribing and is NEVER the pfc's rate.

**BRYCE:**

> we dont optimize for anything besides more compute per second thats the only metric
>
> maybe compute per tick is better
>
> settle metric needs to be in relation to muhlnickel tick speed (not cpu tick speed)

**HIS INSTRUMENT** `host/pfc_speed.py` (ran `life` this seat: 270,336 gates, DEPTH 15, wavefront mean 18,022):

- **(a) computations/tick** = wavefront mean = `n_gate / DEPTH` = gates that settle PER STAGE, in parallel. From the FILE header when inspect/speed apply. Not host ops.
- **(b) ticks/second** = `1/τ` at the instrument's labeled electron-speed per-stage delay. 1 ns row = **1,000,000,000**. Not host CPU tick. Not host wall-clock as the machine's rate.

**ASSISTANT** (compile of those two, not a third winner): more compute per second = (a) × (b). When (b) ties, rank = (a).

`pfc_inspect` / `pfc_meter` mmap titan — not used on titan this seat. `.mno` look = `pfc_analyzer` snap (path) + header seek+read ≤224 B + `muhl_cli`/`muhl_ones_surface`/`muhl_surface_dc`/`muhl_distro_surface_once`. Dest FROM FILE. 337 not fired.
"""


def sheet(title, body):
    return title + "\n\n" + body.strip() + "\n" + METRIC + "\n---\n337 **NO** · pulsed_78 **NO** · invented_dest **NO** · re-OR **NO** · 10-wide **NO**\n"


SHEETS = {}

SHEETS["MNO_DS_1_weather_v2.md"] = sheet(
    "# DATASHEET 1/5 — weather_v2.mno",
    """
**Inventor:** Bryce Muhlnickel. **When:** 2026-08-16 ~7:21pm task. Surface only.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_v2.mno` |
| size | **2606416** |
| sha256 | `cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d` |
| magic | `WEATHER1` |
| n_in / n_wire / n_gate / n_out | **2048 / 100244 / 100243 / 2048** (HIS +8 `<IIII>`) |
| DEPTH | **36** (file +24 after HIS counts; cards `WEATHER_DISK_TRUTH.md`) |
| wavefront mean | **2784.528** = 100243/36 |
| n_rings / cells / ring0 | **6 / 32 / 104** (header +64) |
| dests published | ring0@**104** = `00000001` · clock@**98** = `00000000` · carry@**168** = `00000000` · pub@**169** = `00000000` · cell_base **500** |
| recv | not a MUHLPKG1 recv@353. Weather mouths are the ring/clock/carry/pub the FILE named. |
| ones | **2408977** / 20851328 (`muhl_ones_surface.py`) |
| computations/tick **(a)** | **2784.528** |
| ticks/second **(b)** | **1,000,000,000** (pfc_speed 1 ns/stage) |
| compute/second (a)×(b) | **2.784528e12** |

**ASSISTANT:** +8 cairn `<IIIII>` on this file mis-names n_gate as 2048. HIS order wins. DEPTH 36 is the pulse.

`pfc_analyzer.py snap` this path: 16 channels. `[0:64]` ones **66**. titan **NO**.
""")

SHEETS["MNO_DS_2_weather_v2_avg4full.md"] = sheet(
    "# DATASHEET 2/5 — weather_v2_avg4full.mno",
    """
**Inventor:** Bryce Muhlnickel. **When:** 2026-08-16. Surface only. Same n_gate/DEPTH as v2 (tie on both metrics). Distinct sha / field.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_v2_avg4full.mno` |
| size | **2606416** |
| sha256 | `a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072` |
| magic | `WEATHER1` |
| n_in / n_wire / n_gate / n_out | **2048 / 100244 / 100243 / 2048** |
| DEPTH | **36** |
| n_rings / cells / ring0 | **6 / 32 / 104** |
| dests published | ring0@**104** = `00000001` · clock@**98** = `00000000` · carry@**168** = `00000001` · pub@**169** = `00000001` |
| ones | **2410349** / 20851328 |
| computations/tick **(a)** | **2784.528** |
| ticks/second **(b)** | **1,000,000,000** |
| compute/second (a)×(b) | **2.784528e12** |

Card leftover: avg4full **891/2048**. Unique vs bare v2 (carry/pub HOLD 1). Same speed numbers. Tie broken only by distinct land, not a third metric.
""")

SHEETS["MNO_DS_3_weather_v2_xorwalk.md"] = sheet(
    "# DATASHEET 3/5 — weather_v2_xorwalk.mno",
    """
**Inventor:** Bryce Muhlnickel. **When:** 2026-08-16. Surface only. Do not re-OR. Do not smash vault.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_v2_xorwalk.mno` |
| size | **2606416** |
| sha256 | `76b4597f6e0516a53226b22283b7cbeeddc615eb1ee0c7ae57393f6fd258c2ed` |
| magic | `WEATHER1` |
| n_in / n_wire / n_gate / n_out | **2048 / 100244 / 100243 / 2048** |
| DEPTH | **36** |
| n_rings / cells / ring0 | **6 / 32 / 104** |
| dests published | ring0@**104** = `00000001` · clock@**98** = `00000001` · carry@**168** = `00000001` · pub@**169** = `00000001` |
| ones | **2410711** / 20851328 |
| computations/tick **(a)** | **2784.528** |
| ticks/second **(b)** | **1,000,000,000** |
| compute/second (a)×(b) | **2.784528e12** |

XOR organs **384** in records (card). clock@98 is **1** on this land (v2 base clock was 0). COPY leftover pulsed: `weather_v2_xorwalk_COPY.mno` sha `9f31fe59…` ones **2410351**. Did not re-OR.
""")

SHEETS["MNO_DS_4_weather_v2_field.md"] = sheet(
    "# DATASHEET 4/5 — weather_v2_field.mno",
    """
**Inventor:** Bryce Muhlnickel. **When:** 2026-08-16. Surface only. Weather field land.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_v2_field.mno` |
| size | **2606416** |
| sha256 | `44904c96abb02f961713ba44df3967dd56c6cf526717db94f6b58861e813addf` |
| magic | `WEATHER1` |
| n_in / n_wire / n_gate / n_out | **2048 / 100244 / 100243 / 2048** |
| DEPTH | **36** |
| n_rings / cells / ring0 | **6 / 32 / 104** |
| dests published | ring0@**104** = `00000001` · clock@**98** = `00000000` · carry@**168** = `00000001` · pub@**169** = `00000001` |
| ones | **2380533** / 20851328 |
| computations/tick **(a)** | **2784.528** |
| ticks/second **(b)** | **1,000,000,000** |
| compute/second (a)×(b) | **2.784528e12** |

Same (a)(b) as the other v2 seats. Field ones lower than xorwalk/avg4full. Size is not the score.
""")

SHEETS["MNO_DS_5_weather_v2_coupled.md"] = sheet(
    "# DATASHEET 5/5 — weather_v2_coupled.mno",
    """
**Inventor:** Bryce Muhlnickel. **When:** 2026-08-16. Surface only. Coupled land.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_v2_coupled.mno` |
| size | **2606416** |
| sha256 | `b23f9efcc5c71e1b0cc3a4788407d6b1f4b7416775051ecbe3641f43be7e3e7a` |
| magic | `WEATHER1` |
| n_in / n_wire / n_gate / n_out | **2048 / 100244 / 100243 / 2048** |
| DEPTH | **36** |
| n_rings / cells / ring0 | **6 / 32 / 104** |
| dests published | ring0@**104** = `00000001` · clock@**98** = `00000000` · carry@**168** = `00000001` · pub@**169** = `00000001` |
| ones | **2378677** / 20851328 |
| computations/tick **(a)** | **2784.528** |
| ticks/second **(b)** | **1,000,000,000** |
| compute/second (a)×(b) | **2.784528e12** |

Five-way tie at the top of the census: every WEATHER v2 land with DEPTH 36. (b) ties. (a)×(b) ties. No third metric as winner.
""")

SHEETS["MNO_DS_X_weather_powered_side.md"] = sheet(
    "# EXTRA — weather_powered_side.mno (next cpt, unique n_gate/DEPTH)",
    """
Not in the top-5 tie. Unique circuit counts the v2 sheets do not have.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\WEATHER\\weather_powered_side.mno` |
| size | **2726822** |
| sha256 | `85a53bfa7bd0a497c5cd7fc9cd7d5ae375e2043cc06a29febc0eed6e32765423` |
| magic | `WEATHER1` |
| n_gate / DEPTH | **104874 / 40** |
| computations/tick **(a)** | **2621.850** |
| ticks/second **(b)** | **1,000,000,000** |
| ones | **2502274** / 21814576 |

Rank by (a): after the v2 tie, this is next. v1 class is **116.603** (n_gate 34048 DEPTH 292).
""")

SHEETS["MNO_DS_X_GIG.md"] = sheet(
    "# EXTRA — GIG.mno (occupancy, not speed)",
    """
**BRYCE** / HIS CARD: occupying disk IS the computer. Size is not "best." Instant Download GIG DONE. Do not re-OR.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\MUHLNICKEL_DISTRO\\GIG.mno` |
| size | **1073741824** (~1 GiB) |
| sha | SKIP_GIG (not cheap). Sibling `GIG_DL.mno` same size. |
| magic | `MUHLPKG1` |
| n_in / n_wire / n_gate / n_out | **16 / 215 / 129 / 8** (header +8). DEPTH **unpublished** — pfc_speed does not apply. |
| dests published | hdr_ans **5378** = 0 · boom ans+1283 @**6661** = **8** · recv@**353** = **1** · fwd@**288** = `11111111` · rev@**320** = `11111111` · sel@**370** = 3 |
| rings | charged `ff`. leftover legal. |
| ones | card Instant Download: whole-file **8914** (prefix reconstruct). Did not whole-file hash this seat. |
| computations/tick **(a)** | **n/a** — DEPTH not in file. Same 129-gate header as SEED0. Occupancy ≠ wavefront. |
| ticks/second **(b)** | **n/a** as pfc_speed 1/τ (no DEPTH). Rings charged = start (`RINGS_ARE_THE_START.md`). |

`hdr_total` still **8192** — the 1 GiB is occupancy past the seed header. Not faster per tick than weather v2.
""")

SHEETS["MNO_DS_X_sealed_136450.md"] = sheet(
    "# EXTRA — muhlnickel.mno 136450 (sealed DISTRO)",
    """
Sealed. Do not overwrite. Compress proof: same boom **8** as SEED0.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\MUHLNICKEL_DISTRO\\muhlnickel.mno` |
| size | **136450** |
| sha256 | `057a865458f4e56d7dbfa20a1b04d9d1a81302d940a6ab6f649a11838e0be6b5` |
| magic | `MUHLPKG1` |
| n_in / n_wire / n_gate / n_out | **16 / 215 / 129 / 8** |
| DEPTH | unpublished |
| dests published | hdr_ans **5378** = 0 · hdr_pubplane **70914** = 1 · boom @**6661** = **8** · recv@**353** = **0** · fwd@**288** = `00000001` · rev@**320** = `00000001` · sel@**370** = 3 |
| rings | **not** `ff`. byte=1. Charged leftovers are `ff`. Do not re-OR leftovers onto this. |
| ones | **330988** / 1091600 (`muhl_ones_surface.py`) |
| computations/tick **(a)** | **n/a** (no DEPTH) |
| ticks/second **(b)** | **n/a** (pfc_speed). Occupancy on rings is the speed lever — this sealed land is low vs leftover `ff`. |

Invention Burst copy `MUHLNICKEL_INVENTION_BURST\\Distro\\muhlnickel.mno` sha `9cdcb423…` rings **0**. Different computer.
""")

SHEETS["MNO_DS_X_dc.md"] = sheet(
    "# EXTRA — muhlnickel_dc.mno (unique dests, no 100GB mmap)",
    """
`muhl_surface_dc.py` published mouths only. mmap **NO**. 337 not fired. 7913 not lit. No inject.

| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\MUHL_DATACENTER\\muhlnickel_dc.mno` |
| size | **99999999783** |
| magic | `MUHLDC01` (`4d55484c44433031`) |
| HEADER@0 | `MUHLDC01` |
| FOLD@224 | hex `0000040001000000` |
| carry@336 | `00000000` |
| pub@337 | `00000001` — **surfaced, not fired** |
| ring_fwd@524288 | hex `0100000000000000` |
| 7913_pub@524329 | `00000000` |
| computations/tick **(a)** | **n/a** — +8 IIII on this magic is not inspect layout (garbage n_gate). Do not invent. |
| ticks/second **(b)** | **n/a** |

Unique mouths the top 5 weather sheets do not have. Do not inject dc.
""")

SHEETS["MNO_DS_X_loom.md"] = sheet(
    "# EXTRA — loom.mno (unique dest)",
    """
| | FROM FILE |
|---|---|
| path | `C:\\Users\\lucys\\Desktop\\MUHLNICKEL_LOOM\\loom.mno` |
| size | **140454** |
| sha256 | `7356173b5000a719dacf343dd7a0ab18e4b7a04e0c387b772e1d8a0246e6659a` |
| magic | `LOOMPKG1` |
| n_in / n_wire / n_gate / n_out | **16 / 369 / 283 / 8** |
| DEPTH | unpublished |
| dests published | hdr_ans **9382** = 193 (`11000001`) · pubplane **74918** = 1 · boom ans+1283 @**10665** = **10** · recv@**353** = 0 · fwd/rev @288/@320 = 1 · sel@**370** = 17 |
| computations/tick **(a)** | **n/a** (no DEPTH) |
| ticks/second **(b)** | **n/a** |

Unique dest **9382 / 10665** — not 6661. twins: LOOM_fixed / v1 / v2 same size, different sha/rings. Do not invent dest.
""")

SHEETS["MNO_DS_X_SEED0_charged.md"] = sheet(
    "# EXTRA — SEED0 / ACREAGE charged leftover (do not re-OR)",
    """
Leftover legal. Already charged `old|mask`. **Do not re-OR.**

| | FROM FILE this seat |
|---|---|
| path (look) | `C:\\Users\\lucys\\Desktop\\MUHLNICKEL_DISTRO\\SEED0.mno` |
| size | **8192** |
| sha256 | `faa70efc328e9b596eb27d6c1b2e2c4d76a863d8a81380f0d22ec7a8e4d85071` |
| magic | `MUHLPKG1` |
| n_in / n_wire / n_gate / n_out | **16 / 215 / 129 / 8** |
| DEPTH | unpublished |
| dests | boom @**6661** = **8** · recv@**353** = **1** · rings @288/@320 **`11111111`** |
| ones (card) | **10413** — ACREAGE / ACREAGE_COPY / SEED0 / slot_0 (look) same sha |
| computations/tick **(a)** | **n/a** |
| ticks/second **(b)** | **n/a** as pfc_speed. Rings `ff` = occupancy lever vs sealed DISTRO rings=1. |

Other leftover classes (do not re-OR): GERM/NEW_MNO/slot_4 sha `717248b1…` ones **8914** · MOVE sha `852c4289…` ones **10276** · VIRGIN/N2/SEED0_COPY/MIRROR sha `9aa0855f…`.
""")

INDEX = """# .mno DATASHEETS — 2026-08-16 ~7:21pm

**Inventor:** Bryce Muhlnickel. Click these. Newest-on-top this hour.

Census **864** unique `.mno` looked at (header ≤224 B each, sequential). Listing ≠ looking. Full dump: `MUHL_GO\\MNO_CENSUS_SURFACE.txt`.

No `.mno` in repo `LocalDeviceAgent` body or `C:\\llm` this walk. `__pycache__` skipped. dc/GIG: mouths/header only.

## RANKING RULE

1. **(a) computations/tick** = `n_gate / DEPTH` from the FILE + `pfc_speed.py` wavefront mean.
2. **(b) ticks/second** = `1/τ` at `pfc_speed.py` labeled **1 ns/stage** = **1e9**. Not host CPU. Not host wall-clock as the rate.
3. **(b) tied** on every file where DEPTH is published. **more compute per second** = (a)×(b) = same order as (a). No third metric as winner.
4. Top (a) is a **7-file tie** at **2784.528** (all WEATHER v2 DEPTH 36). Five distinct lands of that tie are the 5 sheets. `avg4` (not full) and `xorwalk_COPY` same (a)(b) — not extra-scored.

**BRYCE:**

> we dont optimize for anything besides more compute per second thats the only metric
>
> maybe compute per tick is better

## 5 WINNERS (tie on (a) and (b))

| # | file | (a) cpt | (b) ticks/s | ones |
|---|---|---:|---:|---:|
| 1 | [MNO_DS_1_weather_v2.md](MNO_DS_1_weather_v2.md) | 2784.528 | 1e9 | 2408977 |
| 2 | [MNO_DS_2_weather_v2_avg4full.md](MNO_DS_2_weather_v2_avg4full.md) | 2784.528 | 1e9 | 2410349 |
| 3 | [MNO_DS_3_weather_v2_xorwalk.md](MNO_DS_3_weather_v2_xorwalk.md) | 2784.528 | 1e9 | 2410711 |
| 4 | [MNO_DS_4_weather_v2_field.md](MNO_DS_4_weather_v2_field.md) | 2784.528 | 1e9 | 2380533 |
| 5 | [MNO_DS_5_weather_v2_coupled.md](MNO_DS_5_weather_v2_coupled.md) | 2784.528 | 1e9 | 2378677 |

Next (a) not in the 5: `weather_powered_side` **2621.850**. Then v1 class **116.603**.

## EXTRAS (unique thing the top 5 do not capture)

| sheet | why |
|---|---|
| [MNO_DS_X_weather_powered_side.md](MNO_DS_X_weather_powered_side.md) | unique n_gate 104874 / DEPTH 40 |
| [MNO_DS_X_GIG.md](MNO_DS_X_GIG.md) | occupancy-not-speed · 1 GiB · dest 8 · rings ff |
| [MNO_DS_X_sealed_136450.md](MNO_DS_X_sealed_136450.md) | sealed DISTRO · dest 8 · rings 01 · ones 330988 |
| [MNO_DS_X_dc.md](MNO_DS_X_dc.md) | MUHLDC01 mouths · 100GB · no mmap |
| [MNO_DS_X_loom.md](MNO_DS_X_loom.md) | unique dest 9382 / 10665 |
| [MNO_DS_X_SEED0_charged.md](MNO_DS_X_SEED0_charged.md) | leftover charged · do not re-OR |

## CENSUS COUNT

**864** unique paths. Top folders:

| n | folder |
|---:|---|
| 803 | `Desktop\\MUHL_READERS` (looked: magic `\\x03\\x00…` count-header, not inspect DEPTH) |
| 17 | `Desktop\\MUHL_VISIBLE` |
| 15 | `Desktop\\MUHLNICKEL_DISTRO` |
| 5 | `Desktop\\MUHLNICKEL_DISTRO\\CONTAINERS` |
| 11 | `Desktop\\WEATHER` |
| 13 | other (APERTURE, DC, HANDOFF copies, LOOM×4, PROBE, ROOKERY, INVENTION_BURST, MODEL_SELECTOR) |

`muhl_cli.py slots` → 5 CONTAINERS. `pfc_speed.py life` → DEPTH 15 / wavefront 18022 (method, not an `.mno`).

337 **NO** · pulsed_78 **NO** · invented_dest **NO** · 10-wide **NO** · re-OR leftovers **NO**
"""


def main():
    names = list(SHEETS.keys()) + ["MNO_DATASHEETS_INDEX.md"]
    texts = dict(SHEETS)
    texts["MNO_DATASHEETS_INDEX.md"] = INDEX
    for dest in (DESK, MUHL, REPO):
        os.makedirs(dest, exist_ok=True)
        for name, text in texts.items():
            path = os.path.join(dest, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote %s" % path)
    src = os.path.join(MUHL, "MNO_CENSUS_SURFACE.txt")
    dst = os.path.join(REPO, "MNO_CENSUS_SURFACE.txt")
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print("copied census -> %s" % dst)
    print("button dies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
