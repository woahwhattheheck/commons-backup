# Opportunity Portfolio Live Intake

`revenue/opportunity_portfolio_intake` is the offline composition layer between normalized live swarm evidence and the already-landed `revenue.opportunity_portfolio` allocator.

It exists for one operational failure mode: multiple workers can see the same lead, bid, contest, bounty, or service lane while their views of TAKE/RELEASE/DNR/closure state differ. Hand-normalizing that state near an external action makes duplicate execution easy. This package folds one explicitly bounded snapshot before the allocator sees the opportunity.

## What it consumes

The intake packet keeps two categories separate:

- **facts**: allocator-native source, freshness, deadline, eligibility, exact integer value/probability evidence, capacity, static blockers, dependencies, exclusivity, and labels. Status events cannot rewrite these fields.
- **events**: typed evidence only — `TAKE`, `RELEASE`, `EXPIRE`, `BLOCKER_OPEN`, `BLOCKER_RESOLVED`, `DNR`, `BUYER_REOPEN`, `CLOSED`, and `SHIPPED`. Every event has a stable ID and exact source ref/digest/time.

Exact replay of the same event ID collapses. Reusing an event ID with changed bytes fails closed. Events are reduced in `(observedAt,eventId)` order, so array ordering is not authority.

`DNR` is an execution blocker, **not** an eligibility rewrite. Generic blocker-resolution events cannot clear it. Only a later typed `BUYER_REOPEN` whose origin is literally `BUYER` resolves DNR. Internal TAKE/RELEASE activity never does. `CLOSED` and `ALREADY-SHIPPED` remain terminal blockers.

## Completeness is host authority, not packet authority

The packet still carries `snapshot.custodyComplete` and `snapshot.statusComplete` for compatibility and audit, but those booleans are assertions only. **They do not establish absence.**

A host that actually owns a complete snapshot can call `compile_intake(..., trusted_snapshot_authority=...)` with a `commons-opportunity-portfolio-intake-snapshot-authority/v1` record. **A second mapping is not authority by itself.** The record must carry an HMAC that verifies under the host-retained capability in `OPPORTUNITY_INTAKE_SNAPSHOT_AUTHORITY_KEY_HEX`. The key is never accepted from packet bytes, authority bytes, function arguments, or CLI.

`issue_host_snapshot_authority()` exists only for protected host integration after that host has independently established snapshot completeness. It signs:

- one stable authority ID, generation, key ID, issuance time, and compiling `actorSeat`;
- the exact snapshot source ref/digest/time;
- a SHA-256 commitment over every normalized opportunity ID and its complete normalized event set;
- exact opportunity and event counts; and
- the authoritative custody/status completeness booleans.

The packet actor seat, source, projection digest, counts, completeness assertions, authority chronology, and HMAC must all match. Removing a TAKE, DNR, or whole opportunity; relabelling the compiling seat; resealing only the packet snapshot digest; transplanting authority between snapshots; changing completeness after authority capture; supplying a fake second authority mapping; or verifying under a different/missing host capability fails closed. Authenticated snapshots are also subject to a code-owned 300-second maximum age at `trusted_as_of`; an old once-complete snapshot cannot be replayed later as current availability.

If no authenticated snapshot authority is supplied, effective custody and status completeness are both forced to `false`, regardless of packet booleans. The compiler therefore emits `UNKNOWN` ownership plus explicit `CUSTODY-INCOMPLETE` / `STATUS-INCOMPLETE` blockers rather than deriving `AVAILABLE` from absence.

The authority record is intentionally a **host-library input only** and the capability is a **trusted-process input only**. The public file CLI has no flag for injecting either. Code/process access able to read the capability is part of the trusted-host boundary and must not be exposed to untrusted request code. A caller that controls both packet and an unauthenticated authority mapping has established no independent completeness authority.

## Custody semantics

When trusted authority says custody is complete:

- zero active TAKEs -> allocator owner `AVAILABLE`;
- exactly the compiling actor -> `OWNED_BY_THIS_SEAT`;
- exactly one other actor -> `OWNED_BY_OTHER`;
- more than one active actor -> `UNKNOWN` plus open `OWNER-COLLISION`.

An unmatched `RELEASE`/`EXPIRE` produces `CUSTODY-HISTORY-CONFLICT`. Same-time contradictory custody/status events fail closed. Incomplete custody or status inventory produces an explicit open blocker and cannot manufacture an executable lane through absence.

## Receipt verification

Receipt schema v2 binds the normalized source packet, folded owner/blocker projection, exact allocator input, allocator receipt digest, and the snapshot-authority binding.

A receipt compiled with trusted snapshot authority can be verified only when the verifier is independently given the exact same authority generation **and** has the same host capability needed to validate its HMAC. The receipt cannot bootstrap its own external trust or carry the capability. A receipt compiled without trusted authority rejects later authority injection and recompiles only in the same fail-closed incomplete posture.

Compilation still calls the real merged `revenue.opportunity_portfolio.normalize_input()` and `compile_portfolio()` functions. Verification performs deterministic full recompilation.

## Authority ceiling

The adapter is read-only. Every receipt fixes these to false from source-literal maps in both compilation and verification: contact, send, submission, merge, spend, payment mutation, buyer acceptance, and revenue recognition authority. There is no mutable module authority template whose rebinding can widen a receipt. A downstream portfolio `EXECUTE_NOW` result is still human execution review exactly as defined by the allocator; this package does not add provider or external-action authority.

## CLI

The public CLI deliberately has no trusted-completeness injection surface:

```bash
python -m revenue.opportunity_portfolio_intake.cli compile intake.json \
  --trusted-as-of 2026-09-14T01:00:00Z \
  --portfolio-input portfolio-input.json \
  --receipt intake-receipt.json

python -m revenue.opportunity_portfolio_intake.cli verify intake-receipt.json
```

CLI-compiled receipts therefore remain fail-closed/incomplete unless a protected trusted-host integration uses the library API and its independently retained HMAC capability. Input reads are bounded, strict UTF-8/JSON, duplicate-key rejecting, no-follow regular-file reads. Outputs are create-exclusive and fsynced; existing files are never overwritten.
