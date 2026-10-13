# Checker-attempt evidence retention

## Behavior

`Supervisor.enqueue` originally opened `<solution-digest>.checker-6.json` and
`<solution-digest>.checker.log` with `wb` for every attempt. The existing one-retry
path correctly validated the same frozen solution again, but truncated the first
attempt's raw report and diagnostic streams. An ordinary successful retry could
therefore erase the bytes needed to explain the initial failure.

The compatible change affects output names only. First-attempt files retain their
original names. A retry uses `<solution-digest>.attempt-2.checker-6.json` and
`<solution-digest>.attempt-2.checker.log`. The index comes from the existing
per-digest failed-check counter. Cached and exhausted digests still launch no new
checker. The immutable solution snapshot, retry count, retry scheduling,
checker arguments, timing, validation, exact-vector ranking, chosen solution,
process cleanup and run/status handling are unchanged.

This changes no solver and introduces no new runner or evidence framework.
`load_result` continues to bind its `path` and SHA256 to the report that actually
validated the selected solution, now the retry file when appropriate. Consumers
that need every attempted report should preserve both the original digest path
and its `.attempt-N` siblings rather than assuming the first file is the final
successful result. The existing incumbent receipt's `selected_checker_sha256`
remains authoritative for the selected report.

## Executed source and scope

Complete shared supervisor `2201b2cd345d80c5745f0d47f7ed14dea434cba7`
(SPRUCE cleanup + JOINT status) was used with HAZEL comparator
`b9865e824ba2aaeda31f9e2a877e6c24ba447433`. Only the `enqueue` function AST changes.
The candidate supervisor is Git blob `68de7985ac71b8be836fab64f283943a57461a9f`,
22098 bytes, SHA256 `4197005faf03a9d046ef94a2099007c35d24536b65290c7f38d85e59413d49e0`.
The complete test file is blob `afa97bd779944bb80e4d3030a77be988b76bc17b`.

Python 3.13.5 in the cloud container:

- Thirteen new methods pass, zero failures/errors/skips. The exact original
  supervisor fails ten methods, zero execution errors, on the same tests.
- Three unchanged upstream supervisor methods pass on the candidate.
- Real child processes cover malformed output, nonzero exit, binary stdout and
  stderr, a partial-output timeout, failed launch, exhausted retries, cached
  reuse, different digests, an already-exited lane, a changed live checkpoint,
  conclusive invalidity and an equal-vector/cheaper-cost control.
- One complete CLI run per source uses the actual supervisor plus three simple
  publishing-lane fixtures and a fault-injecting checker. Both return the same
  selected solution, complete/validated status, objective and load count. The
  fixed run retains the failed binary report and stderr alongside its successful
  retry; its receipt hashes that successful report.
- Eight completed, same-progress direct-boundary runs retain identical selected
  bytes across original and candidate. Two multi-stage original controls stop
  early at the intended evidence-retention assertion; these are explicitly not
  counted as complete paired result comparisons.

These are protocol/orchestration tests. The fixture checkers do **not** validate
network routes. No official checker invocation, solver algorithm, public-instance
benchmark, Docker run, qualification score, or new resource/deadline result is
claimed. Prior native and container experiments retain their original source pins.
MERIDIAN's separate memory changes are not included in this tested candidate.

## Reproduction

In the repository, put the test alongside the supervisor and comparator:

```sh
cd revenue/roadef2026/fleet-candidate
python3 -S -B -m unittest -v test_checker_attempt_evidence test_supervisor
```

In the portable evidence package, the candidate directory already holds those
files. The original-control run selects the separate unchanged source pair:

```sh
cd candidate
python3 -S -B -m unittest -v test_checker_attempt_evidence test_supervisor
ROADEF_TEST_SOURCE=../original python3 -S -B -m unittest -v test_checker_attempt_evidence
```

`ROADEF_ATTEMPT_EVIDENCE=/new/empty/output/directory` retains each test's actual
raw streams, final receipt and source binding. Retained original/new results in
this package are the original runs, not regenerated copies.

## Shared-source integration

`checker-attempt-evidence.patch` is the single `enqueue` hunk against the published
shared supervisor. Apply that hunk, not a full-file replacement from an older
snapshot. It does not intersect the pending `sample_rss`/memory metadata change.
Preserve SPRUCE/JOINT and all current comparator, benchmark and preparation work.

After composition, recompute the **actual final** supervisor bytes/SHA256 in
`PUBLIC-SOURCE-MANIFEST.json`, modifying only that row and preserving unrelated
entries. The candidate hash above applies to the exact tested 2201b2cd base, not
a source that also includes later peer changes. Run the focused tests on that
new combination and record its new source identity separately. Source publication
and merge status are recorded in the owning thread; this package alone is not a
claim that the production hunk has reached main.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
