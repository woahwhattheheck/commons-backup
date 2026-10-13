# Source-control practice assessment

UIOWA-043 provides a read-only local Git history inventory, an editable six-practice
worksheet, and two exercised fictional workflows. These are assessment aids,
not University findings, a maturity rating, or a mandated branching policy.
Python 3.10+ and Git are the only dependencies. No network access is requested.

## Use a real repository

From the Commons root, choose a **new** output directory:

```sh
python3 revenue/uiowa_rfq_18649_source_control/assess.py /path/to/repository \
  --ref main --limit 500 --out /tmp/source-control-assessment
```

The command resolves the ref to an exact commit before reading it and writes
`history.json` plus `worksheet.csv`. It reads only first-parent history, records
whether the requested limit was exceeded and whether the repository is shallow,
and disables lazy object fetching. Missing objects produce an error, not an
implicit download. Existing output directories are never overwritten. Failures
print a diagnostic and exit 2; successful exports exit 0.

The inventory reports commit identities, parents, timestamps, merge counts and
reference-like text in commit subjects. It does not export contributor identities.
Commit subjects can still contain sensitive information; keep the worksheet in
the assessment's agreed evidence destination. Edit the CSV to record the actual
context and observations. All six assessments begin `UNASSESSED`.

A merge count is not integration frequency: fast-forward, squash and rebase
workflows leave different histories. Deleted branches, reviews and deployment
results are outside this local history view. Git timestamps are author-controlled
records, not measured effort. Reference mentions do not establish that the
referenced requirement exists or was met. A shallow or bounded result never
claims to cover the complete history.

## Exercise the comparison

```sh
python3 revenue/uiowa_rfq_18649_source_control/exercise.py \
  --out /tmp/source-control-workflows
```

This creates two disposable local repositories under the new directory. It
performs real commits, a deliberate same-line conflict and its resolution, a
revert, a release tag and reintegration. No existing repository is modified.
Commit dates use a declared fictional timeline so the examples can be inspected
without suggesting measured delivery speed. Each workflow exports the same
history/worksheet format plus exact command arguments, output and exit codes.
The script checks that the conflict actually occurred, both parents were retained,
and the recovered content is the intended content before reporting success.

The checked-in `examples/` files are outputs of this runnable demonstration,
not customer evidence. The disposable repositories are intentionally not stored
in Commons. Re-run the command to examine them with ordinary Git commands.

| Practice | Short-lived branch demonstration | Release branch demonstration | Additional assessment evidence |
| --- | --- | --- | --- |
| Repository ownership | One fictional operator can commit and integrate | The same fictional operator can release and reintegrate | Accountable owner, backup operator, actual administrative continuity |
| Branching | One change branch joins continuing main | Release stabilization proceeds alongside next-release work | Release obligations, concurrent versions, actual branch lifetimes |
| Integration frequency | One explicit merge after main changes | A release fix is reintegrated into main | Representative observation window and agreed integration definition |
| Conflict handling | Real same-line conflict resolved into a two-parent merge | Disjoint changes merge without conflict | Intended behavior and who can decide a real conflict |
| Traceability | SC-101–SC-105 labels connect fictional changes | SC-201–SC-205 labels connect release decisions | Reachable requirements, reviews and deployed artifact references |
| Recoverability | Revert restores the prior service content | Tagged release content is recovered into a separate file | Independent offsite restore, recovery objectives and ref comparison |

**Unresolved evidence gap:** neither example demonstrates recovery after loss of
the original repository or loss of the administrator. A local revert or tag read
does not fill that gap. The generated reports retain it explicitly.

## Improvement options and adoption conditions

The worksheet contains options with transparent initial effort assumptions:
ownership mapping (2–4 staff hours), branch-context comparison (3–6), integration
definition (2–3), conflict exercise (2–4), traceability convention (2–5), and an
independent restore exercise (4–8). These are planning assumptions for one small
team and one repository, not estimates derived from Git history or a quote.
They exclude organization-wide migration, access provisioning, backup storage
cost and ongoing maintenance. Replace them with team estimates before planning.

A short-lived branch pattern can suit frequent integration when independent
changes can be released together. A release branch can suit overlapping supported
versions when a team can sustain reintegration work. Both need clear ownership,
traceability and recovery. Select improvements against actual constraints; the
demonstration does not rank one model above the other.
