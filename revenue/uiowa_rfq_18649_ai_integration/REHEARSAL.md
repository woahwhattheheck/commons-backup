# Executed synthetic rehearsal — UIOWA-080

Run date: 2026-09-19. Environment: Python 3.13.5; Linux ephemeral cloud container. Standard library only.

All design timings, capacities and observations in the example are fictional. Only the execution of this evaluator and its tests was measured. No network or model-service experiment was run.

## Commands and actual results

```sh
python example_cases.py --out /tmp/uiowa-080/cases.json
python assess.py /tmp/uiowa-080/cases.json --out /tmp/uiowa-080/report
python -m unittest discover -s . -p 'test_assess.py' -v
python -O -m unittest discover -s . -p 'test_assess.py'
python -m py_compile assess.py example_cases.py test_assess.py
```

Actual outcome: 42/42 tests passed in normal execution and 42/42 under `python -O`; bytecode compilation passed. The CLI generated JSON, Markdown and CSV for 3 cases / 9 alternatives. CLI replay tests compare all three output files byte-for-byte across repeated runs and verify the input hash.

Fixture SHA-256: `aa7d7b3762542589a3c95372fd8e3149c3bd7cdf55d2be8579e46eea2f2f731d`.

| System | Alternative | Result | Response envelope ms | Completion envelope ms |
|---|---|---|---|---|
| SYN-APP | SYNC | conflict | 1100–6700 | 1100–6700 |
| SYN-APP | ASYNC | supported_by_inputs | 90–250 | 61990–316250 |
| SYN-APP | RETRIEVAL | conflict | 880–2760 | 880–2760 |
| SYN-KNOWLEDGE | SYNC | conflict | 1100–6700 | 1100–6700 |
| SYN-KNOWLEDGE | ASYNC | conflict | 90–250 | 61990–316250 |
| SYN-KNOWLEDGE | RETRIEVAL | unknown | 880–2760 | 880–2760 |
| SYN-SUPPORT | SYNC | conflict | 1100–6700 | 1100–6700 |
| SYN-SUPPORT | ASYNC | conflict | 90–250 | 61990–316250 |
| SYN-SUPPORT | RETRIEVAL | conflict | UNKNOWN | UNKNOWN |

## Interpretation and next observations

The release-summary case demonstrates an input-supported async candidate, not an automatic choice. Its response-path availability bound is 0.9995–0.9997 under the supplied comparable-window assumptions; no independent product is silently substituted. Its integration effort is 96–168 hours, recurring maintenance 16–32 hours/month and later migration 36–72 hours, kept separate. A real decision still needs retained observations and a business owner.

The research-support case needs source citations. SYNC and ASYNC lack that declared capability. RETRIEVAL offers it but has unknown export/rebuild evidence and conditional maintenance/migration effort. The next useful observation is an export/rebuild plus retrieval-set replay with the maintenance owner, not a product purchase.

The identity-support drafting case demonstrates explicit mismatches and unknowns: a strict response-path target is not met by the supplied dependency assumptions, one retrieval stage lacks a bound, and support ownership/processing-zone facts are missing. This case proposes no automated identity decision and performs no change to an identity service.

## Regression scope

Coverage includes acknowledgement/completion separation; incomplete latency; budget boundaries; rejection of percentile addition; dependency bounds with and without explicit independence; window mismatch; missing and known-bad dependencies; randomized bound sanity; separate effort units; ownership gaps; data movement/retention mismatches; missing capabilities; asserted versus demonstrated portability; unresolved evidence; untested/manual fallback; synthetic provenance; malformed numeric/type/range/duplicate inputs; aggregate overflow; Unicode and CSV presentation; deterministic CLI output; malformed-input behavior and protection against overwriting the input.

## Exact tested source hashes

| File | SHA-256 | Git blob SHA-1 |
|---|---|---|
| `assess.py` | `3fd21b5d9795f21102dd0a1dfcf851d96d5d277111e05b72aeaac8258b4a3740` | `0a795791c374aba9abcaae5b662007a8584a8337` |
| `example_cases.py` | `4e7de432e43f6b893cd9860e3aa25ef80bbeea2e8ebb3b19828008e6843f4bc5` | `3116a01a18a1cae4449885fcd66d30b9727a7e0e` |
| `test_assess.py` | `24369bed66b0ce684806fc2fd6f6f863f4f3dd1eebf0ba84d6ad5f6db04073d9` | `388d15c972e4278f99168431ea8b6f7851fae368` |

This is a focused validation receipt for this isolated kit, not a claim that the entire Commons test suite or a deployed AI workflow passed. Full sample reports are reproducible with the commands above.
