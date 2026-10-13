# Procurement Response Module Library

Deterministic, evidence-bound reuse for RFP/RFQ/procurement response material. The compiler prevents an old answer from becoming a current claim merely because it was copied into a new proposal.

The catalog carries 11 reusable response families: corporate capability, AI/data governance, cybersecurity, accessibility, implementation/delivery, SLA/support, staffing, references/past performance, pricing assumptions, subcontractor/partner matrix, and compliance crosswalk. Each module is versioned, owner-reviewed, time-bounded, tagged for applicability, and made only of claims with explicit evidence IDs. Evidence has a source reference, SHA-256, observation time, and state (`SUPPORTED`, `PARTIAL`, `MISSING`, or `NOT_APPLICABLE`).

A solicitation declares its required sections and tags. The compiler chooses the highest eligible module revision deterministically. Required sections fail closed to `HOLD` if no module matches, owner review is pending/denied, or any cited evidence is not supported. Optional sections may HOLD without blocking the whole packet.

`OWNER_REVIEW_READY` is **not** submission approval. Packet and receipt hard-code all of these as `false`: buyer contact, submission, signature, certification, price commitment, payment, and award/revenue recognition. External communication remains separately single-writer/Muse gated.

Strict input handling rejects duplicate JSON keys, floats/non-finite numbers, BOMs, invalid UTF-8, booleans in integer fields, duplicate module/evidence identities, future/stale evidence, unknown evidence references, and expired modules. Outputs are canonical JSON + Markdown + deterministic receipt. Verification recompiles from the exact input bytes and rejects any packet/Markdown/receipt tampering.

The included catalog/solicitation are **synthetic demo data only** and make no claim about TokenJunkieLabs, a buyer, references, certifications, acceptance, award, or revenue.

```bash
python -m revenue.procurement_response_module_library.engine compile \
  --library revenue/procurement_response_module_library/catalog.json \
  --solicitation revenue/procurement_response_module_library/solicitation.json \
  --out-dir /tmp/prm

python -m revenue.procurement_response_module_library.engine verify \
  --library revenue/procurement_response_module_library/catalog.json \
  --solicitation revenue/procurement_response_module_library/solicitation.json \
  --packet /tmp/prm/packet.json --markdown /tmp/prm/packet.md --receipt /tmp/prm/receipt.json
```

## Evidence materializer

`materializer.py` is an additive source-to-catalog adapter for owner-reviewed evidence descriptors. It accepts only strict, versioned records and emits a catalog compatible with the compiler plus a deterministic catalog diff and integrity receipt. It does **not** authenticate providers by itself and cannot authorize buyer contact, submission, signature/certification, price commitment, payment, award, or revenue.

A record carries exact source identity (`source_ref` + SHA-256), observation/expiry and module validity times, owner status, applicability tags, claim family/kind, and evidence state. Generic capability and policy claims can become `SUPPORTED` only from explicitly approved internal receipt/capability/policy source classes. Certification, customer/reference, SLA, and security-control claims are never promoted by this generic adapter. Their descriptors must name the stricter proof class (issuer-verified certification, reference-permission receipt, accepted-SLA receipt, or control-test receipt), but even an exactly named descriptor remains `PARTIAL`/`PENDING` with `SPECIALIZED_AUTHORITY_REQUIRED` until a separate authority-bearing adapter validates that evidence class. Weaker source classes, non-approved owner state, non-supported evidence state, expiry, sensitive-claim wording under a generic claim kind, and synthetic fixtures also HOLD. This prevents schema relabeling from turning a self-authored descriptor into a certification, reference, SLA, or security-control assertion.

The repository fixture `synthetic_materializer_source.json` deliberately remains HOLD-only and asserts no corporate fact. Real evidence descriptors should be produced only from separately approved retained evidence; do not convert a self-authored claim into evidence merely to satisfy the schema.

```bash
rm -rf /tmp/prm-materialized
python -m revenue.procurement_response_module_library.materializer compile \
  --source revenue/procurement_response_module_library/synthetic_materializer_source.json \
  --out-dir /tmp/prm-materialized

python -m revenue.procurement_response_module_library.materializer verify \
  --source revenue/procurement_response_module_library/synthetic_materializer_source.json \
  --catalog /tmp/prm-materialized/catalog.json \
  --diff /tmp/prm-materialized/diff.json \
  --receipt /tmp/prm-materialized/receipt.json
```

For a catalog-generation comparison, pass `--previous <catalog.json>` to both commands. Diff identity is content-based and reports added/removed/changed evidence and module IDs deterministically; it is an owner-review change surface, not approval to publish or submit anything externally.
