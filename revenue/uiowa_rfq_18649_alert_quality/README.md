# Alert usefulness and response readiness

Offline UIOWA-066 preparation kit: analyze a fictional notification history,
inspect each episode's response evidence, and record practical improvements.
The analyzer uses Python 3.10+ and the standard library. It makes no provider
calls, changes no monitoring configuration, and accepts only `SYNTHETIC` input.
These examples are not University findings or a census of service reliability.

## Run the analysis

From the repository root:

```sh
python3 revenue/uiowa_rfq_18649_alert_quality/alert_quality.py \
  revenue/uiowa_rfq_18649_alert_quality/synthetic.json \
  --out /tmp/alert-quality-review
```

The command writes `report.json`, `report.md`, and four CSV files: episodes,
notifications, recommendations, and evidence. Use a separate output directory:
the exporter replaces those six named files. JSON retains lossless values;
CSV uses `UNKNOWN` for missing values and escapes spreadsheet formula prefixes.
Invalid structure, duplicate IDs, contradictory linkage, missing evidence
references, and invalid chronology exit with code 2.

[Read the generated report](example-output/report.md) or open the
[editable workbook](alert-quality-workbook.xlsx). The workbook has five sheets:
Overview, Actions, Episodes, Evidence, and Interview. Amber cells accept assigned
roles, review decisions, next steps, observations, and evidence locators. Source
observations and computed results are a snapshot of the analyzer output. Editing
them in Excel does not rerun the Python analysis. Keep annotated copies separate
from regenerated exports.

The workbook can be regenerated in a Node environment providing
`@oai/artifact-tool` (the workbook builder dependency only):

```sh
node revenue/uiowa_rfq_18649_alert_quality/workbook.mjs \
  /tmp/alert-quality-review/report.json /tmp/alert-quality-review/workbook.xlsx
```

An optional third argument writes visual previews. The Python analyzer and CSV
workflow do not require Node or that package. The checked-in XLSX opens directly
in ordinary spreadsheet applications.

## Worked interpretation

The existing example contains 12 notification records, six episodes, and four
confirmed duplicate deliveries. Five notifications are reviewed redundant, five
useful, and two unreviewed: the redundant share is **5 / 10 = 50% of reviewed
notifications**, not 50% of all notifications. A redundant notification need
not meet the stricter same-episode, same-rule, same-route duplicate definition.

The useful-response median is **4 minutes, completed-only n=3**. It uses
impacting episodes with an observed useful action and complete notification
coverage. It excludes missing, censored, and partial-history responses.

- `ESS-101` has two evidenced repeats plus useful escalation. Reviewing repeat
  policy must preserve the escalation route.
- `ESS-102` is a different next-day incident despite matching rule identity.
  It remains a separate episode.
- `IAM-301` has acknowledgement but no useful action observed by window end.
  Its ownership is explicitly unowned, and the retained runbook was unhelpful.
- `IAM-302` records useful action before button acknowledgement. That ordering
  is valid; acknowledgement is not the definition of useful response.
- `RIS-201` has partial exports. Acknowledgement is present, useful response
  remains unknown, and elapsed time from the first observed notification is only
  a lower bound when earlier notifications may be missing.
- `RIS-fragment` stays unlinked with unknown ownership. Fingerprint similarity
  cannot supply missing incident linkage.

The generated register has 13 recommendations. Each retains its episode,
evidence IDs, proposed change, and outcome to measure. It proposes no monetary
savings, individual score, fleet performance rating, or automatic paging change.

## Input and interchange

`synthetic.json` is the complete editable input example. Its strict v1 contract
contains `schema`, `evidence_class`, a half-open UTC-offset-aware `window`,
per-service `coverage`, retained `evidence`, `episodes`, and `notifications`.
Each record type requires exactly the fields demonstrated in the example.

Keep notification IDs unique. A repeated export row is rejected rather than
silently counted twice. A distinct delivery known to be a duplicate carries its
own ID, `kind: repeat`, `value: redundant`, review evidence, and `duplicate_of`
pointing to an earlier notification in the same episode, rule, and route.

Episodes use explicit incident/linkage records. Multiple notifications without
an incident ticket still require retained correlation evidence. A runbook can
be useful, unhelpful, untested, missing, or unknown. A URL alone does not make it
useful. Coverage distinguishes complete, partial, and unknown notification and
response exports. Missing evidence stays unknown rather than becoming a zero.

The output contract is `uiowa.alert-quality-report/v1`. Consumers should retain
`input_sha256`, window and coverage, original episode/notification/evidence IDs,
response state, latency basis, and completed-only denominator. The input digest
uses canonical JSON with each record array sorted by ID. It identifies these
example bytes and does not authenticate an external evidence provider.

## Source recovery and execution

This completes the earlier [work record #16123](https://github.com/woahwhattheheck/commons/issues/16123).
COPPERFINCH-83 published the analyzer and example at
[`94a551af41d188e30d90d24f8372b98ac5a848d0`](https://github.com/woahwhattheheck/commons/commit/94a551af41d188e30d90d24f8372b98ac5a848d0)
on an unmerged branch. Both files are preserved byte-for-byte here:

| File | Original Git blob |
|---|---|
| `alert_quality.py` | `94e842752eb7458bf79321571d7c43ad571306f2` |
| `synthetic.json` | `889a596b4282e4fbe6a09a518f72cb17e32efe23` |

This integration adds the operator guide, actual generated exports, editable
workbook, and its builder. The real CLI was run on that published example and
returned the counts above with exit 0. The workbook was generated from the same
report, its five sheets were rendered and inspected, and its key values match
the report. No original or new test suite was run. No live telemetry was collected.
