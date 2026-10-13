# UIOWA-118 — Inline help snippets

Copyable documentary records, not a runtime installation. `expanded_ref` names the
glossary paragraph and example to show on demand. Resolve relative references from this
package directory, preserve `source_ids`, and retain status/units beside the actual value.
Unknown term IDs have no implied fallback or score. [Source register and reuse](README.md).

```json
{
  "schema": "uiowa.explanation-help/v1",
  "status": "DOCUMENTARY_COPY_NOT_INSTALLED",
  "source_register": "README.md",
  "examples": "FICTIONAL_NOT_UNIVERSITY_FINDINGS",
  "records": [
    {
      "id": "ess",
      "label": "ESS",
      "short_text": "Enterprise Student Systems: one of the three assessment groups.",
      "expanded_ref": "GLOSSARY.md#ess",
      "source_ids": [
        "S01",
        "S03"
      ]
    },
    {
      "id": "ris",
      "label": "RIS",
      "short_text": "Research Information Systems: an assessment group, not a single application.",
      "expanded_ref": "GLOSSARY.md#ris",
      "source_ids": [
        "S01",
        "S05"
      ]
    },
    {
      "id": "iam",
      "label": "IAM",
      "short_text": "Identity and Access Management: identity and access scope in the assessment.",
      "expanded_ref": "GLOSSARY.md#iam",
      "source_ids": [
        "S01",
        "S06"
      ]
    },
    {
      "id": "assessment-cell",
      "label": "Assessment cell",
      "short_text": "One group and one assessment dimension, with its own evidence and status.",
      "expanded_ref": "GLOSSARY.md#assessment-cell",
      "source_ids": [
        "S02",
        "S03",
        "S04"
      ]
    },
    {
      "id": "maturity",
      "label": "Maturity",
      "short_text": "A source-supplied practice assessment; not a value invented by this help layer.",
      "expanded_ref": "GLOSSARY.md#maturity",
      "source_ids": [
        "S01",
        "S02",
        "S04"
      ]
    },
    {
      "id": "confidence",
      "label": "Confidence",
      "short_text": "Declared evidential confidence, separate from maturity and business importance.",
      "expanded_ref": "GLOSSARY.md#confidence",
      "source_ids": [
        "S02",
        "S04"
      ]
    },
    {
      "id": "basis-points",
      "label": "Basis points",
      "short_text": "100 basis points equal one percentage point.",
      "expanded_ref": "GLOSSARY.md#basis-points",
      "source_ids": [
        "S04"
      ]
    },
    {
      "id": "evidence-authority",
      "label": "Evidence authority",
      "short_text": "Independently retained source authority, not merely a matching checksum.",
      "expanded_ref": "GLOSSARY.md#evidence-authority",
      "source_ids": [
        "S01",
        "S04"
      ]
    },
    {
      "id": "public-inspection",
      "label": "Public inspection",
      "short_text": "A non-authorizing view of evidence consistency.",
      "expanded_ref": "GLOSSARY.md#public-inspection",
      "source_ids": [
        "S01",
        "S02",
        "S08"
      ]
    },
    {
      "id": "historical-replay",
      "label": "Historical replay",
      "short_text": "A reproducible view at a stated past time, not current authority.",
      "expanded_ref": "GLOSSARY.md#historical-replay",
      "source_ids": [
        "S01",
        "S02"
      ]
    },
    {
      "id": "missing-evidence",
      "label": "Missing evidence",
      "short_text": "No rooted source record for this cell; not proof the practice is absent.",
      "expanded_ref": "GLOSSARY.md#missing-evidence",
      "source_ids": [
        "S01",
        "S02"
      ]
    },
    {
      "id": "stale-evidence",
      "label": "Stale evidence",
      "short_text": "Evidence exceeds this component's stated age limit at its evaluation time.",
      "expanded_ref": "GLOSSARY.md#stale-evidence",
      "source_ids": [
        "S01",
        "S02",
        "S03"
      ]
    },
    {
      "id": "conflicting-evidence",
      "label": "Conflicting evidence",
      "short_text": "Rooted source maturity values disagree; both readings need reconciliation.",
      "expanded_ref": "GLOSSARY.md#conflicting-evidence",
      "source_ids": [
        "S02"
      ]
    },
    {
      "id": "source-locator",
      "label": "Source locator",
      "short_text": "The place a reader can inspect the supporting material.",
      "expanded_ref": "GLOSSARY.md#source-locator",
      "source_ids": [
        "S01",
        "S04",
        "S07"
      ]
    },
    {
      "id": "observation-window",
      "label": "Observation window",
      "short_text": "The bounded period and service population used for a measurement.",
      "expanded_ref": "GLOSSARY.md#observation-window",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "lead-time",
      "label": "Change lead time",
      "short_text": "Elapsed time from the agreed change timestamp to production deployment.",
      "expanded_ref": "GLOSSARY.md#lead-time",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "deployment-frequency",
      "label": "Deployment frequency",
      "short_text": "Production deployment count over an explicit time window.",
      "expanded_ref": "GLOSSARY.md#deployment-frequency",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "change-fail-rate",
      "label": "Change fail rate",
      "short_text": "Failed deployments divided by deployments with known intervention outcomes.",
      "expanded_ref": "GLOSSARY.md#change-fail-rate",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "deployment-rework",
      "label": "Deployment rework rate",
      "short_text": "The share of known-outcome deployments that were unplanned production rework.",
      "expanded_ref": "GLOSSARY.md#deployment-rework",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "coverage",
      "label": "Metric coverage",
      "short_text": "How many eligible inputs actually contributed to this metric.",
      "expanded_ref": "GLOSSARY.md#coverage",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "failed-deployment-recovery",
      "label": "Failed deployment recovery time",
      "short_text": "Elapsed recovery time for qualifying failed production deployments.",
      "expanded_ref": "GLOSSARY.md#failed-deployment-recovery",
      "source_ids": [
        "S05"
      ]
    },
    {
      "id": "backup-restoration",
      "label": "Backup versus restoration",
      "short_text": "A completed backup job does not demonstrate a usable restored service.",
      "expanded_ref": "GLOSSARY.md#backup-restoration",
      "source_ids": [
        "S06"
      ]
    },
    {
      "id": "rpo",
      "label": "Recovery point objective and observed recovery point",
      "short_text": "RPO concerns recoverable data age, not how long restoration takes.",
      "expanded_ref": "GLOSSARY.md#rpo",
      "source_ids": [
        "S06"
      ]
    },
    {
      "id": "rto",
      "label": "Recovery time objective and observed recovery time",
      "short_text": "RTO concerns elapsed time until the required business function is usable.",
      "expanded_ref": "GLOSSARY.md#rto",
      "source_ids": [
        "S06"
      ]
    },
    {
      "id": "one-time-effort",
      "label": "One-time effort",
      "short_text": "Person-hours needed once for implementation, process change and training.",
      "expanded_ref": "GLOSSARY.md#one-time-effort",
      "source_ids": [
        "S07"
      ]
    },
    {
      "id": "recurring-effort",
      "label": "Recurring effort",
      "short_text": "Maintenance person-hours per month, separate from one-time work.",
      "expanded_ref": "GLOSSARY.md#recurring-effort",
      "source_ids": [
        "S07"
      ]
    },
    {
      "id": "scenario-range",
      "label": "Planning scenario range",
      "short_text": "Conditional low, central and high assumptions; not a confidence interval.",
      "expanded_ref": "GLOSSARY.md#scenario-range",
      "source_ids": [
        "S07"
      ]
    },
    {
      "id": "unknown-total",
      "label": "Known subtotal versus complete total",
      "short_text": "A known subtotal remains incomplete when an estimate or scope is missing.",
      "expanded_ref": "GLOSSARY.md#unknown-total",
      "source_ids": [
        "S07"
      ]
    },
    {
      "id": "specialist-capacity",
      "label": "Specialist capacity",
      "short_text": "Net available hours for the required role and period, not interchangeable staffing.",
      "expanded_ref": "GLOSSARY.md#specialist-capacity",
      "source_ids": [
        "S07"
      ]
    }
  ]
}
```
