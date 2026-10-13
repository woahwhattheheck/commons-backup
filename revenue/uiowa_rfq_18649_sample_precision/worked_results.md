# Denominators, unknown outcomes and conditional precision

SYNTHETIC EXERCISE — fictional observations, not University findings.

Each row is a separate collection. Collection bounds are not statistical intervals.

| Sample | Success / failure / unknown | Complete-case rate | Full-collection bounds | Wilson interval |
|---|---|---|---|---|
| MODEL-3-OF-3: Three successful fictional independent trials | 3 / 0 / 0 | 3/3 (100.0000%) | 1 to 1 (100.0000%–100.0000%); n=3 | 43.8503%–100.0000% at 95%, model-conditional |
| MODEL-300-OF-300: Three hundred successful fictional independent trials | 300 / 0 / 0 | 300/300 (100.0000%) | 1 to 1 (100.0000%–100.0000%); n=300 | 98.7357%–100.0000% at 95%, model-conditional |
| MODEL-0-OF-3: No successes among three fictional trials | 0 / 3 / 0 | 0/3 (0.0000%) | 0 to 0 (0.0000%–0.0000%); n=3 | 0.0000%–56.1497% at 95%, model-conditional |
| EMPTY-WINDOW: No eligible events in the stated fictional window | 0 / 0 / 0 | UNKNOWN (no observed outcomes) | UNDEFINED (eligible = 0) | NOT COMPUTED |
| ALL-OUTCOMES-UNKNOWN: Ten fictional events with no observed outcomes | 0 / 0 / 10 | UNKNOWN (no observed outcomes) | 0 to 1 (0.0000%–100.0000%); n=10 | NOT COMPUTED |
| THEME-1-TIMELY-UPDATES: Shared incident service: next-update timing | 17 / 1 / 0 | 17/18 (94.4444%) | 17/18 to 17/18 (94.4444%–94.4444%); n=18 | NOT COMPUTED |
| THEME-2-REVIEW-OCCURRENCE: Normal changes: whether pre-deployment review occurred | 14 / 0 / 1 | 14/14 (100.0000%) | 14/15 to 1 (93.3333%–100.0000%); n=15 | NOT COMPUTED |
| THEME-3-PREPARED-CASES: Different stacks: selected operating outcomes | 15 / 0 / 0 | 15/15 (100.0000%) | 1 to 1 (100.0000%–100.0000%); n=15 | NOT COMPUTED |
| CLUSTERED-REPEATED-CHECKS: Thirty repeated checks across three fictional batches | 27 / 3 / 0 | 27/30 (90.0000%) | 9/10 to 9/10 (90.0000%–90.0000%); n=30 | NOT COMPUTED |

## MODEL-3-OF-3

- Outcome: Trial meets its specified outcome
- Unit: trial
- Observation window: Fictional model exercise A, trials 1 through 3
- Declared sampling design: independent\_bernoulli
- Basis supplied: Independent Bernoulli trials with one common unknown success probability are assumptions of this invented model exercise. No random sampling was actually conducted.
- Eligible collection: 3
- Interval status: CONDITIONAL_MODEL
- Source references:
  - fixtures.json#MODEL-3-OF-3 (invented counts)

## MODEL-300-OF-300

- Outcome: Trial meets its specified outcome
- Unit: trial
- Observation window: Separate fictional model exercise B, trials 1 through 300
- Declared sampling design: independent\_bernoulli
- Basis supplied: Independent Bernoulli trials with a common unknown success probability are declared solely to illustrate denominator precision. This is not an extension or replication of exercise A.
- Eligible collection: 300
- Interval status: CONDITIONAL_MODEL
- Source references:
  - fixtures.json#MODEL-300-OF-300 (invented counts)

## MODEL-0-OF-3

- Outcome: Trial meets its specified outcome
- Unit: trial
- Observation window: Separate fictional model exercise C, trials 1 through 3
- Declared sampling design: independent\_bernoulli
- Basis supplied: Independent Bernoulli observations with a common probability are assumed for a numerical boundary example, not established by collection evidence.
- Eligible collection: 3
- Interval status: CONDITIONAL_MODEL
- Source references:
  - fixtures.json#MODEL-0-OF-3 (invented counts)

## EMPTY-WINDOW

- Outcome: Event meets its specified outcome
- Unit: event
- Observation window: Separate fictional empty observation window
- Declared sampling design: census
- Basis supplied: The invented window contains no eligible events. It demonstrates undefined rates rather than zero performance.
- Eligible collection: 0
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_CENSUS, NO_OBSERVED_OUTCOMES
- No eligible observations: rate and collection bounds are undefined, not zero.
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - fixtures.json#EMPTY-WINDOW (invented empty collection)

## ALL-OUTCOMES-UNKNOWN

- Outcome: Event meets its specified outcome
- Unit: event
- Observation window: Separate fictional collection D, ten listed events
- Declared sampling design: unknown
- Basis supplied: Only the eligible count is stipulated; sampling design and every outcome are unavailable.
- Eligible collection: 10
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_UNKNOWN, INCOMPLETE_OUTCOMES, NO_OBSERVED_OUTCOMES
- Complete-case rate excludes unknown outcomes; do not report it as the full-collection rate.
- All outcomes are unknown; collection bounds span 0 to 1.
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - fixtures.json#ALL-OUTCOMES-UNKNOWN (invented counts)

## THEME-1-TIMELY-UPDATES

- Outcome: The next update occurred by its recorded due time
- Unit: incident recorded in the shared service
- Observation window: UIOWA-083 fictional exercise days E01–E28
- Declared sampling design: convenience
- Basis supplied: One fictional register records 18 service-entry incidents, split ESS 8 / RIS 6 / IAM 4. Other incidents are excluded and random selection or independence is not established. Group slices are not three independent sources.
- Eligible collection: 18
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_CONVENIENCE
- Source interpretation limit: A late update is an observed timing exception, not a finding that every notification fails. Initial-owner assignment and next-update timing are different outcomes.
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - [https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa\_rfq\_18649\_themes/worked\_narratives.md#syn-e1-01](<https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa_rfq_18649_themes/worked_narratives.md#syn-e1-01>)
  - SYN-E1-01 edition 1: summary rows 1–3 and IAM-04 update field; SYN-F1-01

## THEME-2-REVIEW-OCCURRENCE

- Outcome: Peer review occurred before deployment
- Unit: normal change in the fictional sample
- Observation window: UIOWA-083 Theme 2 convenient sample of 15 normal changes; no calendar dates asserted
- Declared sampling design: convenience
- Basis supplied: Records corroborate ESS 6 / RIS 3 / IAM 5 pre-deployment reviews. RIS-C04's record is unavailable and its owner's verbal-review recollection is uncorroborated. Selection was convenient, not random; urgent restorations are excluded from this denominator.
- Eligible collection: 15
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_CONVENIENCE, INCOMPLETE_OUTCOMES
- Source interpretation limit: Unavailable documentation does not demonstrate that review failed to occur. The complete-case 14/14 rate is not a 15/15 full-sample claim. Two urgent restorations and retrospective timing are a separate question.
- Complete-case rate excludes unknown outcomes; do not report it as the full-collection rate.
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - [https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa\_rfq\_18649\_themes/worked\_narratives.md#syn-f2-01](<https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa_rfq_18649_themes/worked_narratives.md#syn-f2-01>)
  - SYN-E2-02 ESS-C01..C06; SYN-E2-03 RIS-C01..C04; SYN-E2-04 IAM-C01..C05; SYN-E2-05 item 4

## THEME-3-PREPARED-CASES

- Outcome: All three specified outcome checks O1–O3 were met
- Unit: prepared demonstration case
- Observation window: UIOWA-083 Theme 3: one fictional prepared demonstration, five cases per group
- Declared sampling design: prepared\_demo
- Basis supplied: One assessor worksheet records fifteen prepared cases, five per group. Each case has three checks. Cases are neither random releases nor production incidents; forty-five checks are not forty-five independent deployments.
- Eligible collection: 15
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_PREPARED_DEMO
- Source interpretation limit: Equivalence applies to the selected checks and prepared cases. No production reliability, efficiency advantage, savings or migration case is established.
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - [https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa\_rfq\_18649\_themes/worked\_narratives.md#syn-e3-01](<https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa_rfq_18649_themes/worked_narratives.md#syn-e3-01>)
  - [https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa\_rfq\_18649\_themes/worked\_narratives.md#syn-e3-02](<https://github.com/woahwhattheheck/commons/blob/1bafceba3a902acef861c633d251351e0ed51aaf/revenue/uiowa_rfq_18649_themes/worked_narratives.md#syn-e3-02>)

## CLUSTERED-REPEATED-CHECKS

- Outcome: Check meets its specified outcome
- Unit: check within a shared batch
- Observation window: Separate fictional exercise E: three batches with ten checks each
- Declared sampling design: clustered
- Basis supplied: Checks within each batch share conditions, so thirty independent Bernoulli observations are not asserted. No intracluster-correlation estimate or effective sample-size adjustment is supplied.
- Eligible collection: 30
- Interval status: NOT_COMPUTED
- Reasons: SAMPLING_DESIGN_CLUSTERED
- Descriptive collection only; the independent-binomial model is not selected.
- Source references:
  - fixtures.json#CLUSTERED-REPEATED-CHECKS (invented counts)

## Interpretation

- Counts describe separate collections; no pooled rate or ranking is produced.
- Collection bounds vary only the unknown outcomes in the stated collection.
- Sampling design is declared input, not a fact verified by this utility.
- A Wilson interval is conditional on independent Bernoulli observations with a common probability.
- Intervals are not maturity, evidence-confidence scores, future prediction or significance tests.

Formula reference: [NIST §7.2.4.1](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
