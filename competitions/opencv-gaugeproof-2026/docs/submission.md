# Competition submission carrier — NOT SUBMITTED

## Working title

**GaugeProof — visual evidence, not guesses, for legacy industrial gauges**

## One-line pitch

GaugeProof uses OpenCV to read analog gauges from short inspection videos, rejects bad or contradictory visual evidence, and produces tamper-evident annotated receipts for a human/operator workflow.

## Demo storyboard (<= 3 minutes target)

1. **Problem (0:00–0:20):** show a synthetic pressure gauge and explain why one plausible-looking frame can be wrong.
2. **Stable evidence (0:20–0:55):** run five near-50 psi frames; visualize dial and pointer; show `ACCEPT_READING` and receipt hashes.
3. **Refusal (0:55–1:25):** blur/glare/occlusion examples; show explicit reasons rather than fabricated numbers.
4. **Conflict (1:25–1:50):** mix valid 20 psi and 80 psi frames; system returns `ESCALATE_HUMAN`, no value.
5. **Evidence contract (1:50–2:20):** tamper with JSON; verifier fails. Highlight all external authority flags false.
6. **Scale story (2:20–2:45):** independent frame analysis -> AWS/Graviton/COOL benchmark path while preserving the same evidence contract.
7. **Close (2:45–3:00):** "Agentic vision should know when not to act."

## Architecture diagram source

```text
short image/video burst
        |
        v
[bounded image ingress]
        |
        +--> blur/glare ----------- refusal reason
        |
        v
[OpenCV dial localization]
        |
        +--> ring support --------- refusal reason
        |
        v
[pointer angular projection]
        |
        +--> ambiguity ------------ refusal reason
        |
        v
[declared calibration]
        |
        v
[frame evidence x N]
        |
        v
[temporal consistency reducer]
   |          |            |
 ACCEPT    REINSPECT    ESCALATE_HUMAN
   \          |            /
    +----> receipt + annotations
            authority=false
```

## Submission-readiness truth table

| Item | Current state |
|---|---|
| Competition source/repository carrier | READY |
| Offline synthetic demo | READY after exact merged readback |
| Hostile regression suite | READY after exact merged readback |
| Real customer/site dataset | NOT REQUIRED / intentionally absent |
| AWS deployment | NOT PERFORMED |
| Cloud Optimized OpenCV benchmark | NOT PERFORMED |
| Devpost registration | NOT PERFORMED |
| Rules/terms acceptance | NOT PERFORMED |
| Public demo video | NOT RECORDED |
| Final submission | NOT PERFORMED |
| Prize/award/revenue | $0 asserted |

## Before any actual submission

Re-read the live Devpost rules and organizer page; resolve the currently inconsistent published prize totals; verify entrant eligibility; decide whether AWS/COOL usage is needed for a target prize; record a real demo video; add screenshots; disclose AI assistance as required; inspect repository for secrets; then have the authorized entrant perform registration/terms/submission.
