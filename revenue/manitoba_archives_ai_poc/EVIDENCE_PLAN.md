# Evidence plan for the Archives AI PoC pursuit

This plan separates **technical evidence we can build** from facts only the buyer, controlling RFP, or company owner can establish.

## Technical evidence families

These can be demonstrated on synthetic or lawfully supplied test material once the controlling package identifies the required workflow:

- source/version/content-hash provenance and citation custody;
- corpus snapshot and change detection;
- explicit abstention when evidence is absent;
- human-review routing for records/policies marked review-required by an authoritative policy input;
- retrieval boundary checks and no hidden cross-corpus source use;
- deterministic replay receipts for fixed model/prompt/policy/source versions;
- model/prompt/policy version registry and change log;
- evaluation fixtures with source-bound expected behavior;
- exportable audit evidence without claiming semantic/legal correctness beyond the test contract.

`poc_acceptance.py` provides an initial synthetic implementation of these invariants.

## Facts that must not be inferred

Do not turn generic archive/AI practice into University facts. Keep these unknown until source-bound:

- sensitivity or legal classification of any University record;
- public/private/restricted access rights;
- applicable privacy, archival, records, Indigenous-data, accessibility, copyright, security, residency, or retention obligations;
- permission to send University data to any hosted AI/API/provider;
- required accuracy, recall, hallucination, bias, latency, cost, or throughput threshold;
- required technology/model/provider;
- production deployment scope;
- bidder eligibility, certifications, insurance, references, staffing, local-presence, or financial qualifications.

## Suggested evidence matrix after requirement extraction

For every mandatory/evaluated RFP requirement, create one row with:

- requirement ID;
- controlling source ID + SHA + locator;
- classification (`MANDATORY`, `EVALUATED`, `INFORMATIONAL`);
- claimed response;
- evidence ID(s) and exact artifact SHA(s);
- owner of any attestation-only fact;
- gap status;
- proposed proposal section;
- validation method;
- last verified source/currentness timestamp.

A synthetic PoC PASS is only one possible evidence artifact. It cannot satisfy an official requirement unless the requirement explicitly maps to what the artifact proves.
