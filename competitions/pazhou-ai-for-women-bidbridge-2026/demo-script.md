# BidBridge demo script — 3 to 5 minutes

**Status:** DRAFT. Designed for screen recording or live judging. Uses only the checked-in synthetic opportunity. Do not import real customer data for the competition demo unless separately reviewed and authorized.

## Setup

Open:

`https://woahwhattheheck.github.io/commons/competitions/pazhou-ai-for-women-bidbridge-2026/`

If Pages has not propagated, serve the folder locally with any static file server. Do not use a `file://` URL because browser fetch restrictions may block the JSON fixture.

Default trusted review time:

`2026-09-13T14:00:00.000Z`

## 0:00–0:35 — Problem and promise

Show the hero.

Suggested narration:

> Small businesses often discover an RFP before they are ready to decide whether they should spend scarce founder time pursuing it. BidBridge is an evidence-bound procurement copilot. Instead of starting by generating proposal prose, it first asks: what is mandatory, what is actually proven, what depends on a partner, and can the team finish with a safe submission buffer?

Point to the truth box:

> It cannot claim compliance, contact a partner, register a vendor, or submit a bid. Those boundaries are part of the product.

## 0:35–1:20 — Synthetic opportunity

Point out that the example is explicitly synthetic.

Explain:

- source revision = 3;
- submission mode = portal;
- source reference amount is displayed as a source reference, not revenue;
- three mandatory requirement rows exist.

Press **Evaluate opportunity**.

Expected default state:

`READY_FOR_GAP_REVIEW`

Expected remaining effort:

`12 h`

Expected usable capacity:

`22 h`

## 1:20–2:15 — Requirement evidence

Show the matrix.

Narration:

> The certification row is satisfied with current revision-bound evidence. The technical plan is partial. The field-capacity row needs an external partner. Those are different operational problems, so BidBridge does not collapse them into one AI confidence score.

Point to team state `IDENTIFIED`.

> A partner candidate being identified is not permission to contact or commit them.

## 2:15–3:05 — Critical path and deadline

Show the queue.

Narration:

> The queue prioritizes external dependency, partial evidence, and the upcoming question deadline. The ordering is deterministic. If evidence becomes stale, conflicts with the opportunity revision, or disappears, the system moves to HOLD rather than guessing.

Change the trusted review time to the exact submission deadline:

`2026-09-18T16:00:00.000Z`

Press evaluate.

Important: the default evidence freshness window is 72 hours, so at this later time evidence may also be stale. Use this to explain HOLD precedence if it appears. For a clean exact-deadline state demonstration, use the automated test evidence or temporarily use a separately prepared synthetic fixture with current evidence; do **not** edit current evidence during a recorded demo without explaining it.

Recommended live alternative: keep the default timestamp and explain the exact deadline boundary is covered by the checked-in test suite.

## 3:05–3:45 — Authority boundary

Scroll to “Authority stays with the owner.”

Narration:

> Every external authority is false. The product can help a founder organize and reason, but it cannot silently cross from decision support into representation, submission, contract, or payment action.

This is the product’s trust differentiation from generic AI bid-writing tools.

## 3:45–4:35 — Women-friendly product value

Narration:

> The women-friendly thesis is entrepreneurship empowerment, not a gender stereotype. U.S. Census data report 14.2 million women-owned U.S. businesses in the 2023 reference year. The SBA has a women-owned small business contracting program and a 5% federal contracting goal. BidBridge is designed to test whether evidence-first procurement operations save time for women entrepreneurs and other owner-led firms with limited proposal staff.

Do not claim current women-owned customers or pilots.

## 4:35–5:00 — Close

Suggested close:

> The next AI layer will extract requirements and amendment changes with source citations. The deterministic evidence core remains underneath it. The goal is simple: generate useful assistance, but never generate facts the business has not proven.

## Suggested screenshots

1. Hero + truth box.
2. Default `READY_FOR_GAP_REVIEW` summary.
3. Requirement evidence matrix.
4. Critical-path queue.
5. All-false authority grid.
6. GitHub test result showing focused suite pass.

## Claims not permitted in the demo without new evidence

- “We have women-owned customers.”
- “We have saved X hours.”
- “We increase win rates.”
- “We are WOSB certified.”
- “We are compliant with Chinese/U.S. procurement law.”
- “We submitted to Pazhou.”
- “We won/placed.”
- “The organizer endorses BidBridge.”
