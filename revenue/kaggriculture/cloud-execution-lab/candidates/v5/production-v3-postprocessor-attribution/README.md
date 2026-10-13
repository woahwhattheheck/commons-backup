# Production-v3 postprocessor attribution

This is one bounded screening carrier on the single merged TITAN V5 production-recovery line. It does **not** create another producer tree, flip a default, authorize a release, or submit Kaggle.

## Why this exists

Merged production-v3 archive `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239` repairs the native import seam while preserving 91/92 production-v2 members and the exact gameplay config. Fresh native seed `1209129901` completed against Apex v7 and Arlene v14 in both seats:

- full production-v3 beats submitted V3.1 margin by **+258** against Apex and **+220** against Arlene;
- full production-v3 own score is **-237** versus V3.1 against Apex and **+332** against V3.1 against Arlene;
- full-context `town_procurement=false` loses another 2 Apex / 1 Arlene own-score point and the same margin amount;
- the merged aggregate postprocessor bypass returns exactly to the V3.1 terminal scores on this seed.

The aggregate comparison therefore justifies localization, but the strict champion rule correctly blocks the full candidate on the Apex own-score regression. The goal here is to identify the responsible stage or consumer boundary before anyone opens single-feature forks.

## Exact baseline authority

- production-v3 archive SHA256: `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
- `TITAN-CONFIG.json` SHA256: `ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af`
- repaired v3 `main.py` SHA256: `b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035`

The materializer reuses the already-reviewed R04/FrozenSelected semantic pins from the aggregate-survivorship carrier and rotates only the `main.py` identity to production-v3. It authenticates the whole archive before emitting anything. Every treatment changes only `TITAN-CONFIG.json`; the other 91 members remain byte-identical. The machine receipt records the complete 92-member SHA256 map for the baseline and every arm, and the exact-head workflow independently reconstructs those maps from the reproduced package.

## Original three stage knockouts

These remain semantically unchanged from the merged v1 screen. They start from full production-v3 and keep `consumer=frozen`, `town_procurement=true`, and every unrelated flag unchanged.

| Arm | Flags turned off | Stage screened |
|---|---|---|
| `seed_hire_off` | `seed`, `funding`, `redundant_hire` | selected-action seed/funding/hire enrichments after FrozenSelected |
| `inventory_spatial_off` | `operating_stock`, `idle_fertilizer`, `crop_release` | inventory/stock/spatial/fertilizer/crop finalization family |
| `late_market_off` | `market_pressure`, `early_capital` | late market-pressure reorder + early-capital reorder |

They are stage knockouts, not an assertion that effects are additive.

## Matched consumer-boundary pair

A lone `consumer=parent` arm against the full baseline is invalid evidence. The shipped production entrypoint rejects `town_procurement=true` whenever the consumer is not frozen, while `Features` rejects `redundant_hire`, `idle_fertilizer`, and `crop_release` on a non-frozen consumer. Turning those required leaves off only in the parent treatment would confound the consumer boundary with several config changes.

The carrier therefore emits a matched conditional pair:

| Arm | Consumer | Required leaves off |
|---|---|---|
| `consumer_boundary_control` | `frozen` | `redundant_hire`, `idle_fertilizer`, `crop_release`, `town_procurement` |
| `consumer_boundary_parent` | `parent` | the exact same four leaves |

The materializer machine-proves that the two resulting configs differ on exactly one key: `consumer`. `seed`, `funding`, `operating_stock`, `market_pressure`, and `early_capital` remain at their authenticated production-v3 config values in both archives.

That one-config-knob match does **not** mean the treatment is a pure FrozenSelected-only runtime effect. In the pinned runtime, changing the consumer to parent also prevents SpatialTempo installation, makes operating-stock finalization a no-op, suppresses the frozen-only feed-stock finalizer, and makes early-capital finalization a no-op. The receipt publishes these effective parent gates explicitly. Interpret treatment-minus-control as the **consumer-boundary bundle** and nothing narrower.

## Materialization

```bash
python -B materialize_stage_knockouts.py \
  --baseline /path/to/production-v3.tar.gz \
  --bundle postprocessor-screen.tar.gz \
  --receipt postprocessor-screen.json
```

The bundle contains `SCREEN.json` plus five deterministic nested archives: the original three stage knockouts and the matched boundary pair. Publication uses the existing cooperative create-only pair routine.

## Native follow-up

After exact-head source gates are green, first run the original three stage knockouts on seed `1209129901`, Apex v7 + Arlene v14, both seats, with the same official interpreter/engine/opponent identities/RNG/timeouts as `selective-carrot/native-9901`. Reuse the existing V3.1, V4, full production-v3, town-off, and aggregate-bypass controls; do **not** rerun them merely to populate the screen.

If one of those three restores Apex own score without erasing the positive V3.1 margin delta, widen that minimal composition before finer splitting. If all three miss, run the two consumer-boundary archives in the same workspace and compare `consumer_boundary_parent` **only** against `consumer_boundary_control`. Never attribute the parent treatment directly against full production-v3; the required-off leaves make that comparison confounded.

A one-seed result is development evidence only and cannot clear the champion/release transaction by itself. No runtime/default/config pointer/CURRENT/release/Kaggle mutation is authorized by this carrier.
