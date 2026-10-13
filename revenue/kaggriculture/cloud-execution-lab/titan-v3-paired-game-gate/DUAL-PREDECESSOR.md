# Titan V3 dual-predecessor win gate

`dual_predecessor_gate.py` closes the gap between a valid one-baseline paired
comparison and the stronger release claim that one exact Titan V3 candidate
beats **both** predecessor builds.

Running `gate.py` twice is not sufficient by itself. The second invocation may
bind a different candidate panel, candidate runtime, engine, runner, grid, or
policy. Worse, one predecessor panel can be copied into the second slot and
relabeled with a different declared hash. The custody-bound dual gate makes
those conditions one atomic, fail-closed decision.

## Required inputs

The command consumes fourteen regular files. All fourteen are privately
snapshotted before either single gate runs:

1. predecessor A contract, provenance evidence, `GAMES.jsonl`, strict run
   receipt, and executable artifact bundle;
2. predecessor B contract, provenance evidence, `GAMES.jsonl`, strict run
   receipt, and executable artifact bundle;
3. one shared candidate `GAMES.jsonl` and executable artifact bundle;
4. one shared engine artifact and one shared runner artifact.

An executable artifact input must be a deterministic regular-file bundle that
represents the complete executable closure used in the run. A tiny entrypoint
that imports changing siblings is not a runtime identity. In particular, the
committed historical Titan panels currently share the same 66-byte
`candidate.py` entry file while their scheduler closures differ; that entry
file hash is not admissible as a V1/V2/V3 artifact identity.

Each single-gate report must bind back to the exact outer contract, evidence,
baseline panel, and shared candidate-panel snapshots. Each custody receipt must
also bind the observed engine, runner, baseline artifact, candidate artifact,
contract, evidence, and both game files.

The gate requires:

- the same observed candidate artifact and candidate panel in both comparisons;
- the same engine, runner, normalized seeds, opponents, seats, expected-cell
  count, and policy;
- distinct predecessor names and observed executable artifact bytes;
- declared artifact hashes that equal the hashes of the supplied artifact
  bundles;
- a candidate artifact that does not alias either predecessor artifact;
- exact command and panel identity agreement among contract, evidence, receipt,
  and the inherited single-gate report.

Canonical semantic identity is derived from each validated and sorted cell key
plus its baseline score vector. Numerically equivalent signed zeros are
normalized so `0.0` and `-0.0` cannot create different semantic identities.

Byte-identical predecessor panels are valid when the two observed, receipt-bound
closure artifacts remain distinct. Reserialized or signed-zero copies whose
file bytes differ but whose canonical score matrices match stay `INVALID`:
different serialization is not evidence of a second execution. Closure artifacts
are the execution theorem; result bytes are the observation.

Each comparison must independently satisfy the existing complete-grid,
provenance, metric, numeric-closure, and policy rules in `gate.py`.

## Custody receipt

Each comparison requires a duplicate-key-rejecting JSON object with exactly
this shape:

```json
{
  "schema_version": 1,
  "receipt_type": "titan-paired-run-custody/v1",
  "panel_id": "v3-vs-v1-heldout-01",
  "baseline_name": "titan-v1",
  "candidate_name": "titan-v3",
  "exact_command": "python ...",
  "provenance": {
    "engine_commit": "<40-or-64-hex>",
    "engine_sha256": "<64-hex>",
    "runner_commit": "<40-or-64-hex>",
    "runner_sha256": "<64-hex>",
    "baseline_artifact_sha256": "<64-hex>",
    "candidate_artifact_sha256": "<64-hex>"
  },
  "grid": {
    "seeds": [101, 102],
    "opponents": ["apex", "arlene"],
    "seats": [0, 1],
    "expected_cells": 8
  },
  "sha256": {
    "contract": "<64-hex>",
    "evidence": "<64-hex>",
    "engine_artifact": "<64-hex>",
    "runner_artifact": "<64-hex>",
    "baseline_artifact": "<64-hex>",
    "candidate_artifact": "<64-hex>",
    "baseline_games": "<64-hex>",
    "candidate_games": "<64-hex>"
  }
}
```

The runner should emit this receipt from the exact immutable files used and
produced by that execution. The dual gate independently hashes the supplied
files and rejects any receipt field that does not match those observed bytes.

## Usage

```bash
python3 dual_predecessor_gate.py \
  --predecessor-a-contract /evidence/v1.CONTRACT.json \
  --predecessor-a-evidence /evidence/v1.PROVENANCE.json \
  --predecessor-a-games /evidence/v1.GAMES.jsonl \
  --predecessor-a-receipt /evidence/v1.RUN-RECEIPT.json \
  --predecessor-a-artifact /artifacts/titan-v1-closure.tar \
  --predecessor-b-contract /evidence/v2.CONTRACT.json \
  --predecessor-b-evidence /evidence/v2.PROVENANCE.json \
  --predecessor-b-games /evidence/v2.GAMES.jsonl \
  --predecessor-b-receipt /evidence/v2.RUN-RECEIPT.json \
  --predecessor-b-artifact /artifacts/titan-v2-closure.tar \
  --candidate-games /evidence/v3.GAMES.jsonl \
  --candidate-artifact /artifacts/titan-v3-closure.tar \
  --engine-artifact /artifacts/engine.bundle \
  --runner-artifact /artifacts/runner.bundle \
  --report /evidence/V3-DUAL-GATE.json
```

Exit codes retain the single-gate contract:

- `0`: `PROMOTE` — both custody-bound predecessor comparisons are valid and
  pass;
- `2`: `INVALID` — an input, identity, custody, grid, policy, artifact, or hash
  binding is invalid;
- `3`: `REJECT` — evidence is valid, but one or both comparisons fail policy.

The report records all fourteen observed input hashes and byte counts, declared
provenance separately from observed artifact hashes, both normalized custody
receipts, both complete single-gate reports, canonicalized predecessor score
matrix hashes, and each comparison exit code.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v test_dual_predecessor_gate.py test_equal_result_bytes.py
```

The fifteen-case adversarial suite covers custody-bound two-predecessor
promotion, one-sided rejection, byte-identical panels with distinct closures,
reserialized semantic copies of the first predecessor panel, signed-zero
semantic equivalence, candidate and
engine artifact declaration drift, duplicate predecessor artifact bytes,
candidate/predecessor artifact aliasing, receipt tamper, post-receipt
candidate-panel substitution, exact-command drift, stale inner candidate
bytes, and the CLI/report path.

`PROMOTE` proves only the supplied custody-bound panel under the inherited
paired-gate threat model. A receipt is an immutable hash binding, not a digital
signature or proof against a malicious evaluator. The gate does not prove a
leaderboard rank, replace the current release archive, or authorize provider
publication.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
