# Cross-Site Clinical Fill Tech-Transfer Evidence Gate

A dependency-free, read-only compiler for a bounded synthetic/non-production clinical-manufacturing handoff pilot. It freezes source-site and receiving-site generations, reconciles packet identity and declared evidence, and produces owner-review evidence with replayable SHA-256 receipts.

It is not a GMP, quality, scientific, regulatory, deviation, process-parameter, or batch-release engine. It never writes to manufacturing systems.

## Authority split

The production/current surface deliberately separates **candidate compilation** from **current authority**.

### Current candidate

`engine.py` exports `compile_transfer(source, receiving, policy)` with **no caller `as_of` parameter**. It samples process UTC and emits schema `vetter-clinical-fill-tech-transfer-current-candidate/v3` with authority mode `CURRENT_EVIDENCE_CANDIDATE`.

A candidate is not a current owner-review authorization. It is a sealed input/decision generation that must cross a fresh verification gate before any current-authority representation is emitted.

### Current owner-review authority

`verify_report_current(candidate)` accepts no clock override. Under the declared trusted-host runtime, it re-evaluates the candidate snapshots and policy at newly sampled process UTC and requires the entire semantic decision projection—not merely READY/HOLD—to remain identical. Only this verifier emits schema `vetter-clinical-fill-tech-transfer-current-verification/v3` with authority mode `CURRENT_OWNER_REVIEW`.

`render_markdown(candidate)` traverses the same fresh process-time semantic gate before rendering. A stale/backdated candidate therefore fails under an unmodified trusted runtime when its decision projection changes at real process UTC.

### Runtime trust contract

The current Python library is an **application trust boundary, not a pure-Python sandbox**. `contract.json` is the controlling truth contract.

The package does **not** claim resistance to arbitrary same-process monkeypatching or mutation of private helper globals. Python runtime state, private module state, the process environment, carrier source bytes, input acquisition, and policy custody are trusted host requirements. In particular, the retained classifier is an ordinary Python function and its `__globals__` dictionary is mutable; SHA-256 receipts bind data generations but do not attest runtime integrity.

For a current owner-review run, the recommended operational boundary is a **controlled fresh interpreter CLI** using trusted carrier bytes and environment. Same-process private-helper mutation is explicitly outside the current authority claim. This is an intentional, executable scope statement, not a claim that reflection or Python objects are secret.

This contract closes the latest review defect by removing the overbroad assertion that recovered mutable Python internals are mechanically tamper-resistant. The currentness guarantee is: with the declared host runtime trusted, the supported current API owns the clock, historical replay cannot emit the current schema, and current verification re-evaluates the candidate at process UTC.

### Historical/test replay

Explicit time exists only as a supported API in `historical.py`. It emits schema `vetter-clinical-fill-tech-transfer-historical/v1` with authority mode `HISTORICAL_INTEGRITY_ONLY`. Historical verification returns a distinct historical-verification schema and never emits the current-verification schema or `CURRENT_OWNER_REVIEW` authority.

The retained predecessor source is stored as inert `_engine_v1.txt`, not an importable Python module. The current and historical facades evaluate those exact source bytes into private namespaces and wrap them with their distinct authority contracts.

## Custody and packet model

Each snapshot binds immutable snapshot identity, source/receiving role, schema revision, transfer generation, canonical UTC capture time, literal complete-export declaration, normalized rows SHA-256, and the exact normalized packets needed for offline replay.

Every packet additionally satisfies:

`last_updated_utc <= snapshot.captured_at_utc <= evaluation time`

The canonical packet key is `project_id + molecule_id + batch_id + site_id`. Principal deterministic HOLD families are method/version mismatch, lot/release gap, container/batch configuration mismatch, equipment/calibration gap, operator-qualification gap, microbiology/inspection gap, stale evidence, duplicate packet, missing receiving packet, and generic transfer conflict.

## Frozen 144-packet Chicago/Rankweil acceptance

`synthetic_acceptance.py` is deliberately historical/test-only. Its deterministic envelope contains 144 synthetic/deidentified transfer packets: 120 `TRANSFER_READY` and four packets in each of six named HOLD families. The predecessor corpus proves exact distribution, field commitments, deterministic receipts, order invariance, strict generation/schema/role/digest custody, stale/future-time handling, duplicate JSON-key and non-finite JSON rejection, target-only handling, receipt tamper resistance, and create-exclusive outputs.

The recovery corpus additionally proves current/historical schema separation, absence of caller-clock current API parameters, candidate-vs-authority separation, closure-introspection attack handling under the declared trusted runtime, fresh render/verify expiry, row-before-capture chronology, final-symlink rejection, retained-descriptor pathname-swap resistance, and in-read byte-cap enforcement. `test_contract.py` separately proves the exact same-process mutation limitation is declared rather than hidden.

```bash
python -m compileall -q .
python -m unittest -v test_engine.py test_recovery.py test_contract.py
python -O -m unittest -v test_engine.py test_recovery.py test_contract.py
python synthetic_acceptance.py
```

## Production CLI

Production candidate compilation and current verification sample process UTC internally. Run the current lane from a controlled fresh interpreter when `CURRENT_OWNER_REVIEW` is being relied on:

```bash
python engine.py compile --input request.json --report candidate.json --markdown current.md
python engine.py verify --report candidate.json
```

The request contains exactly `source`, `receiving`, and `policy`. Input is read from one retained `O_NOFOLLOW` regular-file descriptor with a hard cap enforced during consumption. Output paths must not already exist. The compile command will not write Markdown unless the newly compiled candidate passes the fresh current-render gate.

## Privacy and authority ceiling

Public fixtures contain no Vetter, patient, product, customer, or production data. No live Vetter access or credentials are used. Even `CURRENT_OWNER_REVIEW` is evidence/handoff support only and does not authorize process-parameter recommendations, deviation disposition, GMP/quality/scientific/regulatory decisions, batch release, deployment, buyer contact, payment, cash, or revenue recognition. Human site operations and QA retain authority.
