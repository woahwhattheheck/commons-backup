# Public-Sector Integration Workshare Pack

This package turns public-procurement scouting into a bounded **paid specialist workshare** packet for qualified system integrators. It is intentionally not a bid generator and never promotes Token Junkie Labs into an enterprise prime by implication.

## Commercial posture

Two commercial shapes are modeled, both `PROPOSED_NOT_ACCEPTED`:

1. a **2–4 week paid fixed-fee pilot** with exact inputs, outputs, acceptance tests, and exclusions;
2. a larger **paid implementation workshare** if a prime confirms fit and commercial terms.

The package deliberately leaves the fee as `OWNER_INPUT_REQUIRED`; it does not invent a price and it never turns a proposed amount into booked/earned cash. A payment path must be current before authorized outreach.

## Modules

- **Migration evidence:** source/target profiling, reconciliation, exception evidence, and deterministic receipts.
- **Integration conformance:** versioned contract tests, retry/idempotency hostiles, and replayable failure evidence.
- **UAT/acceptance evidence:** requirement-to-scenario traceability with explicit HOLD on missing or contradictory evidence.
- **Cutover/replay:** checkpoint/rehearsal evidence without production go-live authority.

Prime-owned responsibilities are explicit on every opportunity overlay. Platform/OEM credentials, public-sector references, eligibility, legal/commercial commitments, production access, deployment, and buyer acceptance stay with the qualified prime/buyer.

## Current overlays

The checked-in manifest covers four live modernization opportunities from Commons #14283:

- Illinois DoIT/CDB `27-448DOIT-ADMIN-B-52519` — SAP/interfaces + legacy migration + UAT evidence.
- Oregon OneODA `S-DASOBO-00017788` — Oracle/APEX→Dataverse reconciliation + integration/UAT evidence.
- NYSED `RFP #144` — mainframe/Access extraction reconciliation + transformation/interface/UAT/cutover evidence.
- NC DHHS `30-2025-037-DHB` — CLMS corpus migration + integration/replay + UAT evidence.

Official buyer/portal sources are retained alongside secondary/scout evidence. Where a deadline is not yet bound to current official bytes, the compiler emits `*_DEADLINE_RECHECK_REQUIRED`; it does not silently promote a scout date to controlling authority.

## Single-writer outbound law

Every target row is permanently `NOT_AUTHORIZED_TO_SEND` in this carrier. A later external touch must independently prove, immediately before provider mutation:

1. fresh organization + opportunity + target + route custody;
2. current mailbox/provider/thread history (including prior sends, replies, bounces, DNR, and active owners);
3. one privacy-safe route fingerprint and deterministic collision key;
4. a last-inch exclusive provider-send fence;
5. exactly one provider mutation. Timeout/ambiguity means DNR/reconcile, **never blind retry**.

`collision_key()` consumes only a privacy-safe route fingerprint; raw email/contact data is not persisted here.

## Run

```bash
python -m revenue.public_sector_workshare_pack.cli compile \
  revenue/public_sector_workshare_pack/opportunities.json \
  --out-json /tmp/workshare-packet.json \
  --out-md /tmp/workshare-packet.md

python -m revenue.public_sector_workshare_pack.cli verify \
  /tmp/workshare-packet.json --current
```

The CLI owns current UTC. Tests call the library with fixed time for deterministic proofs. Inputs use strict duplicate-key/non-finite JSON rejection; outputs are create-exclusive regular files with final-component symlink refusal.

## Authority ceiling

Offline research/packaging only. No buyer/prime contact, email/DM/form/call, route acquisition, provider mutation, bid/portal registration or submission, teaming commitment, signature, price acceptance, contract, spend, payment mutation, cash assertion, or recognized-revenue claim.
