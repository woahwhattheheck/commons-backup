# claude_compute — quarantine / staging

Claude output lands here first. Label every artifact
`CLAUDE_INTERMEDIATE_UNTRUSTED`. This directory is not current
main. A packet here is `CANDIDATE` until a named non-Claude
adjudicator lands the accepted bytes on official main.

## Drop a packet

1. Copy `PACKET.example.json`.
2. Fill spec, input corpus, claimed paths, acceptance criteria,
   output directory, and the **non-Claude adjudicator**.
3. Write the filled packet to `packets/{id}.json`.
4. Put Claude artifacts under `staging/{id}/`.
5. Do not public-push, merge, or treat the staging bytes as HEAD.

Claude may not name itself as adjudicator. Claude may not decide
whether its own output is correct. Opus 5 does bulk drafting.
The named adjudicator tests, reviews, and lands.

Card: `ground/CLAUDE_COMPUTE.md`. Instrument: `host/claude_compute.py`.
No auth. No gate. titan: NOT_WRITTEN.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
