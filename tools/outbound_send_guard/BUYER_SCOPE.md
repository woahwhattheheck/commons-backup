# Explicit buyer-scope outbound dedupe

`guard.py` is the authoritative offline outbound-email authority gate. It is intentionally exact-recipient scoped: mailbox rows match only when `counterparty == intent.recipient`, and Slack rows match only when `recipient == intent.recipient`.

That is the safest primitive, but it is not sufficient when a verified buyer has more than one legitimate email route. A provider-SENT copy of `offer-a` to `info@buyer.example` must be able to fence a later proposed net-new `offer-a` send to `ceo@buyer.example` **only when those addresses have already been explicitly verified as routes for the same buyer**.

`buyer_scope.py` supplies that explicit aggregation layer without changing `guard.py`.

## Scope contract

A buyer scope is caller-supplied JSON:

```json
{
  "schema_version": "outbound-send-buyer-scope/v1",
  "scope_id": "buyer-123",
  "members": [
    {
      "email": "ceo@buyer.example",
      "mailbox_complete": true,
      "mailbox_query_id": "gmail-ceo-query-1",
      "slack_complete": true,
      "slack_query_id": "slack-ceo-query-1"
    },
    {
      "email": "info@buyer.example",
      "mailbox_complete": true,
      "mailbox_query_id": "gmail-info-query-1",
      "slack_complete": true,
      "slack_query_id": "slack-info-query-1"
    }
  ]
}
```

The membership list is evidence, not discovery. The caller is responsible for verifying that every member belongs to the same buyer/account and that every per-member mailbox and Slack lookup covers the same intended snapshot boundary.

The companion deliberately does **not** infer buyer identity from a shared email domain, display names/signatures, local parts such as `info`/`sales`/`ceo`, website ownership, organization-name similarity, redirects, MX records, or other network metadata. The intended recipient must itself be a declared member. Normalized duplicate members are rejected.

## Completeness and decision rules

The base `outbound-send-evidence/v1` snapshot must already claim complete mailbox and Slack coverage. In addition, **every declared buyer-scope member** must carry `mailbox_complete=true` and `slack_complete=true`.

If any declared member is incomplete, the transformed evidence is marked incomplete before it reaches the core guard, so the result fails closed as `HOLD`.

The wrapper deep-copies source evidence. Only rows whose normalized email is an explicitly declared scope member are rebound to the intended recipient. Undeclared addresses remain untouched and cannot widen authority.

The unchanged core guard then decides:

1. hard DNR on any declared route -> `DO_NOT_RESEND`;
2. incomplete/stale/future/conflicting/non-authoritative evidence -> `HOLD`;
3. newer buyer inbound on any declared route -> `REPLY_ONLY`;
4. same-offer outbound evidence on any declared route -> `DO_NOT_RESEND`;
5. different recent outbound on any declared route -> core cross-offer cooldown / `HOLD`;
6. only a complete aggregate with no blocking outbound state -> `ALLOW_NEW`.

No wrapper rule can turn a core denial into send authority.

## Source-custody API

Receipt schema v2 separates **canonical object integrity** from **exact consumed-byte custody**.

### Parsed-object API

```python
receipt = buyer_scope.evaluate(intent_obj, evidence_obj, scope_obj)
```

`evaluate()` accepts only the three parsed objects. At API entry it canonicalizes each caller-owned object exactly once, strict-reparses those bytes into detached local graphs, and performs scope parsing, evidence rebinding, core evaluation, member projection, and source hashing only from those detached snapshots. A later caller mutation therefore cannot splice one semantic generation with another generation's object digest. It derives all source object digests itself and emits `custody_mode="canonical_objects"` with `byte_custody: null`. There are no caller-supplied digest override parameters.

This mode does **not** claim raw-file byte custody. Two JSON byte streams that parse to the same object have the same canonical object digest. The one-time canonicalization is an internal generation boundary, not proof of external provenance or freedom from mutation before that serialization completed.

### Exact-byte API

```python
receipt = buyer_scope.evaluate_bytes(intent_bytes, evidence_bytes, scope_bytes)
```

`evaluate_bytes()` requires actual `bytes`, strict-parses those exact byte sequences through the existing duplicate-key/non-finite-safe guard parser, hashes those same bytes internally, and then evaluates the parsed objects. Its receipt sets `custody_mode="exact_consumed_bytes"` and includes exact SHA-256 values for the three consumed byte streams in addition to canonical object digests.

Whitespace/key-order-equivalent JSON therefore keeps the same object digest but receives a different raw-byte digest. This proves which bytes this local call consumed; it does **not** independently authenticate where those bytes came from.

The CLI uses `evaluate_bytes()`, so CLI byte digests cannot be overridden by caller-provided hash strings.

## Receipt

The wrapper emits `outbound-send-buyer-scope-receipt/v2` and binds:

- normalized, deterministically sorted explicit members;
- each member's mailbox/Slack completeness claim and query ID;
- canonical digests of the intent, source evidence, buyer scope, and transformed scoped evidence;
- exact consumed-byte digests only when the exact-byte API/CLI actually consumed those bytes;
- the complete core guard payload and its digest;
- the final receipt digest.

`side_effects_authorized` is always `false`.

## CLI

```bash
python -m tools.outbound_send_guard.buyer_scope \
  --intent intent.json \
  --evidence evidence.json \
  --scope buyer_scope.json \
  --out receipt.json
```

The three inputs must be distinct. The output may not alias any input. JSON parsing is strict through the existing guard parser. The CLI reads each input once for evaluation, and the same bytes that are parsed are the bytes whose SHA-256 values appear under `byte_custody`. File output remains atomically published.

Exit codes mirror the core guard:

- `0` — `ALLOW_NEW`
- `3` — `REPLY_ONLY`
- `4` — `HOLD`
- `5` — `DO_NOT_RESEND`
- `2` — malformed/unsafe input

## Boundary

This is an offline authority projection only. It does not query Gmail or Slack, send mail, resolve identities, infer domains, contact buyers, create leases, schedule work, mutate campaigns, or grant send authority. A caller still needs independently verified scope membership and complete provider/workspace evidence.

The receipt is an integrity/custody artifact, not an external attestation. It does not prove that the caller's buyer membership, provider evidence, or source bytes were independently trustworthy merely because hashes are internally consistent.