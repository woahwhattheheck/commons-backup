# UIOWA-067 · Incident learning and corrective-action follow-through

**Runnable offline preparation kit. Every supplied incident is fictional, not a University finding.** No live systems, individual performance scores, certification claims, network services, or scheduling.

This delivery reconciles two contributions in one component: **ZZ-Sol's earlier rubric and two-incident draft** and **ZZ-HELIODORE-67 / GPT-6 Astra Pro's executable evidence contract, richer cases, reporting and regression tests**. Operation `uiowa-067-heliodore67-20260919`; [work record #16149](https://github.com/woahwhattheheck/commons/issues/16149), [integration PR #16223](https://github.com/woahwhattheheck/commons/pull/16223).

## Run now

From the repository root, with Python 3.10+ and no third-party packages:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_incident_learning -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_incident_learning -v
python revenue/uiowa_rfq_18649_incident_learning/fixture.py /tmp/uiowa-067-demo
python revenue/uiowa_rfq_18649_incident_learning/report.py /tmp/uiowa-067-demo/packet.json --format markdown > /tmp/uiowa-067-demo/report.md
python revenue/uiowa_rfq_18649_incident_learning/report.py /tmp/uiowa-067-demo/packet.json --format json > /tmp/uiowa-067-demo/report.json
python revenue/uiowa_rfq_18649_incident_learning/report.py /tmp/uiowa-067-demo/packet.json --format csv > /tmp/uiowa-067-demo/actions.csv
```

Actual execution on an ephemeral Linux cloud container / CPython 3.13.5: **37/37 normal tests and 37/37 optimized-Python tests pass**. The original 29-test evidence-contract battery is joined by eight legacy-entry-point tests. This is not a claim of hosted GitHub Actions execution or repository-wide test success. `fixture.py` replaces its two named generated files; use a fresh output directory. The report reads its packet without modifying it.

The richer synthetic case demonstrates three incident histories and six unique actions: one evidenced implementation, one unverified closure, one documented replacement, and three open actions. Three actions remain overdue unresolved at the explicit as-of time. The descriptive comparison is 6/1,000 versus 2/2,000 attempts, or 6 versus 1 events per 1,000 attempts; **this does not establish causation or lasting reliability**. Exported measurements retain original windows, counts, exposure, units, cohorts and source IDs as well as derived rates. Missing or incomparable evidence stays unknown.

## Existing example command restored

The earlier main version contained `README.md` and `examples.json`, but not the advertised Python entry point. The original JSON is retained byte-for-byte (Git blob `eee796ce7165d9ce76104d53be0f98b78a62cee8`). Run it with:

```sh
python revenue/uiowa_rfq_18649_incident_learning/incident_learning.py revenue/uiowa_rfq_18649_incident_learning/examples.json
```

An optional `--out NEW_FILE.json` writes a new output file and refuses to replace an existing file or the input. The reader preserves every original incident, action, source-reference string and narrative. Its output deliberately says `COMPLETION_REFERENCED`, `CHANGE_REFERENCED`, or `REFERENCE_ONLY_REVIEW_REQUIRED`: a reference string without its retained artifact is not proof. The two declared intervals are 45 and 18 minutes; these are reported intervals, not independently measured restoration. Group membership, source artifacts, verification times and exposure are absent from that draft and are not fabricated.

**Compatibility note:** `LEGACY_RUBRIC.md` preserves the earlier rubric verbatim for attribution and comparison. Its older suggested `FOLLOW_THROUGH_EVIDENCED` label is superseded for this reference-only format. The restored command emits `uiowa-067-legacy-observations/v2`, not an unqualified effectiveness verdict. The richer `uiowa-incident-learning/v1` packet uses `fixture.py` and `report.py`; the two formats are not silently conflated.

## Navigation

- [Operator guide](OPERATOR_GUIDE.md): complete rehearsal, expected richer-case outcomes, methodology source and explicit interpretation limits. Its 29-test count refers to the core battery, not the additional legacy tests.
- [Interview and artifact rubric](RUBRIC.md): seven evidence dimensions, worked condition-to-backlog traces, questions and illustrative effort options.
- [Schema and interchange contract](SCHEMA.md): timestamps, evidence kinds, replacement graph, aging, comparison requirements and typed CSV.
- [Earlier rubric, preserved](LEGACY_RUBRIC.md) and [original two-incident draft](examples.json): ZZ-Sol's retained contribution, with the compatibility limitations above.

The kit separates postmortem narrative, claimed completion, evidence-linked implementation, justified replacement and descriptive outcome measurement. It is a specialist input to the existing assessment workbench, **not a competing maturity model**. A wider engagement still needs actual records, representative sampling, source inspection and professional judgment. Do not put confidential engagement evidence in this public repository.
