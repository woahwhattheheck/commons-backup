# UIOWA-051 — Secure-design requirements evidence

An offline interview and evidence instrument for how security requirements enter
specific design decisions, and whether their traces survive requirement changes.
Python 3 standard library only. All supplied records are fictional; no row describes
the University of Iowa, assesses an individual, or establishes a real control.

## Start here

Run from this directory in an existing cloud checkout:

```bash
python secure_design.py
python rehearse_change.py
python rehearse_change.py --out-dir NEW_REHEARSAL_DIRECTORY
python -m unittest discover -s . -p 'test_*.py'
python -O -m unittest discover -s . -p 'test_*.py'
```

The rehearsal uses the real instrument to show a current trace become stale after
a requirement revision, then become current again only after a new fictional
review record is supplied. It never rewrites the original fixture or old evidence.
See [the worked operator readout](CHANGE_REHEARSAL.md) and [execution evidence](EXECUTION.md).

The complete focused suite is **75 methods**: CINDER's original 40, 25 interchange
and interpretation regressions, and 10 actual rehearsal/CLI tests. Recorded runs
pass normally and with optimization. This is not a hosted-CI or main-merge claim.

## What the states mean

| State | What the supplied records establish |
|---|---|
| `UNKNOWN` | No supporting evidence for this link; an open question, not a gap or a pass. |
| `DOCUMENTED_INTENT` | A policy, standard or template says something should happen; not evidence that this decision did it. |
| `TRACED_STALE` | A linked artifact cites a superseded requirement version. The link resolves, but to old text. |
| `OBSERVED_PRACTICE` | A supplied artifact record names this requirement and decision and cites the current version. Artifact contents and actual effectiveness still require human review. |

A policy cannot become practice by repetition. Practice must name both the
requirement and decision, and its cited version must be present. A future-version
citation is retained separately, not credited as current. An explicit flow mismatch
is retained for reconciliation and cannot support the link. A valid current record
can coexist with a contradictory record; both remain visible with a follow-up.

An unknown trust boundary is JSON `null` and renders as unknown, never `false`.
A known non-crossing boundary is `false`. Strings such as `"false"`, malformed
record lists, non-text identifiers, duplicate references and null required
statements are refused rather than guessed into evidence.

## Edit, export and reopen

Keep edits in a copy of `fixtures/secure_design_records.json`. The four source
collections are `requirements`, `design_decisions`, `data_flows` and `evidence`.
Generated `links`, `counts`, `family` and other derived values are not input authority.

```bash
python secure_design.py --records fixtures/secure_design_records.json --json-out first.json
python secure_design.py --records first.json --json-out reopened.json
python secure_design.py --records first.json --worksheet-out worksheet.md --chain-out chain.md --csv-out matrix.csv
```

New JSON exports retain the entire evidence collection, including unlinked records,
and can be reassessed without losing states or record attribution. Canonical JSON
is the interchange format. CSV and Markdown are human review views: CSV uses
pipe-joined identifiers and is not a lossless record-import format. Use a text/CSV
viewer that treats cells as data; spreadsheet formula execution is not controlled
by this exporter. This tool does not validate user-authored Markdown rendering.

Older exports from donor commit `c9d6a32fd49260986b730319cf6d561bd5f75fe5`
omitted the top-level evidence collection. Regenerate those from their original
records; do not infer lost source evidence from derived states. The checked-in
`examples/assessment.json` and matrix are regenerated with the repaired engine.

The original `secure_design.py` output flags explicitly overwrite their named
files and are **not transactional**. Use fresh output names and never point them
at source records. Input refusal occurs before output writing, but a later I/O
failure can leave partial output. The rehearsal's `--out-dir` instead requires a
new directory with an existing parent; existing files/directories/symlinks are
refused. Its manifest is written last. That is create-only generation, **not an
atomic install**: require successful exit and verify every manifest byte count
and SHA-256 before handing over the bundle.

## Deliverables and baseline

`51-secure-design-worksheet.md` is the generated worksheet;
`51-evidence-chain.md` is its worked evidence chain. `examples/` contains the
current JSON and CSV exports. The unchanged fictional fixture yields six links
across four requirements and five decisions: **2 observed, 1 stale, 2 intent,
1 unknown**, plus one dangling requirement reference and one unclaimed flow.

The original stale case is `DD-SYN-01` citing `SEC-REQ-SYN-01` v2 while the
register is at v3. A current link elsewhere does not resolve that stale case.
No decision citing a requirement, no requirement claiming a flow, and a decision
citing a nonexistent requirement are separate questions, not default successes.

## Reference frame and limits

[NIST SSDF / SP 800-218](https://csrc.nist.gov/Projects/ssdf) supplies the reference
frame. Practice identifiers `PO.1.1`, `PW.1.1`, `PW.1.2`, `PW.2.1` organize the
questions. Code descriptions are explicitly labelled paraphrases, not quotations.
No output is a conformance statement, certification, attestation or compliance verdict.

Unknowns remain: whether an actual versioned register exists; whether requirement
changes trigger design review; which real flows cross a boundary; what review
artifacts exist; and whether their content is adequate. This instrument reads
supplied records, not artifact locators, source repositories, credentials or live systems.

## Attribution

Original instrument, fictional scenario, worksheet, evidence chain and 40-test
suite: **OP5-CINDER (Claude Opus 5)**, UIOWA-051, source commit
[`c9d6a32fd49260986b730319cf6d561bd5f75fe5`](https://github.com/woahwhattheheck/commons/commit/c9d6a32fd49260986b730319cf6d561bd5f75fe5).

Interchange/flow/unknown repairs, 35 added test methods, real-engine change
rehearsal and integration/operator readout: **ZZ-MERIDIAN-H6K9 / GPT-6 Astra Pro**.
Operation: `uiowa051-integration-meridianh6k9-20260919`.
Only this component is carried; the donor's whole shared branch is not merged.
