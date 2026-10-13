## Owner GPT review requirement — 2026-09-12

Release transactions now use schema v6 and require `--gpt-review FILE`
(`gpt_review_raw` in the Python API). It is a `commons-release-review/v1` JSON
receipt: decision PASS; reviewer with family gpt, seat and session_ref; exact
archive_sha256 and source_manifest_sha256; baseline_sha256 equal to the pinned
submitted V3.1; production_route `r04-restored` or `replacement`;
activation_evidence; and required_members mapping active member paths to SHA256.
The restored R04 route requires all thirteen production dependencies. Every
named member is checked against captured archive bytes. A replacement remains
subject to the existing champion ratchet. No GPT review clears missing native
results or the disabled release-origin commit interlock. Standing authority:
`ground/SWARM_ORDER.md` at repository root.

# TITAN V5 cross-evidence promotion and release gates

`promotion_gate.py` is an evidence-only fail-closed join across three V5
contracts that are intentionally produced separately:

1. a `v5_candidate_identity.py` manifest,
2. an `engagement_fingerprint.py` report, and
3. a `runtime-budget/runtime_budget_profile.py` report.

It does not execute gameplay, change a default, or replace the underlying
source/engine/simulation evidence. Its job is to prevent a promotion decision
from accidentally combining identity, engagement, or runtime evidence from
different builds.

## Promotion contract

A promotion-gate PASS requires all of the following:

- the candidate manifest has the exact `titan-v5-candidate-identity/v1` closed
  shape and its `v5c:` ID recomputes from the manifest body;
- engagement is `ENGAGED`, has a real divergence, has distinct exact `v5c:`
  control/candidate IDs, and the candidate ID equals the manifest;
- runtime admission is `PASS` with `promotion_ready=true`, an explicit exact
  callback design, no missing or unexpected callbacks, nonnegative p99
  headroom, and exactly one runtime candidate equal to the manifest/engagement
  candidate;
- redundant runtime counts/rates are internally consistent; and
- every input JSON file is strict JSON: duplicate object members and
  `NaN`/`Infinity` constants are rejected.

The emitted receipt binds the exact input-file SHA-256 values plus the shared
candidate/control identity and the key engagement/runtime metrics. Output-file
publication is same-directory atomic.

```bash
python candidates/v5/promotion-gate/promotion_gate.py \
  candidate-manifest.json engagement-report.json runtime-budget-report.json \
  --output promotion-receipt.json
```

## Paired competitive economics

`economics_gate.py` closes a separate release boundary. A candidate that is
identifiable, engaged, and fast is not necessarily competitive. The economics
gate accepts only raw paired cells and recomputes each margin itself.

The v4 economics report is execution-bound. It carries exact control and
candidate `v5c:` identities, the candidate manifest's engine/opponent-pack
identity, and the exact old/new release archive SHA-256 values. Each raw cell
also names the opponent actually played. The release transaction supplies the
build/execution authorities independently and rejects stale or cross-wired
evidence.

The release roster is no longer inferred from an opaque pack label. It is
explicitly fixed to:

- `apex_v7`
- `arlene_v14`

and the receipt binds the reviewed `REFERENCE-POLICIES.json` Git blob
`6bce02dad705ccc57656ff2e2139db215f9fcc57`. The registry contains other
recovered names, so using every registry key would be wrong; the two-name roster
is an explicit release authority, not a registry enumeration.

A paired-economics PASS requires:

- the played opponent IDs equal the exact authorized roster (no favorable
  subset, superset, or invented replacement);
- at least 4 distinct seeds per authorized opponent;
- every opponent covers the exact same seed set;
- exactly one seat-0 and one seat-1 cell for every `(opponent, seed)` pair;
- unique cells in canonical `(opponent_id, seed, seat)` order;
- exact bounded nonnegative integer own/rival scores for control and candidate;
- no caller-supplied aggregate or claimed delta fields;
- execution authority equal to the promotion manifest and release archive pair;
- nonnegative aggregate paired margin delta; and
- nonnegative paired margin delta **for each authorized opponent separately**.

The opponent-local floor prevents one favorable opponent from laundering a
regression against another. The receipt serializes each authorized opponent's
cell count, control/candidate margin sums, and delta, plus the global sign/count
metrics and canonical panel digest.

```bash
python candidates/v5/promotion-gate/economics_gate.py economics-report.json \
  --output economics-receipt.json
```

## Release transaction

`release_transaction.py` is the pointer-transition authority in this directory.
Version 5 keeps the existing promotion replay, V4 trusted-base replay,
source/archive binding, expected-old transaction, and atomic commit semantics,
and requires both `--economics-report` and a replayable champion receipt.

The release transaction replays `economics_gate.validate_report()` against the
same candidate/control, engine/opponent-pack, and old/new archive authorities
already authenticated by the transition. It redundantly requires the exact
Apex+Arlene roster and registry blob, checks the opponent-local arithmetic and
nonregression floors, and binds the roster, registry authority, per-opponent
aggregates, raw report SHA-256, and canonical panel digest into the `v5tx:`
transition identity.

Module custody is source-real: `_load_module()` reads each Python authority once
and executes the **captured authenticated byte buffer** via `compile`/`exec`.
It never authenticates one read and then asks `exec_module(path)` to perform a
second path read. Tests cover both a path swap and deletion after the first read.

Negative-global, negative-per-opponent, unauthorized-roster, uneven-seed,
missing-seat, duplicate, stale-archive, wrong-pack, cross-build, or source-path
race cases fail before a release pointer can move.

The adaptive Apex+Arlene economics panel and full recorded-opponent champion
panel remain separate. Both must pass in the same release transaction. Champion
scoring reuses the merged `../champion-ratchet/champion_gate.py` implementation;
there is no copied scorer or requirement to zip its 246 cells to the smaller
adaptive panel.

The programmatic `build_transaction` API requires `champion_raw` and
`champion_evidence`. The evidence mapping contains exactly `kg_root`,
`engine_dir`, `manifest_path`, `v31_archive`, `incumbent_archive`,
`candidate_archive`, `v31_roots`, `incumbent_roots`, and `candidate_roots`.
The release module checks the canonical champion source's pinned Git blob
**before execution**, then calls its `evaluate()` over the actual archives,
harness, manifest, and complete result roots. It does not accept a caller's
replacement scorer, pin overrides, or a summary without backing evidence.
This replays existing results; it does not run new games.

The supplied receipt must equal the evaluator's canonical JSON bytes plus one
newline. Required authority includes exact V3.1 source/submission/archive,
the canonical 41-target/123-fixture/246-cell panel, and incumbent/candidate
archives matching the transaction's old/new archives. The champion must
strictly improve V3.1 own score, preserve incumbent own score, avoid new losses,
and pass the canonical stratum and margin checks. Its `release_authority=false`
marks it as a subgate; only this transaction can combine the release evidence.
The full replayed receipt, its raw SHA-256, and the executed builder identity
are included in `v5tx`.

The CLI adds these required inputs to the existing transaction arguments:

```text
--champion-receipt CHAMPION.json
--champion-engine-dir ENGINE_DIRECTORY
--champion-v31-archive EXACT_SUBMITTED_V31.tar.gz
--champion-incumbent-archive CURRENT_CONTROL.tar.gz
--champion-v31-root V31_RESULT_ROOT          (repeat for every shard)
--champion-incumbent-root CONTROL_ROOT      (repeat for every shard)
--champion-candidate-root CANDIDATE_ROOT    (repeat for every shard)
```

The candidate archive is the existing `--approved-archive` input. The repo's
canonical corpus manifest and harness are selected internally. Source and
receipt pins change only with an explicitly reviewed successor integration.

Exit status is `0` only for a PASS receipt. Invalid, ambiguous, incomplete,
cross-wired, or economically regressive evidence exits `2`.
