# UIOWA-058 — Secure-development knowledge in practice

Offline assessment kit for the University of Iowa RFQ 18649 preparation work order on guidance usability, reusable secure-development patterns, onboarding, and specialist access.

The unit of assessment is the **team guidance/support system**. The kit does not grade individual engineers, inspect application code, scan systems, or make compliance findings.

## Included

- `assess_guidance.py` — validates the evidence packet, evaluates guidance usability evidence, emits a CSV worksheet and facilitator discussion pack.
- `fixtures/synthetic_guidance_packet.json` — six fictional guidance records plus exactly three discussion exercises covering input handling, authorization design, and error handling.
- `examples/guidance-usability.csv` — generated guidance evidence matrix.
- `examples/discussion-pack.md` — generated facilitator-ready exercise pack.
- `guidance_usability_worksheet.md` — discovery worksheet for evidence requests and interviews.
- `test_assess_guidance.py` — regression tests for required coverage, current/superseded/unknown states, partial guidance, missing references, and sensitive-value rejection.

## Run

```bash
python3 assess_guidance.py fixtures/synthetic_guidance_packet.json \
  --csv-out examples/guidance-usability.csv \
  --md-out examples/discussion-pack.md
python3 -m unittest -v test_assess_guidance.py
python3 -O -m unittest -v test_assess_guidance.py
```

## Interpretation guardrail

A missing owner, search location, application trigger, or specialist route is evidence about the **guidance system represented by the supplied packet**. It is not evidence that an individual lacks knowledge or that a University practice is insecure. Real findings require representative Iowa artifacts and interviews during the engagement.
