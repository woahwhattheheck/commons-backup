# Net-new outbound collision gate

`net_new_collision_gate.py` composes the existing buyer-scope dedupe preflight and connector-native v3 possession lease into one fail-closed decision for **net-new** email outreach.

It exists for the seconds-apart fleet race: two workers can both inspect the same hot lead before either provider send becomes visible. The repository already has strong primitives for complete mailbox/Slack dedupe (`buyer_scope.py`) and provider-backed mutual exclusion (`connector_capability_lease.py`), but treating those as separate green checkboxes leaves room for a worker to combine unrelated generations or skip the possession half.

Before acquiring the v3 lease, derive its two public seam tokens from the already-normalized buyer receipt:

- `buyer_scope = email-<sha256(normalized core recipient)>`
- `offer_scope = offer-<sha256(exact core offer_id)>`

This prevents independently named local buyer IDs from creating separate branches for the same target email and makes arbitrary offer text safe for the v3 machine-token contract. The gate emits `COLLISION_CLEAR` only when all of these are simultaneously true:

1. the exact `outbound-send-buyer-scope-receipt/v2` is untampered, `ALLOW_NEW`, and `authority=complete`;
2. its embedded core guard receipt is untampered and agrees on decision/authority;
3. the v3 lease receipt is structurally valid and says `LEASE_HELD`;
4. lease `buyer_scope` equals `email-<sha256(normalized target email)>`, so independent workers cannot evade the same-lead seam by inventing different local buyer IDs;
5. lease `offer_scope` equals `offer-<sha256(exact offer_id)>`, making arbitrary offer text a deterministic v3 machine token;
6. lease `preflight_sha256` equals the **exact buyer-scope receipt digest**, binding both artifacts to one preflight generation; and
7. `connector_capability_lease.verify_possession()` succeeds against the privately retained capability plus fresh live branch, parent, and metadata readback.

A copied winner receipt without the winner's raw capability is `HOLD`. Two individually-green artifacts for different target emails, offers, or preflight generations are `HOLD`. The v3 seam keys are derived from the normalized core recipient and exact offer ID rather than caller-supplied `scope_id`, so two workers targeting the same email/offer contend on one deterministic branch even if they chose different descriptive buyer IDs. Malformed/tampered public artifacts are invalid input, not a soft green.

`COLLISION_CLEAR` is deliberately **not** external-send authority. Every result keeps `external_send_authorized=false`; content, route health, owner/commercial authority, provider authorization, compliance and any other required controls remain separate.

## CLI

The raw v3 capability is accepted only from a regular owner-only file (no argv, no symlink, no group/world permissions on POSIX):

```bash
python -m tools.outbound_send_guard.net_new_collision_gate \
  --buyer-receipt buyer-scope-receipt.json \
  --lease-receipt v3-lease-receipt.json \
  --capability-file ./private/lease.cap \
  --live-branch-sha "$LIVE_BRANCH_SHA" \
  --live-parent-sha "$LIVE_PARENT_SHA" \
  --live-metadata live-lease-metadata.json \
  --out collision-receipt.json
```

Exit codes: `0 COLLISION_CLEAR`, `4 HOLD`, `2 malformed/tampered/unsafe input`.

## Regression gate

```bash
python -m py_compile tools/outbound_send_guard/net_new_collision_gate.py tools/outbound_send_guard/test_net_new_collision_gate.py
python -m unittest -v tools.outbound_send_guard.test_net_new_collision_gate
python -O -m unittest -v tools.outbound_send_guard.test_net_new_collision_gate
```

Hostiles cover caller-renamed buyer scopes, offer/preflight cross-generation splicing, non-ALLOW and partial evidence, unheld leases, copied public winner evidence with a wrong private capability, stale/drifted live readback, buyer-member/recipient mismatch, outer/core digest tamper, unknown fields, strict duplicate/non-finite JSON rejection, raw-capability non-disclosure, deterministic receipts, and a real v3 plan → bind → readback → default-verifier composition test.
