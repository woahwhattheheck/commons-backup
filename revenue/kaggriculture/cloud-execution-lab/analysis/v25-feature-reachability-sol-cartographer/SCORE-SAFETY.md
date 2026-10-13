# TITAN V3 feature-reachability score and identity safety

**Operation:** `TITAN-V3-FEATURE-REACHABILITY-SCORE-SAFETY-20260910-01`  
**Owner:** `SOL-PRO`  
**Parent evidence lane:** SOL-CARTOGRAPHER PR #11976  
**Child implementation:** PR #11985

## Defects closed

### Margin-only keep/drop routing

The parent runner records disabled-minus-enabled TITAN cash, rival cash, and margin for every opponent/seed/seat pair. Its original classifier nevertheless used **margin alone** to emit `investigate_disable`.

Counterexample:

- all enabled: TITAN 100, rival 90, margin +10
- one feature disabled: TITAN 95, rival 80, margin +15

The disabled arm gains +5 margin only because the rival loses more; TITAN itself loses 5 terminal cash. The old rule routes the feature toward disable. The score-safe rule keeps it `mixed_or_neutral`.

`investigate_disable` now requires a changed trace, nonnegative TITAN own-cash and margin deltas in every cell, a strict own-cash gain somewhere, zero new losses, and zero lost wins. `retain_enabled` is the symmetric one-sided signal. All sign conflicts remain `mixed_or_neutral`.

The receipt now includes a policy ID, own/rival/margin summaries, positive/zero/negative own-cash counts, outcome transitions, and explicit score-safety gates. Markdown exposes own cash and outcome regressions beside margin.

### False exact-control identity

The original materializer rewrote `TITAN-CONFIG.json` for `all_enabled` via normalized JSON serialization. The result could be semantically equal yet byte-different from the bound archive, so “exact control” was not proven.

The materializer now:

- preserves the copied all-enabled config bytes exactly;
- builds deterministic SHA-256 manifests for every regular file;
- requires the control tree to have zero added, removed, or changed paths;
- requires each disabled arm to change exactly `TITAN-CONFIG.json` and no other path;
- parses the resulting config and requires exactly the named boolean to differ;
- records the path-level tree diff and non-config byte-identity verdict in variant metadata.

Any mismatch fails before gameplay.

## Focused validation

```text
python -m unittest -v test_feature_reachability.py
14 tests in 0.007s — OK
python -m py_compile feature_reachability.py test_feature_reachability.py
PASS
```

Contracts cover margin-only false positives, own-cash gain with win-to-loss, equal-cash margin gain, true Pareto-safe gain, noncanonical archive-config preservation, exact one-path variant diffs, and deterministic added/removed/changed manifest reporting.

Exact current source receipts:

- `feature_reachability.py`: Git blob `5d2423f77fe1146294964194adc74fc2bde04490`
- `test_feature_reachability.py`: Git blob `65be76df9b907e54ae327329a652f304be431a2a`

No gameplay code, package, archive, pointer, runtime configuration, provider, or Kaggle submission is changed by this review.