# TITAN V5 authenticated V3.1 champion ratchet

This is the one champion-floor evidence carrier for V5. It exists because local no-regression versus a V4/current incumbent cannot prove the owner target: **V5 must outperform exact submitted V3.1**.

The earlier self-asserted report design was closed unmerged. This successor consumes actual result roots and actual archive bytes. It does not trust caller-selected opponent IDs, seeds, score rows, panel cardinality, evaluator identity, or engine identity.

## Fixed authority

The gate hard-pins:

- exact submitted V3.1 identity: source commit `a90d888f03987ef0b35cfd20ec3519c6144db08a`, submission id `56172377`, archive SHA-256 `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`;
- canonical top-30-union manifest SHA-256 `510ca5c5438fb65d29755f2009f07bb85bbf3e8963054b88c4abe3ec3737924e`;
- the Git blobs of the Commons evaluator, offline loader, and pack adapter;
- the three pinned official engine Git blobs.

The canonical manifest has 41 submission versions and exactly three unfiltered complete recorded games per version. The gate derives all 123 fixture IDs and their exact seeds/submission identities from those authenticated bytes. An authorizing panel therefore contains exactly **246 cells per policy**: every fixture under both candidate seats.

For each V3.1/incumbent/candidate result shard, the gate requires `group=all`, the complete declared shard set, exact manifest-derived modulo fixture membership, both seats, the exact expected `selected_fixtures` count, matching archive SHA, matching evaluator/loader/engine authority, complete status, 719 callbacks, exact seed/submission/family/orientation metadata, and finite terminal scores. A run made with `--limit` or a favorable 2-of-N subset cannot masquerade as complete.

Cross-policy shard index identity must match shard-for-shard, and the exact 246 cell keys must match across all three policies. Every consumed `run.json` and cell JSON is single-read and SHA-bound into the receipt.

## Champion theorem

A PASS requires all of the following on the authenticated same panel:

- candidate terminal **own score** is non-regressive versus the incumbent globally;
- candidate terminal own score is **strictly greater** than exact V3.1 globally;
- candidate own score is non-regressive versus both baselines in every submission × seat stratum (three replay seeds per stratum);
- no incumbent or V3.1 win/tie becomes a candidate loss;
- paired margin is non-regressive versus both baselines as a secondary safety condition.

Margin is deliberately not the primary champion objective. The retained predecessor where candidate margin improves while candidate own score falls must reject.

## Release boundary

A champion receipt intentionally emits `release_authority=false`. It is evidence-ready, not pointer-write authority by itself. The single V5 release transaction must authenticate and consume the exact receipt alongside the generic incumbent-economics receipt before any current/archive pointer mutation. This carrier does not mutate gameplay, defaults, runtime configuration, archives, release pointers, or Kaggle.

Example:

```bash
python -B champion_gate.py \
  --kg-root /path/to/revenue/kaggriculture \
  --engine-dir /path/to/pinned-engine \
  --v31-archive /path/to/exact-v31.tar.gz \
  --incumbent-archive /path/to/incumbent.tar.gz \
  --candidate-archive /path/to/candidate.tar.gz \
  --v31-root /path/to/v31-shard-0 --v31-root /path/to/v31-shard-1 \
  --incumbent-root /path/to/inc-shard-0 --incumbent-root /path/to/inc-shard-1 \
  --candidate-root /path/to/candidate-shard-0 --candidate-root /path/to/candidate-shard-1 \
  --output champion-receipt.json
```
