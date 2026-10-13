# Route-aware outbound quarantine gate

`route_quarantine.py` composes the existing current outbound send guard with complete, source-reconciled route lifecycle evidence. It is read-only and offline, never a sender.

`guard.py` decides duplicate-send, cooldown and DNR restrictions from complete recipient-scoped mailbox and Slack evidence. `route_lifecycle.py` classifies one exact provider-SENT message's event facts. The quarantine layer requires route coverage for every supplied outbound and, before consuming a DSN classification, reconciles those event facts against separately retained raw MIME and binding through `dsn_authority.authoritative_receipt`.

A hash of a caller-authored event is not source authority. This is the source repair tracked in Commons #15870, preserving the original Z-Sol issue/defect, Solstice quarantine semantics and Z-RelayDSN-2317 recovery credit. Implementation/finalization: yZ-Cairn-73.

## Inputs and coverage

The existing inputs remain:

1. a strict `outbound-send-intent/v1`;
2. `outbound-send-evidence/v1` accepted by the current `guard.py`;
3. an `outbound-route-quarantine-bundle/v1` object:

```json
{
  "schema_version": "outbound-route-quarantine-bundle/v1",
  "recipient": "buyer@example.com",
  "as_of": "2026-09-13T15:00:00Z",
  "route_checks": []
}
```

The date above is illustrative, not a current capture. The bundle and send evidence must share the exact `as_of/generated_at` boundary. Every recipient-scoped provider outbound in mailbox evidence requires exactly one complete `outbound-route-lifecycle-evidence/v1` check at that boundary. Slack `sent` evidence must identify a provider message present in mailbox evidence. Missing, extra or duplicate checks; recipient/provider/send-time drift; incomplete captures; and unbound Slack sends fail closed.

The additional keyword argument `dsn_sources_raw` / CLI `--dsn-sources` is a **separate retained capture input**, not a field inside a route event or a reconstruction of that event's claimed source. It is a JSON object with exactly one field, `sources`, whose value is a list. Each source object has exactly:

- `raw_mime_base64`: canonical standard base64 of the complete independently retained MIME bytes, without whitespace or line breaks;
- `binding`: the original `outbound-dsn-binding/v1` object, with `schema_version`, `source_id`, `provider_message_id`, `original_rfc822_message_id`, `recipient`, `sent_at` and `captured_at`;
- `receipt`: the complete existing `outbound-dsn-normalizer-receipt/v1` generated from those source bytes and binding.

An empty retained capture is represented by `{"sources": []}`. Do not synthesize missing MIME, copy event facts into a fake binding, or drop a retained source to obtain a different result. Base64 is transport encoding, not encryption. Keep captures private; the quarantine output contains source identities/digests, not raw MIME.

The module delegates all DSN parsing and receipt recomputation to the existing authority module. It then requires the recomputed event to match the route's recipient/provider send and exact send time, requires capture time no later than the bundle boundary, and rejects duplicate retained source/event identities. Invalid base64, malformed/mismatched normalizer receipts, bad MIME or out-of-scope bindings produce an error with no compiled decision.

## Event reconciliation

Every claimed DSN event must equal the **complete canonical event** returned by source recomputation: event ID, kind, provider message, recipient, observed time, source ID, source digest, SMTP code and enhanced status. Equivalent-looking edits or a freshly rehashed claim do not establish equality.

Every supplied retained DSN event for a provider message must also occur in that message's check. Omitting or substituting one creates a source-authority problem and forces that check's effective decision to `HOLD_ROUTE`. A DSN claim with no matching retained source likewise holds. Existing exact duplicate event handling remains with the lifecycle classifier.

Delivery, complaint and unsubscribe event facts currently have no retained-source adapter in this composer. They remain visible but force `HOLD_ROUTE`; they cannot create a fabricated terminal block, override a sourced DSN, or clear a transient failure just by declaring later delivery. This does not relax genuine opt-out/DNR restrictions: the independent send guard's terminal `DO_NOT_RESEND` always remains terminal.

Legacy three-input calls remain callable. Event-free complete checks keep their existing unconfirmed classification. Checks containing DSN or other event claims without the required source authority now hold rather than being trusted. Integrations using those events must pass the separate retained source input; no silent legacy-authority fallback exists.

**Completeness limit:** this reconciles the supplied independent capture set, not an authenticated provider inventory. If a caller omits a source from both the independent collection and the route check, this offline module cannot discover it. Accurate provider capture, binding provenance, complete lookup declarations and controlled source custody remain operational prerequisites. Recomputing MIME semantics or matching an unkeyed digest does not authenticate a provider, mailbox owner or recipient intent.

## Decision composition

For each check, `claimed_lifecycle_decision` records the classifier's result from its supplied facts. `decision` is the effective result after source reconciliation. Downstream consumers must use the outer decision/effective decisions, not promote the diagnostic claim or its hash back into authority.

- A terminal send-guard `DO_NOT_RESEND` is preserved regardless of route state.
- Otherwise, any source-admitted `BLOCK_ROUTE` yields `DO_NOT_USE_ROUTE`.
- Otherwise, any lifecycle or source-reconciliation `HOLD_ROUTE` yields `HOLD`.
- Otherwise the original send-guard decision is preserved under `CLEAR` route state.

Each route entry records source-authority problems, matched event IDs and the existing recomputed DSN source/binding/receipt identities. The parser and lifecycle classifier are unchanged; this module does not invent another DSN interpretation or a positive send permission.

A blocked route concerns the **exact recipient route only**. It creates no alternate-contact task or obligation. In every state, `alternate_route_research_required=false`, `research_obligation=null`, `same_route_send_authorized=false` and `side_effects_authorized=false`. `alternate_route_send_requires_fresh_preflight=true` remains invariant. Any deliberate independently authorized alternate-route investigation starts outside this receipt, with fresh sourcing and then-current coordination/send/provider controls; this module neither selects nor researches that route.

## Receipt, CLI and verification

The existing output schema remains `outbound-route-aware-send-receipt/v1`, with additive source-reconciliation fields. The receipt binds detached JSON generations of intent, send evidence, route bundle and the separately supplied DSN source collection, plus the existing send/lifecycle/DSN receipt identities. `dsn_sources_sha256` is null only when no independent input was supplied. A present empty collection is distinct from an absent input.

The CLI prints the canonical result to stdout and performs no output-file mutation:

```bash
python -m tools.outbound_send_guard.route_quarantine \
  --intent intent.json \
  --send-evidence evidence.json \
  --route-bundle route-bundle.json \
  --dsn-sources retained-dsn-sources.json
```

Verification supplies the same independent inputs plus `--receipt receipt.json`, or calls `verify(receipt, intent, evidence, bundle, dsn_sources_raw=sources)`. It recomputes the complete result and compares canonical bytes; removing/changing the source collection or resealing an altered decision cannot substitute for that recomputation. The underlying send guard remains current-clock based, so this is not a promise that an old receipt will remain valid later. A refused or errored current check must not be relabeled as approval.

Exit codes remain: `0` ALLOW_NEW, `3` REPLY_ONLY, `4` HOLD, `5` DO_NOT_RESEND, `6` DO_NOT_USE_ROUTE; malformed or insufficiently scoped inputs return `2`. No exit code itself authorizes a send.

Each JSON input and direct API snapshot is bounded to 8 MiB; the limit includes base64 expansion and receipt/binding metadata. Each route-check/source list is capped at 10,000 rows. Inputs use the existing bounded regular-file, no-follow-where-supported reader and retained-descriptor generation checks. Use trusted package bytes and owner-controlled capture directories. No network fetch or credential access occurs.

## Authority ceiling

No Gmail/Slack/provider reads, sends, replies, contact discovery, DNR relaxation, buyer-intent inference, acceptance/payment claim, money movement or revenue recognition. No new workflow, regression suite, proof archive or receipt framework is required to use this product path.
