# Review several workflow histories together

`portfolio.py` runs the existing `lifecycle.analyze()` on each selected history
and turns the results into a cross-workflow inventory and investigation queue.
It does not replace the single-workflow analyzer, change its schema, call a model,
or take any action against a live system. Python 3.10+; standard library only.

## Run

From `revenue/uiowa_rfq_18649_ai_lifecycle/`:

```sh
python portfolio.py /path/to/histories --output-dir /path/to/new-review
```

The new output directory contains:

- `portfolio.json`: input coverage, every included workflow's complete original
  analysis, recorded leaf branches, latest leaf-run IDs and the combined queue.
- `overview.md`: workflow inventory, investigation queue and input diagnostics.
- `investigation_queue.csv`: source, workflow, group, provenance, record reference,
  recorded owner, evidence gap and suggested next action.
- `comparisons.csv`: all historical comparisons, keeping each metric's baseline,
  candidate, delta, paired/expected denominator, exclusions and interpretation status.

The destination must be new. Put it outside the input directory, especially when
using `--recursive`, so a later run does not interpret its own reports as histories.
Output files are not an atomic filesystem transaction: an I/O failure can leave
an incomplete new directory and is reported on stderr with exit code 2.

Explicit file selection, streaming and nested directories also work:

```sh
python portfolio.py ess.json ris.json --format markdown
python portfolio.py /path/to/histories --recursive --format comparisons-csv
python -m revenue.uiowa_rfq_18649_ai_lifecycle.portfolio /path/to/histories
```

The last command runs from the repository root. No directory is scanned unless
it was explicitly selected. Directory discovery uses `*.json`; recursion is
opt-in. A file argument may have any extension. Overlapping path arguments are
normalized so the same resolved path is processed once.

## Input problems stay visible

Exit code **0** means all selected inputs were included. Missing observations,
unresolved incidents and incomparable comparisons are valid analysis results,
not CLI failures or deployment decisions.

Exit code **2** means an input/discovery/output error occurred. For input errors,
the tool still emits the valid workflows and lists every excluded input in the
report, queue and stderr. `complete: false` is conspicuous in the JSON and overview.
Malformed JSON uses the existing strict duplicate-key/nonfinite-number loader;
the existing schema, references, chronology and evidence semantics still apply.
An empty directory is an input error, not a successful empty assessment.

Two distinct files declaring the same `workflow_id` are both excluded, even when
their bytes match or their groups differ. Their paths remain in `inputs` with
`duplicate_workflow` and `conflicting_sources`. The tool never silently chooses a
newest-looking snapshot or combines conflicting histories. Select the intended
snapshot and run again. Input files are never modified.

## Read the queue without inventing a current deployment

A recorded **leaf version** has no child in that history. All leaves are shown;
none is inferred to be the deployed or authoritative branch. The queue includes
unresolved incidents from any version, evidence gaps and absent runs on leaves,
missing/error observations in each leaf's latest finished run, leaf-candidate
comparison gaps or adverse descriptive deltas, and non-exact recorded leaf replays.
Latest-run timestamp ties are all retained. Incidents whose resolution has
recorded evidence are not reopened merely because an older run was unsuccessful.
Historical comparisons and replay records remain in the full report and comparison
register rather than all becoming new work orders.

A missing owner stays `null` in JSON, blank in CSV and `UNKNOWN` in Markdown.
Synthetic and caller-supplied observations keep their original labels on each
workflow and each CSV row. Inventory totals count records, not performance,
production incidents, labor savings or revenue. Metrics are never averaged across
workflows or ranked against each other. `complete` describes selected-file
coverage only, not a complete organizational inventory or evidence sufficiency.
