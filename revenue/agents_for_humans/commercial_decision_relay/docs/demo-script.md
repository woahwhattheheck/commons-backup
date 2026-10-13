# Demo script (target: 3m 40s)

**0:00–0:25 — Problem.** A closer should not re-read every routine commercial thread. But an agent must not hallucinate "deal closed" from vague prose. Commercial Decision Relay handles the repetitive custody loop and interrupts only for real decisions.

**0:25–0:55 — Architecture.** Show the Strands agent, five deterministic custom tools, hash-only lifecycle audit hooks, and the explicit authority boundary. Trusted normalized evidence plus trusted UTC are preloaded and locked before model orchestration; deterministic code decides evidence status.

**0:55–1:45 — Reproducible fixture.** Run `decision-relay reconcile --batch fixtures/demo-batch.json --evaluated-at 2026-09-13T12:00:00Z --output /tmp/receipt-demo-001.json`. Show four series: exact acceptance, counteroffer, decline, and unanswered offer. Only two are surfaced. Decline/unanswered stay quiet. Re-running against the same output path fails rather than overwriting the receipt.

**1:45–2:20 — Product board.** Run `python -m decision_relay.web_demo --batch fixtures/demo-batch.json --evaluated-at 2026-09-13T12:00:00Z`. Show the decision cards, trusted evaluation instant, and the all-false authority footer.

**2:20–2:55 — Tamper + time resistance.** Verify with the independently supplied receipt digest and `--evaluated-at 2026-09-13T12:00:00Z`. Change source evidence or the expected digest and show verification fail closed. Explain that a pre-expiry receipt also fails current verification at a later post-expiry trusted UTC, requiring a newly reconciled `REISSUE_REQUIRED` receipt.

**2:55–3:30 — Strands live path.** With configured Bedrock or OpenAI provider, run `decision-relay agent --provider bedrock --batch fixtures/demo-batch.json --evaluated-at 2026-09-13T12:00:00Z "Show me only decisions that need a human."` The trusted batch is already ingested/reconciled before the model starts; show the agent using `decision_queue` / `explain_blocker` / `verify_current_receipt`. An attempted model-side `ingest_batch` replacement is rejected. Briefly show hash-only audit JSONL, including `ok:false` for failed/cancelled tool calls.

**3:30–3:40 — Why it matters.** The closer gets fewer interruptions without surrendering commercial authority to the model. It is a professional agent designed to quietly do work and surface only real decisions.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)
