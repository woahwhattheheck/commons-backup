# Catawba ERP implementation evidence workstream

Internal source/test/demo + commercial carrier for Catawba County RFP 27-1004. It turns a plausible specialist seam into executable acceptance evidence without representing Token Junkie Labs as the ERP software prime.

## Demonstrated contract

- deterministic PeopleSoft-era source identities across finance, procurement, HR, and payroll domains;
- exact source→target migration reconciliation, including missing/extra/changed records and amount-total conservation;
- fixture guardrails against committing obvious raw SSNs, bank/routing data, birth dates, home addresses, or personal email;
- interface request/replay identity, retry monotonicity, timeout recovery, and duplicate-commit detection;
- requirement-linked UAT result/evidence hashes;
- a combined cutover gate that may become `ready_for_owner_review` but always keeps `production_cutover_authority=false` and `county_submission_authority=false`.

The checked-in fixture is synthetic and tokenized. It is not County data, does not prove a live ERP integration, and does not satisfy Attachment C on behalf of any prime.

## Dated Addendum 2 source update

The October 4 [source reconciliation](../rfp_addenda_delta/packets/catawba_erp_27_1004_20261004/README.md) binds the recovered September 25 Addendum 2 and records the existing addenda checker's **SOURCE_REFRESH_REQUIRED** result. A-D workbook custody and named source ambiguities remain open. See `RFP_LINKAGE.md` before reusing opportunity assumptions. The synthetic implementation product, accepted proof and `PROPOSED_NOT_ACCEPTED` offer retain their existing boundaries.

## Verify

```bash
python -m unittest -q tests/test_acceptance.py
PYTHONOPTIMIZE=1 python -m unittest -q tests/test_acceptance.py
python scripts/verify_demo.py
```

See `RFP_LINKAGE.md` for source-bound opportunity logic and `OFFER.md` for the `PROPOSED_NOT_ACCEPTED` specialist workshare.

## Outbound / transport guard

Before sharing the package with any ERP vendor or integrator: re-check current Addenda; run the exact commit tests; re-census Slack and Gmail for that organization + RFP 27-1004; obtain Muse single-writer clearance; send at most the cleared message; then make the organization/opportunity route DNR until a genuinely newer human/provider event. No County contact or sealed submission is authorized by this repository.
