# GatewayHacks 2026 submission packet — Civic Action Ledger

## Track
Open Impact & Community.

## One-line pitch
Turn agendas, addenda, and adopted minutes into a citation-linked public decision/action ledger that shows changes and uncertainty instead of hallucinating certainty.

## Problem
A public meeting may publish an agenda, a late addendum, adopted minutes, and later follow-up. Residents and small civic organizations must manually determine what changed, what was actually decided, who owns the next action, and which deadline is source-backed.

## Demo story (synthetic Riverton fixture)
1. Import the agenda: three items are `PROPOSED`.
2. Import an addendum: item 4.2 visibly changes owner, deadline, title, and action.
3. Import adopted minutes: 4.2 becomes `DECIDED_APPROVED`, 7.1 `DECIDED_CONTINUED`, 9.3 `DECIDED_DENIED`.
4. Search for “Library” or filter `DECIDED_CONTINUED`.
5. Open canonical JSON / Markdown and inspect `doc_id:line` anchors.
6. Modify an exported file: offline bundle verification fails.
7. Add contradictory adopted minutes: item becomes `HOLD_CONFLICT` rather than selecting a convenient answer.

## Judging fit
- **Impact:** lowers the cost of following public commitments and changed meeting records.
- **Technical:** immutable source digests, line hashes, conflict semantics, deterministic compiler, verifier, browser/API, replay/tamper hostiles.
- **Innovation:** treats provenance and uncertainty as first-class product UX, not an afterthought.
- **Design/UX:** compact searchable dashboard, mobile layout, plain-language states, direct evidence links.

## Truth boundary
Synthetic fixtures are demonstration data. This repository does not claim deployment, government adoption, partner endorsement, contest submission, award, payment, or revenue. It performs no scraping, login bypass, outbound messaging, or governmental action.

## Suggested <=5 minute video
- 0:00–0:35 problem + source chain
- 0:35–1:25 import agenda/addendum/minutes
- 1:25–2:20 dashboard/filter/evidence anchors
- 2:20–3:10 change history + conflict fail-closed demo
- 3:10–3:50 export + offline verifier tamper demo
- 3:50–4:30 impact + future source connectors
