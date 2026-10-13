# UIOWA-064 — software delivery metrics data dictionary

Status: **synthetic assessment instrument / not a University finding**  
Owner: ZZ-Semaphore / GPT-5.6 Sol  
Official metric reference: https://dora.dev/guides/dora-metrics/  
Reference checked: 2026-09-19; DORA guide last updated 2026-01-05.

This dictionary supports the offline calculator in `calculator.py`. The calculator operationalizes DORA's current five software-delivery metrics for a bounded assessment dataset. It is deliberately service-scoped and does not emit peer percentiles, maturity scores, compliance verdicts, or individual productivity ratings.

## Current DORA metric set

DORA's current guide groups five metrics into two factors:

| Factor | Metric | Source concept used by this calculator |
|---|---|---|
| Throughput | Change lead time | Elapsed time from a change being committed to version control until production deployment. |
| Throughput | Deployment frequency | Number of production deployments in a period, or interval between deployments. |
| Throughput | Failed deployment recovery time | Elapsed time to recover from a production deployment failure requiring immediate intervention. |
| Instability | Change fail rate | Ratio of deployments that require immediate intervention after deployment. |
| Instability | Deployment rework rate | Ratio of deployments that are unplanned work caused by a production incident. |

The source definitions above are paraphrased from the official DORA guide. Aggregation details below are **TJLabs assessment-tool choices**, not claims that DORA mandates these exact event fields or summary statistics.

## CSV schema

| Field | Required | Type / format | Assessment meaning | Missing-data behavior |
|---|---|---|---|---|
| `deployment_id` | yes | non-empty string | Stable identifier for one production deployment event. | Row rejected if blank or duplicated. |
| `service` | yes | non-empty string | Application/service whose delivery performance is being measured. | Row rejected if blank. Multiple services require an explicit `--service` filter. |
| `commit_at` | for complete lead-time coverage | offset-aware ISO-8601 timestamp | Timestamp for the change/batch reference used to link committed work to this production deployment. | Blank row remains usable for other metrics; lead-time coverage becomes `PARTIAL`. |
| `deployed_at` | yes | offset-aware ISO-8601 timestamp | Production deployment timestamp. Also controls inclusion in the explicit observation window. | Row rejected if blank or malformed. |
| `intervention_required` | for complete change-fail coverage | `true`, `false`, or blank | Whether the deployment required immediate remedial intervention because the production deployment failed or impaired service. | Blank stays unknown; change-fail-rate coverage becomes `PARTIAL`. |
| `recovered_at` | when `intervention_required=true` | offset-aware ISO-8601 timestamp | Time service was recovered after a qualifying failed deployment. | Missing qualifying recovery time makes failed-deployment-recovery coverage `PARTIAL`; no time is imputed. |
| `unplanned_rework` | for complete rework-rate coverage | `true`, `false`, or blank | Whether this deployment was unplanned rework resulting from a production incident/user-facing defect. | Blank stays unknown; rework-rate coverage becomes `PARTIAL`. |
| `notes` | yes for this assessment fixture | free text | Trace note explaining event interpretation or provenance. | Blank rejected by review convention; calculator preserves but does not score notes. |

All accepted timestamps are normalized to UTC internally. The observation window is start-inclusive and end-exclusive.

## Change-to-deployment linkage assumption

Real delivery systems can contain many commits in one deployment, rebases, cherry-picks, release branches, or artifact promotion without a one-to-one commit/deployment relationship. This simple assessment fixture therefore treats `commit_at` as the agreed change/batch timestamp for the deployment being summarized.

Before using real engagement data, document the linkage rule, for example:

- earliest constituent commit in the deployed batch;
- merge-to-main timestamp for the deployed change set;
- release-candidate creation timestamp;
- another source-backed event consistently available across the service.

Do not compare lead times computed from different linkage rules as though they were the same measure.

## Failure and recovery assumption

`intervention_required=true` is reserved for a deployment whose production outcome required immediate remediation such as rollback or hotfix. Failed-deployment recovery time is computed only for those rows and only when `recovered_at` is known.

A generic infrastructure outage unrelated to a software deployment does not belong in this deployment-failure denominator merely because service recovery took time. This follows DORA's current narrowed recovery concept.

## Rework assumption

`unplanned_rework=true` means the deployment itself was unplanned work resulting from a production incident or user-facing production defect. Planned maintenance, an ordinary scheduled enhancement, or a planned defect fix should not be labeled rework solely because it changes existing code.

## Calculator aggregation choices

These are explicit implementation choices for transparent assessment use:

- **Change lead time:** median and arithmetic mean hours over deployments with known `commit_at`.
- **Deployment frequency:** deployment count in the declared window, deployments/day, deployments/week, and median interval between observed deployment timestamps.
- **Failed deployment recovery time:** median and arithmetic mean hours over qualifying failed deployments with known recovery timestamp.
- **Change fail rate:** qualifying failed deployments divided by deployments with known `intervention_required`.
- **Deployment rework rate:** unplanned-rework deployments divided by deployments with known `unplanned_rework`.

Every metric carries `eligible`, `used`, `missing`, and a status:

- `COMPLETE`: all eligible inputs for that metric are present.
- `PARTIAL`: at least one relevant input is unknown.
- `NOT_OBSERVED`: there was no qualifying event, such as no failed deployment in the selected window.

`NOT_OBSERVED` is not converted to zero recovery time. `PARTIAL` is not silently imputed.

## Scope rule

The official DORA guide advises applying the metrics in the context of one application or service and warns that disparate cross-application comparisons can mislead. Accordingly, the calculator refuses an unfiltered observation window containing multiple services.

ESS, RIS, and IAM results should therefore be computed per service/application first. Any later aggregation must preserve the different service contexts and measurement definitions rather than manufacturing a single institutional score.
