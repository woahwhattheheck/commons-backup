# UIOWA-099 source notes

## 1. Current build-order requirement

The live UIOWA-099 work order requires the closeout kit to “accurately reflect the RFQ's 30-day post-completion requirement” and to translate NDA/confidential-use/return-destruction/closeout requirements into practical records.

**Treatment:** operational requirement for this build; **primary agreement locator pending**. The kit carries the 30-calendar-day value but refuses to label it a verified controlling-clause citation until the actual RFQ/agreement locator is supplied.

## 2. Commons workshare evidence boundary

Repository source:
`revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`, Section 8 (“Evidence, privacy, and repository boundary”).

Relevant constraints preserved in this kit:

- real University, prime, customer, credential, or confidential assessment evidence must not be committed to the public Commons repository;
- operational evidence should use minimum-necessary content and stable source references/digests;
- secrets, credentials, private source material, and restricted evidence stay in an authorized private custody boundary;
- public repository receipts prove code/artifact state only, not permission to publish customer facts.

The exhibit also says controlling RFQ materials, amendments, Q&A, eBid instructions, prime commitments, and any executed agreement supersede the exhibit where they differ.

## 3. University standard terms — separate records boundary

The University of Iowa Standard Terms and Conditions attached to the solicitation include Section 12, “University records,” stating that the contractor shall not remove University records from the University.

This is a records-custody constraint, not the source used to invent the 30-day closeout deadline.

Public solicitation attachment trail:
- University of Iowa RFQ 18649 public portal / solicitation attachment listing
- Standard Terms and Conditions 2026.06.30 FINAL
- Professional Services Agreement with Travel Addendum 2026.02.25 FINAL (exact closeout locator still to be bound for live use)

## 4. Pre-live source freeze checklist

Before this kit is used on real University evidence:

1. identify the executed/controlling agreement version;
2. record the exact section/paragraph governing confidentiality, permitted use, return/destruction, timing, and written confirmation;
3. confirm whether the 30-day period is calendar days or defined otherwise by the controlling agreement;
4. record any legal-hold, records-preservation, or University-instruction exception;
5. set `primary_requirement_locator_status` to `verified_controlling_source` only after those checks.

No synthetic fixture in this directory is a University finding or real customer record.
