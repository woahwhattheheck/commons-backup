# Strict single-pair returned-action evidence

Operation: `TITAN-V3-RETURNED-ACTION-DIFF-STRICT-PAIR-20260910-02`

This is the review-consumption successor to Commons PR #12103 review
`5172879917`. The reviewer credited the strict **single-pair** validation but
correctly held the earlier multi-row "temporal/causal" label: independent
snapshots do not become a trajectory merely because their outer labels are
contiguous.

The repair therefore removes the ledger feature completely. It does **not**
manufacture an engine-owned state-transition edge, run identity, episode
completeness, or executable identity that the capture format does not contain.

## Exact claim

Given two parent `titan-returned-action-capture/v1` bundles, this consumer may
report only whether their deterministic returned actions are equal or different
after it proves that both bundles encode the exact same canonical state/request
bytes.

Every report says:

```json
{
  "scope": "single_pair_only",
  "trajectory_claim": false,
  "causality_claim": false
}
```

`DIFFERENT` means only: *these two validated arms returned different action JSON
for this one validated same-state/same-request pair under the chosen numeric
and explicitly reviewed unordered-path policy*. It is not a trajectory claim,
not a first-temporal-divergence claim, and not proof of downstream score
causality.

## Validation performed before comparison

The consumer:

- parses JSON with duplicate-key and non-finite-number rejection;
- recomputes canonical state bytes, state SHA-256, request SHA-256, and request
  byte length;
- requires the parent endpoint field to be present and records both arm
  endpoints in the report without pretending that endpoint identity proves an
  executable identity;
- recomputes every sample's unwrapped action, unwrap path, and action SHA-256
  from the persisted raw response;
- recomputes sample count, unique-action count, determinism, first unstable
  sample, the parent internal diagnostic, and all top-level sample-zero
  projections;
- requires both operands to have identical validated state and request digests;
- emits `HOLD_UNSTABLE` without comparing sample zero if either arm varies
  across repeats;
- treats list positions as semantic by default, including market/order rows;
- allows identity-based unordered alignment only at an exact caller-supplied
  `--unordered-path` and only with unique reviewed identities;
- keeps exact zero-tolerance integer/cross-int-float comparison so `2**53+1`
  cannot alias `2**53` through binary64 coercion;
- requires regular non-symlink input files and rejects input inode aliases,
  input/output aliases, and output symlinks; and
- writes reports with temp-file + `fsync` + atomic replacement and a
  self-excluding report SHA-256.

The parent capture's `http.body_sha256` was computed from raw network bytes, but
those bytes are not persisted. The consumer validates that digest's shape only;
it never claims to recompute it. The trusted action projection is recomputed
from the persisted raw response.

## CLI

Only one pair is accepted:

```bash
python strict_returned_action_diff.py \
  --left captures/v1.capture.json \
  --right captures/v3.capture.json \
  --json-out strict-pair-report.json
```

There is no ledger/trajectory mode. Use `--unordered-path` only for an exact
path whose ordering has been separately reviewed as semantically irrelevant.
No unordered path is enabled by default.

Exit status is `0` for valid evidence, `1` for a valid pair difference when
`--fail-on-diff` is requested, `2` for malformed/insufficient/aliased evidence,
and `3` for repeat instability.

## Review predecessor closure

The focused suite kills these predecessors directly:

- keyed execution-bearing list reorder falsely compares equal;
- forged state/request/action hashes or raw-response projections are trusted;
- state or endpoint is absent;
- unstable repeats are silently reduced to sample zero;
- duplicate keys, NaN/Infinity/overflowing floats are accepted;
- `2**53`-scale integer values false-alias through float conversion;
- symlink/hardlink/input-output aliasing can overwrite or confuse evidence; and
- the consumer regrows a temporal-ledger API or temporal-divergence field.

The workflow also runs the inherited parent tests and rejects any return of the
removed ledger symbols/fields.

## Boundary

This remains evidence/control-plane code only. It changes no TITAN policy,
scheduler, runtime, configuration, archive, release pointer, game/seed bank,
provider state, Kaggle state, promotion state, merge state, or submission. A
future real trajectory analyzer would need an engine-owned transition chain,
start/completeness proof, and immutable arm/run/executable identity; this PR
intentionally does not claim to provide those.