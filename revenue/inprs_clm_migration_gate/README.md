# INPRS CLM migration + public-release evidence gate

This package is a **data-free acceptance harness** derived from Indiana Public Retirement System RFP 26-04. It is intended to help a qualified CLM prime prove a bounded migration/publication workstream; it is not a CLM product, an Icertis implementation, an INPRS submission, or evidence of agency acceptance.

## Source scope and planning

Use the [original RFP](https://www.in.gov/inprs/files/rfp-documents/RFP26-04ContractLifecycleManagement(CLM)System.pdf) together with the [published inquiry answers](https://www.in.gov/inprs/files/rfp-documents/RFP26-04ContractLifecycleManagementCRMSystemResponsestoInquiries.pdf). The [current qualification record](https://github.com/woahwhattheheck/commons/issues/14580) maps the answered questions and separates the delivered source from remaining partner and proposal work.

The schema and fictional fixture demonstrate verifier behavior. They do not define INPRS's inventory, migration scope, reference qualifications or acceptance criteria. In particular, a version-history field in this package is not evidence that legacy Word histories must be migrated; consult inquiry answers 8–9 before proposing the source asset set. Future CLM version-management functionality and legacy-export acceptance are separate workstreams.

The original RFP specifies proposals due October 16, 2026 at 3:00 PM EDT (cover, §1.7 and §1.16). Re-check the [official procurement page](https://www.in.gov/inprs/about-us/procurement) for changes before relying on that deadline.

## What the gate proves

Given a candidate JSON evidence bundle, `verify_bundle.py` fails closed unless all of these invariants hold:

- the declared source row count reconciles exactly, preventing a silent migration drop;
- legacy IDs are unique;
- every amendment has a resolvable parent chain terminating at a master, with no cycles;
- migrated document hashes equal source document hashes;
- each document has a consecutive version history whose final revision equals the migrated hash;
- public projections are one-to-one with records declared for publication;
- withheld records never appear in the public projection;
- redacted public documents use a distinct declared hash plus a redaction-attestation hash;
- public rows contain only an explicit metadata allowlist;
- search terms are an exact deterministic projection of the required searchable metadata;
- Certificates of Insurance, W-9s, and SOC reports remain internal and byte-preserved;
- the emitted report is canonical JSON, so identical evidence produces byte-identical receipts.

This is deliberately narrower than full CLM acceptance. It does **not** prove Microsoft Word integration, DocuSign behavior, Outlook integration, Icertis configuration, authentication/authorization, production security, availability, agency policy correctness, legal sufficiency of a redaction, or actual Conga connectivity.

## Bundle shape

`fixtures/golden_bundle.json` is a synthetic six-contract example with two masters and four amendments. Its counts and historical revisions exercise the schema and are not a current INPRS inventory or migration requirement. It includes full publication, redacted publication, an explicit legal-review hold, version histories, and three internal vendor documents. It contains no INPRS or vendor production data.

A real evidence run should be generated from immutable source/export manifests. The `expectations` counts must be populated from that independently frozen manifest rather than calculated from the candidate migration itself; otherwise a dropped row could lower both the data and the expectation together.

## Run

```bash
python revenue/inprs_clm_migration_gate/verify_bundle.py \
  revenue/inprs_clm_migration_gate/fixtures/golden_bundle.json
```

A passing CLI run exits `0`. Any invariant failure exits `2`. Use `--report PATH` to write the same canonical receipt that is printed to stdout.

## Handoff to a CLM prime

The useful commercial workstream is not “we implement Icertis.” It is independently testable migration/release evidence:

1. freeze source export counts and document hashes;
2. migrate into the prime's candidate CLM environment;
3. export a normalized evidence bundle;
4. run this gate and repair every deterministic failure;
5. separately witness product-specific workflows (Word redlining, approvals, signatures, permissions, integrations);
6. obtain INPRS/prime approval for the actual redaction policy and public-portal acceptance set.

The verifier can be adapted to the prime's export schema without changing these invariants. Any such adapter should preserve the raw source manifest and emit the normalized bundle as a separate derived artifact.
