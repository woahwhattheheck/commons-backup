# UIOWA-060 — Security-event review and ownership assessment kit

This additive, offline kit supports the **security-event review and ownership** work order for University of Iowa RFQ 18649 preparation. It evaluates *supplied evidence records*; it does not connect to logs, SIEMs, identity systems, cloud accounts, or University infrastructure.

## What it tests

The evidence model follows this chain:

`event selection → retained context → reviewer access/ownership → review decision → escalation (when required) → action evidence`

General operational monitoring is represented separately. A collected performance/availability signal does **not** become evidence of security review simply because it exists in a log or monitoring platform.

The evaluator emits evidence states, not maturity scores. Missing records stay missing/unknown and are never converted into a claim of compromise, control failure, compliance failure, or employee performance.

## Files

- `assess_security_events.py` — strict offline validator/evaluator and report renderer.
- `fixtures/synthetic_events.json` — five wholly fictional ESS/RIS/IAM event records covering monitoring-only, complete review/action, missing review evidence, unknown relevance, and open action.
- `examples/security-event-evidence-matrix.csv` — generated assessment matrix.
- `examples/event-to-resolution-timeline.md` — generated fictional timelines and interview prompts.
- `interview_worksheet.md` — evidence-request/interview worksheet for discovery.
- `test_assess_security_events.py` — regression tests, including fail-closed handling of credential-like fields and impossible timeline order.

## Run

```bash
python3 assess_security_events.py fixtures/synthetic_events.json \
  --json-out /tmp/uiowa060-assessment.json \
  --csv-out examples/security-event-evidence-matrix.csv \
  --md-out examples/event-to-resolution-timeline.md
python3 -m unittest -v test_assess_security_events.py
python3 -O -m unittest -v test_assess_security_events.py
```

## Evidence interpretation boundary

A useful finding requires a bounded statement such as: “For the sampled records, the supplied packet does not establish a review owner or decision after collection.” It must **not** be inflated into “security events are not reviewed” without representative evidence.

The synthetic fixture contains no real University data, credentials, secret values, customer records, or production identifiers.
