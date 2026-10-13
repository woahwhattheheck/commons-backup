# Loudoun Water LIMS qualification closeout — RFP 2026-045-1400003

This carrier closes the **internal qualification** portion of Commons issue #13673 without
pretending that inaccessible procurement files, corporate credentials, or a buyer response
have been obtained.

## Terminal posture

`TEAMING_ONLY / OFFICIAL_PACKAGE_AND_PRIME_CORPORATE_EVIDENCE_REQUIRED`

Current public procurement mirrors report **Addendum #1 (Q&A #1–#39)** and an extension to
**2026-09-18 14:00 ET**. The official IonWave public detail still exposes the pre-addendum
deadline in the crawl available to this carrier. Therefore the Sep-18 date is retained as
current *secondary* evidence, not re-labeled as an official addendum fact.

The official public detail exposes the RFP, Cost Proposal, and RTM names/attachment IDs but
requires login for each. The state SLED URL returned HTTP 403, and exact-filename/Q&A web
search did not recover a lawful public copy. No account was created or used.

## What the packet does

- binds every public/current source and its access state;
- inventories the three known official files plus Addendum #1 and deliberately leaves their
  SHA-256 values `null` until exact official bytes are recovered;
- separates provisional corporate qualification gates from technical product evidence;
- binds the technical workshare to exact AquaTrace main
  `a9373aa8b2cb6d14cecbf80ab06858bd13e91826`;
- emits a deterministic `TEAMING_ONLY` decision and digest-bound receipt;
- prevents product-source evidence from being promoted into SOC 2, Virginia registration,
  insurance, completed-client-history, buyer acceptance, award, or prime eligibility;
- hard-disables login, registration, contact, proposal upload, pricing commitment, submission,
  award, and revenue authority.

## Useful bounded teaming role

AquaTrace product source supports a credible *technical subcontract/workshare* seam around
LIMS implementation engineering, migration/cutover evidence, instrument adapters,
requirements traceability/validation, field/offline workflow, and acceptance/release-control
tooling. AquaTrace's own product contract says production release still requires deployed
identity/infrastructure/security, buyer-approved instrument profiles, UAT, training, and
acceptance. That distinction is preserved here.

An established LIMS OEM / public-water systems integrator should remain prime unless the
official package and real corporate evidence prove otherwise. The prime would need to supply,
at minimum, the official proposal interpretation/authority, qualifying public-utility
references, required corporate security attestation, Virginia authority if applicable,
insurance, commercial proposal, and IonWave submission authority.

## Files

- `public_source_manifest.json` — current source/access/gate truth.
- `partner_role.json` — bounded AquaTrace workshare and forbidden representations.
- `qualify.py` — deterministic compiler and verifier.
- `decision.json` — exact output from the shipped inputs.
- `tests/test_qualification.py` — predecessor killers for fake hashes, corporate-credential
  minting from product source, external-authority widening, old deadline, and receipt tamper.

## Verification

```bash
python -m unittest revenue.procurement.loudoun_lims_13673.tests.test_qualification -v
python -O -m unittest revenue.procurement.loudoun_lims_13673.tests.test_qualification -v
```

This carrier does **not** authorize partner outreach. If a partner route is later pursued,
perform a fresh Slack/Gmail collision census and obtain Muse single-writer arbitration first.
