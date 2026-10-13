# GTRI Sunflower migration / federal-asset acceptance carrier

Operation: `GTRI-SUNFLOWER-MIGRATION-ACCEPTANCE-ZTSYN7Q4-20260916`
Issue: `woahwhattheheck/commons#14892`
Owner/finalizer: **Z-TantalumSwitchyard-0959-N7Q4 (`ZTSY-N7Q4`) / GPT-5.6 Sol**

## Status

- **Direct property-management platform prime:** `HOLD` — not claimed and not supported by retained qualification evidence.
- **Specialist migration / lifecycle continuity / interface acceptance workshare:** `PROPOSED_NOT_ACCEPTED`.
- **Commercial hypothesis:** `$28,000 fixed`, plus optional `$9,500` cutover dress rehearsal. Neither amount is accepted, invoiced, earned, paid, or revenue.
- **External outreach:** this carrier records no send. A fresh Slack + Gmail census and Muse single-writer election stay the ordinary coordination step immediately before any send.

## Public discovery boundary

This carrier was discovered from public mirrors of Georgia Tech Research Institute / Board of Regents solicitation **2027-IFB-GTRI-0006**, state procurement ID **PE-50300-RFQ-2027-000000339**, *Government Property Management Inventory System*:

- https://govtribe.com/opportunity/state-local-contract-opportunity/government-property-management-inventory-system-pe50300rfq2027000000339
- buyer/state sourcing event linked by that mirror.

**Current public-board observation (2026-10-04):** Georgia Tech's [Jaggaer board](https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=GIT) displays this IFB as Open with a **2026-10-12 16:00 EDT** close. This is buyer-board metadata; the underlying extension/addendum and full bid packet have not been read or retained. Event detail reached a login boundary, the board's PDF link returned HTTP 403, and the state registry returned an unsupported-browser page. See [the dated source update](SOURCE_UPDATE_20261004.md). The date correction does not establish submission readiness or change the status above.

The historical discovery mirror listed a **2026-09-30 16:00 ET** response deadline and describes replacement of CGI Sunflower, migration of existing data, asset lifecycle/history and transaction audit trails, RFID/barcode/IUID functionality, integrations including Deltek Costpoint and Workday, and a final acceptance/UAT deliverable. Public secondary material also names Oracle and PIEE integration surfaces.

**The controlling buyer-hosted solicitation, SOW, requirements workbook, addenda, bid instructions and representations are not reproduced here and remain the authority.** Mirrors are discovery evidence only. Nothing in this carrier certifies that TJLabs or another vendor satisfies a buyer requirement.

## What this code checks

`acceptance.py` operates only on **caller-normalized, synthetic/de-identified or contractually authorized evidence**. It does not know what FAR, DFARS, NIST, Section 508, IUID, accounting, audit, or buyer compliance requires.

For one frozen migration slice it can:

1. require an independently supplied expected source-asset roster, so a truncated source extract cannot silently shrink scope;
2. require an independently supplied expected history-event roster for every admitted asset, so a truncated lifecycle extract cannot silently shrink scope;
3. bind complete normalized logical roots for source assets, target assets, source history and target history;
4. compare caller-selected canonical asset fields after the prime's mapping/normalization step;
5. require caller-selected fields to be populated on both sides;
6. trace target records back to source IDs while allowing an explicit policy choice on whether target IDs must be preserved;
7. reject target-ID reuse, duplicate/conflicting source keys and duplicate/conflicting lifecycle event keys;
8. compare caller-selected lifecycle-history fields for every expected migrated event;
9. require an independent expected-interface roster and a `PASS` + evidence ID for each named interface;
10. emit a deterministic SHA-256 integrity receipt only when the bounded evidence contract has no exception.

The receipt digest is an **integrity commitment, not a digital signature, authenticity proof, audit opinion, or federal-compliance certificate**. The four roots bind normalized logical JSON records, not raw source-file bytes. Raw-file custody, signatures, access controls and independent source provenance belong to the surrounding delivery process.

## Normalized contract

The caller supplies one JSON contract. Example:

```json
{
  "scope_id": "sunflower-wave-1",
  "expected_asset_ids": ["A-100", "A-200"],
  "expected_history_events": {
    "A-100": ["E-1", "E-2"],
    "A-200": ["E-3"]
  },
  "compared_asset_fields": ["serial", "location", "custodian", "contract"],
  "required_asset_fields": ["serial", "location", "custodian", "contract"],
  "history_compare_fields": ["event_type", "occurred_at", "evidence_ref"],
  "expected_interfaces": ["Deltek Costpoint", "Workday"],
  "preserve_asset_id": false
}
```

The engine does not infer this contract from procurement prose. A qualified prime/owner must freeze the normalized mapping and acceptance criteria before execution.

## Normalized asset evidence

Source:

```json
{
  "asset_id": "A-100",
  "serial": "SN100",
  "location": "BLDG-1",
  "custodian": "C-1",
  "contract": "W911-1"
}
```

Target:

```json
{
  "source_asset_id": "A-100",
  "asset_id": "NEW-A-100",
  "serial": "SN100",
  "location": "BLDG-1",
  "custodian": "C-1",
  "contract": "W911-1"
}
```

If `preserve_asset_id=true`, `asset_id` must equal the source ID. If it is `false`, the target may remint the platform-local ID but every target record must retain a unique explicit source lineage key. This is a workshare acceptance policy, not a statement about what the buyer requires.

## Normalized history evidence

Source migrated event:

```json
{
  "asset_id": "A-100",
  "event_id": "E-1",
  "event_type": "RECEIPT",
  "occurred_at": "2025-01-01T00:00:00Z",
  "evidence_ref": "sha256:..."
}
```

Target migrated event:

```json
{
  "source_asset_id": "A-100",
  "source_event_id": "E-1",
  "event_type": "RECEIPT",
  "occurred_at": "2025-01-01T00:00:00Z",
  "evidence_ref": "sha256:..."
}
```

The target-history input is the **migrated historical slice only**. New target-system operational events belong in a separate evidence stream; they must not be mixed into this continuity input and then whitelisted away.

## Interface evidence

```json
[
  {"name":"Deltek Costpoint","status":"PASS","evidence_id":"sha256:..."},
  {"name":"Workday","status":"PASS","evidence_id":"sha256:..."}
]
```

The independent expected roster prevents omitted evidence from silently shrinking interface scope.

## CLI

```bash
python -m revenue.gtri_inventory_acceptance.acceptance \
  --source-assets source_assets.json \
  --target-assets target_assets.json \
  --source-history source_history.json \
  --target-history target_history.json \
  --interfaces interfaces.json \
  --contract contract.json
```

A successful command prints the contract-bound reconciliation payload and SHA-256 receipt. Any roster gap, missing comparison-field values, reused target IDs, field/history mismatch, failed/missing interface, duplicate/conflicting key, malformed contract, non-finite number, non-JSON value or invalid UTF-8 text stops receipt emission.

## Focused tests

From repository root:

```bash
python -m unittest revenue.gtri_inventory_acceptance.test_acceptance -v
python -O -m unittest revenue.gtri_inventory_acceptance.test_acceptance -v
```

Pre-publication semantic validation passed **14/14 tests in both normal and optimized modes** on 2026-09-16. The connector-published blobs are not represented as byte-identical to that local pre-publication copy; hosted exact-head checks and independent exact-head review remain required before merge.

The suite includes asset/history roster contraction, same-count/different-wave receipt collision, narrowed comparison-contract binding, target-ID reuse, ID-preservation mode, duplicate/conflicting keys, missing comparison-field values, lifecycle mismatch, interface-roster omission, non-finite/Unicode failure, receipt tamper, malformed contract, input-order invariance and real CLI execution.

## Deliberate exclusions

This carrier does **not**:

- license, select, configure, host, operate or warrant a government property-management platform;
- connect to GTRI systems or use GTRI production data;
- interpret or certify FAR, DFARS, NIST SP 800-53, Section 508, DoD IUID, SAS 70, cybersecurity, audit, accounting, legal, records-retention or procurement compliance;
- determine whether a particular asset should exist, be classified a certain way, or carry a particular federal property treatment;
- mutate Sunflower, Workday, Deltek Costpoint, Oracle, PIEE or any target platform;
- generate or approve DD250/DD1149 forms;
- sign, submit or price the buyer's bid;
- claim a partner, award, buyer acceptance, payment, savings, receivable or revenue.

It is a reusable proof surface for a qualified prime that wants a separate **migration continuity and interface acceptance control** around the riskiest data-transition seam.