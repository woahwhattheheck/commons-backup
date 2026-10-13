# Requirements-to-acceptance traceability (UIOWA-042)

**These examples are fictional.** Every request, criterion, implementation,
test and acceptance record below was invented for rehearsal. Not a
University of Iowa finding and not a statement about University delivery
practice. No individual is named.

The chain: request → acceptance criterion → implementation → test → user
acceptance. A criterion closes only when every link resolves **and** the
acceptance is recorded against the criterion's current revision.

## UIOWA-042-SYNTHETIC-MAINTENANCE-001 — maintenance_change

**Verdict: `EVIDENCED`** — every current criterion traces to a recorded acceptance of the current revision

| State | Criteria | Meaning |
| --- | ---: | --- |
| TRACED | 2 | every link resolves and acceptance is recorded against the current revision |

| Criterion | Rev | State | What the records show |
| --- | ---: | --- | --- |
| `AC-200-01` | 1 | TRACED | implemented by IMP-200-01; no dedicated test; declared covered by synthetic://uiowa-rfq18649/042/regression-suite-statements; accepted by business office liaison on 2026-08-14 |
| `AC-200-02` | 1 | TRACED | implemented by IMP-200-02; tests passing: TST-200-02; accepted by business office liaison on 2026-08-14 |

## UIOWA-042-SYNTHETIC-PROJECT-001 — project

**Verdict: `NOT_ESTABLISHED`** — at least one criterion has an open question; see the follow-ups

| State | Criteria | Meaning |
| --- | ---: | --- |
| TRACED | 2 | every link resolves and acceptance is recorded against the current revision |
| ACCEPTED_AGAINST_SUPERSEDED_REVISION | 1 | acceptance exists, but against an earlier revision of this criterion |
| INCOMPLETE_ACCEPTANCE | 2 | nobody has recorded accepting this, or the acceptance has no evidence behind it |
| TEST_NOT_PASSING | 1 | a test exists but did not pass, or was never run |
| UNTESTED | 1 | implemented with no test and no declared regression coverage |
| NOT_IMPLEMENTED | 1 | no implementation record references this criterion |
| SUPERSEDED | 1 | this revision was replaced; its successor carries the requirement |

| Criterion | Rev | State | What the records show |
| --- | ---: | --- | --- |
| `AC-100-01` | 2 | ACCEPTED_AGAINST_SUPERSEDED_REVISION | implemented by IMP-100-01; tests passing: TST-100-01; accepted against revision 1; this criterion is at revision 2 |
| `AC-100-02` | 1 | INCOMPLETE_ACCEPTANCE | implemented by IMP-100-02; tests passing: TST-100-02; no user acceptance record |
| `AC-100-03` | 1 | TRACED | implemented by IMP-100-03; tests passing: TST-100-03; accepted by research administration lead on 2026-05-30 |
| `AC-100-04` | 1 | SUPERSEDED | replaced by AC-100-05 |
| `AC-100-05` | 1 | TRACED | implemented by IMP-100-05; tests passing: TST-100-05; accepted by research administration lead on 2026-05-30 |
| `AC-100-06` | 1 | NOT_IMPLEMENTED | — |
| `AC-100-07` | 1 | TEST_NOT_PASSING | implemented by IMP-100-07; test results: FAIL |
| `AC-100-08` | 1 | UNTESTED | implemented by IMP-100-08 |
| `AC-100-09` | 1 | INCOMPLETE_ACCEPTANCE | implemented by IMP-100-09; tests passing: TST-100-09; acceptance recorded by research administration lead with no evidence locator |

### Follow-up questions

These are questions, not conclusions. Nothing below is resolved by
this tool.

- **`AC-100-01`** (ACCEPTED_AGAINST_SUPERSEDED_REVISION) — The requirement changed after this was accepted. Ask who accepted revision 2 and whether the change was reviewed with them; do not carry the earlier acceptance forward.
- **`AC-100-02`** (INCOMPLETE_ACCEPTANCE) — Ask who agreed the delivered work met the need, when, and where that is recorded. A passing test is not a substitute for that record.
- **`AC-100-06`** (NOT_IMPLEMENTED) — Ask whether this criterion was dropped, deferred, or delivered under another record. A criterion with no implementation is not evidence of anything either way.
- **`AC-100-07`** (TEST_NOT_PASSING) — Ask what the failing or unrun test covers, and what was done about it before delivery.
- **`AC-100-08`** (UNTESTED) — Ask how this change was checked. If an existing regression suite covers it, record that locator rather than assuming it.
- **`AC-100-09`** (INCOMPLETE_ACCEPTANCE) — Ask who agreed the delivered work met the need, when, and where that is recorded. A passing test is not a substitute for that record.

## Still UNKNOWN (University inputs not collected)

- where business requests are recorded, and whether acceptance criteria live with them
- who is empowered to accept delivered work, by role
- whether acceptance is recorded at all for maintenance changes
- what happens to a recorded acceptance when the requirement later changes
- whether regression coverage is asserted anywhere a locator could be read from
