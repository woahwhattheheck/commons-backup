# E17 public-regime history source checkpoint — 2026-09-09

Operation: `titan-v25-orders-20260909-E17`

## Scope

This checkpoint adds a run-only E17 candidate without changing the canonical `scheduler.agent` entrypoint or any default configuration. The candidate wraps the existing SELL scheduler and replaces only its scalar rival-supply stress signal with bounded public-regime evidence.

The helper:

- counts a yield decrease as harvest evidence only when the same producer remains visible at the same tile;
- keeps the existing eight-turn concept as the short signal;
- extends evidence to a 24-turn bounded rate only after at least two distinct public event timestamps;
- treats market-flow evidence as a conservative rival admitted-supply lower bound after known town/shop absorption and the full requested own SELL quantity are removed;
- leaves residual flow unknown when the prior returned action is unavailable;
- never adds harvest and market-flow quantities together, avoiding obvious double counting;
- forgets pre-change evidence only after the public production mix differs for two consecutive observations;
- caps the stress size at the physical shed-capacity bound and assigns no probability or hidden-stock interpretation.

`regime_scheduler.agent` is the explicit experimental entrypoint for matched E17 games. `scheduler.agent` remains byte-unchanged by this checkpoint.

## Cloud checks run

Local pure-stdlib checks in the GPT cloud container:

```text
python -m unittest -v test_seller_regime_history.py
Ran 9 tests in 0.000s
OK

AST_OK seller_regime_history.py
AST_OK regime_scheduler.py
AST_OK test_seller_regime_history.py
```

The first test pass exposed one causal timestamp bug: inferred residual market-flow evidence was initially stored at the prior market step and was pruned when the initial public regime began. The implementation now timestamps that evidence at the current observation, when it first becomes knowable. The corrected suite is the 9/9 result above.

## Test contracts

1. Same-producer yield decrease is harvest evidence.
2. Producer removal/replacement is not labeled a harvest.
3. One isolated event does not survive beyond the short window.
4. Repeated events support bounded long-memory stress.
5. Known town absorption is not attributed to the rival.
6. Requested own SELL quantity is removed before the rival lower bound.
7. Missing previous returned action keeps residual flow unknown.
8. Public production-mix reset requires persistence and clears older evidence only after confirmation.
9. Stress is capped by capacity.

## Boundaries / remaining E17 work

The container could not materialize the repository through shell Git because DNS resolution for `github.com` was blocked. Connector reads and writes remained healthy, so source publication uses GitHub connector Git Data rather than shell credentials/network.

No official-engine full games were run in this checkpoint. Therefore there is **no terminal-cash, win-rate, downside, runtime, or default-promotion outcome**. The next experiment remains a source-pinned matched screen of canonical `scheduler.agent` versus `regime_scheduler.agent`, both seats, periodic/switching/pressure/symmetric opponents, followed by untouched holdout before any canonical enablement.

## Post-merge review correction — 2026-09-09

Independent exact-head review of PR #11110 found two bounded source regressions. This source-author follow-up corrects both without changing the canonical scheduler entrypoint or enabling the candidate by default.

1. **Opening regime lifecycle.** The run-only wrapper now feeds the opening public observation into `PublicRegimeHistory` before any transition exists. That seeds only the public production baseline; a step0→1 production-mix switch now enters the existing two-observation confirmation path instead of being silently adopted as the initial baseline.
2. **Cross-stream repeat noise.** Long-memory admission is now evaluated per evidence stream. Harvest history needs repeated harvest timestamps before harvest magnitude contributes; residual-flow history independently needs repeated flow timestamps before flow magnitude contributes. Distinct timestamps split across the two streams no longer combine to reactivate an old outlier.

Corrected local checks:

```text
python -m unittest -v test_seller_regime_history.py
Ran 12 tests in 0.004s
OK

AST_OK seller_regime_history.py
AST_OK regime_scheduler.py
AST_OK test_seller_regime_history.py
```

New adversarial contracts cover the opening wrapper lifecycle, the exact review witness `harvest=(2,90)` plus `flow=(10,1)` at step 20 (now `long_rate=0`, `stress=0`), and the positive control that two repeated flow events still form bounded long memory.

This correction remains **source-only and run-only**. It does not add official-engine full-game evidence, terminal-cash or win-rate evidence, or a default-promotion claim. The matched E17 screen and untouched holdout are still required before any canonical enablement.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
