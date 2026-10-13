# Illinois TRS Investment-Technology Interoperability Evidence Workshare

**State on publication:** `HOLD_CONTROLLING_PACKET`  
**Commercial state:** `$24,000 fixed / PROPOSED_NOT_ACCEPTED`  
**External authority:** none.

This opportunity-specific package is deliberately not a generic investment-operations engine. It preserves the source/finalization custody of `smb-showcase-inventory#1364` (Investment Operations Implementation Acceptance Desk) and can later feed that product once it exists. It also treats the shipped Investment Position Rollforward workbench (`#1292/#1354`) as a reusable control, not code to copy.

## Why this exists

A current third-party discovery listing describes an Illinois Teachers' Retirement System investment-technology/RFP-consulting pursuit involving a multi-system investment stack and objectives around interoperability, authoritative data, reconciliation/reporting, analytics and governance. TRS first-party procurement pages were checked, but the exact controlling buyer-hosted packet was not recovered from the public surfaces available to this build.

Accordingly, every opportunity-specific stack/objective fact in `example_input.json` remains `THIRD_PARTY_DISCOVERY`. The fixture marks those page observations `METADATA_ONLY`; their synthetic fixture digests are **not** represented as downloaded page bytes. The compiler cannot promote that material to buyer authority.

## Trust boundary

`controlling_packet.status = RETAINED_CURRENT` in input JSON is not authority.

To clear the packet gate, the source must be `BUYER_FIRST_PARTY`, must explicitly bind `RETAINED_BYTES`, and compile/verify must also receive an **out-of-band** `--trusted-packet-sha256` exactly matching that source record. This prevents a caller from changing both a payload status and a payload digest and thereby minting readiness.

Even with that gate clear, every system/objective/control used for qualification must itself be supported by buyer-first-party evidence. Otherwise the strongest state is `HOLD_SOURCE_AUTHORITY`.

The highest state emitted by this tool is `READY_FOR_PARTNER_QUALIFICATION`. There is no bid-ready, submission-ready, award, payment, investment/trading, accounting/compliance, or revenue authority in the schema.

## Current useful output

Even while held, the compiler produces:

- a deterministic source-authority inventory;
- a per-domain system matrix;
- explicit multi-system authority-review seams (for example overlapping market-data systems);
- proposed control definitions linked to their evidence sources;
- all source-authority holds;
- hard-false external authority flags;
- exact input/report receipts suitable for later replay.

## Proposed paid workshare

Subject to the real RFP and a qualified prime/consulting partner:

1. **Investment data authority map** — owner-approved source-of-record roles by domain, with collision/override rules.
2. **Cross-system mapping and reconciliation evidence** — retained source/target mappings, deterministic control totals and exception queues.
3. **Parallel-run acceptance** — position/accounting/performance reference comparisons using approved closed snapshots and explicit tolerances.
4. **Data-quality and provenance controls** — source identity, completeness, chronology, duplicate/remint resistance and replay receipts.
5. **Implementation acceptance handoff** — feed validated artifacts into the generic Investment Operations Implementation Acceptance Desk when that product is available.

No TRS contact, bidder representation, production data request, trading/investment advice, proposal submission, platform mutation, or customer acceptance is performed here.

## Commands

Current discovery-only fixture:

```bash
python trs_interop.py compile --input example_input.json --output report.json
python trs_interop.py verify --input example_input.json --report report.json
```

Expected state: `HOLD_CONTROLLING_PACKET`.

After retaining exact buyer-hosted packet bytes, update the source ledger from those bytes and supply their trusted SHA out of band:

```bash
python trs_interop.py compile --input authoritative_input.json --output report.json --trusted-packet-sha256 <sha256>
```

Do not substitute a discovery-page hash for the buyer packet.
