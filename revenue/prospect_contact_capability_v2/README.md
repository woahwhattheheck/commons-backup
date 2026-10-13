# Connector-native prospect contact custody v2

This package is a fail-closed, contact-level **single-writer custody protocol** for concurrent outbound workers that have ordinary GitHub connector primitives but do not have repository-administration authority.

It is additive to the existing outbound safety stack. It does **not** send email or DMs, grant provider-send authority, replace relationship/DNR checks, prove buyer acceptance, mutate payments, or recognize revenue.

## Why v2 exists

The current v1 contact lock was hardened to require its mutable authority branch to be protected before any production record read. On 2026-09-18 the live branch `coordination/prospect-contact-lock-v1` still reports `protected:false`. A normal managed GitHub connector seat can create/read blobs, trees, commits, and branches, but does not expose branch-protection administration. v2 therefore uses a separate namespace and a narrower threat model: prevent accidental/concurrent cooperating fleet writers without depending on an admin-only protection setting.

A repository administrator can still rewrite or delete refs. v2 does not claim to resist a malicious repository administrator. Any missing, moved, or semantically different expected ref fails closed.

## Core invariants

- The contact key is derived only from normalized email/domain/phone identity. Campaign name, offer, price, message wording, claimant, and anchor do not change the collision seam.
- A claim is won only by create-exclusive creation of one deterministic claim branch.
- The claim binds a privately retained random 256-bit capability by SHA-256 commitment. Public receipts do not prove possession.
- Every operation re-reads the exact claim branch head, commit parent, and metadata bytes. Possession additionally requires the private capability.
- `RELEASED_UNSENT` and `DISPATCHED_OUTCOME_UNKNOWN` compete for **the same deterministic terminal branch**. Only one terminal state can win for a claim generation.
- There is no timeout, stale takeover, force update, or ordinary release after dispatch.
- A release terminal contains only an HMAC holder proof. The still-active capability is **not** disclosed while the terminal branch is being raced.
- Only after the release terminal is confirmed live may a separate deterministic reveal branch disclose the now-retired capability. That makes release publicly verifiable without exposing an active capability before the atomic release exists.
- Generation N+1 requires fresh live readback of all three prior refs: claim -> release terminal -> retired-capability reveal. A copied or resealed JSON receipt is insufficient.
- Dispatch binds exact message SHA-256, channel, and compensation-path digest/category. The dispatch terminal burns this custody generation into `DISPATCHED_OUTCOME_UNKNOWN`; it still does not grant provider-send authority.
- Confirmed provider acceptance may be recorded in a deterministic `CONTACTED` branch using only a provider-receipt digest.
- All sealed plans/intents/receipts use exact field sets. Unknown fields such as `approved=true` are rejected even if an attacker recomputes the unkeyed integrity seal.
- Every public plan/receipt keeps `external_send_authorized=false`, `provider_send_completed=false`, and `payment_or_revenue_inferred=false`.

## Connector transaction pattern

The Python module is intentionally an **offline planner/verifier**. The connector executor performs GitHub mutations, then feeds exact readback into the verifier. The executor must never substitute local clock, Slack visibility, or a cached receipt for GitHub ref readback.

### 1. Claim

1. Call `prepare_claim(...)` and persist the returned private capability through the required retention callback **before any GitHub mutation**.
2. Create a blob containing `plan["metadata_json"]` exactly.
3. Create a tree from the frozen `anchor_sha` tree that adds `plan["metadata_path"]` -> that blob.
4. Create one commit with **exactly `anchor_sha` as parent**.
5. Call `bind_claim_commit(plan, commit_sha)`.
6. Create `plan["branch_name"]` create-exclusively at that commit. If it already exists, this worker lost custody and must not send.
7. Fresh-read branch head, commit parent, and metadata bytes; compile `claim_receipt_from_readback(...)`.
8. Immediately before any later step, use `verify_claim_possession(...)` against another fresh readback plus the private capability.

### 2. Release without provider mutation

1. Only while exact claim possession is still proven, call `prepare_release_terminal(...)`.
2. Create its metadata blob/tree and a commit whose exact parent is the claim commit.
3. Create the deterministic terminal branch create-exclusively.
4. Fresh-read and compile `terminal_receipt_from_readback(...)`.
5. The capability remains private through this point.
6. Only after the live terminal receipt is proven `RELEASED_UNSENT`, call `prepare_release_reveal(...)`.
7. Create the reveal metadata commit with the **release terminal commit as exact parent**, create the deterministic reveal branch, and compile `release_reveal_receipt_from_readback(...)`.
8. A later worker may prepare generation N+1 only by supplying that reveal receipt **and** fresh live readbacks of the prior claim, terminal, and reveal refs.

If the release terminal lands but reveal publication fails, the contact remains safely blocked. Do not guess, skip generations, or disclose/reuse the secret through an alternate path.

### 3. Dispatch attempt

1. Prove current claim possession and call `prepare_dispatch_terminal(...)` with exact message SHA-256, channel, and a concrete paid/award compensation path.
2. Create the terminal commit with the exact claim commit as parent and create the same deterministic terminal branch create-exclusively.
3. Fresh-read and compile the terminal receipt.
4. The state is `DISPATCHED_OUTCOME_UNKNOWN`. There is no ordinary release or reacquire path from it.
5. Satisfy every separately required route, DNR, relationship, provider-turn, terminal-send-authority, and one-shot provider control. **This package alone never authorizes a provider call.**
6. If provider acceptance is independently confirmed, `prepare_contacted(...)` can compile a digest-only CONTACTED record.

## Paid-path parsing

Dispatch requires a concrete positive compensation path. Explicit free/negative language and zero amounts such as `$0 bounty` fail closed. The plaintext compensation path is never retained; public metadata contains only its SHA-256 and a bounded category.

## Validation

```bash
python -m py_compile \
  revenue/prospect_contact_capability_v2/__init__.py \
  revenue/prospect_contact_capability_v2/protocol.py \
  revenue/prospect_contact_capability_v2/test_protocol.py

python -m unittest -v revenue.prospect_contact_capability_v2.test_protocol
python -O -m unittest -v revenue.prospect_contact_capability_v2.test_protocol
```

The hostile suite covers deterministic collision seams, private-capability possession, copied public claims, ref movement, parent mismatch, metadata tamper, retention failure, shared release/dispatch terminal contention, zero/unpaid compensation, release-before-reveal secrecy, reveal lineage, wrong-secret reveal, exact next-generation reopening, stale claim/terminal/reveal readbacks, dispatch suppression, provider-receipt digesting, authority ceilings, resealed-document attacks, and unknown-field injection.
