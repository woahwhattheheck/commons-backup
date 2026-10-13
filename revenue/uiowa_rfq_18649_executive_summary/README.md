# UIOWA-081 — evidence-linked leadership briefing

Render an editable executive briefing from the existing UIOWA-093 source bundle.
The renderer reuses its native structural validator, preserves finding and
recommendation text, and keeps each statement's evidence and limitation visible.
It does not introduce another assessment, rating or prioritization engine.

## Read or edit immediately

- [Editable executive-summary template](executive-summary-template.md) — a
  complete Markdown document with stable finding, recommendation, planning and
  measure IDs, placeholders and explicit unsupplied values.
- [Fictional worked executive summary](executive-summary-example.md) — a concise
  leadership readout of the existing rehearsal and proposed planning example,
  with all statement/evidence relationships retained. No Python is needed to
  read or edit either document.
- [Editable planning input](planning-template.json) and
  [worked planning input](planning-example.json) — the structured counterparts
  used by the detailed renderer below.

The static Markdown files are editable drafts. Amend the source/trace register
and planning input when changing substantive statements; a hand-edited summary
does not update or revalidate those sources automatically.

## Run the published example

From the Commons repository root with Python 3.10+:

```sh
python revenue/uiowa_rfq_18649_executive_summary/render_summary.py \
  > /tmp/uiowa-leadership-briefing.md
python revenue/uiowa_rfq_18649_executive_summary/render_summary.py \
  --format json > /tmp/uiowa-leadership-briefing.json
```

The default source is the actual checked-in
`revenue/uiowa_rfq_18649_traceability_rehearsal/` bundle. Its three findings,
two recommendations, eight evidence rows and five statement mappings are
fictional preparation material. No new findings or example evidence are created.
The output is readable without the source checkout and editable as Markdown or
structured JSON. Links between findings, recommendations and evidence stay inside
the briefing. No network calls or third-party dependencies are used.

The briefing covers:

- Supplied strengths, gaps and mixed findings with confidence labels and limitations.
- Proposed actions, source-linked rationale and practical dependencies.
- Implementation-effort labels kept separate from unestimated cash savings.
- Expected outcomes kept separate from measurements that were not supplied.
- Unresolved owner, priority, schedule, resource and outcome-measurement decisions.
- Original statement IDs, report locations, evidence locators and exact source hashes.

## Reuse the structured inputs

Pass another authorized local bundle directory as the positional argument. Keep
the established UIOWA-093 six-file contract: `evidence.csv`, `findings.csv`,
`recommendations.csv`, `trace-map.csv`, `executive-summary.md` and `final-report.md`.
The native validator must accept all source links and statement declarations
before a briefing is emitted. The renderer also requires the existing register
columns needed for the briefing; omitted columns fail explicitly.

Use the CSV registers as the editable input template. Finding IDs, recommendation
IDs and evidence IDs remain stable; the trace map identifies exact statements and
their original report locations. Amend the source bundle and its trace map when
changing an authoritative statement, then regenerate the briefing. A hand-edited
rendered briefing is a draft and has not been revalidated automatically.

The renderer copies supplied text and classifications without guessing a priority
order. Identifier order is only display order. A missing limitation or other blank
display value is printed as `NOT SUPPLIED`. Effort categories are not converted to
hours, money or benefit, and no desired outcome is treated as achieved. External
source locators are retained as text; the program does not fetch or authenticate
their underlying documents.

## Add owners, sequencing, resources and outcome measures

Use `--planning` to include decisions and measurement records supplied separately
from the assessment evidence. The six-file trace bundle stays unchanged. Without
this option, Markdown and JSON retain the original v1 output byte for byte.

Copy `planning-template.json` to a new private working file and edit it. The
template is valid immediately: it links the two existing rehearsal recommendations
and leaves every unsupplied decision as `null`. For another engagement, replace
the recommendation/evidence IDs with IDs from that engagement's trace bundle;
set `context` to `SUPPLIED_RECORDS` and identify the actual planning source.
Use a new version when the supplied planning changes.

```sh
python revenue/uiowa_rfq_18649_executive_summary/render_summary.py \
  --planning revenue/uiowa_rfq_18649_executive_summary/planning-template.json \
  > /tmp/uiowa-planning-draft.md
```

`planning-example.json` is a complete editable worked plan for the same published
rehearsal, without copying or creating another evidence corpus:

```sh
python revenue/uiowa_rfq_18649_executive_summary/render_summary.py \
  --planning revenue/uiowa_rfq_18649_executive_summary/planning-example.json \
  > /tmp/uiowa-planned-briefing.md
python revenue/uiowa_rfq_18649_executive_summary/render_summary.py \
  --planning revenue/uiowa_rfq_18649_executive_summary/planning-example.json \
  --format json > /tmp/uiowa-planned-briefing.json
```

The worked plan explicitly proposes role owners, priorities, sequence, timing and
resource assumptions for R-001/R-002. M-RIS-001 has a proposed target of one
retained propagation example and no supplied baseline or observed result.
M-IAM-001 has an illustrative proposed target of seven, using the E-008 inventory;
its baseline and observed value remain unsupplied. Existing representative
evidence stays in the finding register and is not recast as an outcome measured
for this plan. The output labels the entire plan fictional and retains those limits.

### Planning input contract

The file is UTF-8 JSON (a BOM is accepted), at most 2 MiB, with schema
`uiowa-executive-planning/v1`. Duplicate JSON fields, unknown fields, broken
references and incorrectly typed values produce a clear error and exit 2 before
any briefing is printed.

| Field | Meaning |
|---|---|
| `context` | `SYNTHETIC_EXAMPLE` or `SUPPLIED_RECORDS`; a display label, not authentication. |
| `plan_id`, `version` | Stable identity and supplied version of the planning record. |
| `source_name`, `source_locator` | Nonempty name and locator of the source of the planning decisions. These are retained text, not fetched URLs. |
| `recommendations` | Zero or more planning records. A subset is allowed; recommendations without a record still display `NOT SUPPLIED`. |

Each planning record requires unique `planning_id`, an existing
`recommendation_id`, and nonempty `evidence_ids`. Evidence IDs must belong to the
recommendation's existing finding-to-evidence chain. They identify its rationale;
they do not assert that the assessment evidence dictated a new owner, budget or
target. Planning statements retain their own file identity and JSON locator.
There can be at most one planning record per recommendation.

Optional `owner`, `priority`, `sequence`, `timing` and `resource_assumptions` are
text or `null`. Text is displayed as supplied. No priority is ranked, no schedule
is calculated, no person is assigned or contacted, and no resource quantity is
converted to cash savings. Recommendation display order still follows IDs;
`sequence` records the supplied ordering or dependency in words.

Optional `outcome_measures` contains zero or more objects:

| Field | Meaning |
|---|---|
| `measure_id`, `name` | Required unique stable measure ID and nonempty name. |
| `unit` | Supplied unit, or `null` when unknown. |
| `baseline`, `target`, `observed_value` | Separate text values or `null`. Quote numbers, including `"0"`, to preserve exact values and units; no arithmetic or target-attainment calculation occurs. |
| `measurement_window` | Supplied period/record label. Required for an observed value; a missing date can remain explicit in the source label. |
| `observation_evidence_ids` | Unique IDs from the same evidence register. A supplied observed value requires at least one reference. These may differ from the recommendation's original rationale evidence. |
| `notes` | Supplied limitations or interpretation, or `null`. |

Plan, planning, recommendation and measure IDs follow the existing ASCII ID
convention: start with a letter or digit, then letters, digits, `_`, `.`, `:`, or
`-`. Empty/whitespace-only optional text is displayed as `NOT SUPPLIED`; quoted
zero remains zero. Null and empty values remain distinct in JSON. No target is
filled into an absent result, and reference validation does not independently
authenticate an observation or make it a realized benefit.

With planning supplied, JSON uses `uiowa-executive-summary/v2`. It retains the
planning fields, recommendation/measure identities, original JSON pointers, and
the exact planning file's name, bytes, Git blob and SHA-256. The original
`source_bundle_sha256` continues to identify only the six evidence-bundle files;
the planning identity is separate. `planning_state` says which categories have
supplied values and lists recommendations without planning. It does not report
completion or approval. Markdown links remain internal and all supplied text is
escaped for rendering.

## Output and limits

JSON retains all four source tables, source file/physical-line locators, exact
file lengths, Git blob identities and SHA-256 values. A deterministic bundle digest
binds those source file identities. The renderer checks the source files again
after reading them and rejects a moving bundle. These are byte and structure
checks, not an independent evidence trust root or professional judgment.

Exit 0 means the source bundle passed structural checks and a draft was rendered.
Missing inputs, broken references or malformed fields exit 2 without a partial
briefing. Output goes to stdout; redirect to a new path to retain earlier drafts.

Real evidence belongs in the authorized private engagement environment. The public
sample remains fictional, with no University findings, customer communication,
contract acceptance, scheduling, invoice or payment action implied.

Original UIOWA-093 source authorship is retained. This delivers the reusable
rendering and traceability seam requested in Commons #16154 using the existing
published rehearsal rather than a second demonstration corpus.
