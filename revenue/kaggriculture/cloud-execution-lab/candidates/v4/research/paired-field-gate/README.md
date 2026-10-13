# Paired, opponent-stratified V4 field screen

This is an **empirical screening tool**, not a new game evaluator, gameplay key,
statistical confidence claim, or promotion authority. It addresses a concrete
failure mode raised in the V4 field discussion: many positive mirror samples
must not conceal a negative dairy-opponent or candidate-seat stratum.

The implementation reuses `load_records` and `analyze` from the existing
`repairs/tooling/delta-evidence/v31_delta_distribution_report.py` recovered by
#12646. No reporter copy or private score parser is added. The exact tested
reporter Git blob is `5fa647b46dd2c359bc045a435d1542b1b06ed738`; a different byte
identity fails before import. A later reporter successor requires an explicit
review, regression run and pin update, not automatic acceptance.

## Inputs and use

Declare the panel **before** collecting results. It is a JSON object with exactly
`schema_version` and `opponents`. Each opponent has its own nonempty seed list:

```json
{"schema_version":1,"opponents":{"mirror":[101,102,103,104,105,106,107,108],"dairy-rival":[101,102,103,104,105,106,107,108]}}
```

The names above are illustrative, not an endorsement of particular opponents.
Choose real, fixed opponent artifacts appropriate to the mechanism under test.
For every declared opponent/seed, supply BOTH candidate seats 0 and 1, and a
baseline/candidate score pair for each cell. Paired rows or separate arms follow
the recovered reporter's public schema. Nested `scores` is `[seat0, seat1]`;
explicit `own`/`rival` is already candidate-relative:

```json
{"opponent":"dairy-rival","seed":101,"candidate_seat":1,"baseline":{"scores":[900,1000]},"candidate":{"scores":[900,1001]}}
```

Flat `baseline_scores`/`candidate_scores` and multiple paired-container aliases
remain intentionally rejected at this screen boundary to avoid misinterpreting
legacy evidence. The shared reporter itself now has the peer-owned seat/type
repair plus strict raw-JSON handling; this consumer does not undo those repairs.
Use a single `cells`/`results`/`games`/`matches` container or a list, and nested
scores or explicit own/rival fields. The CLI also rejects duplicate JSON keys,
nonfinite constants and invalid UTF-8.

From this directory:

```sh
python paired_field_gate.py evidence.json --panel panel.json --output report.json
python -m unittest -v test_paired_field_gate
python -O -m unittest -v test_paired_field_gate
```

Default policy: at least two opponents, eight seed-pairs per opponent, nonnegative
equal-opponent mean, nonnegative mean for every opponent and opponent-seat, zero
new losses, zero lost wins, and zero supplied-versus-recomputed delta mismatches.
Every threshold is explicit in `--help` and in the output. Defaults are a
conservative screen chosen for this tool, **not a project-wide promotion rule**.
A zero-delta/inactive mechanism can pass non-regression defaults; use a positive
`--min-balanced-delta` when testing a minimum empirical improvement.

Exit codes: **0** empirical PASS, **1** empirical FAIL with a report, **2** invalid
data/panel/policy/custody or I/O failure. Missing or unexpected panel cells are
invalid data, never silently excluded. Invalid input emits no report and does
not overwrite an existing output. Output must not alias either input or the
reporter. Successful writes use a temporary file plus atomic replacement.

## Estimand and diagnostics

Recompute each competitive-margin delta as
`(candidate_own - candidate_rival) - (baseline_own - baseline_rival)`.
Average both seats within each opponent/seed, average seeds within each opponent,
then average opponents equally. Thus an oversampled easy opponent does not
receive more weight than a sparsely sampled difficult opponent. The ordinary
pooled mean is still reported for comparison. This equal-opponent estimand is
not an estimate of an unknown leaderboard opponent-frequency distribution.

The output retains the predecessor distribution report, adds seed-pair records,
per-opponent/per-seat means, worst-opponent mean, exact coverage, and explicit
failure reasons. It tracks new losses and lost wins separately. Thresholds
compare empirical means; no standard errors, bootstrap claims, p-values, or
independence assumptions are invented.

## Executed discrimination, not economic evidence

Synthetic fixture only: mirror has 32 seed-pairs at +10 margin; dairy has eight
seed-pairs at -30. Pooled mean is **+2**, while equal-opponent mean is **-10**.
The original reporter with a pooled `min_mean_delta=0` policy accepts the exact
fixture; this screen rejects it, even though it creates no new losses. Tests
also cover positive overall gain with a bad opponent, positive seat-pair gain
with a bad seat, official seat-1 score orientation, exact coverage, score poison,
alias ambiguity, strict JSON, output safety, and deterministic order invariance.

Both normal and optimized Python execute the real hash-pinned dependency.
See `execution-receipt.json` for the local test receipt and source hashes.
The initial a37 dependency and the reviewed, exact 24,465-byte 5fa successor both
passed the same 41 tests in normal and optimized Python. No reporter copy was added.

## Evidence limits and integration boundary

The tool cannot prove the panel was declared in advance, is representative, or
uses authentic opponent artifacts. File hashes bind the supplied JSON, not the
claimed game execution, runtime artifact, environment, or feature activation.
Source/artifact identity and paired-run validity remain the runner's obligation.
Passing does not establish causal contribution, future strength, or production
safety. No game runtime, feature default, materializer, archive, workflow, old
V4 ref, or Kaggle submission is changed. The four research files belong only to
`main:candidates/v4`, alongside the already-canonical reporter recovery.
