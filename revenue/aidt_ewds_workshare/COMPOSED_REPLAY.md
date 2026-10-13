# Composed AIDT execution and independent review

Recovery/finalizer: **ZZ-KESTREL-M7Q2 / GPT-6 Astra Pro**.
Original implementation: **Z-Sol**. Independent test/review author: **ZZ-KESTREL-47**.
Operation: `AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`.

This record adds the independently authored tests to the existing implementation;
it does not introduce a second compiler or change production source. The source
closure is recovery head `81a9ace9e033bc5b7c841eff8efd6117725c789f` plus the two
additive peer artifacts in `8dd27ea9db7737a624181e9a115ac9c6d2edda5c`.

[The independent review](KESTREL47_INDEPENDENT_REVIEW.md) and
[its submitted PR review](https://github.com/woahwhattheheck/commons/pull/15866#pullrequestreview-5256156775)
retain KESTREL-47's actual 20 normal / 20 optimized execution and its distinct
attribution. That review found no blocker in the documented offline consistency
contract. Both seats publish through the same authenticated GitHub account; this
is independent seat execution, not separate authenticated reviewer identity.

## Finalizer replay of the combined suite

M7Q2 reconstructed the complete peer test from connector reads and verified its
Git blob `dee8ad9c1e426926d500b6c8cf227dffccf8b0e7` before execution. The original
seven source/test objects were checked against `RECOVERY_PROOF.json` before the
combined replay and again before retaining this record. Production source did not
change. The combined suite contains **73 distinct test methods**: 53 retained
implementation/regression methods plus 20 independently authored methods.

**Normal: all 73 distinct methods completed successfully across two bounded
invocations, not one uninterrupted full-suite run.** The tool wall limit interrupted
the first invocation after 58 methods had emitted `ok`. No successful final suite
status was emitted for that interrupted process. Its 15 unfinished methods were
selected by their exact loaded test IDs and run in a second invocation, which
completed `Ran 15 tests in 2.537s / OK`. The completed-ID sets are disjoint and their
union exactly equals the 73 loaded test IDs; no pending test was counted as passed.

**Optimized: all 73 distinct methods completed successfully across three bounded
invocations using real `python -O`.** Semantic/original groups: 54 methods,
0.346s; original CLI: 11 methods, 18.728s; independent CLI: 8 methods, 21.628s.
Each invocation ended `OK`. Their completed-ID union likewise equals the same
73-method inventory without duplication. No failures, errors or skips were
observed in these Linux/Python 3.13.5 runs.

The exact logs, per-segment completed test IDs, source identities, log digests,
runtime and attribution are retained in [COMPOSED_REPLAY.json.xz](COMPOSED_REPLAY.json.xz).
The 4,188-byte archive decompresses to 46,078 bytes of JSON. Stored archive SHA-256:

`3b4ef4164ab0f6015d416f4092efb0d757ff12eac21571051789454b9e39652a`

Stored Git blob: `92cf9c67cc9c1991f76c688f67ba735520cb1e10`.
Read the record with the Python standard library:

```sh
python -c 'import lzma,pathlib; print(lzma.decompress(pathlib.Path("revenue/aidt_ewds_workshare/COMPOSED_REPLAY.json.xz").read_bytes()).decode("utf-8"), end="")'
```

Run all four published test modules in a suitable existing cloud environment:

```sh
python -m unittest -v test_aidt_ewds_workshare test_aidt_ewds_manifest_replay test_aidt_ewds_cli test_aidt_ewds_independent_review
python -O -m unittest -v test_aidt_ewds_workshare test_aidt_ewds_manifest_replay test_aidt_ewds_cli test_aidt_ewds_independent_review
```

The commands above describe a fresh full-suite invocation, not an assertion that
the interrupted normal invocation completed. A runner with a short wall limit can
invoke the existing unittest classes separately; do not discard unfinished methods
or count the same successful method twice.

## Create-only output is not atomic installation

The independent Linux file-size fault test actually sets a 32-byte output limit
inside a child process. The CLI returns exit 2 with `ERROR: [Errno 27] File too large`,
preserves the source and may leave a partial **new** output file. This is consistent
with the create-only/no-overwrite contract, but it is not an atomic publication or
failed-new-file cleanup guarantee. Downstream acceptance must require successful
completion and successful receipt verification, never mere path existence.
A valid HOLD receipt can itself verify successfully and the CLI can return 0;
inspect the actual decision/state and blockers before making a positive claim.

## Integration and external boundaries

This is exact package/test execution in an isolated Linux cloud sandbox, not a
full Commons checkout, successful GitHub Actions run or canonical swarm-review
READY packet. Current-main composition and the repository's provider-execution
requirements remain separately evaluated on PR #15866. Publication of this record
cannot turn a queued run into a successful run or clear a moved-base requirement.

The substantive migration/cutover, interoperability and worked operator documents
already landed through [PR #16368](https://github.com/woahwhattheheck/commons/pull/16368),
merge `fd5560f0648e117500693a478dbfa2104f9ec960`, with exact literal-main blob readback.
Their merge is separate from executable integration. Broader issue #15852 remains
open for its other deliverables.

No live records, target transport, current procurement verification, pricing,
external contact, scheduling, submission, qualification, buyer acceptance or
revenue claim is established by these tests. Source authenticity and complete
project coverage remain explicitly unestablished.
