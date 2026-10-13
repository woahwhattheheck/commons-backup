# UIOWA-100: execution-evidence contract

This document specifies the proposed revision-2 receipt behavior of the existing
operator sample runner. It does not imply that a University assessment, a
repository-wide rehearsal, or a delivery acceptance has occurred.

## A plan is not execution

The JSON schema name remains `uiowa.operator-sample-run.v1`; `receipt_revision: 2`
adds explicit state and provenance fields while retaining the original fields.
A valid dry run remains `success: true` for API compatibility, but has
`status: PLANNED`, `execution_verified: false`, zero attempted steps, and null
return codes. The CLI prints `PLANNED`, not `PASS`.

A consumer may report this selected sample plan as executed successfully only
when `execution_verified` is exactly `true`. That means the plan was nonempty,
this was not a dry run, every planned command returned zero, each entrypoint
retained its observed before/after bytes, and output inventory completed.
It does not mean every component in the repository has been exercised.

## Selection and output ownership

An unknown asset, a reference-only asset, a selection mixing executable and
reference-only assets, or an empty executable plan is rejected before creating
output. Pending-at-snapshot assets cannot silently supply executable commands.
A manifest selection is explicit; a subset is never advertised as the full kit.

Every invocation needs a new or empty `--out` directory. Use different paths for
a dry run and an actual execution. Existing artifacts and receipts are never
cleared or reused by the runner. A reservation directory arbitrates cooperating
invocations; emptiness is checked again after reservation acquisition to catch a
run that completed between the first check and acquisition. A stale reservation
is not stolen or automatically removed by another invocation.

The runner removes only its own empty reservation directory. It never deletes
old output to make a repeat run appear fresh. `outputs` excludes the receipt
itself and reservation metadata, so it cannot contain an obsolete self-hash.
The returned object and the persisted JSON contain the same data.

## States and CLI exit codes

| State | Meaning | Execution verified | CLI exit |
| --- | --- | --- | --- |
| `PLANNED` | Commands resolved and entrypoints readable; no child executed | false | 0 |
| `PASSED` | All selected commands and output inventory completed successfully | true | 0 |
| `FAILED` | Child exited nonzero | false | 1 |
| `TIMED_OUT` | Child exceeded the configured per-command timeout | false | 1 |
| `EXECUTION_ERROR` | Launch or entrypoint read failed | false | 1 |
| `SOURCE_CHANGED` | Entrypoint digest changed during execution | false | 1 |
| `INVENTORY_FAILED` | Generated outputs could not be inventoried as regular files | false | 1 |

Invalid setup or a failure to persist the receipt exits 2. Such an invocation
does not claim a durable failure receipt. Steps stop after the first failure.
An inventory failure may become the top-level state while the original failed
step remains visible in `steps` and `errors`.

`planned_steps` counts all selected commands. `attempted_steps` counts real-run
step attempts, including a launch or entrypoint-read failure; it is not a count
of child processes proven to have started. `steps[].returncode` remains null when
there is no observed completed-process return code. Timeout streams may be
empty when a busy host times out during interpreter startup.

## Evidence retained

Each attempted execution records state, available return code, elapsed time,
stdout/stderr SHA256 values and the final 4,000 decoded characters of each stream.
Timeout captures are retained when supplied by the subprocess API. A post-run
entrypoint read failure does not erase stdout/stderr captured before the failure.
Generated regular files carry relative path, byte length, and SHA256.

`manifest_sha256` binds canonical JSON of the actual supplied manifest.
`entrypoint_sha256` and `entrypoint_sha256_after` bind the selected script before
and after completed execution. `snapshot_main_sha` remains the catalog's declared
snapshot, not an attestation of the checkout actually executed. Imported modules,
configuration dependencies and the complete checkout are **not** hashed by this
revision. Before/after equality also does not prove the file could not have
changed and reverted between observations.

## Trust and durability limits

This is a trusted-Python-code runner, not a process, filesystem, network,
credential, or resource sandbox. No shell is launched by the runner, but selected
Python code can still perform its own operations. The output reservation
coordinates cooperating invocations; it is not a defense against arbitrary
concurrent filesystem mutation. Rejecting a generated symlink does not turn the
child process into a sandbox. Review selected entrypoints and their dependencies
before executing them.

Receipt creation is exclusive and never overwrites a prior receipt. It is not a
power-loss atomicity guarantee: a machine or filesystem failure may leave an
incomplete file. Process-tree termination, full stdout/stderr archival, dependency
closure hashing and repository-wide runtime validation remain outside this
change. Inspect the JSON and the CLI exit code rather than inferring success
from a file's presence.

## Reproduce the contract suite

From this directory, with Python 3.10 or later:

```sh
python -m unittest discover -s tests -p test_run_evidence.py -v
python -O -m unittest discover -s tests -p test_run_evidence.py -v
```

The suite uses the unchanged real preflight with six-phase, local synthetic
fixtures. Actual child processes exercise success, nonzero exit and timeout.
Mocks cover deterministic failure timing and interleavings. No University data,
network request, external system, or client approval is involved. Passing this
suite is runner-contract evidence, not a full engagement rehearsal or hosted-CI
result. Run the existing checkout-dependent suite and actual selected samples
separately in a complete repository before treating integration as verified.
