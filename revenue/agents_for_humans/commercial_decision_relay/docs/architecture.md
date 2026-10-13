# Architecture

```mermaid
flowchart LR
    A[Trusted normalized offer/reply evidence] --> C[Preload + lock]
    T[Caller-supplied trusted UTC] --> C
    C --> D[Deterministic evidence engine]
    C --> B[Strands orchestration agent]
    B --> E[reconcile_evidence tool]
    E --> D
    D --> F[All-false-authority receipt]
    F --> G{Decision queue}
    G -->|routine| H[Stay quiet]
    G -->|exact accept / counter / ambiguity / expiry / conflict| I[Human decision card]
    B --> J[verify_current_receipt tool]
    J --> D
    K[Audit hooks] -. hash-only tool audit .-> B
    I --> L[Human closer]
    L -. no execution capability .-> M[External contracting / payment systems]
```

## Trust and authority boundary

The model never determines commercial truth. The CLI preloads normalized evidence and caller-supplied trusted UTC before orchestration, then locks evidence ingestion for that run. Strands selects deterministic read/decision tools; the tools validate normalized evidence and produce a receipt. The model cannot replace the trusted batch or choose the clock used by reconciliation/current verification.

`HUMAN_CLOSING_READY` means only that a human-reviewed response exactly matches the current offer before expiry. The relay has no capability to sign, execute a contract, create checkout/invoices, charge, start fulfillment, or recognize revenue.

The independent receipt digest, source batch, and caller-supplied current UTC are separate trust inputs during current verification. The receipt's own SHA-256 is only an integrity checksum, never authenticity by itself. Historical integrity verification remains available separately and is not treated as current authority.

Receipt outputs are create-exclusive so a later run cannot silently replace the claim-time evidence file. Audit hooks record SDK exceptions and cancellations as failures and retain only hashes/metadata rather than raw commercial evidence.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)
