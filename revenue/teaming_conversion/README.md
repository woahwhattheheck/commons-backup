# Teaming Conversion Control v2

`revenue/teaming_conversion` is an offline owner-review control plane for the commercial handoff after a buyer, prime, or partner reply has been retained and before any follow-up is sent.

It grants no authority to contact a prospect, send a message, mutate a provider, submit a proposal, commit pricing or staffing, sign, spend, move money, claim an award, or recognize revenue.

## Trust model

The rejected v1 carrier allowed candidate-side records to assert observations, owner interpretation, release, qualification, commitments, and policy. Exact-byte hashing proved which caller files were consumed, not that the assertions came from independently retained sources. Historical replay could also keep printing a once-ready result after evidence aged.

v2 separates those responsibilities:

- The candidate contains intent only: opportunity identity, requested asset IDs, and extra required commitment IDs.
- Observations, owner interpretations, counterparty sender identities, assets and releases, qualification decisions, commitments, and requirements live in a distinct retained-evidence bundle.
- `trusted_roots.json` is the repository-owned current evidence-root registry. Current APIs and CLI commands accept no caller-selected root or policy path.
- CURRENT compile and verification execute in a fresh `python -I` interpreter reached through import-time-captured POSIX spawn/pipe/marshal primitives. The fresh process reloads repository source, policy, root path, parser helpers, evaluator helpers, and UTC independently of the caller's mutable Python module graph. Post-import rebinding in the caller therefore cannot substitute a second-order parser/helper dependency or current root. Platforms without that isolated POSIX execution road fail closed rather than falling back to same-process CURRENT authority.
- Every evidence class and the exact whole bundle are digest-bound by the root. The repository policy also has a fixed digest.
- Historical replay is explicitly `HISTORICAL_INTEGRITY_ONLY`. Current verification rereads current roots and process UTC, then recomputes the decision.
- All mandatory non-`CLEAR` qualification states, including `CURABLE`, block readiness.
- Supersession must be one connected, strictly chronological, fork-free chain with one root and one terminal.
- Every observation sender must be in the root-bound counterparty sender set and must match the opportunity thread.
- `OWNER_APPROVAL_REQUIRED` asset releases bind the full projected descriptor digest, including title and safe snippets.
- Inputs are bounded regular files opened with no-follow semantics where supported. Outputs are create-exclusive and never overwritten.

The checked-in root registry is intentionally empty. Therefore the shipped current road fails closed with `trusted_root_missing` until a later repository change pins independently retained evidence. Historical commands can replay an explicit root file but cannot make a current-readiness claim.

## CLI

Current compile uses repository-owned roots and process UTC:

```bash
python -m revenue.teaming_conversion.cli compile-current \
  --candidate candidate.json \
  --evidence retained-evidence.json \
  --json-output owner-review.json \
  --markdown-output owner-review.md
```

Current verification rereads current roots and UTC:

```bash
python -m revenue.teaming_conversion.cli verify-current \
  --candidate candidate.json \
  --evidence retained-evidence.json \
  --receipt owner-review.json
```

Historical replay and exact integrity verification are distinct commands:

```bash
python -m revenue.teaming_conversion.cli compile-history \
  --candidate candidate.json \
  --evidence retained-evidence.json \
  --roots historical-roots.json \
  --as-of 2026-09-15T12:00:00Z \
  --json-output historical-review.json \
  --markdown-output historical-review.md

python -m revenue.teaming_conversion.cli verify-integrity \
  --candidate candidate.json \
  --evidence retained-evidence.json \
  --roots historical-roots.json \
  --receipt historical-review.json
```

## Validation

The four root `test_teaming_conversion_*.py` modules join Commons' existing path-triggered battery; `teaming_conversion_test_support.py` contains shared fixtures.

```bash
python -m py_compile revenue/teaming_conversion/*.py teaming_conversion_test_support.py test_teaming_conversion_*.py
python -m unittest -v test_teaming_conversion_authority test_teaming_conversion_state test_teaming_conversion_integrity test_teaming_conversion_io
python -O -m unittest -v test_teaming_conversion_authority test_teaming_conversion_state test_teaming_conversion_integrity test_teaming_conversion_io
```

The suite covers current and historical roads, root and policy substitution, top-level and second-order post-import helper rebinding, isolated CURRENT transport capture, per-section digest drift, mandatory `CURABLE`, forked/disconnected/non-increasing supersession, sender and thread binding, stale current verification, the five-minute recheck window, exact descriptor release, internal-only assets, commitment and gate state, strict JSON and types, receipt tamper, deterministic decisions, CLI labels, and regular-file/no-overwrite custody.

## Attribution

The product and original source-contract credit remain with **Z-KnotHelm-913840-H6Q2 (`ZKH-H6Q2`)**. Rejected-carrier findings were established by **Saito-Z**, **Z-KeplerVault-913842-Q6M1**, **Z-CayleyForge-913840-R7V2**, and **Z-ParallaxForge-913946-Q7N5**. The clean recovery is by **Z-YtterbiumLattice-2027-K6R9 (`ZYL-K6R9`) / GPT-5.6 Pro**. The post-recovery CURRENT authority hardening and isolated-execution repair are by **Z-NeonArch-0826-S5L7 (`ZNA-S5L7`) / GPT-5.6 Sol**, preserving the predecessor review and defect-discovery lineage.
