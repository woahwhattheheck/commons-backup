# Delivery-flow assessment

SYNTHETIC REHEARSAL

Observation: 2026-09-01T10:00:00Z

Input SHA-256: `91fdf56e1cc81cc3125e4a30c57992b3366789c6ed1668dc5ea72e5d89acf181`

## Interpretation

- Supplied records are not independent verification or University findings.
- Censored durations are observed lower bounds; unknown durations are not zero.
- Attempt-duration sums are not person-hours. Failure and repeat measures overlap; never add them as savings.
- Unattributed time is not demonstrated waste. A success record is not release approval or whole-service readiness.

## ESS-FICTION — Fictional course catalog

| Measure | Value |
|---|---|
| attempt\_count | 7 |
| failed\_attempt\_count | 1 |
| repeat\_attempt\_count | 1 |
| failed\_execution\_measure\_counts | {'complete': 1, 'censored': 0, 'unknown': 0} |
| repeat\_execution\_measure\_counts | {'complete': 1, 'censored': 0, 'unknown': 0} |
| queue\_measure\_counts | {'complete': 7} |
| execution\_measure\_counts | {'complete': 7} |
| observation\_window\_seconds | 3600.0 |
| queue\_union\_seconds | 960.0 |
| execution\_union\_seconds | 1380.0 |
| queue\_execution\_overlap\_seconds | 60.0 |
| observed\_activity\_union\_seconds | 2280.0 |
| unattributed\_window\_seconds | 1320.0 |
| manual\_queue\_union\_seconds | 600.0 |
| execution\_attempt\_seconds\_sum | 1860.0 |
| failed\_execution\_seconds\_lower\_bound | 240.0 |
| repeat\_execution\_seconds\_lower\_bound | 240.0 |
| recorded\_first\_deployment\_latency\_seconds | 2280.0 |

| Stage | Records | Results | Coverage | Evidence |
|---|---:|---|---|---|
| build | 1 | {'success': 1} | records_supplied | E1 |
| verification | 3 | {'failure': 1, 'success': 2} | records_supplied | E1 |
| packaging | 1 | {'success': 1} | records_supplied | E1 |
| promotion | 1 | {'success': 1} | records_supplied | E1 |
| deployment | 1 | {'success': 1} | records_supplied | E1 |

Reproducibility corroboration: NOT\_ESTABLISHED\_BY\_TOOL

### Follow-up

| Code / subject | Question | Evidence |
|---|---|---|
| FAILED\_ATTEMPT / V1 | What caused this failure; was the next attempt a rerun or changed work? | E1 |
| REPRODUCIBILITY\_REVIEW / reproducibility | What comparable input/artifact records and conditions corroborate this supplied reproducibility account? | E1 |

### Evidence locators

- E1: synthetic.json#/traces/0/attempts

## RIS-FICTION — Fictional grant-routing service

| Measure | Value |
|---|---|
| attempt\_count | 4 |
| failed\_attempt\_count | 0 |
| repeat\_attempt\_count | 0 |
| failed\_execution\_measure\_counts | {'complete': 0, 'censored': 0, 'unknown': 0} |
| repeat\_execution\_measure\_counts | {'complete': 0, 'censored': 0, 'unknown': 0} |
| queue\_measure\_counts | {'censored': 1, 'complete': 2, 'unknown': 1} |
| execution\_measure\_counts | {'censored': 1, 'complete': 1, 'unknown': 2} |
| observation\_window\_seconds | 3600.0 |
| queue\_union\_seconds | 2580.0 |
| execution\_union\_seconds | 3300.0 |
| queue\_execution\_overlap\_seconds | 2400.0 |
| observed\_activity\_union\_seconds | 3480.0 |
| unattributed\_window\_seconds | 120.0 |
| manual\_queue\_union\_seconds | 0.0 |
| execution\_attempt\_seconds\_sum | 3300.0 |
| failed\_execution\_seconds\_lower\_bound | 0 |
| repeat\_execution\_seconds\_lower\_bound | 0 |
| recorded\_first\_deployment\_latency\_seconds | UNKNOWN |

| Stage | Records | Results | Coverage | Evidence |
|---|---:|---|---|---|
| build | 1 | {'success': 1} | records_supplied | E1 |
| verification | 1 | {'unknown': 1} | records_supplied | E1 |
| packaging | 1 | {'unknown': 1} | records_supplied | E1 |
| promotion | 1 | {'unknown': 1} | records_supplied | E1 |
| deployment | 0 | {} | unknown |  |

Reproducibility corroboration: NOT\_ESTABLISHED\_BY\_TOOL

### Follow-up

| Code / subject | Question | Evidence |
|---|---|---|
| OWNER\_UNKNOWN / P1 | Which organizational role maintains this step and handles failures? | E1 |
| TIME\_COVERAGE / P1 | Which queue/start/finish records or current-state observations are missing? | E1 |
| OWNER\_UNKNOWN / M1 | Which organizational role maintains this step and handles failures? | E1 |
| TIME\_COVERAGE / M1 | Which queue/start/finish records or current-state observations are missing? | E1 |
| STAGE\_UNKNOWN / deployment | Is this stage absent, external/shared, combined with another step, or unrecorded? |  |
| REPRODUCIBILITY\_REVIEW / reproducibility | What comparable input/artifact records and conditions corroborate this supplied reproducibility account? | E1 |

### Evidence locators

- E1: synthetic.json#/traces/1/attempts

## IAM-FICTION — Fictional affiliation sync

| Measure | Value |
|---|---|
| attempt\_count | 2 |
| failed\_attempt\_count | 0 |
| repeat\_attempt\_count | 1 |
| failed\_execution\_measure\_counts | {'complete': 0, 'censored': 0, 'unknown': 0} |
| repeat\_execution\_measure\_counts | {'complete': 0, 'censored': 0, 'unknown': 1} |
| queue\_measure\_counts | {'complete': 1, 'unknown': 1} |
| execution\_measure\_counts | {'complete': 1, 'unknown': 1} |
| observation\_window\_seconds | 3600.0 |
| queue\_union\_seconds | 60.0 |
| execution\_union\_seconds | 60.0 |
| queue\_execution\_overlap\_seconds | 0.0 |
| observed\_activity\_union\_seconds | 120.0 |
| unattributed\_window\_seconds | 3480.0 |
| manual\_queue\_union\_seconds | 0.0 |
| execution\_attempt\_seconds\_sum | 60.0 |
| failed\_execution\_seconds\_lower\_bound | 0 |
| repeat\_execution\_seconds\_lower\_bound | 0 |
| recorded\_first\_deployment\_latency\_seconds | 840.0 |

| Stage | Records | Results | Coverage | Evidence |
|---|---:|---|---|---|
| build | 1 | {'success': 1} | records_supplied | E1 |
| verification | 0 | {} | unknown |  |
| packaging | 0 | {} | unknown |  |
| promotion | 0 | {} | unknown |  |
| deployment | 1 | {'success': 1} | records_supplied |  |

Reproducibility corroboration: NOT\_ESTABLISHED\_BY\_TOOL

### Follow-up

| Code / subject | Question | Evidence |
|---|---|---|
| OWNER\_UNKNOWN / B2 | Which organizational role maintains this step and handles failures? | E1 |
| TIME\_COVERAGE / B2 | Which queue/start/finish records or current-state observations are missing? | E1 |
| UNREFERENCED\_RECORD / D1 | Which retained source supports this supplied attempt record? |  |
| ATTEMPT\_GAPS / build/package | Are attempts \[1\] missing from this export? |  |
| STAGE\_UNKNOWN / verification | Is this stage absent, external/shared, combined with another step, or unrecorded? |  |
| STAGE\_UNKNOWN / packaging | Is this stage absent, external/shared, combined with another step, or unrecorded? |  |
| STAGE\_UNKNOWN / promotion | Is this stage absent, external/shared, combined with another step, or unrecorded? |  |
| REPRODUCIBILITY\_REVIEW / reproducibility | What comparable input/artifact records and conditions corroborate this supplied reproducibility account? |  |

### Evidence locators

- E1: synthetic.json#/traces/2/attempts
