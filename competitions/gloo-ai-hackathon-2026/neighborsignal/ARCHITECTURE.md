# NeighborSignal architecture and threat model

## Trust split

**Deterministic authority plane**

`request + resource catalog + trusted process time -> validate -> policy -> plan -> receipt`

This plane alone determines eligibility evidence, action class, authority ceiling, and receipt identity.

**Model advisory plane**

`deterministic plan -> Gloo guarded completion -> explanation / internal question`

The advisory is attached *outside* the receipt-bound plan. A model cannot change an action class, evidence ref, eligibility state, receipt digest, or external authority bit.

## Deliberate non-capabilities

No SMTP, SMS, social, provider-send, payment, purchase, calendar, CRM, case-management, or church-management mutation client exists in the package. There is no function named `send`, `pay`, `approve`, `promise`, `book`, or `contact` exposed to the model.

## Main threats and controls

| Threat | Control |
|---|---|
| model invents eligibility | deterministic requirements only; model advisory cannot mutate plan |
| prompt injection in intake summary | summary is opaque data; no policy parsing from prose |
| stale resource facts | catalog and every resource expire; stale catalog is `HOLD` |
| missing eligibility fact | resource is not eligible; fact is named in reason |
| duplicate / conflicting resource identity | strict duplicate-ID rejection |
| direct PII or credentials | forbidden field-name scan rejects common direct identifiers/secrets |
| caller-selected “current” clock | current API takes no clock; explicit historical API is separately named |
| receipt copied to another case/catalog generation | receipt binds normalized request + catalog + plan + evaluation time |
| model asks for dangerous tool | Gloo adapter rejects every unlisted tool name |
| live provider unavailable | offline simulator is explicit `SIMULATED`; never relabeled live |
| source pretends competition is ready | readiness compiler requires live Gloo receipt + registration + attendance + submission evidence |

## Remaining real-world gates

A production deployment would still need organization-specific privacy review, retention policy, threat modeling for its deployment environment, provider credentials, authenticated catalog stewardship, incident response, and human operating procedures. This hackathon carrier claims none of those as complete.
