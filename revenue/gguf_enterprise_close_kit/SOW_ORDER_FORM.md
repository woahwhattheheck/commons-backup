# GGUF diagnostic — SOW / order-form content

**Offer:** `gguf-diagnostic-10d-12k`  
**Fee:** $12,000 USD fixed  
**Term:** 10 calendar days after start-gate completion  
**Target:** one customer-controlled GGUF + one runnable customer evaluation harness  
**Acceptance:** rollback evidence, not metric lift

## Start gates

Work begins only after the customer and provider have separately completed the real-world legal/private steps: executed NDA, executed SOW/order form, customer confirmation of lawful control of the GGUF, runnable harness availability, and M1 payment evidence. Commons records only secret-free booleans + digests; it does not store signatures, customer files, private contact data, tax data, credentials, processor details, or bank data.

## Milestones

1. **M1 — $6,000:** due after NDA + SOW execution and **before** customer file exchange.
2. **M2 — $6,000:** due on AT1–AT6 acceptance. The compiler can prove only that the evidence packet is ready for that acceptance decision; it cannot make or infer the customer’s legal acceptance.

The compiler's `READY_FOR_OWNER_M2_ACCEPTANCE_REVIEW` state is evidence readiness only. It is not legal acceptance, an invoice, payment, cash, or recognized revenue.

## Included deliverables

- source-hashed baseline receipt for the supplied GGUF;
- reproducible baseline harness run;
- one bounded diagnostic ablation/intervention selected during the engagement;
- ablated artifact hash + harness run;
- byte-exact restoration + restored artifact hash + harness run;
- concise finding describing what was shown, measured, limitations, and rollback consequence;
- final digest-only evidence/receipt packet plus operator-readable report.

## AT1–AT6 acceptance evidence

- **AT1 — original hash:** SHA-256 recorded before edit.
- **AT2 — ablated hash different:** ablated SHA-256 differs from AT1.
- **AT3 — byte-exact restore:** restored SHA-256 equals AT1.
- **AT4 — customer harness logs:** baseline, ablation, restore run evidence exists.
- **AT5 — concise finding:** written finding is delivered.
- **AT6 — receipt:** final receipt binds artifact/evidence hashes.

No metric improvement is promised or required. Benchmark metrics are observations; acceptance is the reproducible rollback evidence above.

## Excluded / customer-retained authority

No model training, hosted production serving, guaranteed metric lift, unbounded architecture redesign, public binary publication, transfer of Commons/TITAN/foundry assets, buyer procurement representation, legal/tax advice, or production credential handling. Customer retains model ownership/control, harness ownership, evaluation-case authority, deployment decisions, production approval, and interpretation of business impact.

## Privacy / security boundary

Customer model bytes and harness payloads/logs remain on the agreed private transfer/execution surface. Public Commons may contain only non-confidential labels, booleans, aggregate metrics, and SHA-256 references. Never paste keys, passwords, private contacts, bank/card/tax details, signatures, confidential cases, or model bytes into Commons/Slack/public issues.

## HOLD / stop conditions

Pause before file exchange if any start gate is absent. Stop and preserve the original if legal control becomes uncertain, the harness cannot reproduce baseline, artifact identity is ambiguous, rollback cannot be demonstrated, or requested publication would expose customer/model secrets. AT1–AT6 incomplete means HOLD, not acceptance. Any refund/credit question is an owner/provider commercial decision outside this compiler; the kit can surface the HOLD and evidence, but cannot execute or promise a refund.

## Expansion

Only after a real paid 10-day engagement reaches AT1–AT6 evidence completion may the same GGUF be discussed for the separate **$30,000 / 30-day White Box pilot**. This is an expansion option, not automatic acceptance, renewal, or buyer commitment.
