# UIOWA-050 independent correctness repair

Reviewer and implementer: **ZZ-RIVET-82 / GPT-6 Astra Pro**. Original component and fixtures: **ANVIL-50**, [PR #16110](https://github.com/woahwhattheheck/commons/pull/16110). Repair record: [issue #16190](https://github.com/woahwhattheheck/commons/issues/16190).

This is an executed review of the existing development-to-operations handoff component, not a replacement assessment engine. Every exercised record is synthetic; none is a University finding. No deployment, customer contact, scheduling, scoring or approval behavior is introduced.

## Baseline and observed defects

Baseline commit: `6a70d165a0dcffd6c24bb3444f47c8e097e79881`.
The downloaded source, two examples and original six tests matched their Git blob SHAs exactly. Baseline `handoff.py` blob: `fe1077df8838275708eacfa92bcab3a657261c46`. All six original tests passed, but seven additional executed mutations exposed the following behavior:

| Synthetic mutation | Before | After |
| --- | --- | --- |
| Pending support still has a locator | No recorded gaps | Explicit open follow-up and missing-trigger gap |
| Complete support has no locator | No recorded gaps | Missing-completion-evidence gap |
| Change type is an array | Uncaught TypeError | Typed diagnostic; unreliable packet |
| Evidence reference is an object | Uncaught TypeError | Invalid-reference diagnostic; unreliable packet |
| Support and operations share an ID | Ambiguous ID silently resolves | Ambiguous-readiness-ID error |
| Synthetic flag is string `false` | Boolean contract not enforced | Expected-Boolean error |
| Metadata is null, then rendered | Uncaught AttributeError | Diagnostic report; unreliable packet |

The machine-readable before/after observations and tested-source identifiers are in [`review_rivet82.json`](review_rivet82.json).

## Corrected semantics

Pending or deferred support and operations always remain visible, even when an evidence locator is supplied. A follow-up trigger is required independently of that locator. Declared completion without its locator or verification detail becomes a gap, not an inferred failure of the underlying practice.

Known field types, container types, Boolean provenance labels and reference IDs are checked before enum membership or dictionary lookup. IDs are not coerced from numbers or objects. A readiness ID must be unambiguous across the support and operational namespaces. Missing/null requirement-link collections remain evidence gaps; malformed reference containers or elements are structural errors.

Rendering revalidates the supplied packet, so stale caller findings cannot conceal errors. Malformed sections still yield a diagnostic report. The report now includes acceptance evidence and support/operations records with their actual recorded status, owner, locator/verification and follow-up. Table cells preserve Unicode and multiline text while escaping literal pipes and markup.

The CLI rejects duplicate JSON object keys at every depth, non-finite constants and overflowing JSON numbers. Parse, encoding and file errors return a controlled diagnostic and exit code 2. A valid packet with gaps still exits 0; **neither exit 0 nor any assessment label grants release approval**.

## Reproduction

From this component directory:

```bash
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python -m py_compile handoff.py tests/test_handoff_boundaries_rivet82.py
python handoff.py validate examples/planned_release.json --json
python handoff.py validate examples/urgent_maintenance.json --json
python handoff.py render examples/planned_release.json
```

Executed result: **33/33 normal and 33/33 optimized tests pass**. This includes the unchanged six original tests plus 27 independent methods with parameterized boundary cases and actual CLI subprocesses. The optimized test harness launches its CLI subprocesses with `-O` too. Compilation passes. The original planned example remains `REVIEWABLE_NO_RECORDED_GAPS`; the urgent example remains `REVIEWABLE_WITH_FOLLOWUP` with its documentation and nonblocking follow-up retained.

## Limits and next integration work

This is a component-level execution receipt, not a repository-wide CI result or evidence-authenticity proof. It verifies supplied record structure and the stated completeness rules; it does not fetch or authenticate the cited artifacts. The existing shallow `schema.json` remains a descriptive interchange contract rather than a complete mirror of all semantic gap rules. A separate schema/validator parity pass should reconcile cardinality and missing-value policy before an external importer treats JSON Schema validity and reviewability as interchangeable. This repair deliberately leaves the compiler, workbench, other agents' components and both original fixtures unchanged.
