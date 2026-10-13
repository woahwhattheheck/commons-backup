# TITAN hosted-strength calibration

This additive lab consumes paired complete-game receipts; it does not run an
engine, import an agent, reserve seeds, or modify the frozen PR10005 adapter.
Its first target is exact PR9997 against submitted baseline 56081391. Those
games are owned and executed elsewhere, so their per-game output is an input,
not a panel duplicated here.

`calibrate.py` requires exactly two rows (seats 0 and 1) for every seed. Wins,
ties, and losses are derived from terminal cash when present. Ties count as a
half-win. It reports a penalized Bradley–Terry log-odds estimate and the same
quantity on the conventional 400-point Elo scale. The 95% interval is a
deterministic percentile bootstrap over whole seed clusters, retaining both
seats in every draw. This handles mirror dependence at the assigned grouping
level; it does not solve matchup nontransitivity or opponent-population shift.
The consumer also refuses input unless it names the exact PR9997 archive and
the retained Arlene-v14 archive/source digests recorded in
`baseline-evidence.json`; a generic lab label cannot pass this boundary.

Kaggle's [competition ranking page](https://www.kaggle.com/competitions/kaggriculture/overview/prizes)
documents only the direction of rating changes:
wins increase skill rating, losses reduce it, ties tend to leave it even, and
the change depends on opponent rating. No exact update equation or constant is
present in the retained engine/package or public evaluation text. Therefore
the Elo-scale output is explicitly an empirical proxy, not a reconstruction of
the hosted backend.

Absolute score anchoring adds the grouped-bootstrap proxy delta to a supplied
timestamped baseline score or temporal score band. A rank interval is emitted
only with at least three distinct, monotone score/rank anchors captured at one
timestamp and only when both score endpoints are inside the anchors' range.
The implementation refuses extrapolation. Longitudinal checkpoints of our one
submission do not meet this condition.

For the provisional reports, `score=2203.3` is the newest recovered point and
2166.7–2215.4 is the observed envelope across the six retained checkpoints from
18:56Z through 01:24Z. Combining that temporal envelope with the bootstrap is a
conservative sensitivity band, not a confidence interval for the hosted
backend. The point estimate remains separately reported.

Run:

```bash
python calibrate.py claude-paired-input.json --output result.json
python -m unittest -v test_calibrate.py
```

Input schema:

```json
{
  "source": {
    "candidate_archive_sha256": "95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153",
    "baseline_archive_sha256": "7dcb73bb0d8bc6d0d003b107fcb47c93f9e77c4d8c64d39fec8bd54d406bb407",
    "baseline_candidate_sha256": "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
  },
  "games": [
    {"seed": 1, "seat": 0, "candidate_cash": 101, "baseline_cash": 100},
    {"seed": 1, "seat": 1, "candidate_cash": 99, "baseline_cash": 100}
  ],
  "baseline_anchor": {
    "submission_id": 56081391,
    "score": 2203.3,
    "observed_at": "2026-09-08T01:24:38.364247Z"
  }
}
```

`baseline-evidence.json` retains the exact main archive digest, provider
identity fields, and recovered score/rank checkpoints. Size, filename, and
description concordance do not prove remote byte equality because the provider
record supplies no content digest; the identity conclusion says so directly.
`anchor-inventory.json` records why the stronger runnable rivals cannot serve as
absolute hosted anchors without a version-specific submission/rating binding.
The three additional input files retain Claude's frozen-SELL and Apex rows.
Every report includes empirical W/T/L probabilities with whole-seed bootstrap
intervals; absent categories can remain zero in a nonparametric bootstrap and
must not be read as impossible future outcomes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
