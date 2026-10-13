# DCSA Innovation Call #01 pursuit carrier

Operation: `DCSA-INNOVATION-CALL-01-20260914`  
Notice: `DCSAInnovationCall01` under `HS0021-26-CSO-DCSA`

This package is an internal, fail-closed qualification, architecture, acceptance-evidence, and teaming carrier for the Unified Application Access and Integration Prototype. It does not contact DCSA or a prime, submit a concept paper, represent clearance, commit pricing, or claim award, payment, cash, or revenue.

## Current authority boundary

The public CURRENT API accepts only exact candidate bytes and owns process UTC. It has no caller-selected source, time, authority, floor, `HOME`, cwd, environment, or URL input. Current source and eligibility trust are loaded only from code-pinned root-owned files:

```text
/etc/commons/dcsa-innovation-call-01/source-generation.json
/etc/commons/dcsa-innovation-call-01/sources/<code-owned filename>
/etc/commons/dcsa-innovation-call-01/authority.json
/etc/commons/dcsa-innovation-call-01/authority-floor.json
```

The source-generation record binds generation number, observation time, required document set, code-owned roles and first-party URLs, posting time, exact byte length, and SHA-256. Each retained source is captured and re-hashed before use. Historical raw-source evaluation is always `HISTORICAL_INTEGRITY_ONLY`, outward `HOLD`, and cannot mint CURRENT readiness.

CURRENT concept rendering accepts exact candidate/report bytes only and re-runs fresh fixed-host `verify_current`. Mapping-based CURRENT rendering is rejected.

Every CLI output set is precomputed, every destination is preflighted absent and unique, and the complete set publishes through one exact-inode transaction using create-exclusive files, bounded short-write-safe I/O, file and parent-directory `fsync`, same-descriptor exact-byte readback, visible-path identity checks, and rollback of only the generations created by that invocation.

## States

- `DIRECT_READY`: internal owner-review state only; every direct eligibility, source, capability, ROM, and owner-route gate is independently current and verified.
- `TEAMING_REQUIRED`: internal owner-review state only; direct evidence is insufficient or teaming is selected, and a separately evidenced cleared-prime path is current.
- `HOLD`: default for missing source bytes, missing or stale authority, deadline closure, incomplete capability evidence, missing owner authority, or any custody mismatch.

Every state keeps external contact, submission, signature, pricing, clearance, award, payment, cash, and revenue authority false.

## Commands

Current compile:

```bash
python -m revenue.dcsa_innovation_call_01 compile-current \
  --candidate revenue/dcsa_innovation_call_01/candidate.example.json \
  --report /tmp/dcsa-report.json \
  --concept /tmp/dcsa-concept.md \
  --acceptance-json /tmp/dcsa-acceptance.json \
  --acceptance-markdown /tmp/dcsa-acceptance.md
```

A machine without independently provisioned fixed-host trust fails closed.

Historical verification:

```bash
python -m revenue.dcsa_innovation_call_01 verify-historical \
  --candidate revenue/dcsa_innovation_call_01/candidate.example.json \
  --source revenue/dcsa_innovation_call_01/source_ledger.example.json \
  --authority revenue/dcsa_innovation_call_01/authority.example.json \
  --floor revenue/dcsa_innovation_call_01/authority-floor.example.json \
  --as-of 2026-09-14T04:45:00Z \
  --report revenue/dcsa_innovation_call_01/historical_report.example.json
```

Tests:

```bash
python -m unittest -v revenue.dcsa_innovation_call_01.test_source_red_closure
python -O -m unittest -v revenue.dcsa_innovation_call_01.test_source_red_closure
```

## Validation

- 38/38 normal Python tests.
- 38/38 optimized Python tests.
- 1,000/1,000 candidate/source/capability permutations.
- 500/500 source-generation tamper cases.
- 500/500 authority/source transplant cases.
- Deterministic create, write, `fsync`, metadata, pathname, and exact-byte-readback rollback hostiles.
- Historical integrity and current/historical authority separation.

## Custody and credit

Original DCSA carrier product/source/finalization credit remains Forge-Z and the canonical #14336 lineage. Z-ArchimedesRelay-001 supplied the #14341 authority/custody donor. SCREE-Z / GPT-5.6 Sol Pro supplied the exact-head SOURCE RED closure and current-main clean landing. Review credit is preserved in `SOURCE_RED_CLOSURE_RECEIPT.json`.
