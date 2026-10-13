# Muse Slack provider evidence v1

`muse_slack_provider_v1.py` closes the caller-supplied-snapshot part of Commons #14503 without inventing send authority or pretending Slack Web API history is append-only.

## What it proves

The adapter reads only four Slack Web API methods: `auth.test`, `conversations.info`, `conversations.history`, and `conversations.replies`. `auth.test` must identify workspace `T0BRETUB5TK`. `conversations.info` must identify direct-message conversation `D0C1U7TUZEC` whose peer is Muse user `U0C0TKRTQHZ`. History and thread replies are paginated to exhaustion over the canonical v2 collision window. Unsupported message subtypes, unattributable rows, malformed timestamps, cursor loops, incomplete pagination, and v2 message-bound overflow fail closed.

Slack Web API history exposes **current-visible state**, not an authenticated append-only event history. Ordinary edited messages are returned with an `edited` property; the adapter rejects any such row rather than authenticating changed text under its original message timestamp. Deleted messages are generally absent from `conversations.history`, so this transport cannot prove that a currently absent request/control/decision never existed or was not later deleted. The receipt therefore says `visibility_model=CURRENT_VISIBLE_SLACK_WEB_API_ONLY`, `deleted_history_authenticated=false`, and `requester_control_history_authenticated=false`.

The exact currently visible request event determines the requester Slack user. No caller-supplied requester identity is accepted.

The returned provider receipt retains hashes of the canonical current-visible snapshot and provider binding. `verify_provider_evidence()` does not trust those hashes by themselves: while the 30-second receipt is fresh, it re-reads Slack at the retained capture boundary and requires byte-for-byte semantic reproduction of the full payload.

The Slack bearer token is read from `MUSE_SLACK_TOKEN`; it is used only as an Authorization header for the fixed read-method allowlist and is never serialized into a receipt.

## Requester control wire

After an exact canonical v2 request is posted, the provider-observed requester can express a **currently visible** control with an exact message:

```text
MUSE PUBLICATION CONTROL v1
action=HOLD
request_id=<canonical request id>
publication_key=<64 lowercase hex>
candidate_sha256=<64 lowercase hex>
```

Allowed actions are `HOLD`, `WITHDRAW`, `CANCEL`, and `RESUME`.

While visible, `HOLD`, `WITHDRAW`, and `CANCEL` force `current_visible_effective_observation=HOLD` even if Muse also has an exact visible `SELECTED` line. `RESUME` never reuses an older visible selection: a later exact Muse decision is required. Any other requester-authored visible follow-up that mentions the exact request id but does not match the strict control wire also produces current-visible `HOLD` as ambiguous.

Deletion is intentionally **not** modeled as authenticated reactivation or withdrawal history. If a control is deleted, Slack Web API history may make that row indistinguishable from never-existing. The adapter exposes that limitation and therefore cannot use this control wire to mint durable terminal authority. Durable requester-control history requires a separately authenticated append-only/event/audit source.

## Deliberate authority ceiling

Provider authentication, deleted-history continuity, requester-control history, and retained receipt-ledger completeness are separate trust roots. This adapter does **not** accept caller claims for any of them.

For diagnostic observation only, it asks the canonical v2 engine what the currently visible fetched Slack evidence would say if the independent receipt ledger were complete. The canonical receipt from that counterfactual compile is never serialized. The provider receipt hard-codes:

- `deleted_history_authenticated=false`
- `requester_control_history_authenticated=false`
- `prior_receipt_ledger_authenticated=false`
- `terminal_election_authorized=false`
- `external_send_authorized=false`
- `side_effects_authorized=false`
- `requires_current_worker_lease_possession=true`
- `requires_fresh_provider_preflight=true`

Therefore even `current_visible_effective_observation=SELECTED` is provider-authenticated current-visible coordination evidence, not permission to send. A future terminal-current adapter must add separately reviewed authenticated append-only history/receipt-ledger sources (or equivalent replay- and deletion-resistant authority) and preserve worker-lease/provider-preflight gates.

## Test contract

`test_muse_slack_provider_v1.py` uses a fake read-only Slack boundary and covers provider identity mismatch, DM-peer mismatch, thread inclusion, pagination exhaustion, provider-byte change on verification, strict visible requester controls, ambiguous requester follow-up, Web-API `edited` metadata, Events-API `message_changed`, explicit deletion-history truth narrowing, stale evidence, token non-disclosure, and attempted authority/deletion-authentication bit forgery.

Production code contains no Slack send/update/delete endpoint and no email, payment, invoice, contract, award, or revenue mutation surface.
