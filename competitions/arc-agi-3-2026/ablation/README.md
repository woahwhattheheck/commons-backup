# ARC3 SAGE ablation harness

This package is a deterministic, data-free experiment rail for the four explicit post-SAGE questions that otherwise invite confounded anecdotes:

1. **Full animation vs settled frame.** Paired scenarios differ only in whether intermediate action frames are retained. The synthetic control deliberately erases a transient cue in the settled frame.
2. **Information gain vs random probing.** Opaque shuffled action IDs are identical between arms; only the probe-selection policy changes.
3. **Coordinate reduction vs a superset.** Both arms use the same target-independent ranking. The treatment performs an offline scene scan to eliminate impossible background cells; those offline scans are counted as `simulated_expansions`, never real actions.
4. **Cross-level transfer vs cold start.** The treatment may reuse effect signatures across translated levels, but never literal coordinates or action IDs. It verifies evidence under the new level before reuse.

Every experiment is paired by exact `(experiment_id, seed)` and has the same real-action budget. Receipts keep real actions separate from offline/simulated work and report success, action counts, invalid/repeated actions, evidence acquisition, transfer reuse, abstention and budget exhaustion. The aggregate adds deterministic bootstrap intervals and a paired sign-flip diagnostic; these are synthetic research diagnostics, not official ARC statistics.

## Run

From `competitions/arc-agi-3-2026`:

```bash
python -m ablation.test_ablation
python -O -m ablation.test_ablation
python -m ablation.benchmark --seeds 64 --budget 24 --output /tmp/arc3-ablation
```

The benchmark writes canonical JSON receipts and Markdown summaries. `verify_experiment()` recompiles aggregates from raw trial rows, rejects missing paired arms, duplicate/changed trial identities, metric-domain violations, action-budget overflow, tampered digests, resealed authority escalation, and aggregate/report drift.

## Adapter boundary

`synthetic.py` is deliberately a no-network reference adapter. A later authorized public-game trace adapter may produce the same `TrialRow` contract if it binds exact trace/source digests and preserves paired treatment/control seeds and budgets. This package does **not** call Kaggle, ARC servers, APIs, or paid compute.

## Authority ceiling

A valid receipt never authorizes or claims: official game action, rules acceptance, Kaggle submission, leaderboard score/rank, prize, payment, cash, or revenue. Checked-in results are synthetic/data-free evidence only.
