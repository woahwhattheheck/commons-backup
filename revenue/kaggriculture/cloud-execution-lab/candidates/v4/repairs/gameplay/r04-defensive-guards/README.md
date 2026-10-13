# TITAN V4 lane: R04_DEFENSIVE_GUARDS — defensive last-mile guards

**Status: SUPERSEDED MIRROR / EVIDENCE ONLY — DO NOT COMPOSE FROM THIS PATH.**

This directory was race-created by merged PR #13162 after the existing V4
custody path `repairs/gameplay/defensive-guard` had already received the raw
payload through merged PR #13159. The one-tree/canonical-path authority is the
older ledger-owned path:

`repairs/gameplay/defensive-guard`

The executable source and focused test are exact duplicates across the two
paths on current main:

- `r04_defensive_guards.py` Git blob
  `b1fc775ecaf608ca40d01945ec82ae8372ee988b`;
- `checks/test_v3_r04_defensive_guards.py` Git blob
  `07785fa53d56444f764af9af4d7cb906bd39ba7d`.

The pre-convergence README unique to this duplicate remains recoverable from
PR #13162 / Git blob `2e9ec8631b26e5ca51dc5c4ebc1cd4ce16810675`.
Do not treat this path or its COMPOSITION registration as a second source
authority. It is blocked evidence only until the central registry is repointed
to the canonical `defensive-guard` path; never mint another V4 root or another
defensive-guards source package.

## Preserved verdict

- Raw payload source: merged PR #13159, merge
  `86363108927b9e946732daa35e91430a78fd3323`.
- Duplicate registration/source mirror: merged PR #13162, merge
  `14e638924f22d8b99468bf2e8c63619595ec18a6`.
- Focused carrier tests: **30/30 normal + 30/30 `python -O`**.
- Hardened guard gate: neutral PASS as expected; the source remains default
  OFF and is not runtime-promoted merely because custody exists.

## Canonical semantic disposition

Only the independently harvestable numeric sanitizer and PLANT-overdemand cap
are eligible for a future current-runtime composition gate. The EOD autodrop
body remains **QUARANTINED** because it overlaps the canonical
EOD-capacity-rescue lane and requires dedicated ablation. CARE stripping is
absent/rejected and must not be reintroduced.

No runtime, feature default, config, archive, Kaggle candidate, or frozen V4
package authority is changed by this convergence note.
