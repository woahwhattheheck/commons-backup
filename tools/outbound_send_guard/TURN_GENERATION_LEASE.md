# Outbound turn-generation lease

`turn_generation_lease.py` closes the reply-generation race that remains after an ordinary buyer/offer possession lease. It is a **prerequisite only** and never authorizes an external send.

## The race it closes

A complete preflight can be correct for two workers at the same instant. If both workers read the same latest inbound provider event before either provider-SENT receipt becomes visible, both can compose and send replies. The provider thread has one human/provider generation but two locally-valid actors.

The turn-generation lease makes the provider generation itself the atomic seam:

```
(provider, account_scope, provider_thread_id, latest_inbound_message_id)
```

Recipient route, worker identity, intent and body are deliberately **not** part of the seam. Changing an address alias or prose cannot mint another turn. A genuinely newer inbound message ID creates a new seam and can legitimately be claimed later.

## Connector-native acquisition

1. Build the strict turn claim. It binds `send_intent_sha256`, `body_sha256` and the ordinary preflight digest.
2. `prepare_acquisition()` creates a 256-bit turn capability and invokes the private retention callback **before** any provider mutation. Only the SHA-256 commitment is public.
3. Create the metadata blob/tree/off-main commit described by the public plan, with the exact frozen `anchor_sha` as parent.
4. Create the deterministic `outbound-turn-generation-v1/<seam_sha256>` branch **exclusively**. This create is the atomic provider event. Do not force-update it and do not retry under a new route/body/worker seam.
5. Read the branch, parent and metadata back. `receipt_from_readback()` holds unless all three are exact.
6. Immediately before a separately-authorized provider send, re-read the same branch/metadata and obtain fresh provider-thread history. `finalize_turn()` returns `TURN_READY_FOR_POLICY` only when:
   - the caller still knows the private capability;
   - the live branch/parent/metadata still match;
   - provider history is `COMPLETE` (not unknown/throttled);
   - the bound inbound message is still the latest inbound generation; and
   - no provider-SENT event exists after that bound inbound.
7. **Still run every ordinary outbound policy gate.** `external_send_authorized` is hard-false in every plan, intent, receipt, finalization and result object. `TURN_READY_FOR_POLICY` means only “this exact generation remains unsent and this worker still possesses it.”
8. After an independently-authorized provider attempt, bind `SENT`, `BOUNCE`, `REJECTED` or `UNKNOWN` with `record_provider_result()`.

## Fail-closed rules

- Unknown/throttled provider history is `HOLD`, never “probably clean.”
- A newer inbound message invalidates the old-generation finalization; acquire the new generation instead.
- Any provider send after the bound inbound invalidates the turn, even if it came from another worker.
- Public metadata/receipts cannot prove current-worker possession without the private capability and fresh live readback.
- Route aliases cannot mint another generation claim.
- No auto-expiry, branch deletion or force-update is part of this contract.
- Content-addressed receipts prove internal binding, not independent remote attestation.

## Composition

This control complements the existing buyer/offer leases under `tools/outbound_send_guard/`. It does **not** replace buyer/offer ownership, DNR/cooldown, route-health, content review, provider authorization, commercial authority or legal/compliance checks. A production caller should require both the relevant higher-level possession/policy evidence and a fresh turn finalization before crossing the provider boundary.
