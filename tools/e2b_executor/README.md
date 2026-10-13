# E2B archive execution receipts

This optional adapter runs caller-supplied archive bytes in one E2B sandbox.
The planning, validation, and test surface uses only Python's standard library.
A real execution additionally requires the official `e2b` package and an already
authorized `E2B_API_KEY` in the caller environment. Tests never contact E2B.

```sh
python -m tools.e2b_executor job.json
python -m unittest -v test_e2b_executor test_e2b_executor_receipts
python -O -m unittest -q test_e2b_executor test_e2b_executor_receipts
```

A job uses schema `e2b_exact_head_job.v1`, `repository` in `owner/name` form,
a lowercase 40-hex `commit_sha`, `source_archive_sha256`, local `archive_path`,
explicit `template`, bounded `sandbox_timeout_seconds`, and an ordered
`commands` list of `{ "argv": ["python", "-m", "unittest", "-q"],
"timeout_seconds": 30 }` objects. Optional `manifest` entries contain a safe
relative `path` and lowercase SHA-256. The command working directory is the
archive extraction root: archive layout and manifest paths must agree.

The local archive is bounded to 128 MiB and its captured bytes are hashed before
provider construction. The same bytes are uploaded and hashed inside the
sandbox before extraction. Extraction preflights at most 20,000 members,
64 MiB per file, and 512 MiB aggregate expanded files; links and special files
are refused. Job JSON is bounded to 2 MiB, rejects duplicate keys and nonfinite
constants, and has a 32-level semantic depth limit. A manifest has at most
4,096 entries. These are input and extraction limits, not a billing estimate.

## Failure evidence is retained

The synchronous E2B SDK raises `CommandExitException` when a command finishes
with a nonzero status. The adapter recognizes that SDK exception specifically
and retains its exit code, stdout/stderr digests, redacted excerpts, and command
order. A zero or malformed exit value on an exception is not success. A generic
transport error remains a provider failure even if it has result-like fields.

Each completed command is attached to the receipt immediately. A later timeout,
malformed result, or transport interruption therefore cannot erase earlier
completed-command evidence. An interrupted command without a provider result
has no invented exit code or output. Later commands are not run after a failure.
Teardown is attempted after every successful sandbox construction; failed
teardown prevents a green receipt. Exit status is 0 for a green receipt, 1 for
a non-green provider/execution receipt, and 2 for invalid input at the CLI.

## Meaning of a receipt

`green` means the requested command sequence returned zero and teardown
succeeded. It does not establish Git origin. Repository and commit labels remain
`CALLER_ASSERTED_UNVERIFIED`, and `git_commit_binding_verified` is always false.
A separate independently verified source-custody record is needed to bind the
archive digest to a repository revision. These receipts are not GitHub-hosted
CI, merge authority, live provider activation evidence, buyer acceptance,
payment, or revenue. Synthetic fake-provider tests must not be described as a
live E2B smoke run. Do not spend provider credit without separate authorization.

Source lineage: Commons #15922, #15953, and #16007. The failure-result API is
specified by E2B's `CommandResult` / `CommandExitException` implementation at
`packages/python-sdk/e2b/sandbox/commands/command_handle.py` (reviewed upstream
blob `043f871c256c2569d3b4db9f857cb8df0c2bf0f4`).
