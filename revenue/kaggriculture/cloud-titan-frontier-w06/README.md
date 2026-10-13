# TITAN frontier W06 — Apex counterexample

Operation: `titan-frontier-W06-apex-counterexample-20260909-01`.

This lane turns the repeatable Apex loss at seed `2611002002` into source-bound evidence. It verifies and safely extracts the exact 109-file current release, runs the existing process-isolated official evaluator in both candidate seats, captures every parent-interpreter transition, locates the permanent deficit onset and largest one-step expansions, and performs a small deterministic screen of one-returned-action interventions.

The full baseline traces are retained as deterministic gzip JSON. `REPORT.json` contains terminal score comparisons, loss-onset events, ranked cash outflows, and counterfactual terminal-margin deltas. `SUMMARY.md` is human-readable; `MANIFEST.json` hashes every retained artifact.

## Safety and interpretation

This is offline diagnostic compute. It does not contact Kaggle, submit an agent, spend a paid provider budget, choose a production policy, or mutate the canonical archive. Agent modules are executable code and must run in an isolated worker.

A counterfactual is a **screening lead**, not final causal proof. The runner substitutes one action after the agent returns it; private agent state may therefore remember the original decision. A controller repair still requires a source-level explanation, exact regression tests, both-seat replay, and fresh-seed nonregression evidence before F1 integration.

## Local contracts

```bash
python3 -m unittest discover -s revenue/kaggriculture/cloud-titan-frontier-w06 -p 'test_*.py' -v
```

The hosted workflow additionally verifies the pinned release hash, file count, source-manifest hash, official engine pin, and Apex source before running the two baselines and bounded intervention screen.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
