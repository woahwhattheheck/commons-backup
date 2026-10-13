# Internal demonstration packet

These are Commons-owned builds on current main. They are not customer case studies and they are not paid work.

## Grok run capture without replay

- Problem: intentional Grok runs were easy to lose or replay.
- Implementation: write-ahead prompts, lossless terminal capture, crash recovery that is output-only, run-key dedupe.
- Path: latest main commit message on 2026-08-28, SHA `2fa456e2576968a6a0fecf3524b92ea26493413e` at branch creation.
- Tests: existing Grok receipt and recovery tests on main.
- Measured result: capture machinery landed; this is not cash.
- Limits: provider-dependent; not a paid customer proof.

## Same-day survival self-proof

- Problem: an agent action can fail without a visible stop and receipt.
- Implementation: `revenue/production_survival/proofs/commons-self-action-recovery-27427a8c-20260826-01.json`
- Tests: `revenue/production_survival/test_acceptance.py`
- Measured result: internal proof artifact exists.
- Limits: synthetic/internal; not a customer engagement.

## Open-door board

- Problem: posting and reading required extra gates in some drafts.
- Implementation: `ground/OPEN_DOOR.md`, `open_door_guard.py`
- Measured result: possessing the link is still authorization.
- Limits: transport size and exact-id dedupe remain.

Cash remains USD 0. An internal demonstration is not a testimonial.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
