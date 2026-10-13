# OneWriter — single-writer outreach control

**Operation:** `EMERGENT-BUILDERFEST-ONEWRITER-ZSOL-20260917`  
**Competition:** Kevin O'Leary × Emergent Builders' Fest 2026  
**Source state:** durable source packet only; `DRAFT_NOT_SUBMITTED`

OneWriter prevents a concrete multi-agent business failure: two workers independently discover the same hot lead and contact it seconds apart through the same or different aliases. The duplicate touch looks like spam, damages trust, and can destroy follow-up ownership. OneWriter turns the pre-send ownership decision into an atomic, auditable writer lease.

This packet is a build contract for a working Emergent app. It does **not** send email, DMs, forms, mutate providers, or grant contest-submission authority.

## Contest fit

First-party contest page checked 2026-09-17: `https://emergent.sh/ai-contests/kevin-oleary-emergent-builder-fest`.

The page says the app must solve a real business problem and actually be used in the business; submissions close 2026-09-20 23:59 GMT; deployment is not submission; one active submission is allowed per participant/team; Business Impact / Potential to Scale is the largest rubric component at 30%.

OneWriter maps directly to operations/team and revenue/sales: it coordinates lead ownership, prevents duplicate external touches across aliases, distinguishes route failures from human outcomes, and produces evidence for real before/after measurement.

## Deterministic contract

The **writer-lane identity** is:

`normalized organization × domain × purpose × opportunity`

The exact `route` is deliberately **not** part of the collision key. It is normalized, stored as lease metadata, and bound to provider outcomes. This is the core anti-spam rule: a worker leasing `sales@example.com` blocks another worker from simultaneously leasing `founder@example.com` for the same organization/opportunity/purpose.

The SHA-256 collision key is deterministic over canonical JSON. State is one of `CLEAR`, `LEASED`, `HARD_DNR`, `DEAD_ROUTE`, `HUMAN_EVENT_REOPEN`, or `HOLD`.

Important semantics:
- exactly one live writer lease per organization lane, across routes;
- an active lease blocks parallel claims even when the proposed alias differs;
- an **ordinary** expired lease can be stale-recovered with an explicitly selected route;
- only the current holder can record `SENT` or `BOUNCE`, and the recorded route must match the currently leased route;
- `SENT` creates `HARD_DNR`;
- a provider bounce records `DEAD_ROUTE`, **not buyer rejection**;
- no fallback alias is opened merely because a route failed;
- a retained genuine human event is the only event that reopens a fenced lane;
- one human event authorizes exactly one bounded next lease attempt; if that lease expires unused, the lane restores its exact prior fence instead of becoming stale-recoverable;
- event ids, provider receipts, and human evidence ids share one workspace uniqueness namespace, preventing cross-type evidence reuse;
- every receipt binds a canonical normalized accepted-event object, so evidence/lease/reason/identity/route/actor/kind/time substitution changes the receipt digest;
- no event in this source packet authorizes an external send.

See `state_machine.json`, `acceptance.py`, and `product_spec.md`.

## Retained identifier contract

Event ids, `provider_receipt`, and `human_evidence_id` are opaque workspace identifiers, not notes. All three use the same exact admission contract: **trimmed nonempty text, 1–240 characters, no ASCII control characters, no Unicode category-C codepoints, no non-category-C Default_Ignorable codepoints, and at least one visible base codepoint outside Unicode C/M/Z categories**. Reject whitespace-only, padded, overlong, control/format/private/unassigned, grapheme-joiner, Hangul-filler, variation-selector, other Default_Ignorable-bearing, or combining-mark-only values; do not silently normalize them. Ordinary combining marks remain admissible when attached to a visible base.

After admission, event ids + provider receipt ids + human evidence ids use one workspace-wide uniqueness namespace. A provider id cannot later masquerade as human evidence or an event id, human evidence cannot be recycled as provider evidence or an event id, and an event id cannot collide with either evidence class.

## Synthetic demo

`demo_events.json` is deliberately synthetic (`*.invalid` domains). It demonstrates:

1. Alpha leases Northstar through `ops@...`;
2. Beta races three seconds later through a **different alias** `founder@...` and is denied by the same organization-lane key;
3. provider `SENT` on Alpha's leased route hard-fences the lane;
4. a claim through yet another alias is blocked;
5. retained human evidence reopens one bounded next action, which may choose a new route explicitly;
6. an expired **ordinary** Harbor Forge lease is recovered;
7. a matching-route provider bounce creates `DEAD_ROUTE` without claiming buyer rejection;
8. a fallback alias remains blocked absent a genuine reopen;
9. a Cedar Works `HOLD` blocks claims across aliases until human evidence.

The expected replay contains 14 events across 3 lanes. Those counts are **synthetic proof only**, not TJLabs production impact.

## Offline proof

Run from this directory:

```bash
python3 acceptance.py verify-machine state_machine.json
python3 acceptance.py replay state_machine.json demo_events.json
python3 -m unittest discover -v
python3 -O -m unittest discover -v
```

The hostile suite rejects duplicate JSON keys, non-finite numbers, semantic contract remints, the prior blanket-stale-recovery authenticated machine generation, authority escalation, duplicate or cross-type reused workspace identifiers, nonmonotone timestamps, invalid lease types, non-holder outcomes, expired-holder outcomes, provider outcomes on the wrong route, malformed/credentialed/ported domains, and whitespace/padded/control/category-C/Default_Ignorable/combining-only event/provider/human identifiers. It proves the current ordinary-only stale-recovery machine digest under normal and optimized Python, visible-base+combining identifiers remain admissible, cross-route collision, normalized-domain equivalence, one-shot human reopen re-fencing after expiry, and receipt-digest movement under evidence/lease/reason substitution.

## Emergent build handoff

Use `emergent_master_prompt.md` as the build prompt. The deployed app must then be exercised on a real TJLabs coordination workflow and produce measured evidence using `impact_evidence.md` **before** draft submission placeholders are converted into factual impact claims.

`submission_copy.md` remains intentionally `DRAFT_NOT_SUBMITTED`.

## External authority boundary

This repository packet grants none of the following: external email/DM/form sending; provider mutation; contract/signature authority; payment/cash/revenue claims; contest submission; paid Emergent upgrade/spend; or public upvote campaigning.

Any real external communication remains separately single-writer coordinated. Any contest submission must be reconciled against the platform's one-active-submission rule immediately before submission.