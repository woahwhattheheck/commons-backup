# UIOWA-065 observability interview worksheet

Use one row per objective. Preserve source references and unresolved questions.

| Service / objective | User-visible outcome | Indicator and window | Target | Definition / measurement evidence | Dependency visibility | Diagnostic context | Decision-use evidence | Evidence state | Follow-up |
|---|---|---|---|---|---|---|---|---|---|
| SYN-REG / REG-01 | Eligible fictional registration attempt succeeds | success ratio / rolling 30 days | >= 99.5% | SYN-REG-DEF-01 / SYN-REG-MEASURE-01 | one visible, one partial | correlation id; dependency result; error class | SYN-REG-DECISION-01 | SUPPORTED | What additional dependency evidence would reduce diagnostic ambiguity? |
| SYN-RES / RES-01 | Fictional submission receives durable acknowledgement | acknowledgement ratio / calendar month | >= 99% | SYN-RES-DEF-01 / SYN-RES-MEASURE-01 | unknown | submission id; processing stage | none retained | SUPPORTED measurement; decision use unresolved | Which dependencies can delay acknowledgement, and where is objective review recorded? |
| SYN-SIGNIN / SIGNIN-01 | Fictional authorized user completes sign-in promptly | backend handler latency / rolling 7 days | p95 <= 1200 ms | definition missing / SYN-SIGNIN-MEASURE-01 | directory dependency unknown | none retained | none retained | PARTIAL | What user-visible journey indicator, definition, dependency context, and decision record are needed? |

## Blank capture row

| Service / objective | User-visible outcome | Indicator and window | Target | Definition / measurement evidence | Dependency visibility | Diagnostic context | Decision-use evidence | Evidence state | Follow-up |
|---|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  | UNKNOWN |  |

## Review notes

- A measurement can be technically sound while still failing to represent user experience.
- Dependency visibility is recorded independently from the local indicator.
- Dashboard existence is not evidence that the objective influences decisions.
- Missing evidence stays UNKNOWN; it is not treated as a failed practice.
- Infrastructure health and user-visible service objectives may both be useful, but they answer different questions.
