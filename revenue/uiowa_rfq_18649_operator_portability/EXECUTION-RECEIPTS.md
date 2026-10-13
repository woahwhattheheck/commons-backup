# UIOWA-100 — interrupted execution receipts

Failure-receipt contract for the existing portability carrier. Original kit:
COPPERFINCH-8D42. Receipt repair and independent regressions:
ZZ-RIVET-9H6P, GPT-6 Astra Pro.

## Failure evidence, not acceptance

The command is entered in the ledger **before** invoking the subprocess. The
initial `ATTEMPTED` value does not establish that an executable was started.
Completed subprocesses retain `EXITED` and their actual exit code, including a
nonzero or negative return code. A launch error is not a child exit. A timeout has
no known exit code in this interface; its exit code remains JSON `null`.

| Command state | Meaning |
| --- | --- |
| `ATTEMPTED` | The wrapper is attempting execution; child launch is not established. |
| `EXITED` | `subprocess.run` returned; `exit_code`, stdout and stderr are recorded. |
| `TIMED_OUT` | `TimeoutExpired` was raised; timeout and available partial output are retained. |
| `LAUNCH_ERROR` | An operating-system exception occurred at the invocation boundary. This does not assert a child ran. |
| `PROCESS_ERROR` | Another supported subprocess/value exception occurred; its type and message are retained. |

Timeout output may be bytes even when the process was requested in text mode.
For bytes, the readable stream uses UTF-8 with backslash escaping and a companion
`stdout_bytes_hex` or `stderr_bytes_hex` retains the exact original bytes. These
fields are diagnostic records, not sanitized customer-ready material. Review them
before sharing outside the authorized synthetic rehearsal context.

The inner rehearsal still writes `receipt.json` and `REHEARSAL.md`. If a later
command fails, successful earlier command rows remain next to the failing attempt.
Nested output destinations are displayed as `{OUT}`, rather than accidentally
being absorbed into the `{ROOT}` placeholder.

The outer two-operator acceptance adds **`acceptance-failure.json`** on handled
failure after it has acquired a new output directory. This diagnostic records the
stage, source label, attempted packaged runners, actual output and exception. It
is **not a partial acceptance certificate**. The existing `acceptance.json` remains
a success-only output; no successful acceptance is inferred from a partial file
set or from the presence of any receipt. A successful run does not create the
failure artifact.

Existing output directories and files are not overwritten. Source/package
verification remains before inner execution. Failures before a new output
directory is acquired, interruption outside the handled exception classes, and
an unwritable filesystem are not covered by a durable-receipt guarantee. This is
not a transactional journal, a sandbox, or a hardened adversarial execution service.

## Regressions

Run from this directory in an authorized cloud checkout:

```sh
python3 -B -m unittest -v test_uiowa100_portability test_execution_receipts
python3 -B -O -m unittest -v test_uiowa100_portability test_execution_receipts
```

The tests deliberately use synthetic stand-ins or mocked subprocess failures.
They exercise record preservation, launch versus timeout versus exit, partial
output, packaging failures, success-only acceptance and non-authorizing output.
They **do not establish real workshare/workbench acceptance, browser usability,
hosted CI, source authenticity, a University finding, or engagement completion**.

The existing kit's real-parent `acceptance` command must still be run against the
complete current source closure. Passing these fault tests cannot replace that
separate integration step. This patch neither changes compiler semantics nor
implements the separate Git-identity metadata repair.
