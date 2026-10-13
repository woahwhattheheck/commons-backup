# Reading a rating report without erasing uncertainty

**UIOWA-022 analyst walkthrough — synthetic rehearsal, not University findings.**

This is a practical companion to Anchor-ZZ's existing [rating method](22-rating-model.md),
not another maturity scale or assessment engine. It explains the actual three checked-in
fixtures, adds two small interpretation exercises, and gives a repeatable command that
uses the existing engine. The supplied ranks, labels and confidence are fictional inputs;
this tool does not establish their factual support or define the UIOWA-021 anchors.

The reader's job is to retain the observation, its limits and the next question. A
composition label is not a grade, confidence is not maturity, and “unassessed” is not
“absent.” The 60% coverage threshold and two-rank mixed-practice threshold are the existing
proposed method defaults, not University requirements or validated benchmarks.

## Which implementation does this walkthrough describe?

The five worked results below were executed with **both** the original engine and the
published UIOWA-022 integrity repair. Their pre-existing structured results agree.
The repair adds display identities and service-level Markdown detail; that does not
make old whole-output hashes valid for the new output generation.

| Source generation | Exact Git blob | Reporting distinction |
| --- | --- | --- |
| Original, retained from Anchor-ZZ PR #16126 | `61d98e53631b684ed390b3b6c66f4870a2ad6dd8` | Service summaries exist in JSON; generated Markdown omits them. |
| Repair, published in PR #16317 | `071fee6aad933954d05e0a1e6769ea9220614f71` | Explicit service identities, collision-safe keys, service Markdown, strict settings and text-safe cells. |

[Repair carrier and independent review](https://github.com/woahwhattheheck/commons/pull/16317#pullrequestreview-5256158044).
**Publication of this document does not merge that executable repair.** Its current
integration state belongs to the PR and provider receipts, not this static guide.
The replay below reports which exact implementation it actually read.

## Case 1 — a known critical gap survives strong observations

Input: `synthetic_case_critical_gap.json`, five assessed security criteria in ESS.
Four observations have rank 4 and one has rank 1. The latter is explicitly material
and critical. Those supplied facts produce this actual output:

| Interpretation field | Actual result |
| --- | --- |
| Composition | `critical_gap_present` |
| Coverage | 5 assessed / 5 eligible = 100% |
| Rank distribution | rank 1: one; rank 4: four |
| Confidence | four high; one moderate; floor moderate |
| Critical and material gap | `SEC-A5` |

A usable rehearsal sentence is: “The five supplied observations cover the eligible
fixture, and the named critical gap remains visible despite stronger observations
elsewhere.” Do not replace this with an overall average or a claim that ESS is strong.

The facilitator's next question is concrete: **Which evidence supports `SEC-A5`, what
makes its consequence critical, and what would demonstrate that the gap was addressed?**
The composition engine cannot answer those evidence and impact questions. Carry the
criterion ID into the discussion rather than invent a remediation from the rank alone.

## Case 2 — high confidence does not repair missing coverage

Input: `synthetic_case_low_coverage.json`, twelve software-development records for RIS.
Two are explicitly not applicable. Ten remain eligible, four are assessed and six are
unassessed. The calculation is **4 / (4 + 6) = 40%**, not 4/12 and not 100% because the
four observed rows all have high confidence.

| Interpretation field | Actual result |
| --- | --- |
| Composition | `insufficient_coverage` |
| Assessed pattern | four rank-4 observations, all high confidence |
| Unassessed | `DEV-C05` through `DEV-C10` |
| Not applicable | `DEV-C11`, `DEV-C12` |
| Eligible denominator | ten, with six unknown observations retained |

A usable sentence is: “The four assessed observations share the supplied pattern;
coverage is 40%, and six eligible criteria remain unassessed.” This is not a finding
that the six practices are missing. Nor does the fixture establish why the sample
was selected or whether it represents real operations.

Next ask: **Which of the six IDs can be supported by an appropriate artifact or
interview, and are the two applicability reasons defensible for this service boundary?**
Do not improve coverage by relabeling unknown rows as not applicable.

## Case 3 — a coherent service pattern is not a high-maturity verdict

Input: `synthetic_case_mixed_services.json`, six deployment/operations observations.
The area is `mixed_practice`, with 100% coverage and a rank range of 1–4.
The actual service rows are:

| Service | Assessed / eligible | Rank distribution | Confidence distribution | Composition |
| --- | --- | --- | --- | --- |
| ESS | 2 / 2 | one rank 3; one rank 4 | one moderate; one high | `coherent_pattern` |
| IAM | 2 / 2 | one rank 3; one rank 4 | two high | `coherent_pattern` |
| RIS | 2 / 2 | two rank 1 | one moderate; one high | `coherent_pattern` |

RIS is coherent **because its two supplied observations agree**, not because rank 1
is high maturity. The area-level result preserves the unevenness between services.
The executable fixture has two RIS rank-1 observations; the prose method's broader
illustrative description of ranks 1–2 is not substituted for these actual bytes.

Ask: **Are the compared criteria, evidence windows and service boundaries sufficiently
aligned to explain this difference?** Preserve each service row while investigating.
This method does not declare a winning group, a preferred technology stack or a
procurement recommendation. On the original engine, read these rows from JSON;
do not take the absence of a service table in its Markdown as absence of service data.

## Case 4 — unassessed and not applicable lead to different questions

The additional `unknown-vs-na` exercise has two criteria in the same fictional
AI-readiness area. ESS has one unassessed criterion. IAM has one not-applicable
criterion with the explicit reason “This synthetic service boundary excludes the
practice.” There is no assessed rank in either service.

| Group | Eligible | Coverage | Composition | Correct follow-up |
| --- | --- | --- | --- | --- |
| ESS | 1 | 0% | `unassessed` | Obtain the evidence or complete assessment. |
| IAM | 0 | null, displayed as n/a | `not_applicable` | Review the applicability reason. |
| Combined area | 1 | 0% | `unassessed` | Keep the eligible unknown visible. |

Null coverage is not zero coverage: the IAM denominator is empty, while ESS has a
real eligible unknown. Neither state supplies a rank or proves an institutional
practice exists or does not exist.

## Case 5 — insufficient coverage can coexist with a known critical gap

The `low-coverage-critical-gap` exercise has one assessed critical material gap
(`SYN-GAP`) and nine unassessed security criteria. Coverage is 10%, so the composition
label is **`insufficient_coverage`**, not `critical_gap_present`. Nevertheless,
`critical_gap_ids` and `material_gap_ids` both still contain **`SYN-GAP`**.

The existing precedence rule checks coverage before choosing the critical-gap
characterization. It does not remove the gap. A reader who copies only the status
would lose consequential information.

A complete rehearsal sentence is: “Coverage is insufficient for an area
characterization, and the one assessed criterion records a known critical material
gap requiring separate attention.” Ask both questions: **What further coverage is
needed? What evidence and consequence support the already identified gap?** Do not
wait for a complete population before acknowledging the supplied gap, and do not
pretend the one observation characterizes all ten criteria.

## Run the complete five-case rehearsal

Run from the Commons repository root in an existing cloud checkout. This is an
ordinary copyable documentation example; no new runtime module or workflow is
installed. It executes the existing engine from a **single captured source buffer**,
and hashes those same bytes. It reads each checked-in fixture once. Both known
source generations are supported; an unreviewed engine revision is reported as a
mismatch instead of silently relabeling it as the tested revision.

Choose a **new output directory**. The example refuses an existing directory and
uses create-only writes; it does not replace input files or earlier outputs.
A process or storage failure can leave an incomplete new directory: this example
is not an atomic multi-file publisher. Completion is the final printed index plus
all five JSON/Markdown pairs. Do not reuse a partial directory as a completed run.

```sh
python - /tmp/uiowa-022-reader-NEW <<'PY'
from pathlib import Path
import hashlib, importlib.util, json, sys

base = Path('revenue/uiowa_rfq_18649_rating_model')
source = base / 'rating_model.py'
raw = source.read_bytes()
def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
source_blob = git_blob(raw)
known = {
    '61d98e53631b684ed390b3b6c66f4870a2ad6dd8': 'original',
    '071fee6aad933954d05e0a1e6769ea9220614f71': 'published-repair',
}
if source_blob not in known:
    raise SystemExit('Unreviewed engine revision: ' + source_blob)
spec = importlib.util.spec_from_file_location('_reader_engine', source)
if spec is None or spec.loader is None:
    raise SystemExit('Cannot prepare the engine module')
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
exec(compile(raw, str(source), 'exec', optimize=sys.flags.optimize), engine.__dict__)
cases = []
for name in ('critical_gap', 'low_coverage', 'mixed_services'):
    data = (base / ('synthetic_case_' + name + '.json')).read_bytes()
    cases.append((name, json.loads(data), git_blob(data)))
cases.append(('unknown-vs-na', {'engagement': 'SYNTHETIC reader exercise', 'criteria': [
    {'criterion_id': 'SYN-U', 'area': 'ai_readiness', 'service': 'ESS',
     'assessment_status': 'unassessed'},
    {'criterion_id': 'SYN-NA', 'area': 'ai_readiness', 'service': 'IAM',
     'assessment_status': 'not_applicable',
     'applicability_reason': 'This synthetic service boundary excludes the practice.'}
]}, None))
rows = [{'criterion_id': 'SYN-GAP', 'area': 'security', 'service': 'ESS',
         'assessment_status': 'assessed', 'criticality': 'critical',
         'maturity_rank': 1, 'maturity_label': 'synthetic-anchor-1',
         'confidence': 'high', 'material_gap': True, 'evidence_ids': ['SYN-E']}]
rows += [{'criterion_id': 'SYN-U' + str(i), 'area': 'security', 'service': 'ESS',
          'assessment_status': 'unassessed'} for i in range(1, 10)]
cases.append(('low-coverage-critical-gap',
              {'engagement': 'SYNTHETIC reader exercise', 'criteria': rows}, None))
# Prepare every interpretation before creating a destination.
prepared = [(name, engine.compose(payload), fixture_blob)
            for name, payload, fixture_blob in cases]
out = Path(sys.argv[1])
out.mkdir(parents=False, exist_ok=False)
index = {'synthetic': True, 'engine_generation': known[source_blob],
         'engine_git_blob': source_blob, 'cases': []}
for name, result, fixture_blob in prepared:
    json_bytes = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode('utf-8')
    markdown_bytes = engine.render_markdown(result).encode('utf-8')
    for suffix, data in (('.json', json_bytes), ('.md', markdown_bytes)):
        with (out / (name + suffix)).open('xb') as f:
            f.write(data)
    index['cases'].append({'case': name, 'fixture_git_blob': fixture_blob,
        'report_sha256': hashlib.sha256(json_bytes).hexdigest(),
        'area_states': {a: s['composition_status']
                        for a, s in result['area_summaries'].items()}})
index_bytes = (json.dumps(index, indent=2, sort_keys=True) + '\n').encode('utf-8')
with (out / 'INDEX.json').open('xb') as f:
    f.write(index_bytes)
print(index_bytes.decode('utf-8'), end='')
PY
```

Open the five JSON reports alongside this guide. The three inherited fixtures should
show `critical_gap_present`, `insufficient_coverage`, and `mixed_practice`, respectively.
The added cases should show `unassessed` and `insufficient_coverage`. Check the named
gap list in the last report even though its area status matches the low-coverage case.
Original-engine Markdown lacks service rows; JSON retains them in both generations.

The first three input files are the actual checked-in fixtures, not the nonexistent
combined `synthetic_cases.json` filename mentioned in the older method inventory.
The additional exercises are fully defined in the command, not hidden University data.
For a repeat run, select another new directory. Under optimized Python use `python -O`
with the same command body; the index/report bytes should match within a source generation.

## Interpretation worksheet for an analyst or facilitator

For each case, write one sentence containing **observed pattern + coverage + confidence
+ named gap or unknown + service boundary**. Then write the next evidence question.
Keep the input evidence IDs and criterion IDs attached to that question. The model does
not decide whether evidence is current, representative, contradictory or sufficient;
those questions belong to evidence review before an assessed criterion is supplied.

When moving to a new source generation, retain the old report and its input, rerun
rather than edit the old receipt, and compare pre-existing semantic fields separately
from added metadata and Markdown presentation. New service identity fields cannot
recover a service group already overwritten by an older delimiter collision. Recompose
from the original input; do not guess the missing group from a saved summary.

## Validation and attribution

This guide's command was executed using both pinned source generations, normally and
under optimized Python, and its reported cells were checked against the actual JSON.
Within each source generation the five reports and index were byte-identical between
modes. Across generations, pre-existing JSON fields matched after removing only the
repair's explicit added service-identity metadata. An existing-directory attempt was
refused without changing its sentinel file. These are cloud-container executions,
not hosted-CI or University-assessment evidence.

The independent review additionally exercised 45 component methods in three modes,
the five-test UIOWA-110 consumer and actual rehearsal in both modes and generations,
24,025 synthetic identity pairs, and eleven coverage boundaries. Those finite checks
do not prove every possible input correct. Source-review and runtime-integration states
remain separate from this document's publication.

Original engine, method, fixtures and ordinal-composition credit: **Anchor-ZZ**.
Integrity repair and original compatibility work: **ZZ-LODESTONE-47**.
Independent execution and this analyst guide: **ZZ-LODESTONE-47R8 / GPT-6 Astra Pro**.
Operation: `uiowa022-reader-lodestone47r8-20260919`.
All institutional assessment conclusions remain unmade by this synthetic rehearsal.
