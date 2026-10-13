# UIOWA-026 execution receipt

Executed on 2026-09-19 by ZZ-ALKALI-26F / GPT-6 Astra Pro in the session's
Linux working container, Python 3.13.5. These are **local execution results**,
not GitHub Actions results, University acceptance, or an external source review.
The repository PR records provider checks and integration state separately.

## Commands and observed results

From `revenue/uiowa_rfq_18649_cross_stack/`:

```text
python -m unittest -v test_compare.py
Ran 37 tests in 2.494s
OK

python -O -m unittest -v test_compare.py
Ran 37 tests in 2.463s
OK
```

From the isolated repository-layout root:

```text
python -m py_compile revenue/uiowa_rfq_18649_cross_stack/*.py
PASS (exit 0)

python -m unittest discover -s revenue/uiowa_rfq_18649_cross_stack -t . -v
Ran 37 tests in 2.445s
OK
```

The real CLI test launches JSON, CSV and Markdown commands against a temporary
packet and compares each output with the generator's output. Malformed input
returns exit 2, a named stderr diagnostic, and empty stdout. The tests are
asserted with unittest methods, not Python `assert` statements that disappear
under `-O`.

The generator was also run twice into two fresh directories. All six artifact
files were byte-identical across the two clean runs. Existing-directory refusal,
all 11 exact source-heading locators, 48 context-worksheet rows and preservation
of the synthetic flag are independently exercised in the test suite.

## Exact tested source identities

Git blob identities (SHA-1 over the Git blob header and exact UTF-8 bytes):

| File | Bytes | Git blob SHA |
| --- | ---: | --- |
| `compare.py` | 20292 | `024f5de095c22650df5d2534c57630f5ff0c07ec` |
| `examples.py` | 13438 | `cd4da5cb142e8816e5e7cfbf0962c196a6284bb8` |
| `test_compare.py` | 14086 | `08890ac1107ab724657c88a08ff12d86940eb00c` |
| `__init__.py` | 86 | `9946cd956f65fc333a7eca2e6ffefebcd10c6f0d` |
| `example-results.csv` | 3111 | `f10b8dfb10f5859a7cba0b43927bf241903dbaf6` |

The three Python implementation/test blobs were returned with these exact hashes
by GitHub publication calls. The final PR/main readback must match these bytes;
a different source revision requires a new execution receipt.

## Actual twelve-pair result

Canonical input-metadata SHA-256:
`ba371bc2b9d24d611c230e8f5e8c09cab643f755050c4b965417408bf287a67c`.
This is not the digest of referenced source-document bytes.

```text
CONTEXT_NOT_COMPARABLE                      1
CONTEXT_UNRESOLVED                          1
DIFFERENT_OUTCOME_DEFINITIONS                1
DISPUTED                                   1
EQUIVALENT_OUTCOME_IN_SUPPLIED_SAMPLE        4
INSUFFICIENT_EVIDENCE                       2
NOT_APPLICABLE                             1
SHARED_GAP_IN_SUPPLIED_SAMPLE               1
```

The hand-worked expected verdicts agree with these actual outputs. Case 02 reports
one shared provenance cluster. Case 12 preserves qualitative descriptions but
emits `INCOMPARABLE_MEASUREMENTS` with no numerical delta. Case 09 retains the
unknown added requirement rather than promoting v1 evidence to v2 achievement.

## Tested boundaries and remaining limits

The 37 tests include 16 implementation-label permutations, metadata/reference
validation, context mismatch and unsupported overrides, policy-only claims,
expired/future support, unresolved old dissent, unknown and not-applicable states,
shared provenance, exact fractions, missing/zero denominators, incompatible
populations/windows, input immutability, deterministic serialization, formula-like
CSV labels, supplied Markdown escaping, and actual CLI execution.

No source authenticity, statistical equivalence, real institutional performance,
all-Python-version matrix, live-system interaction, browser operation, shared
workbench integration or hosted workflow execution is claimed by these runs.
No network, model API, paid provider execution, credentials, real University
records, external outreach or scheduling were used by the rehearsal.
