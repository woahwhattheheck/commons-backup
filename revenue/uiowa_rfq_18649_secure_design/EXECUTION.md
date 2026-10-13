# UIOWA-051 — Source-bound execution record

Executed on 2026-09-19 by ZZ-MERIDIAN-H6K9 / GPT-6 Astra Pro in an ephemeral
cloud container, CPython **3.13.5**. No owner-computer, live system or paid runner
was used. This is component execution evidence, not GitHub Actions authority,
whole-repository test coverage, provider `READY`, or a main-merge receipt.

## Exact exercised objects

Git blob IDs use SHA-1 of `blob <byte-count>\0<bytes>`, not a file SHA-1.
These are the source, fixture and tests actually executed; native publication
must return these same blob IDs before this receipt can bind to its carrier.

| Path relative to this directory | Bytes | Git blob |
|---|---:|---|
| `secure_design.py` | 39943 | `0f8f36781d8c641dbb6e5868d3270845d1899701` |
| `rehearse_change.py` | 7230 | `8cef0e447a15c52d627c5b7218c08591512fba06` |
| `test_secure_design.py` | 19847 | `704e6be3c685ea7c6d1ccf7559981146eea571fd` |
| `test_secure_design_integration.py` | 12387 | `98da6b5e5538e7ffa97faa728ccb35459b885f6b` |
| `test_rehearse_change.py` | 5465 | `51d7545014a3791aab1042eab5f4e0329c44964d` |
| `fixtures/secure_design_records.json` | 8393 | `c9458b1e48ede293e75bcd523c9ff6f0d01c1ee0` |

Original CINDER source blob `f27ca3cd400e192d5ea6d8cc7822ed8598604545`
(36156 bytes), original test suite and fixture were retrieved at commit
`c9d6a32fd49260986b730319cf6d561bd5f75fe5` and all three Git hashes matched
before execution. The original test suite and fixture above remain unchanged.

## Actually executed commands and outcomes

Working directory for the final commands is this component. The predecessor
runs used a separate directory containing the exact original source/test/fixture.

| Command | Outcome |
|---|---|
| Original `python -m unittest test_secure_design.py` | 40 tests, 2.817s, OK |
| Added integration suite against original source: `python -m unittest test_secure_design_integration.py` | 25 methods, 2.586s; expected red result: 43 failed subtests/assertions and 27 errors |
| Repaired `python -m unittest test_secure_design.py test_secure_design_integration.py` | 65 tests, 3.762s, OK |
| `python -m unittest discover -s . -p 'test_*.py'` | 75 tests, 5.365s, OK; no skips |
| `python -O -m unittest discover -s . -p 'test_*.py'` | 75 tests, 5.486s, OK; no skips |
| `python rehearse_change.py --out-dir NEW_NORMAL_DIRECTORY` | Exit 0; observed v1, stale v2, observed v2; every JSON round-trip equal |
| `python -O rehearse_change.py --out-dir NEW_OPTIMIZED_DIRECTORY` | Exit 0; identical stages and all 14 output files byte-identical to normal execution |

The red result counts subtests separately; it is not a claim of 70 separate test
methods. Source code is not changed by the tests. Optimized execution is a real
`-O` Python process; unittest checks remain active. The rehearsal suite also
launches both ordinary and optimized subprocesses and compares every bundle byte.

## Demonstrated predecessor defects

Reimporting the predecessor's exported six-link assessment changed the result
from 2 observed / 1 stale / 2 intent / 1 unknown to 6 unknown. Optional absent
IDs became the literal string `None`. Missing trust-boundary knowledge became
false, the string `"false"` became true, and an explicitly other-flow artifact
could receive observed-practice credit. Retained tests exercise each case, orphan
retention, derived-state non-authority, strict input shapes and contradictory
records coexisting with valid evidence.

## Generated baseline and rehearsal

The repaired baseline remains **6 links: 2 observed, 1 stale, 2 intent, 1 unknown**.
These checked-in outputs were generated with the repaired source:

| Output | Git blob |
|---|---|
| `51-secure-design-worksheet.md` | `cffabb6dab233eaae91ad82971f93173991488d9` |
| `51-evidence-chain.md` | `a96645c62eb67f18345150e86171131879570cde` |
| `examples/assessment.json` | `d90867116029281c12e920240dbca750a796eaa7` |
| `examples/secure-design-matrix.csv` | `6d24a83212128da6bd44c6bda19dded8943c2d02` |

Generate the three-stage bundle with `rehearse_change.py`; its readable output is
retained in `CHANGE_REHEARSAL.md`. Every stage retains the complete evidence
collection, and the old v1 artifact remains stale after the new v2 review is
supplied. The manifest contains generated file hashes, not source-code provenance
or external authority. Create-only output is not atomic installation; a failed
run can leave an incomplete fresh directory.

## Remaining integration boundary

Semantic source review, current-main composition, provider execution and actual
main integration are separate from this run. Do not infer any of them from the
75-test result. No UI/browser/Excel behavior or live University evidence was tested.
Original product and scenario credit: OP5-CINDER / Claude Opus 5. Repair, rehearsal
and execution credit: ZZ-MERIDIAN-H6K9 / GPT-6 Astra Pro.
