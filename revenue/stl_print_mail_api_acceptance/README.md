# St. Louis Print & Mail API — acceptance/evidence rail

Operation: `STL-PRINT-MAIL-API-2027BID000033-ZSHM6Q4-20260913`

This is a **network-free technical acceptance carrier**, not a bid and not a claim that TJLabs satisfies the City of St. Louis procurement packet.

## Verified public procurement envelope

The City public procurement detail page identifies `2027BID000033`, **CONTRACT- Print & Mail API**, as a fixed-price service opened September 9, 2026 and closing October 6, 2026 at noon. The same page states vendor questions are due September 24, requires a product-specification attachment with the bid, lists insurance and multiple signed/notarized forms, and warns that vendor registration can take up to seven days.

Controlling public detail page:

`https://www.stlouis-mo.gov/government/procurement/single-procurement-view.cfm?id=300000175255557`

The product-specification attachment was **not available in the indexed evidence used to author this carrier**. Therefore every product-specific compliance conclusion is `PACKET_REQUIRED`. This package must not convert secondary summaries, vendor marketing, or generic API capabilities into City requirements.

## What the rail proves

Given buyer-approved or synthetic evidence, `validator.py` checks a narrow integration-control boundary:

- exact City bid identity and official-source host/path;
- explicit `TEST` vs `LIVE` environment separation;
- exact SHA-256 binding from content artifact → rendered proof → human authorization;
- LIVE authorizer membership by department;
- no submission before proof/authorization;
- idempotency-key and logical-job uniqueness;
- TEST cannot create a physical effect;
- `UNKNOWN_EFFECT` fails closed;
- provider events must bind to the exact provider request, follow submission time, remain ordered, and stop after a terminal provider state;
- provider submission is not silently promoted to delivery;
- expected LIVE costs are reconciled to a department-specific synthetic/buyer-approved budget ceiling;
- receipt is deterministic and self-integrity-bound.

Even with a packet hash present, the strongest result is `OWNER_REVIEW`; there is no autonomous `READY_TO_BID` or `SUBMIT` state.

## What it never authorizes

The receipt permanently sets these authorities false: City bid submission/contact, provider mutation, purchase/spend, signature/notarization, compliance claims, and award/revenue recognition. A receipt can establish only the integrity of the evidence supplied to this local rail. It cannot establish current City requirements, provider truth, procurement eligibility, or contract award.

## Run

```bash
python -m revenue.stl_print_mail_api_acceptance.cli \
  revenue/stl_print_mail_api_acceptance/example_fixture.json
```

Focused tests:

```bash
python -m unittest -v tests.test_stl_print_mail_api_acceptance
python -O -m unittest -v tests.test_stl_print_mail_api_acceptance
```
