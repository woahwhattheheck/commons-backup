# UIOWA-065 — Service observability and objectives

This directory contains an offline, vendor-neutral assessment kit for checking whether supplied observability evidence explains user-visible service behavior and supports useful operational decisions.

All checked-in examples are fictional. The tool does not connect to monitoring systems and does not assert University of Iowa findings.

## What the assessment asks

For each service objective, record:

| Field | Assessment question |
|---|---|
| User outcome | What user-visible behavior should remain successful or timely? |
| Indicator | What measurement represents that behavior? |
| Objective | What target and measurement window apply? |
| Definition evidence | Where is the calculation or event definition retained? |
| Measurement evidence | What source, period, and population support the observation? |
| Dependency visibility | Which upstream/downstream services can change the outcome, and can their contribution be observed? |
| Diagnostic context | What retained context helps a responder move from a symptom to a useful investigation? |
| Decision use | What review, prioritization, release, capacity, or remediation decision actually used the evidence? |
| Uncertainty | Which missing or conflicting evidence must remain unknown? |

## Three fictional examples

`examples.json` contains:

1. a course-registration service with a user-visible success ratio, one fully visible dependency, one partially visible dependency, diagnostic context, and a retained decision record;
2. a research-submission service with a well-defined user-visible ratio but unknown dependency coverage and no retained decision-use evidence;
3. a sign-in service whose measurement is backend latency rather than a user-visible outcome, lacks an indicator-definition reference, has an unknown dependency, and lacks diagnostic/decision evidence.

The examples separate infrastructure or component health from what a user actually experiences. A technically valid backend metric can be useful diagnostic evidence without being sufficient as the service objective.

## Status semantics

- `SUPPORTED`: supplied measurement evidence is sufficiently defined to interpret for the stated objective.
- `PARTIAL`: measurement evidence exists but a material definition, period, source, or ratio component is incomplete or invalid.
- `UNKNOWN`: no usable measurement-evidence object was supplied.

These are evidence states, not maturity scores. Non-measurement issues such as partial dependency visibility or missing decision-use records are reported as issues and questions rather than silently converted into a numeric score.

## Run

From this directory:

```bash
python observability.py examples.json
python observability.py examples.json --out /tmp/uiowa-065-result.json
python -m unittest -v test_observability.py
```

Expected example summary:

```text
finding_count = 3
SUPPORTED = 2
PARTIAL = 1
UNKNOWN = 0
```

## Interpretation guardrails

- Do not infer that a missing record means a practice did not occur.
- Do not use one infrastructure metric as a substitute for the full user journey.
- Keep the measurement window, population, and definition with any reported value.
- Record dependency gaps separately from the service's own indicator definition.
- Look for evidence that objectives influence decisions; dashboard presence alone is not decision use.
- Do not convert this evidence check into a monitoring-product recommendation.
- Do not compare fictional values to invented peer percentiles.

## Interview prompts

- Which service behaviors matter most to students, researchers, faculty/staff, or application consumers?
- What precise event starts and ends the indicator?
- Which requests or cases are excluded from the population, and why?
- How do you know a dependency—not the local component—is driving a user-visible symptom?
- Which context is retained long enough to investigate a past objective breach?
- Show a decision changed by an objective or indicator, not only a dashboard screenshot.
- When an indicator is healthy but users report failure, how is that mismatch investigated?
- Which objectives are intentionally absent because reliable measurement would cost more than the decision value?

## Files

- `observability.py` — standard-library assessor and JSON CLI.
- `examples.json` — three fully fictional service examples.
- `test_observability.py` — regression tests for expected states and missing/invalid evidence behavior.
