# Banner SaaS Student-Record Parity Gate

A dependency-free, read-only migration-acceptance compiler for comparing an approved source Banner export with an approved target SaaS/Experience/Insights export. It is intentionally a **parity evidence gate**, not a migration tool: it never writes student records, calls Banner/Ellucian, contacts a buyer, or turns synthetic/local evidence into a production migration claim.

## What it checks

Each source record is keyed by the opaque pair `student_id + term` and carries `program`, `enrollment_status`, `holds`, `advisor`, and `last_sync_utc`. Source and target snapshots separately bind their role, immutable snapshot ID, schema revision, capture time, complete-export assertion, normalized-row digest, and exact normalized rows.

For each source key the compiler emits exactly one of:

- `PARITY_OK` — one source row and one target row match and target sync age is within policy.
- `MISSING_TARGET` — the source key has no target row.
- `FIELD_MISMATCH` — business fields differ, or a fresh target has a different `last_sync_utc`.
- `DUPLICATE_ID` — a source key is duplicated or multiple target rows exist for the key.
- `STALE_SYNC` — business fields match but target sync age exceeds the explicit policy.

Precedence is conservative: duplicate evidence wins first, then missing target, then business-field mismatch, then stale sync, then a fresh timestamp mismatch. Target-only keys are separately reported and prevent a parity-clear aggregate state.

The report contains SHA-256 commitments rather than raw differing field values in row-level diff entries. The local report also embeds the normalized source/target snapshots so the offline verifier can recompile the result byte-for-byte; treat any real-data report as private operational material.

## Frozen synthetic acceptance

`synthetic_acceptance.py` generates exactly 2,000 synthetic/deidentified source records and proves the original demand distribution:

| Classification | Count |
| --- | ---: |
| PARITY_OK | 1,850 |
| MISSING_TARGET | 40 |
| FIELD_MISMATCH | 35 |
| DUPLICATE_ID | 25 |
| STALE_SYNC | 50 |

The acceptance suite also proves identical receipt hashes across repeated runs and rejects records missing canonical ID or term.

Run locally from this directory:

```bash
python -m unittest -v test_engine.py
python -O -m unittest -v test_engine.py
python synthetic_acceptance.py
```

## CLI

Production compile samples current UTC itself; callers cannot backdate current readiness:

```bash
python engine.py compile --input request.json --report report.json --markdown report.md
python engine.py verify --report report.json --markdown report.md
```

`request.json` has exactly `source`, `target`, and `policy`. Outputs are create-exclusive ordinary files; existing final paths and final-component symlinks are refused.

## Truth and authority boundary

`PARITY_CLEAR_FOR_OWNER_REVIEW` means only that the supplied approved snapshots match under the declared policy. It is not a FERPA/security/legal conclusion, a migration completion claim, deployment approval, contract acceptance, buyer acceptance, payment, cash, or recognized revenue. No live Franklin & Marshall, Ellucian, Banner, student, or customer data is checked into this package.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
