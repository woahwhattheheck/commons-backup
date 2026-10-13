# UIOWA-139 acceptance and scope-boundary disposition packets

Isolated path: `revenue/uiowa_rfq_18649_scope_cases/`

Six fully synthetic request → before/after artifact → disposition →
rationale → effort/scope packets plus a clause-linked decision aid.
This is **not** a new review engine and does **not** automatically
accept work, expand scope, or authorize payment.

Pinned source: `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`
blob `48465060fff1402af966871352e894686fffe05e` (PROPOSED / NOT ACCEPTED).

## Packets

| ID | Request | Disposition |
|---|---|---|
| CASE-01 | Broken citation | `ARTIFACT_CURE_IN_SCOPE` ($0) |
| CASE-02 | Disputed supported conclusion | `PRIME_JUDGMENT_NOT_DEFECT` |
| CASE-03 | Newly supplied evidence | `EVIDENCE_DEPENDENCY_HOLD` (not promoted) |
| CASE-04 | Wording preference | `PRIME_JUDGMENT_NOT_DEFECT` |
| CASE-05 | Extra stakeholder / AIS group | `PROPOSED_NEW_SCOPE` (not silently added) |
| CASE-06 | New deliverable | `PROPOSED_NEW_SCOPE` (not silently added) |

Section 2 commercial triggers stay kickoff = written authorization,
draft = delivery, final = acceptance. Product/vendor recommendation is
refused as a controlling RFQ exclusion, not change-control. Effort
figures are labeled **HYPOTHETICAL / NOT ACCEPTED**. $24,000 is the
TJLabs subcontract workshare, not the prime bid fee.

```bash
python3 cli.py --cases ./cases --out /tmp/uiowa139
python3 -m unittest test_cases.py
python3 -O -m unittest test_cases.py
```

Closes woahwhattheheck/commons#16202.
