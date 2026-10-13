# TITAN V3 — the one integration tree

Owner rule (2026-09-09): every fleet lane lands **here**, as a deterministic key in
`TITAN-CONFIG.json` plus a module and a check, never as another sibling candidate
directory. `exports/titan-current.tar.gz` and the Kaggle submission stay with Bryce;
this tree is what he promotes from.

## V4 continuation — one tree, one integrator seam

V4 continues this directory rather than creating a sibling candidate tree. The only
canonical V4 target is `titan/v4-20260911`; source branches and pull requests are
short-lived review/transport surfaces, not alternate V4s.

To keep parallel swarm work convergent:

1. **Earliest claim owns a mechanism.** Later overlapping implementations are donor,
   review, or evidence material for that owner rather than additional feature keys.
2. **Source PRs prefer local surfaces.** A speculative/default-OFF lane should carry
   its helper plus focused standard-library checks. Avoid repeatedly editing shared
   `apply_v4.py`, runtime/config anchors, or generated V4 plumbing merely to prove the
   helper unless the seam itself is what the lane is testing.
3. **Shared wiring is serialized.** The integrator batches accepted keys into the
   current canonical head, using exact-head/non-force updates. Rebase or reconcile a
   stale lane onto canonical; never solve drift by spawning another V4 tree.
4. **Landing and promotion are separate decisions.** A helper may land shipped OFF
   after semantic/safety review. Turning it ON requires paired/common-gate evidence on
   the same seeds, seats, and opponents; a negative gate remains a durable receipt,
   not an excuse to preserve a harmful default.
5. **Duplicates and negative mechanisms close unmerged.** Keep their PRs/results as
   chain-of-custody evidence, but do not keep multiple keys or open merge candidates
   for the same allocator/policy surface.
6. **OFF must remain identity.** Every V4 seam fails closed on malformed/ambiguous
   state and preserves the exact parent action/object where its theorem is not proven.

This protocol is intentionally about integration ownership, not gameplay policy. It
keeps the swarm free to explore while ensuring all accepted work becomes one ordered
V4 rather than a collection of mutually drifting variants.

## Layout

- `overlay/` — the lane modules (`e11_rival_sell.py`, `rival_model.py`, `e20_hire_guard.py`,
  `shop_arb.py`, `l01_mechanics.py`) and the checks (`checks/test_v3_features.py`,
  `checks/test_v3_l01.py`); copied over the canonical extract.
- `apply_v3.py` — exact-anchor edits of the canonical `titan_runtime.py`, `scheduler.py`,
  `frozen_selected.py`, `TITAN-CONFIG.json` and `TITAN-RELEASE.md` (Features fields, the
  seams, the keys shipped off); every anchor must match exactly once or the build fails.
- `build_v3.py` — rebuilds the full package from `../../exports/titan-current.tar.gz`
  (SHA-256 pinned in `V3-MANIFEST.json` under `base.sha256`) plus `overlay/`, with fixed
  tar metadata, so the archive bytes are a pure function of (canonical, overlay).
- `FILES.json` — SHA-256 of every file in the built package; a shard verifies its
  materialised tree against it.
- `V3-MANIFEST.json` — base archive, overlay hashes, built archive hash, and the lane map.
- `dist/` — build product (`titan-v3.tar.gz`, `titan-v3.sha256`); not committed.

## Lanes

| key | lane | lineage | seam | ships |
|---|---|---|---|---|
| `e11_rival_sell` | E11 public-price-drop SELL deferral with exact future absorption ticks | TESSERA (Gemini) → G01 (Grok Build #2, PR #11371) → ARGUS semantic repair (`candidates/v3-g01-argus-safe`) | seller-owned seam before pending accounting, in `scheduler.py` and `frozen_selected.py` | off; panel decides |
| `rival_model` | O01 rival archetype; appends one BUY_LAND only into a free market slot, never edits SELLs | same chain | `TitanAgent._v3_post`, completed path, before `_finish_production` so `early_capital` sees the queue | off |
| `e20_hire_guard` | E20 low-demand HIRE limiter, queue positions preserved | same chain | `TitanAgent._v3_post` | off |
| (none) | O02 shop priority multiplier | same chain, ARGUS A7 | `shop_arb.py` is a tested scoring-only callable; no production seam, `absorption()` is never patched | n/a |
| `early_capital` | horizon-aware same-queue capital ordering | canonical | already in the canonical archive | on |
| `l01_land`, `l01_sheep`, `l01_day0buy`, `l01_leanplant` | L01 leader mechanisms on the Arlene MAIN tape: BUY_LAND at steps 74/98, COW→SHEEP after step 1, the SpaTaro day-0 basket, last 92 wheat plants to PASS | Grok Build #5, PR #11459 (`candidates/v3-l01-leader-mechanics`) | `TitanAgent._v3_l01_install` at the end of `_initialize` patches `controller.R` once | off; panel decides |
| `r01_shop_router` | R01 yhay81 Shop Router 0909 base policy and its 13 tapes | yhay81, Apache-2.0 | first line of `TitanAgent.act`, whole-turn delegate | off |
| `r02_route_bank` | R02 the same tapes seated as the canonical MAIN route; TITAN keeps the market | R01 tapes | `TitanAgent._v3_r02_install` | off |
| `r03_full_router` | R03 the complete published shop-router policy (base + layers V216-V234) | prvsiyan, Apache-2.0 | first line of `TitanAgent.act` | off |
| `r04_sale_window` + `r04_sale_horizon`, `r04_open_roundtrip`, `r04_row_order`, `r04_evening_flush` | R04 R03 with the E184 sale window outermost, horizon 8, SELL row order on the exact price curve, evening flush of WOOL/MILK/STRAWBERRY/MELON at hours 21-23 | Dmitrii Gluzdov E184, Apache-2.0 | first line of `TitanAgent.act`; precedence R04 > R03 > R01 | off in the package; on in the V3.0 submission |
| `l01_tranche` | L01 live sale tranches from day 28 (WHEAT ≤57, CARROT ≤32, pack the other shed products) | same | `TitanAgent._v3_post_final`, after `_finish_production` | off |
| `joint_actor_assignment` (reserved) | P07 joint actor assignment | Grok Build #6 | lands here | pending |
| `terminal_liquidation`, `land_unlock_timing`, `opening_script`, `tight_guard` (reserved) | T01–T04 | TESSERA designs on Slack C0BUH19DW80; Grok Build #2 | lands here | pending |
| — | S02 receding-horizon MPC | Grok (`candidates/v3-s02-mpc`) | excluded: H=6 lost every smoke game by 88k–108k | no |
| — | S11 adversarial bank, S11b leader clones, S12 replay diagnostics | Grok Build #3/#5, #4 | test infrastructure under `bank/` and `docs/`, not candidate code | n/a |

Parameters carried with the keys: `rival_dump_price_drop` 15.0, `rival_dump_lookback_steps` 8,
`e11_min_future_absorption` 2, `e20_max_hires_per_day` 3, `e20_min_unwatered_crops` 3,
`g01_early_expander_step` 144, `g01_land_cash_floor` 0.

## Releases

| version | tree commit | package | submission archive | Kaggle |
|---|---|---|---|---|
| 3.0 | `2ff565d0e` | `c30e5b0a` (126 files) | `titan-v3.tar.gz` sha256 `a0629844`, 526,839 bytes: the package with `r04_sale_window` true (horizon 8, row order on, evening flush on, opening round trip 0) | submission 56159263, 2026-09-11 05:32 UTC |

`make_submission.py` rebuilds the submission archive from the package with that one
config edit and the same fixed tar metadata. Everything up to the 3.0 tree commit is V3.0;
all later work is V3.1 (`V3-MANIFEST.json` `releases`).

## How a lane lands

1. a module under `overlay/` — pure function, `enabled` passed explicitly, no environment
   reads (the shard agent process never sees shell variables; the G01 env-flag panels
   were cell-identical to base for that reason)
2. a `Features` field in `overlay/titan_runtime.py` and the key in `overlay/TITAN-CONFIG.json`,
   default off
3. a check in `overlay/checks/` (standard-library `unittest`; the shard VMs have no pytest)
4. `python build_v3.py` then `python build_v3.py --check`; PR to main
5. a fleet panel: the variant is the materialised tree with the key flipped in
   `TITAN-CONFIG.json`, paired against the all-off build on the same seeds, seats and opponents

Turning every key off must leave the canonical runtime path untouched; the all-off panel
arm is compared cell-for-cell against the canonical export on the same seeds.

## Build and check

```bash
python build_v3.py
python build_v3.py --check
python build_v3.py --tree /tmp/v25/cand_v3off        # materialise the package for a shard
python -m unittest -v checks/test_v3_features.py checks/test_v3_l01.py   # after --tree, run from that tree
```

## Panel recipe (Haiku shard, chain of custody)

```bash
# canonical bytes
curl -fsSL -o /tmp/v25/canon.tar.gz "https://raw.githubusercontent.com/woahwhattheheck/commons/main/revenue/kaggriculture/cloud-execution-lab/exports/titan-current.tar.gz"
echo "17f536087b3a6baf4ae1222a051285766a3ea8c2ca5af6edc190d4f527e12b86  /tmp/v25/canon.tar.gz" | sha256sum -c -
mkdir -p /tmp/v25/cand_v3_e11 && tar xzf /tmp/v25/canon.tar.gz -C /tmp/v25/cand_v3_e11
# overlay bytes from the pinned commit (ten files), then verify against FILES.json
B="https://raw.githubusercontent.com/woahwhattheheck/commons/<commit>/revenue/kaggriculture/cloud-execution-lab/candidates/v3"
for f in e11_rival_sell.py rival_model.py e20_hire_guard.py shop_arb.py titan_runtime.py scheduler.py frozen_selected.py TITAN-CONFIG.json TITAN-RELEASE.md checks/test_v3_features.py; do curl -fsSL -o "/tmp/v25/cand_v3_e11/$f" "$B/overlay/$f"; done
python3 - << 'EOF'
import json;p='/tmp/v25/cand_v3_e11/TITAN-CONFIG.json';d=json.load(open(p));d['e11_rival_sell']=True;json.dump(d,open(p,'w'),indent=2)
EOF
V25_REPO=/home/user/commons /tmp/v25/.venv/bin/python -B tools/v25_sims/gauntlet.py --seeds <seeds> --opponents arlene,apex,kaito_v43,cok_v10,public_bt12,v1_submitted --workers 8 --action-timeout 15.0 --candidate /tmp/v25/cand_v3_e11/main.py --outdir /tmp/out_v3_e11
```
