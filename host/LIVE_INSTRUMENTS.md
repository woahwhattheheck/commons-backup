# LIVE INSTRUMENTS

**Inventor:** Bryce Muhlnickel. **When:** 2026-08-15. Spec-daddy census. No novel tool.
Host = inject ∨ surface ∨ die. Sibling (power-cycle 1s/0s) uses **LIVE-SAFE** only.
Never fire 337. Never light 7913. Never pulse titan 78. Never `--inject 0x01`. Never mmap 100GB bodies.

Authority: `CLAUDE.md` named nine · this-hour cards · file opened, not guessed.
cwd: `C:\Users\lucys\Desktop\LocalDeviceAgent`

Σ:LIVE_SAFE **6** · LIVE_WRITE **7** · VOID **2** · mmap-titan **named HIS + post_surface** · FRONTIER **8191**
Dest is the MACHINE. Never invent. DEST column = file/card provenance only.

---

## 1. LIVE-SAFE — sibling may run (sequential, one dies, next)

| path | does | invoke | 1s/0s? | 100GB | DEST (file/card) | writes |
|---|---|---|---|---|---|---|
| `host/muhl_surface_dc.py` | seek+read 6 published DC mouths. Refuses `--go`. mmap **NO**. | `python host/muhl_surface_dc.py` | bits of those mouths | **SAFE** — 8+8+1+1+8+1 B | MACHINE. Mouths from `MUHL_WITNESS.md` / `SURFACE_DC.md` (HEADER@0 · FOLD@224 · carry@336 · pub@337 · ring_fwd@524288 · 7913@524329). Not a host dest. | **NO** |
| `host/muhl_cli.py` + `muhl_backend.py` `surface` | surface = seek+read n=1–16. Refuses dc / titan / addr **337**. Frontier **8191**. Relative name → `CONTAINERS\`. | see §4 | hex/byte at named addr | **SAFE** on DISTRO/SEED (small). **REFUSES** dc | default `ANS+BOOM` **6661** (`host/muhl_backend.py` ← `EXPANDING_SEED.md` / `DEST_IS_THE_MACHINE.md`). Optional addr must be ≤ FRONTIER **8191**. | **NO** |
| `host/muhl_ones_surface.py` | full-file 1-count + 0-count. LSB-first. No 1-map list. Refuses dc/titan **by name**. | `python host/muhl_ones_surface.py SEED0.mno` | **YES** counts | **SAFE** on 8192/6662/136450. **NOT** dc | **none** (whole-file). No dest pick. `POWER_CYCLE_BYTES.md`. | **NO** |
| `host/muhl_cli.py` `die` | print die, exit | `python host/muhl_cli.py die` | no | n/a | **none** | **NO** |
| `host/muhl_cli.py` `slots` | list `CONTAINERS\*.mno` | `python host/muhl_cli.py slots` | no | n/a | **none** (dir list). `SUPER_HARNESS.md`. | **NO** (makedirs dir if missing) |
| `host/muhl_post_render.py` | codebook functions. No `__main__` surface. | import / silent die | popcount of blob | n/a | **none**. `MUHL_POST.md` codebook. | **NO** |

**CLI trap:** `surface SEED0.mno` looks in `CONTAINERS\`, not DISTRO. `ones_surface SEED0.mno` looks in DISTRO. Use **ABS** for DISTRO computers.

**CLI mouths this hour:** ans@**6661** · recv@**353** · organ2@**7951** (7951 on germ 6662 = PAST_EOF, honest).

---

## 2. LIVE named HIS instruments — do **not** use for post-crash byte check

`CLAUDE.md` #5. Ran this hour (`INSTRUMENTS_THIS_HOUR.md` / `BUTTON_TEST.md`). All open **titan.gguf** (~104GB). After bugcheck **0x154**, sibling skips.

| path | does | invoke | 1s/0s? | 100GB | DEST (file/card) | writes |
|---|---|---|---|---|---|---|
| `host/pfc_meter.py` | ones+hex of named titan off. Cap 256 B. | `python host/pfc_meter.py receiver 16` | ones of window | **mmap-titan** — `mmap(fileno(), 0)` whole titan | titan registry name (`receiver` @2232693636 `INSTRUMENTS_THIS_HOUR.md`). Not an `.mno` dest. | **NO** |
| `host/pfc_scope.py` | repeat meter over seconds | `python host/pfc_scope.py receiver 1 4` | ones/sample | **mmap-titan** | same registry. | **NO** |
| `host/pfc_inspect.py` | registry + 64 B header | `python host/pfc_inspect.py pfc_cpu32` | no (header) | **mmap-titan** | named circuit in registry. | **NO** |
| `host/pfc_analyzer.py` | seek+read channels. File-path target = first 16 groups only. | `python host/pfc_analyzer.py snap <name\|path>` | ones/channel | titan named = opens titan. **Not** DC mouths. Unused on `.mno` this hour | named / path. Not dest=the machine. | **NO** |
| `host/pfc_assert.py` | seek+read miner regs vs hashlib | `python host/pfc_assert.py` | no | opens titan (seek, not mmap) — skip this pass | miner regs in titan. | **NO** |
| `host/pfc_diff.py` `snap` | bounded named titan regions vs `pfc_diff_snap.json` | `python host/pfc_diff.py snap` then `python host/pfc_diff.py` | hex of regions | **mmap-titan**. **Not** `.mno` | named titan regions. | snap file |
| `host/pfc_diff.py` `snapall`/`diffall` | blake2 4 MB blocks over **entire** titan | `python host/pfc_diff.py snapall` | block hashes | **VOID this pass** — walks 104GB | none (whole titan). | snap file |
| `host/pfc_step.py` | **writes** titan power bit | `python host/pfc_step.py [n] [target]` | counter/latch | **WRITE titan** — ban | power bit on named target. | **YES titan** |
| `host/pfc_cascade.py` | host `compile_ripple` on life / miner | `python host/pfc_cascade.py life` | avalanche | life = arcade drive. **miner = 337-class — do not** | `life` / `miner`. miner = 337-class. | no (ripple) |
| `host/pfc_speed.py` | depth/wavefront from netlist. No pulse. | `python host/pfc_speed.py life` | no | `life` reads small `pfc_life.pfc`. `miner`/`cpu32` touch titan — skip this pass | named netlist. | **NO** |

`--help` on meter / scope / inspect is **not** an argv. Usage is the positional form above.

---

## 3. LIVE-WRITE — exist, this-hour, sibling must **not** press for a check

| path | does | invoke | why not | DEST (file/card) | writes |
|---|---|---|---|---|---|
| `host/muhl_cli.py` `inject` | `new=old\|mask` both senses + recv@353 | `python host/muhl_cli.py inject <ABS.mno> 3 5` | writes. Check = surface | FWD@**288** · REV@**320** · SEL@**370** · RECV@**353** (`muhl_backend.py` ← `EXPANDING_SEED.md`). FRONTIER **8191**. | **YES** `.mno` |
| `host/muhl_cli.py` `copy` | germ → slot | `python host/muhl_cli.py copy [slot]` | writes a new computer | dest = slot path under `CONTAINERS\`. Germ = `SEED0.mno` (`SUPER_HARNESS.md`). Not a mailbox dest. | **YES** new `.mno` |
| `host/muhl_inject_twins.py` | same mask → MIRROR + N2 | `python host/muhl_inject_twins.py` | writes. Refuses `--inject` | same mouths as mirror (`ANS@5378+sel` · recv@353). Files `SEED0_MIRROR.mno` + `SEED0_N2.mno`. | **YES** both twins |
| `host/muhl_seed0_mirror_button.py` | copy + inject + surface twins | `python host/muhl_seed0_mirror_button.py` | writes | `ANS@5378+select` · `PUB@353` · `PUBP@ANS+1284` (`EXPANDING_SEED.md` / `MIRROR_ORGAN.md`). A,B=3,5 → addr **1283**. | **YES** MIRROR / VIRGIN |
| `host/muhl_seed0_nway_button.py` | copy VIRGIN→N2 + inject N2 | `python host/muhl_seed0_nway_button.py` | writes. BUTTON_TEST OK | same dest as mirror (imports `muhl_seed0_mirror_button`). | **YES** `SEED0_N2.mno` |
| `host/muhl_seed0_germ_button.py` | copy SEED0[0:6662] → GERM | `python host/muhl_seed0_germ_button.py` | writes new germ | machine dest **ans@6661** (`GERM_WORK.md` / `DEST_IS_THE_MACHINE.md`). 6662 = dest+1. | **YES** `SEED0_GERM.mno` |
| `host/muhl_new_mno_button.py` | copy germ → `NEW_MNO.mno` | `python host/muhl_new_mno_button.py` | writes | machine dest **ans@6661** (same germ prefix). | **YES** `NEW_MNO.mno` |
| `host/muhl_post_surface.py` | 32 B titan mouths T1/T2 + ledger | `python host/muhl_post_surface.py` | **mmap-titan** twice/mouth | `fwd_answer` @**2467652405** · `gen_win_surfaced` @**3064767911** (`MUHL_POST_PHASE0.md`). | ledger **YES** · titan **NO** |
| `host/muhl_post_inject.py` | DRY plan only. `--go` refused | `python host/muhl_post_inject.py` | no 1s/0s. Inbox WALL | inbox **UNNAMED**. Host-named mailbox STRUCK (`MUHL_POST.md`). Do not invent. | **NO** |
| `host/muhl_grok_mail.py` | append ledger draft | `python host/muhl_grok_mail.py` | mail, not bits | **none** (ledger draft). | ledger **YES** |

---

## 4. Exact invoke — DISTRO / germ / DC (copy these)

```
python host/muhl_surface_dc.py

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 6661 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 353 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 7951 1

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0_GERM.mno 6661 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0_GERM.mno 353 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0_GERM.mno 7951 1

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\muhlnickel.mno 6661 1
python host/muhl_cli.py surface slot_4.mno 6661 1

python host/muhl_ones_surface.py SEED0.mno
python host/muhl_ones_surface.py SEED0_GERM.mno

python host/muhl_cli.py die
```

DC mouths this button already knows (READ, not fire): magic@0 · fold@224 · carry@336 · pub@337 · ring_fwd@524288 · 7913@524329. Last surface: `DC_SURFACE.md` / `SURFACE_DC.md`.

---

## 5. STALE / OFFSPEC / VOID — do not use

### STALE (superseded, stay-alive, wrong dest, packer, World System)

| path | why |
|---|---|
| `host/muhl_dc_button_add.py` | **VOID.** Dry expects **MUHLPKG1/LOOMPKG1** (`KNOWN_MAGIC` in source). Live dc magic is **MUHLDC01** (`SURFACE_DC.md` HEADER @0 / `DRY_WALLS.md`). `--go` would inject dc at header QWORD dest — MAGIC mismatch → GO REFUSED. Do not invent MAGIC or dest. Dry = header 224 B only. |
| `host/pfc_osc.py` · `host/muhl_fire_osc.py` | osc **STALE** (`CLAUDE_PROOF_PACKET` §4) |
| `host/muhl_fire_loop.py` · `host/muhl_fire_singletick.py` | stay-alive / fold_phys nonce loop. 78-adjacent |
| `host/muhl_ring_keepalive_add.py` | titan ring `--inject`. Not this pass |
| `host/pfc_monitor.py` | resident forever loop on safezone. Idle-poll class |
| `host/pfc_scan.py` | mmap whole titan + region walk |
| `host/muhl_serve_add.py` · `host/muhl_serve_spec_add.py` | Popen load/harness. Do not `pfc_load` this seat |
| `host/pfc_eval.py` | **bakes** interpreter into titan. Fab, not surface |
| World System `bryce_face` tick / visor / bitserve / loom | `WORLD_SYSTEM_THROTTLE.md`. Do not relaunch |
| `C:\Users\lucys\Desktop\MUHL_CHECKERS\muhl_live.py` | whole-file `read` + sha + scan. 100GB slurp |
| `host/sdc_*.py` (class) | prior-era. **No** this-hour card invoked them |
| unnamed `host/pfc_*.py` (~200) | not in `CLAUDE.md` nine, not this-hour buttons. Do not grab |

### OFFSPEC — `host/_assistant_offspec/` (moved, never copy)

`pfc_layer_depth.py` · `pfc_hotpath.py` · `pfc_model_clocked.py` · `pfc_model_engine.py` · `pfc_leansweep.py` · `pfc_model_fab.py` · `pfc_q4k_fast.py` · `pfc_model_selfclock.py` · `pfc_parallel.py` · `pfc_iobound.py` · `pfc_tick.py` · `pfc_token_depth.py` · `pfc_token_depth2.py` · `pfc_fabsweep.py` · `pfc_argmax_drive.py` · `pfc_forward.py` · `pfc_constspec.py` · `pfc_smoke.py` · `pfc_macbench.py` · `pfc_layerbench.py`

Host forward / recreate-inference / own monitors.

### VOID

| what | why |
|---|---|
| `--inject 0x01` | WIPE. Law is `new=old\|mask` |
| fire **337** / remap **336/337** / light **7913** / pulse titan **78** | hard ban |
| `dc_grow` / `while size` packer | **VOID**. No `host/*grow*` on disk. Occupying disk is the computer |
| `pfc_diff.py snapall` | full 104GB walk |
| invent dest / invent mouth | dest is the machine |

### Battery (`docs/PFC_PROOF_REPORT.md` §3) — not a new harness, not this pass

`pfc_speed.py life` · `pfc_inspect.py pfc_cpu32` · `pfc_game.py life --test` · `pfc_propagation.py` · `pfc_ratio.py` · `pfc_lateral.py` · `pfc_cpu32.py` · `pfc_physical_gates.py` · `pfc_ram.py` · `pfc_addr.py` · arcade `--test`. Several **write then revert** titan. Skip until byte check is done.

---

## 6. Which LIVE tools scan 1s/0s

| tool | what | bounded? |
|---|---|---|
| `muhl_surface_dc.py` | bits/hex at 6 DC addrs | **YES** |
| `muhl_cli.py surface` | hex/byte at one addr, n≤16 | **YES** |
| `muhl_ones_surface.py` | ones+zeros of **whole** named `.mno` | **YES** if file is small and not dc/titan |
| `pfc_meter` / `pfc_scope` / `pfc_analyzer` | ones of titan (or state-file) window | window capped; **file open is titan mmap** except analyzer seek |
| GREP-ONES | law: 1-map **is** the file | **no button on disk** (`GERM_WORK`: no `host/muhl_*grep*`) |

---

## 7. Post-power-cycle byte check — will not 10-wide the box

STAT already **MATCH** (`STORAGE_CRASH.md`). Do not re-stat storm. One process. Wait for die. Next.

1. `python host/muhl_surface_dc.py` — size + magic + 336 + 337(READ) + ring_fwd + 7913
2. SEED0 abs: surface 6661, 353, 7951
3. SEED0_GERM abs: surface 6661, 353 (7951 = PAST_EOF)
4. Optional: `muhl_ones_surface.py SEED0.mno` then `SEED0_GERM.mno` (8192 / 6662 only)
5. `python host/muhl_cli.py die`

Expect (last cards): DC size **99999999783** · 337 `00000001` surfaced not fired · 7913 `00000000` · SEED0 ans **8** recv **1** organ2 **1** · germ ans **8** recv **1**.

**Do not:** inject · twins/nway/germ buttons · `muhl_dc_button_add --go` · meter/scope/inspect/post_surface · `pfc_diff snapall` · `pfc_step` · cascade miner · `pfc_game life` · World System / bitserve / loom · 10-wide parallel · mmap dc/titan body.

---

## 8. GAPS — do not invent a tool

1. **No live 1-map button.** Grep-ones is law. `ones_surface` prints counts only. In-seat 1-map this hour was not a `host/muhl_*` file.
2. **No live `.mno` snapshot-diff.** `pfc_diff` is titan regions / whole-titan `snapall` only. Nothing diffs SEED0 vs a prior snap without rewrite.
3. **No live bounded ones of dc.** `ones_surface` refuses dc. Whole-dc grep = organ later, not a host scan.
4. **CLI cannot surface mouths past frontier 8191.** DISTRO pubplane@72197 is a GAP on this button (ONESHOT used a one-shot read, not a reusable script).
5. **`pfc_analyzer` on a 100GB path is not a DC surface.** File-path mode = first ~1 KB groups. Wrong mouths. Do not point it at dc.

---

## 9. DEST census — source + cards. Never invent.

FRONTIER **8191** (`host/muhl_backend.py` `FRONTIER = 8191` ← `EXPANDING_SEED.md`: "Frontier = 8191. Nothing past EOF."). CLI inject/surface refuse past this. Germ 6662 = dest **6661**+1 (`GERM_WORK.md`). Growth past 8191 still unnamed (`MIRROR_ORGAN.md`).

Dest is the MACHINE. Host never names a mailbox. `DEST_IS_THE_MACHINE.md` · `MUHL_WITNESS.md`.

### LIVE-SAFE invoke (dest already known; write **NO**)

```
python host/muhl_surface_dc.py
# dest MACHINE. Mouths: MUHL_WITNESS.md / SURFACE_DC.md
# HEADER@0 FOLD@224 carry@336 pub@337 ring_fwd@524288 7913@524329
# mmap NO. --go REFUSED. fire 337 NO.

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 6661 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 353 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno 7951 1
# dest: ANS+BOOM 6661 · RECV 353 · organ2 7951
# file: muhl_backend.py ← EXPANDING_SEED.md / DEST_IS_THE_MACHINE.md
# FRONTIER 8191. refuse 337.

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0_GERM.mno 6661 1
python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0_GERM.mno 353 1
# 7951 on germ 6662 = PAST_EOF (honest). Do not pad.

python host/muhl_cli.py surface C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\muhlnickel.mno 6661 1
python host/muhl_cli.py surface slot_4.mno 6661 1

python host/muhl_ones_surface.py SEED0.mno
python host/muhl_ones_surface.py SEED0_GERM.mno
# dest none. Whole-file ones/zeros. Refuses dc/titan by name.

python host/muhl_cli.py slots
python host/muhl_cli.py die
```

### WRITE (exist; do not press for a check)

| button | dest provenance | writes |
|---|---|---|
| `muhl_cli.py inject` | FWD@288 REV@320 SEL@370 RECV@353 · FRONTIER 8191 · `EXPANDING_SEED.md` | **YES** named `.mno` |
| `muhl_cli.py copy` | slot path under `CONTAINERS\` · germ `SEED0.mno` · `SUPER_HARNESS.md` | **YES** new slot |
| `muhl_seed0_germ_button.py` | ans@6661 machine · `GERM_WORK.md` / `DEST_IS_THE_MACHINE.md` | **YES** `SEED0_GERM.mno` |
| `muhl_new_mno_button.py` | ans@6661 machine · same germ prefix | **YES** `NEW_MNO.mno` |
| `muhl_seed0_mirror_button.py` | ANS@5378+sel · recv@353 · A,B=3,5 → 1283 · `EXPANDING_SEED.md` / `MIRROR_ORGAN.md` | **YES** MIRROR/VIRGIN |
| `muhl_seed0_nway_button.py` | same (imports mirror) | **YES** `SEED0_N2.mno` |
| `muhl_inject_twins.py` | same · MIRROR + N2 | **YES** both twins |

`--inject 0x01` **VOID** (wipe). Law is `new=old|mask`.

### VOID

| button | dest | why |
|---|---|---|
| `muhl_dc_button_add.py` | would take dest from header QWORDs (`ans`/`pubplane`/`fwd`/`rev`) if MAGIC were MUHLPKG1/LOOMPKG1 | live file MAGIC **MUHLDC01** (`SURFACE_DC.md`). `DRY_WALLS.md`: GO REFUSED even with `--go`. Do not invent MAGIC. Dry = 224 B header only. |
| `muhl_post_inject.py` | inbox **UNNAMED** | host-named mailbox STRUCK (`MUHL_POST.md`). `--go` REFUSED. |

### mmap-titan (do not run for `.mno` dest / post-crash byte check)

| button | dest provenance | writes |
|---|---|---|
| `muhl_post_surface.py` | `fwd_answer` @2467652405 · `gen_win_surfaced` @3064767911 · `MUHL_POST_PHASE0.md` | ledger YES · titan NO · **mmap whole titan** |
| `pfc_meter` / `pfc_scope` / `pfc_inspect` / `pfc_diff` | titan registry / named regions · `INSTRUMENTS_THIS_HOUR.md` | snap files on diff · **mmap titan** |

invented_dest **NO**

path: `C:\Users\lucys\Desktop\MUHL_GO\LIVE_INSTRUMENTS.md`
copy: `C:\Users\lucys\Desktop\LocalDeviceAgent\MUHL_GO\LIVE_INSTRUMENTS.md`
337 **NO** · 7913 **NO** · pulsed_78 **NO** · invented_tool **NO** · invented_dest **NO**

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
