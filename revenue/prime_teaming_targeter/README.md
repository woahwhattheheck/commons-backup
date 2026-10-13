# Prime / Teaming Targeter

An offline revenue-acquisition control for deciding **which credible prime or teaming partner is worth an owner-reviewed paid subcontract approach** for one funded opportunity.

This tool exists because “send more outreach” is not a strategy. It turns an opportunity's weighted requirements, source-custody metadata, candidate-specific evidence, and a concrete paid-scope hypothesis into a deterministic ranked target brief. Missing, stale, future, transplanted, or merely partial mandatory evidence fails closed.

## Authority boundary

The output is internal decision support only. `ELIGIBLE_FOR_OWNER_OUTREACH_REVIEW` means the evidence bundle is complete enough for a human owner to review a possible approach. It does **not** authorize email or any other provider mutation; prove a prime's participation; accept a proposal; submit a bid; form a contract; request or receive payment; or recognize revenue. Every paid scope is emitted as `PROPOSED_NOT_ACCEPTED`.

Source rows are evidence-custody metadata, not proof that an external party authenticated them. `source_ref`, `source_sha256`, `source_kind`, and `observed_at` let the owner retain exactly what the ranking depended on and replace it with stronger acquisition/provenance rails when available.

## Core contract

- Requirement weights must sum to exactly 10,000 basis points.
- Mandatory requirements require at least one current `MEETS` evidence row for that candidate.
- `PARTIAL` contributes 50% of a non-mandatory requirement's weight but never satisfies a mandatory requirement.
- Evidence older than 45 days or dated in the future is non-authorizing and causes HOLD.
- Opportunity deadlines are process-time checked; a historical receipt cannot keep a target current after deadline/staleness.
- Evidence IDs are unique and bound to exact opportunity + candidate + requirement. Cross-candidate/opportunity transplant fails before scoring.
- Candidate ordering is deterministic: eligible first, score descending, candidate ID ascending.
- Receipt verification first replays the exact historical decision at its retained evaluation time, then recomputes a current decision at verifier-owned time.

## CLI

```bash
python -m revenue.prime_teaming_targeter.targeter compile input.json target-receipt.json
python -m revenue.prime_teaming_targeter.targeter verify input.json target-receipt.json
python -m revenue.prime_teaming_targeter.targeter render input.json target-receipt.json target-brief.md
```

`compile` uses create-exclusive output (`xb`) and refuses overwrite. `verify` prints a machine-readable current revalidation and exits 2 on integrity failure.

## Commercial use

A practical paid lane should name real deliverables, an exact amount/currency, and acceptance criteria before anyone spends significant free labor. The targeter deliberately preserves that proposed scope in the ranked record while refusing to call it accepted. Use the target brief to focus research and owner review; route any eventual provider send through the fleet's authoritative outbound controls.
