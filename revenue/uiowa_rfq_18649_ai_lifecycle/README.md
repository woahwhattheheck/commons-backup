# UIOWA-079 — AI workflow lifecycle and observability

A runnable, vendor-independent assessment instrument for explaining how an AI
workflow changed, what behavior was recorded, who supports it, and which records
are missing for investigation or replay. It does not invoke a model, fetch a URL,
rescore an answer, change a live workflow, or grade individual employees.

**The supplied history and all observations are fictional preparation material,
not University of Iowa findings.** Running the analyzer verifies its arithmetic
and record handling, not an actual AI model's performance. This is an additive
UIOWA-079 component, not a replacement evidence compiler or maturity model.

## Collect and review CSV registers

Use the [CSV register intake guide](REGISTERS.md) to create editable templates,
export an existing lifecycle history into ten tables, or build JSON, Markdown,
comparison CSV and a portable HTML review from completed registers. The adapter
reuses this analyzer and its evidence rules; it does not call a model or invent
missing observations. Output histories/registers include supplied artifact text
and must stay on an appropriate private surface.

## Run the complete example

Python 3.10+; standard library only. From this directory:

```sh
python synthetic.py > /tmp/ai-history.json
python lifecycle.py /tmp/ai-history.json > /tmp/ai-lifecycle-report.json
python lifecycle.py /tmp/ai-history.json --format markdown > /tmp/ai-lifecycle-report.md
python lifecycle.py /tmp/ai-history.json --format csv > /tmp/ai-comparisons.csv
python lifecycle.py --schema > /tmp/ai-lifecycle.schema.json
python -m unittest -v test_lifecycle.py
python -O -m unittest -v test_lifecycle.py
```

Use a temporary directory appropriate for the operating system in place of
`/tmp`. `python synthetic.py | python lifecycle.py - --format markdown` also
works without intermediate files. Invalid input produces exit code 2, a
specific `INVALID_INPUT` diagnostic on stderr, and no report on stdout.
Successful analysis exits 0 even when evidence is incomplete or an incident is
open: absence of evidence is an assessment result, not permission to deploy.

The checked-in [worked report](WORKED_EXAMPLE.md) is generated from the exact
fixture. Tests detect stale checked-in report/schema output. The reusable
[interview and investigation worksheet](REVIEW_WORKSHEET.md) explains how to
collect the missing metadata and turn observations into proportionate next work.

## Record contract and evidence semantics

[lifecycle.schema.json](lifecycle.schema.json) is the input schema. The CLI adds
semantic validation that JSON Schema alone cannot express: unique identifiers,
typed references, timezone-aware chronology, parent ordering, case-universe
membership, digest bindings, same-version replay, and incident-resolution links.
The schema checks document shape; `validate` checks the complete contract.

Each version records its parent, change reason/time, support role, model revision,
mutable-alias status, seed, and eight component references: model manifest,
prompt, source snapshot, evaluation set, scoring rubric, code, runtime environment,
and configuration. `null` means explicitly unknown, never an implicit default.
A seed is recording context, not a claim that the provider implements determinism.

Artifacts carry ID, kind, locator, retention state, optional SHA-256, and optional
UTF-8 content. Content present means retention must be true and its digest must
match. Locators are never dereferenced. `registered_only` means bytes were not
supplied; `not_retained`, `digest_missing`, and `missing` are distinct gaps.
A digest checks bytes, not the truth of their content or their authorship. A model
manifest does not preserve model weights or guarantee later provider availability.
Do not place credentials, real University artifacts, or private customer material
in this public source tree. Future offline assessments can use locally supplied
metadata and emit `CALLER_SUPPLIED_METADATA_NOT_INDEPENDENTLY_VERIFIED`.

The evaluation-set artifact is a JSON manifest containing `protocol_id` and a
sorted `cases` array. Every row binds the case ID to the SHA-256 of its input and
expected answer. Changing a protocol, input, or expected answer without updating
that manifest is rejected. A changed set or rubric, unavailable definition bytes,
or unavailable case inputs/expectations suppresses comparison deltas. This
prevents dataset drift from masquerading as model improvement.

## Calculations, units, and interpretation

Correctness is Boolean or unknown. Completeness and usefulness are supplied
rubric scores in [0,1], not judgments calculated by this tool. Repair time is in
minutes and latency is in milliseconds. Numbers must be finite and nonnegative;
booleans do not count as numeric scores. Execution errors cannot carry answer
quality scores, but measured error latency or repair effort may be retained.

Run summaries provide expected, known and missing counts plus mean-of-known.
A comparison names two runs explicitly; it never silently selects the latest
run. For each metric, pair only cases with known observations in both runs:

`delta = mean(candidate(case) - baseline(case)) over the paired case IDs`

Baseline/candidate means use that same paired subset. Reports retain the expected
case denominator, exact excluded case IDs, `complete` versus `subset_only`, and
whether higher or lower is desirable. Values are rounded to six decimal places;
there are no confidence intervals, causal claims, peer percentiles, savings
estimates, maturity scores or automatic deployment decisions. JSON `null` and
empty CSV numeric fields mean unavailable; a literal zero remains observed zero.

Multiple model/prompt/configuration changes are visible as recorded component
changes. Even a single change establishes only association in these supplied
records. Case sampling, evaluator calibration and production transfer remain
questions for the assessor; a small paired fixture is not a workload-wide result.

A replay must name two distinct, chronologically ordered runs of the same
version. `exact_on_recorded_cases` requires matching hashes and retained inline
output bytes for the full case universe, with no execution errors. Different
output hashes produce `different_recorded_outputs`; missing bytes produce
`incomplete`. This is finite recorded-output evidence, not a future reproduction
guarantee. Equal quality scores do not establish identical outputs.

Incident state is derived from event links. A closure without evidence stays
`resolution_claim_without_evidence`; linked evidence is described as recorded,
not independently authenticated. Every event preserves its version, time,
support role, related runs and evidence references. Cross-version repairs can
resolve an earlier incident without relabeling the original observations.

## Worked story and executed acceptance

The fixture contains four versions, six runs, four cases and four runtime events.
Baseline v1 has two matching recorded runs. v2 changes both model and prompt:
three cases have scores, while c4 times out. Regression correctness is -0.666667
on the **3/4 paired subset**, not the full four-case workload. v3 repairs the
prompt and the paired correctness delta is +0.666667, but latency increases
100 ms and repeated wording differs for c2. v4 changes the evaluation definition;
its comparison is explicitly incomparable, and its environment retention,
model pinning, seed and support-owner records are incomplete.

Acceptance executed in an ephemeral cloud runtime on Python 3.13.5:
35 tests passed under normal Python and 35 under real `python -O`. The suite
runs all three CLI formats and schema export; checks arithmetic, missing/zero
behavior, manifests, hashes, malformed JSON, types, bounds, chronology, references,
replay evidence, event closure, escaping, record-order stability, and generated
artifact freshness. This is component acceptance, not whole-repository CI or
production validation. No external service was called by the component.

## Integration seam — no hidden authority conversion

Input is one workflow history. Output `schema_version=1.0` includes:
`workflow_id`, `group`, `assessment_area`, `authority`, `provenance`, `timeline`,
`runs`, `comparisons`, `replays`, `events`, and `limits`. Stable IDs connect every
version, run, case, artifact and incident. Preserve these IDs and source locators
when attaching this output to the existing workshare/workbench.

UIOWA-098/report integrators can attach the report as draft AI-readiness support
for the corresponding ESS/RIS/IAM cell. `cross-group` is scope metadata, not a
fourth assessment group. This component deliberately does not mint a compiler
receipt, claim trusted authority, synthesize a maturity rating, or overwrite
existing findings. An adapter must map the existing compiler's actual fields and
retain the synthetic/caller-supplied label, incomplete denominators, incomparable
comparisons, reproduction gaps, incident links and limits. No end-to-end compiler
integration is claimed by these component tests.

Authored by ZZ-PEREGRINE-17, GPT-6 Astra Pro. Operation:
`uiowa-079-peregrine17-20260919`. Scope source: the UIOWA-079 work order in the
existing Michael demo channel; no new external procurement requirements assumed.
