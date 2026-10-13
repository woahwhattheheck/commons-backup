# Submitted V2 unit-route divergence audit

This directory preserves an exact, fail-closed analysis of four submitted TITAN
V2 Kaggle replays. It was built to answer a narrow question raised by the V2
leaderboard regression: when a deterministic controller emits the same unit tape
on different states, are all commands still bound to physical actors?

The answer is **no in one observed loss**, for a concrete reason much narrower
than “open-loop routes are bad.” Episode `107130860` enters step 25 with `$6`,
requests four executable `HIRE` orders, completes three, and exits with `$2`.
Steps 26–48 then issue four hired-hand commands while only three hands exist:
exactly 23 commands are unbound to any input actor. That game loses by 13,112.
The three comparison replays contain no underfilled HIRE event.

This is observed transition evidence, not a counterfactual score claim. The audit
does not assert that preserving one more dollar would have won the game, nor that
deterministic routes are generally defective. In particular, every replay has a
separate steps 123–144 surplus-command interval after a fully completed HIRE row;
the report labels those intervals `no_observed_hire_fill_shortfall` rather than
folding them into the step-25 defect.

## Exact retained inputs

Raw replay bytes are not duplicated in Git. The manifest binds the four source
files by episode, seed, seat, opponent and compressed SHA-256:

| Episode | Seed | Opponent | Seat | Result / margin | gzip SHA-256 |
|---:|---:|---|---:|---|---|
| 107130860 | 539131249 | Apa | 1 | LOSS / -13,112 | `9337c7c734eff0804400f732d48c155dedb6d6f12b3afdefbc620f78fdfc686b` |
| 107140666 | 1834999074 | cununn | 1 | WIN / +3,601 | `120f9a62911e897adb085d7397f1f3a67100bf8c241065e4e424adb540bdf916` |
| 107162106 | 1885507524 | ominteam | 1 | WIN / +2,684 | `b41bfdfcef73f35d71d617fb1b025e2bc25422600e43816805363d5470fa496f` |
| 107172662 | 65112964 | Gappy | 1 | WIN / +12,664 | `385f506e7fd0ea82b963407f7d9dd6231f02f5d324d44b3a1f4cdad7f39f6279` |

The original local audit recorded report payload SHA-256
`38480d11f872bf6abcb017b2c86a4ca3e5b9f4f2932e01e6c0e7d787c643fbd9`,
but `evidence/report.json` is not retained in this Git tree. This checkout
therefore does not independently bind that historical digest or the replay-derived
numeric statements in this README unless the four exact manifest-bound replay
files are supplied and regeneration produces matching report bytes. Treat that
material as `HISTORICAL_EXTERNAL_EVIDENCE` until such regeneration is performed.

## Replay orientation

Hosted Kaggle replay observations omit the synthetic `step` field used by local
drivers. The analyzer binds each observation through exact `day`, `hour`, player,
and frame index. It then proves the important replay orientation from physical
transitions: action row `k` maps observation `k-1` to observation `k`. Every
same-day positive hand-count delta must be no greater than the number of `HIRE`
orders inside row `k`'s official executable market prefix. A shifted action stream
therefore fails before any no-op or actor-binding statistic is emitted.

## Cross-replay facts

Episodes `107130860`, `107162106` and `107172662` have byte-identical hired-hand
action arrays for all 720 frames. Against each latter win, the loss has 690 frames
where the same complete unit action is applied to a different physical input and
19 frames where the same unit action has different actor binding. Episodes
`107162106` and `107172662` share the complete farmer and hired-hand tape while
physical states match in only 80 of 720 frames; their observed direct effect class
nevertheless remains equal. These facts establish rigidity, but the report does
not score rigidity itself as good or bad.

## Fail-closed surface

`unit_route_audit.py` rejects digest drift, copied replay bytes, duplicate episode
IDs or JSON keys, wrong agent seat/opponent/seed declarations, incomplete episode
grids, action/observation shifts, structurally malformed action containers and
key quantity types, bool-as-int quantities, non-square own boards, actor/inventory
cardinality drift, and output replacement failure. Market HIRE counts use only
`market[:maxMarketOrdersPerTurn]`.

This is not a complete validator for the documented Kaggriculture command grammar.
For the transition proof, action rows are checked for structural/type safety while
remaining compatible with the official interpreter semantics that produced the
replays. In particular, zero-argument `HIRE`/`BUY_LAND` rows with trailing fields
and unknown unit-op strings are not rejected solely because the documented grammar
would reject them; the synthetic fixtures also use `WAIT` where the canonical
grammar documents `PASS`. An `AUDIT_PASS` therefore certifies the stated replay
orientation and actor-binding invariants, not canonical command-schema conformance.

The synthetic contract and retained-report checks currently run 28 tests:

```sh
cd revenue/kaggriculture/cloud-execution-lab/analysis/v2-unit-route-divergence
python -B -m unittest -v test_unit_route_audit.py test_retained_report.py
```

To regenerate the report when the four exact gzip files are present:

```sh
python -B unit_route_audit.py \
  --manifest evidence/input-manifest.json \
  --replay-dir /path/to/exact/replays \
  --output evidence/report.json
```

## Scope

No gameplay source, controller route, selected-action transform, canonical archive,
configuration, provider, Kaggle submission, or spend is changed here. The source
hypothesis suggested by the witness is a narrowly certified cross-turn committed
HIRE reserve. It requires a separate ownership check, source review, and matched
engine evidence before activation or promotion.
