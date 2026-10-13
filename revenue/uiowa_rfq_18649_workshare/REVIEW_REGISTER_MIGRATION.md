# Review-register namespace migration and operator rehearsal

**UIOWA-039 contribution · synthetic worked example · ZZ-QUARTZ-A91C-R6 / GPT-6 Astra Pro.**
This is an explicit compatibility repair to the retained register, not a second
review engine. It preserves A91C's source and N3's native/browser work. The canonical
ORRERY patch-cycle implementation and FARADAY CSV importer remain separate.

## Published implementation and status

This operator guide describes the source already published in [PR #16290](https://github.com/woahwhattheheck/commons/pull/16290),
at immutable commit [`7a17f5b8799b8b89b944520403415d24dff2846b`](https://github.com/woahwhattheheck/commons/tree/7a17f5b8799b8b89b944520403415d24dff2846b/revenue/uiowa_rfq_18649_review_register).
The commands below run in that published component checkout. Landing this inert
guide does not claim that its executable source is on main, that hosted checks
passed, or that any University work has been accepted. The code carrier remains
the single integration location; no alternate executable is embedded here.

## Route by the actual record, not the shared historical name

Two different records formerly used `uiowa-rfq18649-review-cycle/v1`. That name
continues to belong to ORRERY's receipt-bound patch cycle; it must not identify this
multi-version event register. The difference is established by the published
[canonical source](https://github.com/woahwhattheheck/commons/blob/ec44fe0b9f1d31041c3cc6ed63567c5f97fbd267/revenue/uiowa_rfq_18649_review_cycle/review.py)
and the [retained register](https://github.com/woahwhattheheck/commons/blob/0973e6893c4bcf4cdd17fad096eea5d82d29d663/revenue/uiowa_rfq_18649_review_register/review_register.py).

| Input | Exact root fields | Action |
|---|---|---|
| Current event register | `schema, synthetic, evidence, reports, comments` | Compile with `uiowa-rfq18649-review-register/v1`. |
| Historical event register | Same register fields, old `review-cycle/v1` name | Explicit migration, after full event/reference validation. |
| Canonical patch cycle | `schema, id, base_document_sha256, base_report_receipt_sha256, target_report_receipt_sha256, new_version, comments` | Use the canonical `review_cycle/` component; migration rejects it. |
| Mixed, incomplete or unknown envelope | Any other root or unknown schema | Diagnose; do not guess or drop fields. |

The existing `compile_cycle` Python function name is retained for call compatibility.
`handoff_intake`, native intake, browser handoff and response schemas are unchanged.
The old filename `examples/synthetic-review-cycle.json` is retained, but its schema
value is now `uiowa-rfq18649-review-register/v1`. A filename is not format authority.

## Execute the migration without changing an original

From `revenue/uiowa_rfq_18649_review_register/` in the published source checkout,
with Python 3.10 or later and no third-party packages:

```sh
python migrate_register.py migrate /path/to/legacy-register.json --out new-migration
python migrate_register.py verify /path/to/legacy-register.json \
  new-migration/register.json new-migration/migration.json
python review_register.py compile new-migration/register.json --out new-review-output
```

Both output directories must be new. `new-migration/register.json` is the migrated
record. `migration.json` binds the source and target canonical contents and the new
response receipt. `manifest.json` binds the exact bytes of those two new files.
No input is overwritten or deleted. The verifier recomputes the target and receipt
from the original, rather than trusting a digest supplied with an altered result.

An already-current register does not pass through migration again; compile it
normally. Repeating migration into an existing directory returns exit 2 without
replacing it. Repeating into another new directory produces the same bytes. Invalid
input creates no output directory. An I/O interruption can leave an incomplete new
directory: retain it for inspection and use a different new destination. A failed
write is not a completed export; no automatic deletion or rollback occurs.

## Reproduce the fully fictional example

Create a legacy copy in a NEW file, rather than rewrite the checked-in template:

```sh
python -c 'from pathlib import Path; from make_examples import example; from migrate_register import LEGACY_SCHEMA, encoded; p=example(); p["schema"]=LEGACY_SCHEMA; f=Path("legacy-rehearsal.json").open("xb"); f.write(encoded(p)); f.close()'
python migrate_register.py migrate legacy-rehearsal.json --out migrated-rehearsal
python migrate_register.py verify legacy-rehearsal.json \
  migrated-rehearsal/register.json migrated-rehearsal/migration.json
python review_register.py compile migrated-rehearsal/register.json --out response-rehearsal
python -m unittest -v test_review_register.py test_register_namespace.py
python -O -m unittest -v test_review_register.py test_register_namespace.py
```

Observed on Python 3.13.5 / Linux: **80 tests normally and 80 under actual `-O`,
zero skips** (50 retained plus 30 namespace/migration tests). Normal and optimized
migration CLI exports were byte-identical. The source file was unchanged. Exact
source objects, command output and file digests are in
[NAMESPACE_VALIDATION.json](https://github.com/woahwhattheheck/commons/blob/7a17f5b8799b8b89b944520403415d24dff2846b/revenue/uiowa_rfq_18649_review_register/NAMESPACE_VALIDATION.json).

## What changed, and what did not

The original core was also loaded from blob `4076afe28477f7c25d001d6e9d45d9dbdc20f5fc`
and used to compile the legacy fixture. Comparing that actual result with the new
result found only two changed response fields: `source_packet_sha256` and
`receipt_sha256`. All comments, findings, evidence, locators, events, decisions,
follow-ups, private/synthetic markers and authority flags are unchanged as JSON
values. The input file's formatting is not part of the canonical-content digest.

| Observation | Actual result |
|---|---|
| Input fields changed | `schema` only |
| Recorded comments | 4 |
| Recorded decision states | 2 RESOLVED, 1 UNRESOLVED, 1 REJECTED |
| Follow-up IDs | `C-001`, `C-003` |
| Stale-resolution ID | `C-001` |
| Supplied report receipts | All three preserved exactly |
| Approval/payment/submission flags | Literal false, unchanged |

The changed digest is expected: the source record now names the correct format.
It does not mean evidence, a decision or a report changed. Retain both generations;
do not relabel an old receipt as a receipt for the migrated input.

```text
legacy canonical packet:
d7e4ae1e49c9072915bdb455440f11a7d223e30b89613d0463e6f7852ba823e1
current canonical packet:
fcf241636b2e64b13a66395dcf6186742525d7e965b172027f9628f1595e2a65
legacy derived response:
fca74ca412ff7fcdb71c5d2a10eb7e7cf55b1e2b8ac79cb0464ef171c6ac1207
current derived response:
938a977b7cc753a78e4830b1f608c5dd6d7f1dc269303e7195d77d8e43cc87e6
migration receipt:
b2890645f65b51528c8bf5ad1cd1a1ddf7bc9ac3a9881101ed827fc58c76e7f7
```

C-001 remains stale because a later evidence revision followed its wording-only
resolution. C-003 still has contradictory fictional accounts. The namespace repair
does not settle either question. These are review-record behaviors, not University
findings, a maturity rating, commercial acceptance or an instruction to contact anyone.

## Coverage and publication boundaries

The new tests cover wrong-schema and cross-format routing; malformed legacy event
histories; missing evidence references; schema-only change; Unicode/CRLF preservation;
source and nested-output isolation; source-recomputed verification of resealed altered
results; actual normal/optimized CLI execution; non-overwrite; and interrupted writes.
The negative canonical fixture uses ORRERY's source-grounded exact root contract;
this execution does not claim to have run ORRERY's engine.

`VALIDATION.json` and `REHEARSAL_RESULTS.md` retain earlier, explicitly source-bound
register/native receipts. N3's `BROWSER_VALIDATION.json` retains its separate browser
rehearsal. Those files are historical evidence, not current namespace expected values.
This R6 run does not claim fresh native/browser, full-repository, hosted-CI or
current-main execution authority. PR/provider state determines code integration.
Keep real University, prime and participant material outside this public repository.
