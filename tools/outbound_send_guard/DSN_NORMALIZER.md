# Delivery-status (DSN) normalizer

`dsn_normalizer.py` converts one raw RFC delivery-status notification into the strict `dsn` event shape accepted by `route_lifecycle.py`. `dsn_authority.py` is the required source-authority boundary before that event may be inserted into route-lifecycle evidence.

This closes the collector boundary exposed by live Gmail/Googlemail failures: mailbox records arrive as `multipart/report; report-type=delivery-status`, while `route_lifecycle.py` deliberately accepts only normalized evidence.

Both modules are evidence-only. They never send mail, classify a route, authorize a retry, or mutate provider state. Every normalizer receipt has `side_effects_authorized=false`.

## Binding input

The raw MIME is paired with one explicit `outbound-dsn-binding/v1` object:

```json
{
  "schema_version": "outbound-dsn-binding/v1",
  "source_id": "dsn-provider-record-id",
  "provider_message_id": "original-provider-send-id",
  "original_rfc822_message_id": "<original-message-id@example>",
  "recipient": "buyer@example.com",
  "sent_at": "2026-09-13T09:26:31Z",
  "captured_at": "2026-09-13T09:27:00Z"
}
```

The binding separates provider identity from RFC message identity. The normalizer never guesses a provider message id from the bounce.

## Fail-closed extraction contract

The raw message must:

- be at most 10 MiB and parse without MIME defects;
- be `multipart/report` with `report-type=delivery-status`;
- contain exactly one `message/delivery-status` part;
- bind the expected original RFC Message-ID through `X-Original-Message-ID`, `In-Reply-To`, or both; every present supported binding must agree;
- contain exactly one per-recipient block whose `Final-Recipient` matches the expected route (case-insensitive);
- use `rfc822` recipient addressing;
- carry `Action: failed` + `5.x.x`, or `Action: delayed` + `4.x.x`;
- carry `Diagnostic-Code: smtp; ...` with one unambiguous 4xx/5xx SMTP code whose class agrees with `Status`;
- have an outer `Date` between the original send and capture boundary.

A multi-recipient DSN is allowed only when the expected route matches exactly one block. Other recipient blocks are not emitted. Duplicate targets, a missing target, conflicting original-message bindings, malformed status, multiple SMTP codes, unsupported diagnostics, or time-boundary violations fail closed.

The emitted event contains only a deterministic content-addressed `event_id`, `kind=dsn`, exact provider message id, normalized recipient and observation time, source id/raw SHA-256, SMTP code, and enhanced status. Diagnostic prose, remote-host text, and arbitrary MIME payload are intentionally excluded from authority evidence.

## Integrity is not authority

`outbound-dsn-normalizer-receipt/v1` binds the raw-source digest, binding digest, original-message binding sources, recipient-block cardinality, normalized event/event digest, and final receipt digest.

**`dsn_normalizer.verify_receipt()` is integrity-only.** It checks receipt shape, caller-supplied hashes, and the no-side-effects invariant. Because all of those values are carried inside the receipt, a caller can change a normalized fact and refresh every self-hash. Therefore `verify_receipt()` MUST NOT by itself satisfy route-lifecycle evidence authority.

The authoritative consumption boundary is:

```python
from tools.outbound_send_guard.dsn_authority import authoritative_event

event = authoritative_event(receipt, raw_mime, trusted_binding)
```

`raw_mime` and `trusted_binding` must be supplied independently from the trusted capture boundary, never reconstructed from receipt fields. `dsn_authority.authoritative_receipt()` first performs the integrity precheck, then re-runs the complete fail-closed normalizer on snapshots of those independent inputs and requires the entire canonical recomputed receipt to equal the claimed receipt. `authoritative_event()` returns the event from that fresh recomputation, not from the caller's receipt object.

**Only an event returned by `authoritative_event()` is eligible for insertion into an `outbound-route-lifecycle-evidence/v1` envelope.** The route-lifecycle classifier remains responsible for `BLOCK_ROUTE` / `HOLD_ROUTE` / `DELIVERED`; neither DSN module grants send/resend permission.

## CLI

```bash
python -m tools.outbound_send_guard.dsn_normalizer \
  --raw-mime dsn.eml \
  --binding binding.json \
  --out dsn-receipt.json
```

CLI output publication is staged, fsynced, and atomically replaced. A downstream consumer must still apply the authoritative source recomputation above before classifying the event.

## Regression gate

```bash
python -m py_compile \
  tools/outbound_send_guard/dsn_normalizer.py \
  tools/outbound_send_guard/dsn_authority.py \
  tools/outbound_send_guard/test_dsn_normalizer.py \
  tools/outbound_send_guard/test_dsn_authority.py

python -m unittest -v \
  tools.outbound_send_guard.test_dsn_normalizer \
  tools.outbound_send_guard.test_dsn_authority

python -O -m unittest -v \
  tools.outbound_send_guard.test_dsn_normalizer \
  tools.outbound_send_guard.test_dsn_authority
```

Coverage includes the observed Googlemail/Exchange `550 5.4.1` shape; multi-recipient and message-binding ambiguity; 4xx delay; action/status/SMTP mismatches; capture-time, MIME, schema, address and size bounds; stable identities/digests; side-effect escalation; and the authority discriminator from source review: a caller changes the normalized SMTP fact, recomputes the derived `event_id`, `event_sha256`, and `receipt_sha256`, passes the integrity helper, and still fails authoritative verification against the original raw MIME + trusted binding. A fully re-hashed fabricated source digest is rejected the same way.
