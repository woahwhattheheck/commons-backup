# Preserve portfolio recovery on malformed checker reports

This changes only `compare_checker.py::load_result` and its public source-manifest
entry. The solver, official checker, ranking, portfolio timing and supervisor
algorithm are unchanged. The existing preparation script copies this comparator
into its next build context without a new build path. Immutable source
`2885d176373c33410148829fef93c310c3752c0b` remains the native benchmark input;
these corrected bytes are a distinct runtime revision, not a new benchmark result.

## Failure and correction

The original comparator calls `.get` on a decoded JSON document before requiring
an object. A list, null or scalar therefore raises `AttributeError`. Malformed
saturation strings and oversized exponents raise `decimal.InvalidOperation` or
`decimal.Overflow`, including decimal construction inside `json.loads`.
`Supervisor.poll_checker` handles `ValueError`, `KeyError`, `TypeError` and
`OSError`, not those two exception families. Such reports terminate orchestration
instead of following its documented retry path.

`load_result` now requires a JSON object and converts only `DecimalException`
failures at the two numeric decoding boundaries into chained `ValueError`s.
Unexpected programming errors and cancellation are not broadly swallowed. Valid
reports retain the same exact values, descending vector, coordinate checks,
source-byte identity and six-decimal precision requirement. `compare` and the
CLI have identical syntax trees; cost still never breaks a vector tie.

The existing supervisor now retries the same immutable checkpoint once. A
successful retry can select those checked bytes; exhausted malformed reports
leave the previously validated incumbent untouched. A conclusive `valid:false`
report is not retried. If nothing validates, the existing exit code 1 and
`no_validated_solution` status remain explicit.

## Executed boundary evidence

Run from this directory:

```sh
python -B -m unittest -v test_checker_boundary test_supervisor
```

The new suite passes 18 methods, including ten complete supervisor CLI runs with
real isolated solver/checker subprocesses. Those child programs are deliberately
small protocol fixtures, not the competition solver or official checker. The
runs cover transient string/list/null/arithmetic/JSON-exponent failures,
exhaustion, no validated result, ordinary checker crash and conclusive
infeasibility. Original source fails eight assertions and produces fifteen
errors across seven methods of the same new suite. All three retained
`test_supervisor` methods also pass on the repaired comparator, including
snapshot immutability, objective ties and drain-deadline behavior.

The exact-value tests compare 250 generated ranked vector pairs against integer
millionths and 250 independent cost-only ties. A separate 500-document
old/new comparison preserves every parsed field, including byte hashes and
coordinates. These counts are parser/orchestration evidence, not optimization
instances, official feasibility certificates, throughput or ranking improvement.

Set `ROADEF_TEST_SOURCE` to a directory containing the old comparator and
supervisor for the original failure run. Set `ROADEF_TEST_EVIDENCE` to a fresh
cloud directory to retain every subprocess receipt, frozen checkpoint, checker
report and log. Existing evidence directories are not silently overwritten.
`CHECKER-BOUNDARY-VALIDATION.json` binds the compact result to source and log
hashes. Complete original, intermediate and final evidence is retained separately
in the HAZEL delivery archive.

S139 qualification draft, attachment and submission are unchanged. No new public
benchmark, Docker build, deadline calibration or solver search was performed by
this repair. Root's integration and QUARTZ/RENEW's separately pinned executions
remain their own results; later supervisor revisions require their own combined
source attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
