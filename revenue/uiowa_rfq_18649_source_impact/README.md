# UIOWA-120 — source-version impact review

An operator-invoked, offline comparison of two source manifests and a declared dependency graph. The result is a **review queue**, not a rewritten assessment. No input, finding, rating, recommendation, or source artifact is changed.

Carrier: ZZ-HERON · GPT-6 Astra Pro. Operation: `uiowa-120-heron-20260919`. [Issue #16177](https://github.com/woahwhattheheck/commons/issues/16177) · [PR #16254](https://github.com/woahwhattheheck/commons/pull/16254).

## Open the example, then reproduce it

[Read the frozen source-impact report](examples/report.md). Its before/after snapshots are dated **September 18 and September 19, 2026**, solely as fictional demonstration dates. They are not observations of University systems. The report contains the actual synthetic text change and the dependent worksheet → mapping → narrative paths.

Python 3.10+ and the standard library are sufficient. From this directory:

```sh
python source_impact.py compare fixtures/before.json fixtures/after.json fixtures/dependencies.json --out-dir /tmp/uiowa120-review-NEW
```

The output directory must not already exist. Open `report.html` from that directory for an offline, linked review view; `report.json`, `report.md`, and `review-queue.csv` contain the machine-readable report, prose report, and artifact queue. No server, browser script, remote service, or credential is required. Input locators are displayed, never fetched or executed.

**The example intentionally exits 2 with a written `INCOMPLETE` report.** The interview transcript was not supplied. That is an unresolved comparison, not a tool crash and not an unchanged source. The report distinguishes eight cases, one of each: `text_changed`, `content_changed`, `metadata_only`, `interpretation_changed`, `comparison_unavailable`, `added`, `removed`, and `unchanged`. It tracks six fictional dependent artifacts, preserving multiple causes and an exact dependency witness for each changed source/artifact pair.

For the complete two-case rehearsal and the existing authority-bundle integration:

```sh
python rehearse.py --out-dir /tmp/uiowa120-rehearsal-A
python -O rehearse.py --out-dir /tmp/uiowa120-rehearsal-B
diff -r /tmp/uiowa120-rehearsal-A /tmp/uiowa120-rehearsal-B
python -m unittest -v test_source_impact.py
python -O -m unittest -v test_source_impact.py
```

Use fresh directory names for each invocation. The rehearsal command returns 0 when it successfully creates the examples, even though the examples deliberately contain unresolved review work. The comparator's status/exit contract below is separate.

## What the classifications establish

| Classification | Established fact | What it does not establish |
|---|---|---|
| `text_changed` | Both snapshots contain original supplied text and its exact UTF-8 content differs. | The correct interpretation or recommended action. |
| `content_changed` | Comparable declared content digests differ. | That this tool inspected the underlying source text. |
| `metadata_only` | Comparable content fingerprints are unchanged; metadata or revision changed. | Authenticity, currentness, or validity of the underlying source. |
| `interpretation_changed` | Recorded claim/rating fields changed while the content fingerprint did not. | That the original source changed. |
| `comparison_unavailable` | A fingerprint is missing, representations are incompatible, or partial inventory absence prevents comparison. | Unchanged evidence, a missing real-world practice, or a zero score. |
| `added` / `removed` | Source membership entered/left the operator-declared complete inventory. | Creation/deletion of a real file or institutional activity. |
| `unchanged` | Comparable fingerprints and tracked fields are unchanged. | An approved or current assessment. |

A substantive change can also have metadata and interpretation changes; all tracked field deltas remain in the row even when its primary classification is more significant. Metadata distinguishes a missing key from JSON `null`, and `false` from `0`. Source revision is tracked independently so a metadata key named `revision` cannot hide a real version change.

Exact UTF-8 comparison deliberately does not normalize whitespace, line endings, or Unicode. The report includes up to 2,048 characters of each side of an inline text change, with an explicit truncation flag. Original inputs and full content fingerprints remain the authoritative complete comparison material. A declared digest never acquires an invented text preview.

## Input contracts

The committed [before](fixtures/before.json), [after](fixtures/after.json), and [dependency](fixtures/dependencies.json) files are executable examples, not an untested schema sketch.

A manifest uses `schema: uiowa-source-manifest/v1` with `snapshot_id`, ISO `captured_at` including a UTC offset, `namespace`, `scope` object, `coverage` (`complete` or `partial`), and `sources`. Each source has a unique `id`, `revision` (string or null), `metadata` object and `interpretation` object. It may carry `text`, or `content: {representation, sha256}`, and an `unavailable_reason`. Lowercase SHA-256 is required. Inline text plus a declared text fingerprint must agree. Optional manifest `provenance` retains operator context.

The two manifests must have identical namespaces and scope objects. A same-looking identifier in another engagement is not the same source. Reverse chronological comparisons are refused rather than silently swapped. Unknown fields are refused at structural levels; extensible descriptive fields belong in metadata/provenance.

The dependency graph uses `schema: uiowa-source-dependencies/v1`, matching `namespace` and `scope`, explicit `coverage`, and an `artifacts` array. Each artifact has `id`, `kind`, `locator`, and `depends_on`. References are typed objects: `{"source_id":"S"}` or `{"artifact_id":"A"}`. The source and artifact ID spaces can overlap without ambiguity. `notes` and graph `provenance` are optional.

A mismatched graph scope is refused. For backward compatibility, an omitted graph scope is accepted only with `unbound_dependency_scope`, an `INCOMPLETE` report and every artifact marked `mapping_incomplete`. It is not silently trusted. `partial` graph coverage explicitly states that unlisted dependents are outside the queue. Missing references and actual cycle witnesses are reported; mapping uncertainty propagates downstream. Traversal terminates in cyclic graphs.

For shared routes, the report retains **one deterministic shortest witness path per changed source/artifact pair**, not every possible path. Every changed cause remains represented; the original graph preserves all edges. Sources with no declared consumers remain visible in `unmapped_changed_sources`; the tool does not invent consumers to fill a diagram.

## Existing authority-v2 integration

`adapt-authority` consumes the actual existing [`synthetic_authority.json`](../uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json), not a made-up substitute interface:

```sh
python source_impact.py adapt-authority ../uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json /tmp/authority-manifest-NEW.json --snapshot-id prepared-kit-A --captured-at 2026-09-19T13:00:00Z --coverage complete
```

The existing fixture was read at repository commit `809ff46d4a828b2fdb0ea72dd135b1dd5301b926`, exact Git blob `1d58638c067b35dbdc210365ac3f30d6e72c9548`. The replay verifies that blob before running; an upstream fixture change requires explicit version reconciliation, not silent re-pinning. Its twelve source records carry declared content digests and interpretation fields, **not original source text**.

The adapter round-trips every record field. `claim`, `maturity`, and `confidence_bp` become interpretation; source identity, generation and digest retain their dedicated roles; other fields and future extensions survive in metadata. Source scope/generation must agree with the bundle header. This adapter does not execute the compiler, verify the bundle's authority, assign ratings, or claim that a declared digest proves authenticity.

The integration rehearsal mutates a copy only: one declared digest, one source locator, and one analyst claim. The output has **1 content change, 1 metadata-only change, 1 interpretation change and 9 unchanged records**. All twelve source-text comparisons remain unavailable. Its three dependency nodes are explicitly illustrative and **partial**, not a claimed complete survey of the preparation kit.

PEREGRINE-120R's complementary [#16181](https://github.com/woahwhattheheck/commons/issues/16181) supplies the separate actual-023 dependency-index and challenge lane at `../uiowa_rfq_18649_source_impact_023/`. That namespace must remain distinct from authority-v2. This core does not overwrite that adapter or claim its execution as our own.

## Results and exit codes

`compare` exits 0 for a produced `NO_DETECTED_CHANGE` or `REVIEW_REQUIRED` report. It exits 2 for a produced `INCOMPLETE` report, reporting status on stdout. Invalid input or an output error also exits 2 but prints `INPUT_OR_OUTPUT_ERROR` to stderr. Automation should inspect the report/status and stderr, not treat every nonzero exit as the same condition. No status means approval or permission to submit an assessment.

The writer refuses existing output directories and existing adapter output files. It does not delete or replace input files. An I/O error can leave a partially written **new** directory; do not treat that as a complete report. Inputs are limited to 10 MiB per JSON file; duplicate JSON keys and non-finite numbers are refused. This is an operator tool for bounded preparation collections, not a service for unlimited untrusted graphs.

The CSV is a review export, not a lossless interchange: formula-shaped cells are prefixed with an apostrophe. Exact literal values remain in JSON. The HTML escapes source content and links only to generated local source anchors. No browser visual/accessibility certification is claimed by structural link/escaping tests.

## Executed validation and retained evidence

Final local cloud execution on September 19, 2026:

```text
python -m unittest -v test_source_impact.py
Ran 42 tests in 1.218s
OK

python -O -m unittest -v test_source_impact.py
Ran 42 tests in 1.254s
OK

diff -r /mnt/data/heron/rehearsal-final-1 /mnt/data/heron/rehearsal-final-2
(no differences; exit 0)
```

[The frozen receipt](examples/receipt.json) binds each full generated report to the canonical SHA-256 of its before, after and dependency inputs. Tests read those fixtures and expected receipts without rewriting them. They also verify the real twelve-record round-trip, source/interpretation separation, incomplete inventories, scope collisions, cyclic and missing dependencies, shortest witnesses, Unicode/newline fidelity, output preservation, strict JSON parsing, HTML anchors, CSV formula handling, CLI behavior, and unchanged inputs.

These are actual local execution results, **not a claim that hosted repository CI passed**. PR/provider execution and main-merge receipts belong on the linked carrier when observed. Full real-kit dependency coverage, source authenticity/currentness, and University findings remain outside this implementation's claims.
