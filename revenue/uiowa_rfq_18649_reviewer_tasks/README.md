# UIOWA-097 — reviewer tasks and editable continuation

Read a finding's exact support, compare the supplied group states, explain an
unknown, revise one recommendation and see its roadmap impact. The task command
uses the existing source-bound discussion kit and canonical recommendation
register; it adds no assessment model or priority ranking.

The concrete usability gap was the transition from reading a portable report to
changing its underlying recommendation. A manual edit required locating the
register, keeping the source version straight, and refreshing the discussion,
editable tables and roadmap separately. `revise` performs that continuation in
one new directory while retaining the original bytes and a before/after record.

## Read the existing worked bundle

From the repository root with Python 3.10+:

```sh
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py tasks
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py show --card finding:F-001
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py compare
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py show --card cell:ESS:ai_readiness
```

The default is `uiowa_rfq_18649_discussion/examples`. For another exported draft,
place `--bundle PATH` **before** the subcommand. Every command first uses the
existing bundle verifier: source bindings, semantic report integrity, derived
cards and saved rendered views must agree before the tool reads or edits them.
The comparison table preserves the report's embedded evaluation time. It does
not infer which group is better or claim current evidence authority.

## Revise one recommendation

Create a local changes JSON file containing only the fields you intend to replace.
For the existing fictional `REC-SYN-03`, a worked edit is:

```json
{"owner_role":"Identity operations lead (fictional)","phase":"0-90"}
```

Save it as `/tmp/planning-change.json`. Copy the **Register source SHA-256** from
`tasks`. The command below uses the delivered original version's exact digest.
Omitting `--out` previews field changes, before/after roadmap items, effort
accounting and every remaining review item without writing anything.

```sh
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py revise \
  --recommendation REC-SYN-03 --changes /tmp/planning-change.json \
  --expected-sha256 9202cec39fb8200eeca72c0114ccfd64c9a548ada5deb24d29dbf113c9d342eb
```

Add `--out /tmp/revised-discussion` to write the new draft. The destination must not
exist. The original bundle is read-only. The new directory contains:

- Refreshed source-bound `discussion.json`, `discussion.md`, `discussion.html`
  and complete input snapshots, usable by the existing discussion commands.
- `revision.json` with exact source/revised register hashes, changed fields,
  unchanged finding/scope references, before/after roadmap item and remaining
  uncertainties. This records a proposal, not approval or signature.
- `source-register.json`, preserving the previous register's exact bytes.
- `register/`, exported by the canonical register component: editable CSV,
  metadata, complete register, report, roadmap and readable report.
- `reviewer-tasks.md`, which prints the new source digest for the next operator.

Continue with:

```sh
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py \
  --bundle /tmp/revised-discussion show --card recommendation:REC-SYN-03
python revenue/uiowa_rfq_18649_reviewer_tasks/review.py \
  --bundle /tmp/revised-discussion tasks
```

Nested fields such as `effort` are complete replacements, not partial JSON merges;
the canonical register validator checks their full structure. Recommendation ID,
finding links and scope cannot be patched through this command. Use the canonical
register editor for identity or evidence remapping. All other native recommendation
fields are supported; unknown field names, an empty/no-op patch, stale expected
digest, malformed register values and existing output paths exit 2.

An edited owner or proposed phase does not resolve effort, maturity evidence,
capacity, same-phase dependency order or approval. Those remain visible. The
register's roadmap is a projection of proposed phase buckets, not an executable
schedule. This command does not impose new planning semantics or call live systems.

## Actual five-task continuation

Executed against the existing published synthetic discussion inputs:

| Task | Actual result |
| --- | --- |
| Locate finding support | `finding:F-001` returned its exact statement/limitation and E-001/E-002/E-003 observations with physical CSV line locations. |
| Compare groups | Twelve report cells appeared with native statuses and reasons; missing ESS AI evidence, conflicting RIS security evidence and stale IAM deployment evidence remained visible. |
| Explain an unknown | `cell:ESS:ai_readiness` retained `HOLD_MISSING_EVIDENCE`, `NO_ROOTED_SOURCE_RECORD`, null maturity/confidence and no fabricated sources. |
| Revise a recommendation | Preview and publication changed only REC-SYN-03's null owner and phase to the explicitly fictional role and `0-90`. Finding F-SYN-04, IAM/security scope and prerequisite REC-SYN-01 were preserved. |
| Locate roadmap impact | Canonical `register/roadmap.json` showed the new owner/phase and unchanged prerequisite. Effort and maturity step remained unknown; known effort stayed 6–12 person-days and the complete total stayed unknown. |

All five product commands returned exit 0, and the existing discussion verifier
accepted the revised output. The source file retained digest
`9202cec39fb8200eeca72c0114ccfd64c9a548ada5deb24d29dbf113c9d342eb`; the revised
register was `49eee2c0696e1308b1b915523d8428792bd7f5b0edce8ae65e6e20d79653de66`.
This is an executed command-line workflow using existing synthetic records, not a
participant study, browser exercise, new test suite or new evidence corpus.

## Limits and lineage

The original `swarm-zz/rhenium97e-reviewer-tasks` branch contained no task
implementation. This completes the operator continuation requested by work order
#16143 using the delivered discussion, local-search, workshare and recommendation
components. Their authorship and contracts remain intact. No workbench or sibling
component source is modified.

Input limits follow the discussion kit (2 MiB per source/derived JSON). Snapshot
digests are checked again before writing; source paths are copied before rebuild.
Output publication is exclusive but not a transactional directory swap. Use an
operator-controlled workspace; a failed write preserves partial output for
inspection. The receipt records integrity and lineage, not independent authenticity.

No real University findings, private evidence, outreach, interviews, schedules,
procurement, staffing commitments, invoices, payments or revenue are created.
