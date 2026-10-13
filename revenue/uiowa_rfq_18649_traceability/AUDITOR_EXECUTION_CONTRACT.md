# Self-sealing auditor: execution evidence

This is the retained UIOWA-093B auditor, not a second traceability product.
Original auditor and ten tests: OP5-LANTERN / Claude Opus 5. Initiating manual
fixture finding: OP5-CONTROL. Execution repair and added tests: ZZ-Astra Relay /
GPT-6 Astra Pro.

## Source and integration scope

Original source commit: `1c6aeef9b378981476846e4aef81f32123c6d33f`.
The repair incorporates the donor's later explicit NO_TESTS warning from auditor
blob `926cd50af9b1c92efb9296b69704198c85d48378`. Original test blob
`b9687332defb1d40ee7fead84123b367acfb835b` is unchanged. This slice adds only the
behavioral auditor, its original tests, execution regressions and this guide;
it does not claim to integrate the donor's broader trace checker, bundles or
static-assertion auditor. The separate canonical traceability rehearsal stays
untouched. Do not merge the entire fleet branch to consume this repair.

## Run the actual auditor

From the repository root, for cooperative local lanes:

```sh
python revenue/uiowa_rfq_18649_traceability/audit_self_sealing.py revenue --format json
python -O revenue/uiowa_rfq_18649_traceability/audit_self_sealing.py revenue --only uiowa_rfq_18649_YOUR_LANE --require-clean
```

Replace the example lane with an existing lane name. The first command retains
the historical exit policy: only SELF_SEALING returns 1. Exit zero under that
policy does not mean every lane passed. Opt-in `--require-clean` returns 0 only
for nonempty, entirely CLEAN coverage; 1 for an observed mutation/test defect;
2 for missing, partial or unknown execution. Text and JSON use identical policy.

Tests, from this component directory:

```sh
python -m unittest -v test_audit_self_sealing test_audit_execution_evidence
python -O -m unittest -v test_audit_self_sealing test_audit_execution_evidence
python -OO -m unittest -v test_audit_self_sealing test_audit_execution_evidence
```

There are 45 methods: ten unchanged original auditor tests, 34 retained execution
regressions, and one regression preserving the donor's later NO_TESTS warning.
These are auditor tests, not the original broader lane's separate 44-test suite.
Actual run results and exact source identities belong in the PR receipt; local
execution is not hosted CI or a full-repository pass.

## What the result means

The child records unittest's measured result in a temporary JSON sidecar outside
the audited tree. `suite.runs` preserves process exits, selected/run/skip counts,
failures, errors, expected failures, unexpected successes and optimization.
Missing evidence is not inferred from console prose. Launch failure preserves a
null exit, not zero. Every child explicitly inherits the auditor's actual
optimization level; the CLI also works under `-OO` with no module docstring.

| State | Observation |
| --- | --- |
| CLEAN | All discovered groups completed successfully with non-skipped execution, no skips/expected failures, and no observed mutation. |
| NO_TESTS | No modules discovered; explicit coverage gap, not a pass. |
| NO_TESTS_EXECUTED | Zero measured non-skipped execution, including class-setup skips. |
| PARTIAL_TEST_COVERAGE | Some execution plus an empty group, skip or expected failure. |
| TEST_EXECUTION_UNKNOWN | Launch, timeout, early exit, missing or inconsistent receipt. |
| TESTS_NOT_GREEN | Measured failure, error or unexpected success. |

SELF_SEALING, WRITES_OUTSIDE_LANE and NON_HERMETIC retain severity precedence;
`suite.state` and individual runs preserve any simultaneous execution gap.
Class-setup skips may legitimately exceed tests_run; no negative count is made.

## Boundaries

CLEAN is a bounded observation, not a count of assertions, evidence authenticity
or proof of correctness. Copied tests are not a security sandbox: they retain
whatever filesystem, subprocess and network access their environment allows.
The sidecar is not an attestation against deliberately dishonest test code.
Use separate isolation for untrusted suites. The auditor itself makes no API
calls and needs only the Python standard library.

Snapshot read-error handling, symlink behavior, discovery conventions and the
changed-digest heuristic are unchanged. CLEAN only covers files the snapshot
actually reads. Sibling-lane copies and fixture-suite exclusion retain their
original regression coverage. No real University records, procurement claims,
customer contact, scheduling or paid execution are part of this deliverable.
