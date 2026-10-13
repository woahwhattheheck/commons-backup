# Configuration lifecycle and rebuild evidence

UIOWA-069 is a runnable offline assessor and editable interview/improvement
worksheet for heterogeneous infrastructure. It distinguishes a retained recipe,
staff recollection, and a supplied record of a successful rebuild at the current
configuration revision. Manual records can support reconstruction as well as
automated descriptions. It never executes configuration, collects credentials,
contacts infrastructure, or treats a document as a live rebuild.

Recovered from the original implementation at
`85635ff32e1081892668357b866ae7aabb5a8501` on
`swarm/zz-pumice-69q-config-lifecycle-20260919`. The existing evaluator and
fictional input generator are retained; this completion adds operating guidance,
editable improvement assumptions, non-overwriting generation and usable sample
outputs. Scope is the original issue #16132.

## Run

Python 3.10+; standard library only. From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_config_lifecycle/config_lifecycle.py \
  revenue/uiowa_rfq_18649_config_lifecycle/synthetic.json \
  --out /tmp/configuration-assessment
```

Choose a new output directory. The command writes `report.json`, `report.md`
and `worksheet.csv`, then exits 0. Valid evidence gaps are report results,
not malformed inputs. Invalid schemas, duplicate keys, dates after `as_of`,
unreadable inputs and existing output directories produce a diagnostic and exit 2.
It does not overwrite outputs. JSON remains the lossless machine representation;
the CSV is intended for analysts to edit, and protects formula-like cell text.

To regenerate the fictional source into a new file:

```sh
python3 revenue/uiowa_rfq_18649_config_lifecycle/synthetic_config.py \
  --out /tmp/configuration-fictional.json
```

The included `sample_output/` is the actual assessor output from the included
fictional records. The generator describes imagined rebuilds; neither generation
nor assessment actually provisions infrastructure. These are not University
findings or service readiness decisions.

## Editable packet

Copy `synthetic.json` as a schema example and replace its explicitly fictional
records with the assessment's agreed evidence. Set `synthetic` accurately.

| Record | Required content | Meaning of absent evidence |
| --- | --- | --- |
| Packet | schema, synthetic flag, as-of date, selected evidence age, inventory coverage, sources, components, exercises | `partial` or `unknown` coverage never supports a complete reconstruction claim |
| Source | Stable ID, artifact/interview kind, observation date, locator, exact excerpt | Interview-only support stays reported; stale or unresolved references remain explicit |
| Component | ID, name/group/state, owner role and evidence, exact configuration revision, recipe mode/evidence, steps, inputs, dependencies, checks, changes, retirement evidence | `null` input/dependency inventory means unknown; `[]` asserts none within declared scope |
| Change | ID, exact revision, date, record and review evidence, disposition | A written configuration alone does not establish reviewed change traceability |
| Exercise | Target/date/scope, exact dependency manifest, executed step IDs, behavior checks, supporting evidence | Walkthrough or in-place repair never establishes from-scratch reconstruction |

The example supplies every field. IDs accept letters followed by letters,
digits, underscores, dots or dashes. The evaluator validates syntax and preserves
missing cross-references as evidence gaps. Extra schema keys are rejected so
misspellings do not silently disappear. Evidence excerpts are hashed and their
locators are retained; hashes identify supplied text, not source authenticity.

An exercise qualifies only with current dependency versions, all declared
steps, supported from-scratch scope and passing declared behavior checks. The
selected evidence window applies to source support and exercises. A current
revision with only an older-version rebuild remains undemonstrated. Conflicting
latest exercises remain visible. A missing dependency, dependency cycle or
retired required dependency prevents a usable reconstruction order.

## Included example

| Fictional component | Result from supplied records | Assessment implication |
| --- | --- | --- |
| BASE | `demonstrated_current_snapshot` | Manual description, pinned inputs and recorded exercise can be adequate |
| STUDENT | `demonstrated_current_snapshot` | Manual dependent service retains the complete current dependency manifest |
| RESEARCH | `preparation_gaps` | Automation does not resolve missing build-cache evidence, recollected flags or an active reference to a retired bridge |
| SIGNIN | `current_rebuild_not_demonstrated` | Prior revision rebuilt; current revision has only an in-place repair record |
| RETIRED_BRIDGE | `not_applicable_retired`; retirement `follow_up_required` | Retirement narrative conflicts with an observed active consumer |

## Interview and improvement worksheet

Each of the five components produces eight worksheet rows: ownership,
configuration, change traceability, recipe, inputs, dependencies, rebuild and
retirement. Rows retain source IDs, evidence state and concrete follow-up
questions, with columns for analyst notes and the proposed maintaining role.
Source IDs resolve to exact excerpts/locators in the JSON and Markdown reports.

Improvement options carry editable effort assumptions and adoption conditions.
They assume one small component and available maintainers, ranging from 1–2 staff
hours for responsibility mapping to 4–12 for an isolated reconstruction exercise.
They exclude provisioning cost, procurement, migration and ongoing support; they
are planning prompts, not estimates derived from evidence or an engagement quote.
Choose an option against actual context. Nothing requires universal
infrastructure-as-code or treats automation volume as a maturity score.
