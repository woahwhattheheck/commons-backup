# Testing portfolio

**SYNTHETIC EXAMPLE**

Assessment of supplied assertion-specific records. Locators and declared resolutions are not independently authenticated. No tests are executed and no release is authorized.

| Assertion state | Count |
|---|---:|
| SUPPORTED | 4 |
| OPEN_FAILURE | 1 |
| UNTESTED | 1 |
| UNCERTAIN | 1 |
| OUT_OF_SCOPE | 1 |

Supplied runs: 8. Current supporting runs: 6. Unresolved failures: 1.

| Assertion | Service | Level | State | Supporting runs | Open failures |
|---|---|---|---|---|---|
| A01 | ESS | unit | SUPPORTED | R01, R08 |  |
| A02 | ESS | integration | SUPPORTED | R02 |  |
| A03 | ESS | end-to-end | SUPPORTED | R03 |  |
| A04 | RIS | contract | SUPPORTED | R04 |  |
| A05 | RIS | end-to-end | UNTESTED |  |  |
| A06 | IAM | end-to-end | UNCERTAIN |  |  |
| A07 | Shared | integration | OPEN_FAILURE | R07 | R09 |
| A08 | ESS | user-acceptance | OUT_OF_SCOPE |  |  |

## Regression selection

Selection proposal only, including every unresolved failure. No budget silently removes checks.

- C01: CHANGED_COMPONENT
- C02: CHANGED_COMPONENT
- C03: CHANGED_COMPONENT
- C07: UNRESOLVED_FAILURE
- C08: CHANGED_COMPONENT

Known estimated effort: 12 minutes. Unknown effort: C03.

## Duplicate candidates

- C01, C08: same declared assertion, layer, boundary and equivalence key. Confirm failure-mode independence before consolidation.

## Improvement assumptions

Qualitative gain categories are analyst assumptions. Dominance is compared only for identical assertion sets; it is not a confidence score.

| Proposal | Gain | Minutes | State | Dominated by |
|---|---|---:|---|---|
| P01 | high | 30 | ASSESSED |  |
| P02 | medium | 90 | ASSESSED | P01 |
| P03 | unknown | unknown | UNKNOWN_ASSUMPTIONS |  |
| P04 | high | 20 | ASSESSED |  |
