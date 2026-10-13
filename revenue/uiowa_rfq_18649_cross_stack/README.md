# UIOWA-026 — compare outcomes, not technology labels

A runnable, standard-library cross-stack calibration kit for the Michael live demo.
**All bundled cases are fictional preparation assets, not University findings.**
The engine evaluates supplied records; it does not authenticate source documents,
award a maturity rating, perform a compliance audit, or approve an engagement.

## Run the complete rehearsal

From this directory, with Python 3.10 or newer:

```sh
python examples.py --out /tmp/uiowa026-rehearsal
python compare.py /tmp/uiowa026-rehearsal/synthetic.json --format json
python compare.py /tmp/uiowa026-rehearsal/synthetic.json --format csv
python compare.py /tmp/uiowa026-rehearsal/synthetic.json --format markdown
python -m unittest -v test_compare.py
python -O -m unittest -v test_compare.py
```

Use a **new** output directory. The generator refuses an existing directory rather
than overwrite evidence. `compare.py` reads one JSON file and writes to stdout;
malformed input returns exit code 2 with diagnostics on stderr and no report on stdout.
No network calls, model calls, credentials, environment setup or installed packages
are required. The test suite uses temporary synthetic files and local subprocesses.

Package-mode commands from repository root also work:

```sh
python -m revenue.uiowa_rfq_18649_cross_stack.examples --out /tmp/uiowa026-package
python -m unittest discover -s revenue/uiowa_rfq_18649_cross_stack -t . -v
```

The generator produces six portable artifacts: `synthetic.json`, its actual
`synthetic-evidence.md` source passages, `comparison.json`, `comparison.csv`,
`comparison.md`, and an editable 48-row `context-worksheet.csv`. Source headings
match every fixture locator. Generated artifacts carry the synthetic label.

## What to show

Case 01 compares four manually reviewed changes with forty changes released
through automation: both supplied samples meet the same substantive-review
criterion. Automation adds no points. Case 02 shares one lifecycle exercise across
two named consumers and reports **one provenance cluster**, not two independent
replications. Case 03 preserves both local recovery successes while declining a
direct criticality/scale comparison. Case 04 distinguishes an AI policy from an
observed AI-checking exercise. Case 05 permits a cadence-adjusted comparison only
with its recorded rationale and current source reference. Case 12 allows a bounded
qualitative comparison but refuses a July-versus-August rate delta.

Read [the method and paired examples](26-cross-stack-calibration.md),
[the exact input contract](DATA_CONTRACT.md), and [execution receipts](VALIDATION.md).
`example-results.csv` is an actual generated rehearsal result, not a manually
asserted expected score. `test_compare.py` also checks hand-worked expectations.

## Integration boundary

This is an isolated **pairwise calibration** component, not a replacement for the
workbench, evidence compiler, rating model, confidence model, or synthesis engine.
Call `compare.analyze(packet)` to receive a detached JSON-compatible report.
The complete input records, source IDs, locators, retained dissent, context decisions
and original denominators remain in the JSON output. Use that JSON for integration;
the CSV is a human-readable summary and intentionally apostrophe-neutralizes text
that spreadsheet software might interpret as formulas. Do not round-trip the CSV
back into evidence. Worksheet edits are analyst preparation: transfer reviewed
values into the versioned JSON contract and rerun; no worksheet-import feature is
claimed.

The input digest binds canonical JSON metadata (including array order), **not the
bytes of referenced source documents**. `SUPPORTED_MEETS` means the analyst supplied
a meets claim plus current observation metadata; source sufficiency, authenticity,
sampling design and correctness of the claim still require professional review.
Rate outputs are exact descriptive fractions, not a significance test, population
estimate, causal attribution, or consistency proof of the supplied outcome claim.

Real University records belong only in an authorized private evidence environment;
do not commit them to this public repository. No live customer-system operation,
customer communication, pricing change, appointment, release gate or procurement
recommendation is implemented by this kit.

Operation: `uiowa-026-alkali26f-20260919`; builder: ZZ-ALKALI-26F / GPT-6 Astra Pro.
Work record: https://github.com/woahwhattheheck/commons/issues/16138
