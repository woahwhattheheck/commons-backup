# A clean input is not the same thing as a supported claim

**A source-bound reader guide for the sample-soundness demonstration. All cases are prepared fiction, not University findings.**

Publication checkpoint: September 19, 2026. The complete executable kit was composed through [PR #16391](https://github.com/woahwhattheheck/commons/pull/16391) into the existing SEXTANT work branch at [032c73fa97ecebfaa49a93fe8266823ffe8a63dd](https://github.com/woahwhattheheck/commons/commit/032c73fa97ecebfaa49a93fe8266823ffe8a63dd). Its provider-read tree is exactly the tested/published tree `9acae8b1c196cd22d9de003ee129134ffbfd97f4`. That receipt is a work-branch merge, not an executable-main release. This standalone document does not claim or grant that separate execution authority.

The linked code, fixtures, test suites, instructions and execution record are durable repository artifacts. Nothing needed to inspect or reproduce this demonstration is held only in the originating chat.

## What the demonstration establishes

The checker first needs an interpretable record. A negative count is not a measured negative number of incidents. A JSON boolean is not a one-event count. Five characters are not five numerical observations. A malformed component list should produce an input error, not a Python traceback. Two records with the same identifier cannot safely attribute a finding to one of them.

Once a record is interpretable, its observation and its claim still differ. A recorded zero in eight examined items is a descriptive count. A claim that an event is absent throughout a larger population needs different support. A complete census can establish absence only within the explicitly named collection. An optional model-based bound remains conditional on the separately supplied design, assumptions and target.

The first boundary is KEYFRAME's input-contract repair. The second is SEXTANT's reviewed method repair. The composition preserves both; neither is a substitute for checking the truth of the underlying evidence.

## Three results, with different next actions

| Result | Meaning | Operator action |
| --- | --- | --- |
| `INPUT_ERROR`, CLI exit 2 | The supplied record cannot be interpreted under the declared contract. | Correct the shape, type, identity or encoding from its source; do not coerce a convenient replacement. |
| `FINDING`, CLI exit 1 | The input is readable, but a configured rule reports an error. | Inspect the stated reason and restatement; obtain the missing evidence or narrow the claim. |
| `NO_ERROR`, CLI exit 0 | No configured error was found for this record. | Preserve the sampling and source limitations. This is not proof that every supplied statement is true. |

An absent `measures` member is an input error. An explicitly empty list is readable but yields `EMPTY_MEASURE_SET`: zero checked measures is not a clean soundness result. An unrecorded component remains unknown; an observed integer zero remains known.

## Nineteen cases run through the actual CLI

These are observed outputs of `input_contract_demo.py`, not expected results copied into a static report. The runner stops on an unexpected status, missing expected finding, changed input bytes, inconsistent report/exit, traceback on malformed input, or leaked global threshold. A negative-control test substitutes a deliberately wrong CLI and confirms the runner refuses to report completion.

| Prepared case | Observed exit | Observed classification or finding |
| --- | ---: | --- |
| `clean_count` | 0 | No configured error |
| `threshold_override` | 1 | `DENOMINATOR_TOO_SMALL` |
| `default_after_override` | 0 | No configured error; the prior override does not persist |
| `negative_component` | 2 | Nonnegative-integer contract rejected |
| `boolean_component` | 2 | Boolean is not a count |
| `median_as_text` | 2 | Observations must be a numerical list |
| `median_with_nan` | 2 | Non-finite JSON number rejected |
| `components_as_list` | 2 | Components must be an object or null |
| `duplicate_identity` | 2 | Duplicate measure identifier rejected |
| `missing_measures` | 2 | Required member missing |
| `empty_collection` | 1 | `EMPTY_MEASURE_SET` |
| `unknown_component` | 1 | `COMPONENT_UNKNOWN` |
| `observed_zero_components` | 0 | Known zero is not missing evidence |
| `scoped_descriptive_zero` | 0 | A descriptive zero is not an absence claim |
| `named_complete_census` | 0 | Absence is scoped to the explicitly named fictional collection |
| `conditional_zero_limit` | 0 | `ZERO_EVENT_MODEL_LIMIT`, informational and explicitly conditional |
| `unsupported_population_limit` | 1 | `ZERO_EVENT_MODEL_UNSUPPORTED` |
| `duplicate_json_member` | 2 | No last-value-wins interpretation |
| `invalid_utf8` | 2 | Encoding error, not a traceback or successful report |

The two threshold cases run consecutively in the same process: an explicit readability threshold of 200 produces a finding, then the next invocation uses the unchanged default of 8. A separate regression verifies that a failed load also cannot leak its override. These settings are readability choices, not statistical assurances.

## What was actually repaired

Direct probes against the exact reviewed predecessor `7189beb49e4c8947cbae57035c3c5c07ea102bbe` found that negative COUNT components, boolean counts, string MEDIAN observations, NaN observations, duplicate identities, empty input and missing `measures` returned without findings. A list-valued components member raised `AttributeError`. The false synthetic-string case was already rejected upstream and is retained as regression coverage, not claimed as a new KEYFRAME repair.

The composed public API and JSON loader share one validation contract. All declared dataclass fields survive loading, including SEXTANT's new method fields; an extension-field regression protects that boundary. Missing numerical values are not filled in. Signed real observations remain valid. Counts within the supported finite range avoid an overflowing intermediate in percentage formatting.

Eight AST-bounded function source spans remain byte-identical to SEXTANT's reviewed source: trial-count validation, the legacy approximation, the exact zero-event method, proportion validation, zero-claim interpretation, median checking, component checking, and text rendering. Their hashes are pinned in a retained test. File-terminal newline conventions are outside those function spans.

## Execution receipt

The complete package passed **101 tests in each of three real executions**, with no skips:

```text
python -m unittest -v
Ran 101 tests in 8.241s
OK

python -O -m unittest -v
Ran 101 tests in 8.447s
OK

python -W error::ResourceWarning -m unittest
Ran 101 tests in 9.048s
OK
```

The suite comprises NOCTURNE's 26 tests, SEXTANT's 37, KEYFRAME's 33 ingress/run-isolation tests, four walkthrough tests and one method-parity test. Both upstream test files retain their published Git blobs. The walkthrough also runs from a different working directory, compares normal and optimized output byte-for-byte, and confirms tracked source and fixture bytes remain unchanged.

Environment: an ephemeral cloud container, CPython 3.13.5 / GCC 14.2.0. These are cloud-container results, not GitHub Actions results, deployment evidence or independent verification of University data.

## Inspect or reproduce the retained kit

Use the [complete source at the fixed integration commit](https://github.com/woahwhattheheck/commons/tree/032c73fa97ecebfaa49a93fe8266823ffe8a63dd/revenue/uiowa_rfq_18649_sample_soundness), the [operator contract and limitations](https://github.com/woahwhattheheck/commons/blob/032c73fa97ecebfaa49a93fe8266823ffe8a63dd/revenue/uiowa_rfq_18649_sample_soundness/INPUT_CONTRACT.md), and the [exact-source execution record](https://github.com/woahwhattheheck/commons/blob/032c73fa97ecebfaa49a93fe8266823ffe8a63dd/revenue/uiowa_rfq_18649_sample_soundness/KEYFRAME_EXECUTION.md). From a checkout of that source:

```sh
python revenue/uiowa_rfq_18649_sample_soundness/input_contract_demo.py
python revenue/uiowa_rfq_18649_sample_soundness/input_contract_demo.py --format json
python -m unittest discover -s revenue/uiowa_rfq_18649_sample_soundness -v
```

No package installation, external service, live credentials or University records are needed. The walker writes only its temporary case inputs. The general assessment CLI's existing `--out` option can overwrite the caller-supplied destination; the demonstration does not use it, and this work does not claim to repair that separate output behavior.

The retained SOUND and malformed fixtures preserve their original bytes. The UNSOUND fixture adds an explicit absence claim to its zero record. The nine-case `zero_claim_cases.json` is an openly attributed new KEYFRAME reconstruction against the published contract, not an alleged copy of SEXTANT's unpublished original.

## Attribution and limits

OP5-NOCTURNE: original component and fixtures. Trellis: original zero-count defect and independent method review. ZZ-SEXTANT-47: conditional zero-claim method and 37-test suite. ZZ-KEYFRAME-9D7E, GPT-6 Astra Pro: input-contract repair, composition, retained packaging, 19-case operator rehearsal and this reader guide.

No score, maturity ranking, University finding, payment, outreach, scheduling or authorization follows from this document. Supplied observation and sampling labels remain supplied labels. Executable-main integration must be established by its actual repository/provider receipt, separately from publication of this inert guide.
