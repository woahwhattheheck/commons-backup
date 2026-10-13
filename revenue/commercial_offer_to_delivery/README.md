# Commercial offer → scope-to-delivery bridge

This package closes the evidence boundary between the landed
`revenue/commercial_offer_contract` rail and the existing
`host/scope_to_delivery.py` composer.

It does **not** infer buyer acceptance from a sent offer. A commercial offer's
`BUYER_ACCEPTANCE_EVIDENCE_CAPTURED` state intentionally leaves
`buyer_acceptance_verified=false` and `fulfillment_authorized=false`.

## V2 exact-terms gate

V2 requires two buyer evidence layers before it can emit an accepted
`commons-scope-agreement/v1`:

1. the commercial-offer rail's evidence that the buyer accepted the exact
   commercial offer; and
2. separate evidence that the buyer accepted the SHA-256 of the **exact scope
   terms object** that `scope_to_delivery` will treat as written terms.

The second layer is stronger than accepting a schedule alone. The existing
scope-to-delivery terms digest covers all of these fields:

- canonical SKU;
- exact quote;
- service window;
- generated intake sentence;
- generated binary acceptance rows;
- exclusions; and
- `refund_choice`.

V1 derived several of those downstream fields after buyer offer acceptance and
therefore relied on semantic equivalence when emitting the downstream
`AUTHORIZED_OPERATOR_VERIFIED_EXACT_TERMS_ACCEPTANCE` attestation. V2 removes
that assumption. The buyer's scope evidence must carry the exact terms digest,
and the authorized-operator HMAC binds that evidence, the service window, the
commercial-offer contract digest, original offer-acceptance evidence, and buyer
identity verification.

V1 verification receipts fail closed under V2.

## Catalog and authority rules

V2 does not accept a post-hoc catalog mapping. The accepted commercial offer's
`opportunity_id` must already equal a canonical Commons catalog SKU. The
accepted USD total must equal that listing's exact two-decimal catalog total.

The agreement derives rather than retypes:

- opaque buyer identity;
- exact accepted price/currency;
- accepted deliverables and acceptance criteria;
- each deliverable's evidence commitment;
- accepted exclusions; and
- the exact accepted offer SHA-256.

`refund_choice` remains conservatively `UNKNOWN`; the bridge never invents a
refund promise. Raw destination/contact identity is not retained.

The strongest bridge state is `SCOPE_AGREEMENT_READY`. External send,
fulfillment, invoice/payment mutation, cash, and revenue-recognition authority
remain false.

## Example

```python
from revenue.commercial_offer_to_delivery import (
    build_scope_bridge,
    build_scope_terms,
    create_operator_verification,
    terms_digest,
)

service_window = {
    "start": "2026-09-14T13:00:00Z",
    "end": "2026-09-18T21:00:00Z",
    "timezone": "America/Kentucky/Louisville",
}

scope_terms = build_scope_terms(
    accepted_offer_contract,
    canonical_catalog,
    service_window,
)

scope_terms_acceptance = {
    "terms_digest": terms_digest(scope_terms),
    "accepted_at": "2026-09-13T10:05:00Z",
    "evidence_sha256": "...64 lowercase hex...",
    "identity_verification_sha256": "...64 lowercase hex...",
}

verification = create_operator_verification(
    accepted_offer_contract,
    owner_secret,
    acceptance_verification_secret,
    verifier_id="operator-001",
    key_id="acceptance-key-v2",
    verified_at="2026-09-13T10:06:00Z",
    public_ref="p/accepted-scope-terms.md",
    catalog=canonical_catalog,
    service_window=service_window,
    scope_terms_acceptance=scope_terms_acceptance,
    trusted_now="2026-09-13T10:10:00Z",
)

bundle = build_scope_bridge(
    accepted_offer_contract,
    verification,
    owner_secret,
    acceptance_verification_secret,
    catalog=canonical_catalog,
    trusted_now="2026-09-13T10:10:00Z",
)
```

The HMAC secrets are runtime inputs and are never embedded in output.

## Validation

From repository root:

```bash
python -m unittest discover -v -s revenue/commercial_offer_to_delivery -t . -p 'test_*.py'
python -O -m unittest discover -v -s revenue/commercial_offer_to_delivery -t . -p 'test_*.py'
python -m py_compile revenue/commercial_offer_to_delivery/*.py
```

Exact isolated-source evidence for V2 on 2026-09-13:

- 41/41 executable hostile/lifecycle tests PASS normally;
- 41/41 PASS under `python -O`;
- one landed-rail integration test is intentionally skipped only when the
  pre-existing Commons modules are absent from the isolated packet; in-repo CI
  runs it against the real commercial-offer and scope validators;
- deterministic exact-scope corpus: 256/256 PASS, manifest SHA-256
  `578c3b4756a558be73a62c0b8407d22a209935f47be0409fe3fcce8144740a70`;
- `py_compile` PASS.

No provider call, buyer contact, signature, fulfillment, checkout/payment,
invoice, cash assertion, or recognized-revenue action is performed.
