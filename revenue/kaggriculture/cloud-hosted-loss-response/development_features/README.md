# T13 development observation importer

This additive data component reuses the published development results from
PR9936 without changing a runtime policy, selector, or validation panel. It does
not simulate games. `development-scores.csv` projects 36 existing result rows
into 18 SELL/seed pairs; the seed and opponent columns are join metadata, not
runtime features. Scores originate in `../results/games.csv`, blob
`a296802b4e2b162f62a6114dae36b1e54b0978f3` at
`d87f5e6ef3a578128b0d34a7a1d22959b0948e21`.

## Current materialized content

The label-only export contains 18 pairs, 36 outcome rows, **zero available
checkpoint observations**, and zero proven common prefixes. The original
large development reports are not supplied with this component. Their byte
counts and SHA-256 values are retained in `REPORTS`, copied from the published
`../results/validation.json`. Missing features are `null`, not estimates or
zero vectors. This is an executable importer and outcome index, **not a
completed training dataset or evidence that a midgame switch is valid**.

## Reproduction

From the repository root:

```sh
D=revenue/kaggriculture/cloud-hosted-loss-response/development_features
F=revenue/kaggriculture/cloud-policy-portfolio/features.py
python "$D/export_features.py" --output /tmp/t13-development-index.json
python "$D/test_export_features.py" --feature-source "$F" -v
```

To attach available **original** development reports, supply one or more of
these four files and the pinned ASTER extractor:

```sh
python "$D/export_features.py" --feature-source "$F" \
  --report /path/to/dev0-sell-import.json \
  --report /path/to/dev12-sell.json \
  --report /path/to/dev-frozen-sell.json \
  --report /path/to/dev-seed.json \
  --output /tmp/t13-development-features.json
```

Do not substitute reruns for those original report digests. The importer binds
report bytes, official engine revision, case identity, full-trace hash and
both terminal scores before adding observations. The feature extractor is the
unchanged Apache-2.0 implementation from `cloud-policy-portfolio/features.py`,
blob `d8a7d7e3b833c2071fa1c29d80a51951524fd737` at
`e987ed4eec0c27223de7432a8bce88ff7e062697`; it is imported, not reimplemented or
vendored here. Its source pin is checked before execution.

The measurement source is
`cloud-frontier-policy/next-panel/measure.py`, blob
`3fb32630c5a2210d4a52549d600ae41a49b53a7e` at the result commit. Its step360
snapshot is taken before unit actions. The field named `prices` contains the
whole observed market; `shops` contains observed town state. Both farms are
public, but only the selected seat's private dictionary is projected. Actions,
configuration, hidden seed, rival private data and later snapshots do not enter
the feature extractor. The projection hash is not a full-observation hash.

Output keeps `join`, `labels`, `observation` and `features` separate. Only
`features` may be a runtime predictor input. `checkpoint_observation_equal` and
`sampled_prefix_equal` describe their named measurements only. Even when both
are true, sparse timeline samples cannot establish equality on every prior
turn; `full_prefix_equal` and `continuation_pair_eligible` remain `null`.

## Validation

Thirteen local regression methods pass, including the real 36-row outcome
index, deterministic CLI export, exact feature-source pin, original-byte and
score binding, missing/duplicate checkpoints, duplicate cases, own-private
projection, held-file exclusion, and preservation of unknown full-prefix
status. The report/observation fixtures in the parser tests are explicitly
synthetic; no synthetic fixture is shipped as a game or training observation.
No new games or held-panel data were used for this component.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
