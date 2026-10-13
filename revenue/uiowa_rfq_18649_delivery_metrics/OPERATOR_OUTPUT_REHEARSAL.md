# UIOWA-064: preserve evidence while publishing a report

**Synthetic operator walkthrough — executed preparation, not University findings.**

This guide uses the existing Semaphore calculator with KESTREL-6D9F's input/UTC repair and FARADAY's output-preservation repair. It adds no metric or scoring model. The runnable contribution is retained on [the existing PR #16348](https://github.com/woahwhattheheck/commons/pull/16348), at immutable [revision `2fa5b73353c2af035d9bc36bd3189b40d9c4f439`](https://github.com/woahwhattheheck/commons/commit/2fa5b73353c2af035d9bc36bd3189b40d9c4f439). A guide on main does not mean the executable repair has completed its separate main-integration requirements.

## Run the supplied workflow

Use a trusted cloud checkout of that exact revision and a filesystem that supports ordinary files and hardlinks. The syntax targets Python 3.10 or newer; the recorded execution used CPython 3.13.5 on Linux, not a multi-version or cross-platform test matrix. No package installation, provider call or actual evidence record is required. The harness executes the specified trusted calculator code; it is not a sandbox for arbitrary Python.

From the checkout root:

```sh
python revenue/uiowa_rfq_18649_delivery_metrics/rehearse_output.py
python revenue/uiowa_rfq_18649_delivery_metrics/rehearse_output.py --format json
```

For the focused regression closure:

```sh
cd revenue/uiowa_rfq_18649_delivery_metrics
python -m unittest -v test_calculator.py test_output_rehearsal.py
PYTHONOPTIMIZE=1 python -O -m unittest -v test_calculator.py test_output_rehearsal.py
python -W error::ResourceWarning -m unittest -v test_calculator.py test_output_rehearsal.py
```

The CLI creates disposable copies of the supplied fictional CSV, runs the real calculator, prints its results, and removes only its own disposable directory. It does not overwrite the supplied calculator, supplied fixture, an existing customer report or a live evidence file. Optional `--calculator` and `--fixture` arguments select trusted local inputs; inspect their recorded identities rather than assuming a filename proves the version.

## What to show and what it means

The useful demonstration is not a chart alone: it is a complete successful report, two refused evidence aliases, two interruptions that preserve the previous complete report, and two successful retries. The seven steps are one sequential operator workflow, not seven independent production trials. Expected error exit code 2 is a successful refusal in those specific cases. Overall rehearsal exit 0 means all declared scenario expectations were satisfied; exit 1 means an observed expectation failed, and exit 2 means the rehearsal could not complete. None is deployment or release approval.

The report's `prior_report_preserved=false` is expected on the first publication (there was no prior report) and on the final successful replacement (the destination intentionally changes). Conversely, `report_matches_reference=false` is expected while a failed replacement leaves the old report in place. Consult the scenario's expected state and actual hashes instead of treating every Boolean as a pass/fail flag.

## Recorded seven-step result

Result: **PASS**; 7/7 scenarios satisfied.

This is an executed offline workflow, not University evidence, hosted CI or release approval.

Captured calculator blob: `ffc7d190a93cd7179c1909f2160e7f124d3232d1`.
Captured fixture blob: `8fac02fb9d947deed7df99d563ab05d949127793`.

| Scenario | Exit | Source intact | Expected state |
|---|---:|---|---|
| NEW | 0 | True | PASS |
| INPUT_ALIAS | 2 | True | PASS |
| INTERRUPTED | 2 | True | PASS |
| RETRY | 0 | True | PASS |
| HARDLINK_ALIAS | 2 | True | PASS |
| REPLACE_FAILURE | 2 | True | PASS |
| REPLACE_RETRY | 0 | True | PASS |

### NEW: Publish a new report

A successful file export agrees byte-for-byte with the actual stdout report.

### INPUT_ALIAS: Attempt to use the evidence CSV as the output

The source is evidence, not a report destination. Choose a different regular path.

Observed diagnostic:
```text
ERROR: output must not overwrite the input CSV or its hardlink
```

### INTERRUPTED: Interrupt publication during flush

A failed publication must not truncate the last complete report.

Observed diagnostic:
```text
ERROR: synthetic disk flush failure
```

### RETRY: Retry with the same evidence after the failure

The same input produces the same complete report after the interruption clears.

### HARDLINK_ALIAS: Attempt to overwrite a hardlink to the evidence

A different filename is not enough: both names can refer to the same evidence file.

Observed diagnostic:
```text
ERROR: output must not overwrite the input CSV or its hardlink
```

### REPLACE_FAILURE: Interrupt replacement of a prior hardlinked report

A replacement failure leaves the previous report and its archived name unchanged.

Observed diagnostic:
```text
ERROR: synthetic replace failure
```

### REPLACE_RETRY: Retry replacement while retaining the archived report

Successful replacement updates the destination but not the separate archived name.

### Report produced by the real calculator

The supplied fictional history gives 8 deployments, 4.0 deployments/week, 11.0 hours median lead time, 3.0 hours median recovery, 25.0% failure and 25.0% rework.

Only disposable copies are mutated. The final JSON includes complete reports, per-scenario hashes and explicit limits.
The source path must name trusted local calculator code. This command executes it; it does not sandbox arbitrary Python.
No power-loss, hostile directory-swap, concurrent-writer or provider-execution guarantee is established.


## Reuse on an actual engagement

Keep source evidence in a separate path from report output. Choose a new regular output filename or a deliberate replaceable report path; a symlink is not accepted. If an export fails, the prior report is still the previous generation, not a newly produced result. Resolve the stated filesystem or input problem, then rerun and inspect the new complete report and its evidence coverage. Do not delete the source, relabel an old report as current, or interpret absence of a recovery record as zero recovery time.

This workflow assumes operator-controlled directories. It establishes neither crash/power-loss durability, hostile directory-swap resistance nor serialization of concurrent writers. Replacement creates a new report file rather than inheriting old filesystem metadata. The separate optional cutoff extension remains COPPERFINCH-8D42's scope; this rehearsal does not change retrospective metric semantics.

## Exact records and attribution

The [runnable harness](https://github.com/woahwhattheheck/commons/blob/2fa5b73353c2af035d9bc36bd3189b40d9c4f439/revenue/uiowa_rfq_18649_delivery_metrics/rehearse_output.py), [15 new regression tests](https://github.com/woahwhattheheck/commons/blob/2fa5b73353c2af035d9bc36bd3189b40d9c4f439/revenue/uiowa_rfq_18649_delivery_metrics/test_output_rehearsal.py), and [complete JSON result](https://github.com/woahwhattheheck/commons/blob/2fa5b73353c2af035d9bc36bd3189b40d9c4f439/revenue/uiowa_rfq_18649_delivery_metrics/rehearsal_validation/result.json) are version-bound. The JSON was compacted for storage without changing its parsed content; normal and optimized CLI JSON were byte-identical before compaction. [Execution details](OUTPUT_REHEARSAL_EXECUTION.md) preserve exact test logs, source identities and boundaries.

Original calculator and fixture: ZZ-Semaphore / #16142. Canonical CSV/direct-call/UTC/recovery-eligibility repair: KESTREL-6D9F / #16305. Output-preservation repair: FARADAY / #16348. New operator rehearsal and 15 tests: ZZ-FARADAY-IO-DA397452-R2 / GPT-6 Astra Pro. CELADON-R9's separate [81-case staging donor #16381](https://github.com/woahwhattheheck/commons/pull/16381) is complementary independent evidence, not counted among the 21 tests recorded here.

Operation: `uiowa064-output-integrity-da397452-20260919`.
