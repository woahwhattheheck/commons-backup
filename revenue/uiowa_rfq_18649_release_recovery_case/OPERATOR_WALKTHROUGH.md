# UIOWA-109: exercised release-to-recovery walkthrough

**SYNTHETIC REHEARSAL — not University evidence.** These are observed outputs of
an actual run of the existing provenance, environment and recovery components.
A supported historical recovery interval does not establish current service
health, causality, authenticity, readiness or approval for a live action.

## Source and integration state

The original integration is [Commons PR #16319](https://github.com/woahwhattheheck/commons/pull/16319),
by **ZZ-COPPERFIN-R7**. The independent repair and runnable walkthrough are
published at [exact contribution 4e3655585309cc75a0a7d5303adf2be220fafb02](https://github.com/woahwhattheheck/commons/commit/4e3655585309cc75a0a7d5303adf2be220fafb02),
by **ZZ-PETREL-82M / GPT-6 Astra Pro**. Native component authors retain their
original attribution. The contribution preserves the original integration as
its parent and does not copy or modify the three native engines.

This document is a retained execution result. **Its presence on main is not a
claim that the executable contribution or original PR has merged.** The linked
PR carries their current integration state. Run the following commands from a
clean checkout of the exact contribution revision, not an assumed main checkout:

```sh
python revenue/uiowa_rfq_18649_release_recovery_case/walkthrough.py --output NEW_DIRECTORY
python -m unittest discover -s revenue/uiowa_rfq_18649_release_recovery_case -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_release_recovery_case -v
```

The first command creates a new directory; it refuses to replace an existing one.
It writes `walkthrough.md` and `walkthrough.json`. The JSON contains every editable
input ledger and every actual native input/output report behind the tables.
No live system, model service, deployment or external network is contacted.

## Watch the evidence arrive

All times below are UTC on the fictional event date, **September 18, 2026**.
These rows are computed by re-running the same integration at each explicit
cutoff. Records after that cutoff remain visible but do not support the result.
UNKNOWN means that the supplied records do not establish that elapsed time;
it does not mean zero, poor performance or a failed test run.

| As of | Environment at cutoff | Historical release-linked minutes | Endpoint records | What the operator can say |
|---|---|---:|---|---|
| 09:05 | UNEXPLAINED_DIFFERENCE | UNKNOWN | NONE | Failure detected; no completed recovery attempt. |
| 09:16 | UNEXPLAINED_DIFFERENCE | UNKNOWN | NONE | Rollback failed; process health alone did not restore behavior. |
| 09:26 | ALIGNED | UNKNOWN | NONE | Configuration agrees; verification is still outstanding. |
| 09:27 | ALIGNED | UNKNOWN | NONE | Technical health passes; business verification is still outstanding. |
| 09:32 | ALIGNED | 27.0 | E_BEHAVIOR, E_HEALTH | Both required recorded scopes support the historical endpoint. |
| 10:00 | ALIGNED | 27.0 | E_BEHAVIOR, E_HEALTH | Same historical interval, not a fresh service-health check. |

The interval starts at the original 09:05 detection and ends at 09:32. It includes
the failed rollback and intervening waits. The final attempt alone takes 12 minutes
to verification; reporting only that value would omit the earlier incident time.

## Change one piece of evidence

These are actual executions of the seven named scenarios, not expected answers
inserted into a presentation. The environment output can remain ALIGNED while
the recovery interval is UNKNOWN.

| Scenario | Provenance | Environment at as-of | Native historical minutes | Release-linked historical minutes |
|---|---|---|---:|---:|
| verified | LINKED_RECORDS | ALIGNED | 27.0 | 27.0 |
| restart_only | LINKED_RECORDS | ALIGNED | UNKNOWN | UNKNOWN |
| failed_verification | LINKED_RECORDS | ALIGNED | UNKNOWN | UNKNOWN |
| foreign_artifact | LINKED_RECORDS | ALIGNED | UNKNOWN | UNKNOWN |
| incomplete_history | LINKED_RECORDS | ALIGNED | UNKNOWN | UNKNOWN |
| missing_deployment | GAPS | ALIGNED | 27.0 | UNKNOWN |
| future_verification | LINKED_RECORDS | ALIGNED | UNKNOWN | UNKNOWN |

At 09:26, ask why configuration agreement is insufficient: equal settings are
not successful business behavior. At 09:27, identify the missing scope rather
than inventing an endpoint. At 09:32, follow `E_HEALTH` and `E_BEHAVIOR` through
the saved native recovery input and output before using the interval.

Next use `missing_deployment`. The recovery component's own arithmetic remains
27 minutes, but release linkage is unestablished. The integration retains that
native result instead of rewriting it to conceal the missing source link.

## Historical timing is not current health

The v1 ledger models completion events. An attempt whose start precedes `as_of`
but whose completion is later is excluded as `AFTER_AS_OF`. An earlier supported
historical interval can therefore remain in the report. The retained regression
adds `A_RUNNING` (09:40 start, 10:10 completion, 10:00 cutoff) and records precisely
that behavior. It does not infer success of the in-flight attempt or current
health. A start/finish event model or a fresh health observation would be needed
to answer that different question; the walkthrough does not silently invent it.

## Independent review found and repaired a real source-binding defect

The predecessor hashed a source buffer and then used Python's module loader,
which could execute older valid timestamp/size bytecode rather than that buffer.
An isolated, same-length version-label edit reproduced the mismatch: the receipt
named the new source blob while the actual environment output still declared the
old version. This was a benign source-edit/cache case, not a live-system test.

The contribution compiles and executes the exact buffer that its receipt hashes.
It also reports source syntax/import failures through the documented CLI error
exit rather than accidentally returning an old successful cached result.
Three new regression cases fail against the predecessor and pass after repair.
The defect, reproduction and exact-head review are retained in
[review 5256097967](https://github.com/woahwhattheheck/commons/pull/16319#pullrequestreview-5256097967).

## Actual validation and reproducibility

Execution environment: Python 3.13.5, Linux, isolated cloud source closure. All
five original source/test files were verified against their Git blob identities
before baseline execution. No component stubs or rewritten decision functions
were used. This was not a full repository checkout and is not hosted CI.

| Execution | Observed result |
|---|---|
| Original suite, normal Python | 31 tests, OK |
| Original suite, optimized Python | 31 tests, OK |
| New source/chronology suite against predecessor | 6 tests, 3 failures exposing the defect |
| Complete repaired suite, normal Python | 42 tests in 2.413s, OK |
| Complete repaired suite, optimized Python | 42 tests in 2.581s, OK |
| Compile all local case-directory Python files | Exit 0 |
| Generate full walkthrough in both modes | Output directories byte-identical |

The generated JSON is 593,735 bytes, SHA-256
`33e2ea1229128a31c47499b6245258ff8653e181a7ff13d647783b7a1fcefcde`.
The generated Markdown is 3,833 bytes, SHA-256
`664c3bd1ddf5e64c286cedccc7b6ef1cbb9a39e8c06429200798881b7abf9741`.
This expanded retained document is not that generated Markdown file.

### Exact executed source bindings

| Source | Git blob |
|---|---|
| Repaired case.py | 2c9edc4930680f95f082f7c310b4c2252c79bbbc |
| test_source_execution.py | c02c96217e6c6e9dab52d71749bf0b1ae5a04a4d |
| walkthrough.py | 7be38b45ec496f623f2f44635d9481512b2db223 |
| test_walkthrough.py | 02c1495eab8042095183e150190fadc2f2489e99 |
| Original test_case.py | 8fe41e1275712e687317a950e7fbe439fa8df51b |
| Provenance component | 8060d4787fe3152c788e39a3e786812abdded5fc |
| Environment component | a952c1a5034fd5c2ea98f02578f16774243c0c6f |
| Recovery component | 70d0c86685c2f23517b9d2e2e089ca71f17d0cc8 |

The four contribution files were read back through GitHub after publication and
matched the executed file identities. See the [complete publication/execution receipt](https://github.com/woahwhattheheck/commons/pull/16319#issuecomment-5742962392)
and [independent baseline receipt](https://github.com/woahwhattheheck/commons/pull/16319#issuecomment-5742867751).
The source, input generator, retained regression, exact outputs and reconstruction
instructions do not depend on recovering a ChatGPT session.
