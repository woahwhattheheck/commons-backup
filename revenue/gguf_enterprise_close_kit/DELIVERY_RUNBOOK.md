# 10-day GGUF diagnostic delivery runbook

## Day 0 — start gate / custody

Confirm NDA + SOW execution, lawful GGUF control, runnable customer harness, and owner-reported M1 evidence **outside public Commons**. Create a secret-free intake record. If any prerequisite is absent, state `HOLD_PRE_FILE_EXCHANGE`; do not request model bytes.

## Day 1 — baseline

Privately acquire the one agreed GGUF, record AT1 SHA-256 before any modification, freeze harness version/configuration, run the baseline, and retain the baseline log digest + metrics. If baseline cannot reproduce, HOLD and diagnose the harness/environment before any model change.

## Days 2–3 — diagnosis

Inspect the agreed bounded surface and select one intervention/ablation hypothesis. Record the hypothesis and its falsifier. Do not promise metric lift and do not broaden scope into training, production deployment, or unrelated system repair.

## Days 4–5 — bounded ablation

Produce the bounded ablated artifact privately. Record AT2 SHA-256 and verify it differs from AT1. Run the exact same customer harness/configuration; retain digest-only log evidence and aggregate metrics.

## Day 6 — rollback

Restore the original bytes. AT3 requires restored SHA-256 **exactly equal** to AT1. If exact restoration fails, stop; do not call the engagement accepted and do not destroy evidence needed to diagnose the mismatch.

## Day 7 — restore run

Run the restored artifact through the same harness. Retain the restore log digest + aggregate metrics. Metric drift is reported, not hidden; it is not itself acceptance failure unless it reveals the harness is not reproducible enough to support the evidence claim.

## Day 8 — finding

Write the concise finding: hypothesis, intervention, observed baseline/ablation/restore metrics, what the evidence proves, what it does not prove, limitations, and rollback consequence. Hash the exact delivered finding for AT5.

## Day 9 — evidence packet

Assemble AT1–AT6 digest-only evidence and final receipt. Compile and verify with `close_kit.py`. Any missing AT stays HOLD. Public/sample packet must contain no customer model bytes, private contact data, secrets, signatures, processor refs that expose private data, or confidential evaluation cases.

## Day 10 — acceptance review / handoff

Deliver the private evidence bundle and buyer-readable report. `READY_FOR_OWNER_M2_ACCEPTANCE_REVIEW` means the evidence packet is complete for owner/customer review; it does **not** assert legal acceptance or M2 payment. Keep the original GGUF recoverable until the customer closes the engagement.

## Final evidence packet checklist

- exact offer ID + terms digest;
- intake/case ID and secret-free start-gate state;
- AT1 original SHA-256;
- AT2 ablated SHA-256 and inequality proof;
- AT3 restored SHA-256 and equality proof;
- baseline/ablation/restore harness log digests;
- common metric vector + deltas;
- concise finding digest;
- delivery receipt digest;
- deterministic packet receipt;
- authority boundary showing send/payment/refund/revenue authority remains false.

## Failure / HOLD escalation

- **Legal-control uncertainty:** no file exchange; owner/legal review.
- **Harness not runnable/reproducible:** HOLD; repair harness contract before model work.
- **Original identity uncertain:** HOLD before edit.
- **AT2 unchanged:** intervention did not produce a distinct artifact; HOLD/rework.
- **AT3 mismatch:** STOP; rollback integrity failed.
- **Missing run/finding/receipt evidence:** HOLD; no AT1–AT6 completion claim.
- **Secret/publication risk:** stop publication; keep evidence private and expose only digests/aggregates.
- **Refund/credit request:** preserve facts and route to owner/provider; this kit has no refund authority.
