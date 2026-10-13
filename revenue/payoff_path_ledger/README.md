# Payoff-path ledger

This package makes one internal operating rule deterministic: **uncompensated work needs a retained payoff/conversion path, or a bounded strategic exception**.

It classifies exact work generations across bug bounties, competition prizes, paid discovery, partner workshare, product conversion, already-paid work, and strategic-unpaid work. `AMOUNT_UNKNOWN` is explicit and is never treated as zero.

## External evidence and completeness trust roots

A packet does not become bounty, paid-work, settled, duplicate-free, or complete merely by labeling itself that way.

Every external `term_evidence` and `outcome_evidence` row carries `auth_tag_hex`: HMAC-SHA256 over the complete normalized row under the **host-retained** `PAYOFF_PATH_EVIDENCE_AUTHORITY_KEY_HEX` capability. The tag binds exact work ID/generation, source ID/SHA, class/kind, observation/currentness, and economics. Relabeling, reminting, transplanting, or changing economics without an authority retag fails closed.

Positive readiness also depends on negative-space evidence: no omitted settlement, duplicate/custody conflict, or contradictory term. Therefore `evidence_scope_status = COMPLETE` is never trusted by itself. A COMPLETE packet must carry a host-authenticated `scope_attestation` binding:

- exact `subject_work_id` and `subject_generation_sha256`;
- an exact census-source ID and SHA-256 generation;
- SHA-256 of the complete term/outcome evidence census, including row authentication tags;
- observation time and validity boundary.

Removing only a signed adverse row changes the census digest and invalidates the completeness attestation even though all remaining row tags still verify. Missing, forged, stale, expired, future, wrong-subject, or wrong-census completeness authority yields `HOLD_INCOMPLETE_EVIDENCE`. `PARTIAL` packets cannot carry a completeness attestation and also hold incomplete.

The host key is never accepted from packet/API/CLI arguments and is never emitted. Receipts retain only SHA-256 of the active key. The compiler intentionally has no signing CLI: an evidence authority must authenticate source facts and census completeness outside the packet-ingest path, then issue the tags.

**Initialization boundary:** `PAYOFF_PATH_EVIDENCE_AUTHORITY_KEY_HEX` must be present and valid **before the payoff-path module/process is imported or the CLI process starts**. The module samples that authority generation once into a private closure-owned trust generation used by evidence-tag validation and public compile/verify paths. The decoded key is not retained in public or trust-bearing function defaults/kwdefaults or as a module-global authority binding. Changing, removing, or corrupting the environment variable after initialization does not rotate signing authority. Rotation requires a fresh trusted process/module initialization; an in-process environment write is never authority. Ordinary module-name and function-default replacement is in scope and must not replace the captured evidence authority. Direct closure-cell/code-object rewriting or arbitrary interpreter-memory inspection is outside this in-process boundary; callers requiring that threat model must be isolated in another process.

## Bounded strategic/product conversion

`PRODUCT_CONVERSION` without authenticated cash terms and every `STRATEGIC_UNPAID` lane require a nonempty conversion milestone, a strictly positive effort ceiling, and an expiry/review boundary. A positive plan-only state still requires authenticated census completeness, because readiness depends on the absence of settlement/duplicate/conflicting evidence. The compiler validates retained structure/provenance; it **does not establish that a milestone is realistic, likely, externally accepted, or economically attractive**.

Exact-generation `SETTLED` dominates attractive payoff evidence. An active duplicate/custody conflict also blocks readiness. Current verification re-evaluates row and completeness currentness against a process-clock capability captured when the public API is built; assigning a later module `_NOW` name cannot rewind it.

## Strict ingress

Both parsed JSON and direct Python-object ingress are bounded before policy evaluation:

- exact built-in JSON types only;
- duplicate-key, float/nonfinite, unsafe integer, invalid UTF-8/lone-surrogate refusal;
- per-container row bound;
- maximum JSON nesting depth and total graph-node budget;
- recursive overflow normalized to `GateError` rather than leaking raw `RecursionError`.

Canonicalization and trust-bearing validators/compilers retain their intended dependency generation rather than re-resolving mutable module globals. Public ingress and verification surfaces are exact-signature APIs: `loads_strict_json(raw)`, `verify_integrity(packet, receipt)`, `compile_current(packet)`, and `verify_current(packet, receipt)` do not accept caller-selected parser/compiler/verifier dependencies.

## Authority ceiling

Positive states are internal policy states only. Authority is emitted from source-literal exact-false booleans and verified with exact bool type identity. It does not authorize contact, Muse election/consume, acceptance of terms, contract/signature, bounty/competition submission, invoice/receivable creation, payment/funds movement, cash or revenue claims, tax/accounting conclusions, or provider/account mutation. The implementation performs no network I/O.

## CLI

```bash
python -m revenue.payoff_path_ledger compile packet.json --out receipt.json
python -m revenue.payoff_path_ledger verify-integrity packet.json receipt.json
python -m revenue.payoff_path_ledger verify-current packet.json receipt.json
```

`compile` uses create-exclusive output and refuses to overwrite an existing file. `example.json` is intentionally a no-secret `PARTIAL` strategic packet; it compiles to `HOLD_INCOMPLETE_EVIDENCE`, demonstrating that a local caller cannot mint completeness without evidence-authority participation.
