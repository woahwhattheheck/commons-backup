# AI Governance Policy Evidence Core

Offline, buyer-neutral technical core for `MMSD-AI-GOVERNANCE-POLICY-ZHELIX-20260914` / Commons #14287.

It analyzes **exactly the AI-system rows supplied to it** across two independent risk axes: information/governance risk and operational/physical risk. It deliberately does **not** treat "AI" as a single policy class: an administrative drafting assistant can be low operational risk while an OT-linked model can trigger formal safety, fallback, monitoring, validation and change-control requirements.

## Inventory scope is deliberately non-authoritative

This buyer-neutral library has no independently retained enterprise inventory census and therefore does **not** claim that caller-supplied rows are a complete inventory. `inventory_id` and `inventory_generation` are bound into the receipt for replay/audit identity, but they are caller metadata, not completeness authority.

Accordingly:

- report schema v2 fixes `inventory_scope` to `CALLER_SUPPLIED_ROWS_ONLY`;
- `inventory_completeness` is always `NOT_ASSERTED_BY_ENGINE`;
- a clean non-empty subset reports `SUPPLIED_ROWS_ANALYZED`, never a whole-inventory `READY` state;
- an empty input reports `NO_SYSTEMS_SUPPLIED`;
- rows with unresolved governance evidence produce `HOLD_SUPPLIED_ROWS`;
- conflicting generations for one `system_id` produce `HOLD_CONFLICT`.

A deployment that wants a whole-inventory readiness claim must establish a caller-unmintable inventory authority outside this library and must not relabel these relative-analysis states.

The report is evidence state for owner review. It never authorizes a legal/public-records conclusion, vendor approval, operational release, contact, procurement action, payment, or revenue claim. `UNKNOWN` public-record/retention/data/physical facts fail closed into HOLD conditions rather than being guessed.

Key properties:
- exact schemas and exact built-in types;
- duplicate-key and non-finite JSON rejection;
- deterministic canonical JSON and SHA-256 receipt;
- exact replay collapse plus same-ID/different-generation conflict evidence;
- explicit caller-supplied scope and non-assertion of inventory completeness;
- risk-derived control requirements;
- safety/override/manual-fallback requirements for operationally influential systems;
- independent recomputation verifier;
- no network/provider calls.

The buyer-specific Madison proposal remains separately held until the exact controlling District RFP PDF/addenda and bidder qualifications are recovered. This package is not legal advice and does not claim to satisfy Wisconsin public-records law.
