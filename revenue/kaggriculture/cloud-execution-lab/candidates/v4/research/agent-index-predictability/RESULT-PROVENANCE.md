# TITAN V4 result provenance bridge (CHAINLOCK)

This package closes the producer-side gap between raw engine result rows and the
existing V4 agent-index analysis without creating a second evaluator or a new V4
root.

The trust theorem is inherited from merged provenance carrier **#11727**:
regression evidence is only comparable when candidate bytes, engine bytes,
environment seed, opponent bytes, and candidate seat are bound exactly. This
bridge makes those identities from the files actually present on disk rather
than trusting caller-supplied digest strings.

## What it does

`bind_result_provenance.py`:

- hashes the candidate artifact and engine artifact from their real bytes;
- hashes every referenced opponent artifact under one declared opponent root;
- supports either regular files or deterministic symlink-free directory trees;
- reads files with no-follow semantics where available and rejects identity /
  size / mtime changes during the read;
- parses strict JSONL (duplicate JSON members and non-standard numeric constants
  fail closed);
- requires every result to be `status == "DONE"` with a two-item engine-style
  `rewards` vector;
- derives candidate and opponent score from `seat` and `rewards`; any redundant
  `margin`, `candidate_score`, or `opponent_score` is an exact consistency
  assertion and must equal the reward-derived value;
- preserves exact integer identity after finite-range validation, so values above
  the IEEE-754 exact-integer range cannot collapse through float conversion;
- validates the derived candidate-minus-opponent margin after arithmetic, so two
  individually finite rewards cannot produce a non-finite certified outcome;
- rejects bool/type-poison seats, non-finite and numeric-overflow values,
  duplicate cells, errors/timeouts, path traversal, and symlinked artifacts;
- requires both seats for every `(seed, opponent, replicate)` cell;
- preserves legitimate large finite outcomes. There is **no guessed score
  ceiling**, no winsorization, and no relative-tolerance escape hatch;
- emits a #11727-compatible ledger using
  `(engine_sha256, environment_seed, opponent_sha256, seat)` plus an analyzer
  JSONL where opponent identity is the artifact SHA rather than a mutable name;
- folds an explicit replicate into the legacy `environment_seed` string so
  repeated cells remain distinct without changing the historical pair-key
  contract.

Exact equality is intentional here. These fields are provenance assertions, not
noisy measurements. Without an authenticated score-magnitude bound, relative
comparison is unsafe: around `1e20`, the predecessor's `rel_tol=1e-12` accepted
absolute contradictions on the order of tens of millions.

## Input row

Each JSONL row minimally contains:

```json
{"environment_seed":9922023,"opponent_artifact":"starter.py","seat":0,"status":"DONE","rewards":[168572,3550]}
```

`opponent_artifact` is a canonical relative path under `--opponent-root`. An
optional non-negative literal integer `replicate` is supported. Optional
`margin`, `candidate_score`, and `opponent_score` are consistency assertions,
not authorities.

## Run

From this directory:

```bash
python -B bind_result_provenance.py \
  --candidate /path/to/candidate-artifact-or-tree \
  --engine /path/to/pinned-engine-artifact-or-tree \
  --opponent-root /path/to/opponents \
  --results /path/to/raw-results.jsonl \
  --ledger-out /tmp/titan-ledger.json \
  --analyzer-jsonl /tmp/titan-analyzer.jsonl \
  --receipt-out /tmp/titan-provenance.json

python -B analyze_agent_index.py /tmp/titan-analyzer.jsonl --require-complete \
  --output /tmp/titan-seat-analysis.json
```

The ledger can be compared with another exact candidate ledger using the
already-merged root `titan_regression_gate.py`; the analyzer JSONL is the
provenance-bound input surface for this directory's `analyze_agent_index.py`.

For the current mirror/seat investigation, an aggregate W/L/D table is not a
substitute for this input. The producer needs the actual per-game raw rows with
exact environment seed, seat, engine rewards, and opponent artifact path for
both seats. Once bound here, the analyzer can estimate the within-seed/opponent
seat effect without trusting mutable labels or approximate aggregate margins.

When gauntlet wall-clock evidence matters, run the already-landed QUIETBOX
contention gate as a separate trust oracle on the corresponding panel. CHAINLOCK
binds identities and score provenance; it does not duplicate contention
calibration.

## Verification

Current exact producer Git blob: `b98b06980bcec265b36307c7c5e84fdcc84d8f85`,
SHA-256 `426b1c55f2773a3414229eac7383a2d9246f42b3b10e27352ac1867d9be043b6`.

Current exact regression Git blob: `bf7135e0f224b7f982020bafeba5c1e4734e74a3`,
SHA-256 `333176968e45d8ffb86bdcf0b5190227f0a180c2b3256f056bf3e42982810473`.

Exact-byte authored verification: 16/16 tests PASS under normal Python, 16/16
PASS under `python -O`, and `py_compile` PASS. The successor adds three
predecessor-killing cases: a large-magnitude relative-tolerance contradiction,
a `10**20` versus `10**20+1` integer-collapse contradiction, and a finite-input
`1e308 - (-1e308)` derived-overflow rejection.

## Assurance boundary

This adapter authenticates **the bytes and result rows it consumes**. It does
not claim process isolation, remote attestation, or that an untrusted runner was
incapable of fabricating a raw result row before it reached this tool. Runner /
execution trust remains a separate layer. The important improvement here is
that downstream analysis no longer needs to trust caller-declared candidate,
engine, or opponent digests, and it never lets a direct score alias override the
engine-style reward vector.

No gameplay source, feature default, canonical archive, evaluator policy,
provider state, Kaggle state, or submission behavior is changed by this package.
