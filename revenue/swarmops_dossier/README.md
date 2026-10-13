# Commons SwarmOps Evidence Dossier

Turn owner-curated evidence into a dossier that distinguishes what is current from what was demonstrated at a past instant. Repository activity, queued CI, outbound transport, buyer acceptance, payment and recognized revenue remain separate observations.

## Current workflow

Run from the repository root with the original evidence packet and policy:

```bash
python -m revenue.swarmops_dossier.cli compile packet.json policy.json \
  --json-out dossier.json --markdown-out dossier.md
python -m revenue.swarmops_dossier.cli verify packet.json policy.json dossier.json
```

`compile` samples process UTC once. Neither current command accepts `--as-of`. Output schema `commons.swarmops-dossier-output/v4` includes `evaluation_mode: CURRENT`. Its `as_of` is a recorded evaluation instant, not a promise of permanent validity. A feature named by policy still needs current prospect-safe technical evidence. Missing or stale evidence for that feature produces `HOLD`, exit 2, and explanations in the console and Markdown.

`verify` first reconstructs the original dossier with the supplied packet, policy and commercial authority. It then evaluates the same evidence at process UTC and compares every field except the evaluation timestamp and receipt digest. An unchanged dossier does not fail just because the clock advanced one second. It does fail when freshness changes a row classification or reason, including optional rows and commercial observations, or changes a feature result. Changed source inputs, policy, commercial authority, altered content and future timestamps also fail. Failures identify the problem and request recompilation.

**Successful verification means integrity and present classifications match. It does not mean the status is READY.** A still-accurate `HOLD` dossier can verify successfully; the CLI prints its status.

This is a check of retained observations against their declared freshness windows. It does not reread GitHub, payment providers or other external sources, authenticate source bytes by itself, or protect against an administrator changing the machine clock. Acquire new observations upstream when evidence expires; do not retimestamp old observations to make them appear fresh.

## Historical workflow and migration

Historical analysis remains available, and it is explicitly named and labeled:

```bash
python -m revenue.swarmops_dossier.cli replay packet.json policy.json \
  --as-of 2026-09-13T14:00:00Z \
  --json-out historical.json --markdown-out historical.md
python -m revenue.swarmops_dossier.cli verify-replay packet.json policy.json \
  historical.json --as-of 2026-09-13T14:00:00Z
```

Historical output has `evaluation_mode: HISTORICAL_REPLAY` and status `HISTORICAL_READY` or `HISTORICAL_HOLD`, never current `READY_FOR_OWNER_REVIEW`. The Markdown prominently labels it historical and changes the demonstrated-items heading accordingly. Future evaluation instants and observations later than the evaluation instant are rejected.

Archived v3 dossiers can be checked with `verify-replay` at their recorded instant. They are not accepted by current `verify`, because v3 does not distinguish a caller-selected replay clock from current evaluation. Recompile the original packet and policy with the new `compile` command to obtain a current v4 dossier. Do not edit the schema or mode by hand.

The input packet schema remains `commons.swarmops-dossier/v1`; no input migration is needed. The content digest binds the output mode as well as the established packet, policy and commercial-authority digests. Replay of the same valid past input and instant is deterministic.

## Evidence and commercial semantics

Each evidence row binds a feature to a typed source reference, SHA-256, observed state, observation time, freshness window, release class and factual statement. The compiler separates rows into `DEMONSTRATED`, `LIMITED`, `HELD` or `UNKNOWN`.

Commercial observations have an independent host-supplied basis:

- `SENT_NOT_ACCEPTED` requires a provider receipt and never means acceptance.
- `BUYER_ACCEPTED`, `PAID` and `REVENUE_RECOGNIZED` require the corresponding buyer, payment or accounting receipt plus independently retained authority for that exact event.

A packet cannot authenticate its own commercial receipt. Each trusted source ID binds the exact portfolio and the complete row: feature, kind, reference, SHA-256, commercial state, observation time and freshness, prospect class, the row flag, and the factual statement. Exact matching prevents a retained payment receipt being relabeled as acceptance, moved to another portfolio or re-dated. Malformed, inconsistent or unused authority records fail. The authority digest remains bound into the output.

The CLI has no `--trusted-commercial-receipts` option and always supplies an empty commercial map. A second caller-authored JSON file is not independent authority. Only an integrating host that independently acquires the underlying evidence should supply its retained typed map to the library. Current evaluation does not turn local bytes into buyer, payment or accounting authority.

A host record is keyed by source ID and has this shape:

```json
{
  "payment-source-id": {
    "portfolio_id": "commons-swarmops-public-demo",
    "capability_id": "commercial-event",
    "source_kind": "PAYMENT_RECEIPT",
    "source_ref": "retained:payment-provider-receipt",
    "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "observed_state": "PAID",
    "observed_at": "2026-09-13T13:05:00Z",
    "freshness_seconds": 86400,
    "prospect_class": "PROSPECT_SAFE",
    "required": false,
    "claim": "An independently retained commercial receipt exists for one event."
  }
}
```

This describes the existing trusted-host integration format, not a real payment record or CLI input. The host remains responsible for authentication of the original provider evidence.

## Library entry points

Import these functions from `revenue.swarmops_dossier`:

| Function | Meaning |
| --- | --- |
| `compile_current_dossier(packet, policy, trusted_commercial_receipts=None)` | Current v4 dossier, using process UTC; no clock argument. |
| `verify_current_dossier(packet, policy, candidate, trusted_commercial_receipts=None)` | Returns true when retained integrity and current classifications match; raises `DossierError` explaining a failure. |
| `compile_historical_dossier(packet, policy, as_of, trusted_commercial_receipts=None)` | Explicitly historical v4 dossier. |
| `verify_historical_dossier(packet, policy, as_of, candidate, trusted_commercial_receipts=None)` | Historical integrity only; returns a boolean and supports archived v3. |

The old `compile_dossier` and `verify_dossier` names remain callable with their old argument order as historical aliases. **The compile alias now emits labeled v4 historical output**, not an unlabeled v3 READY result. Hosts relying on the old schema or status should migrate deliberately to one of the named modes. Use the current functions for present readiness.

## Files, results and publication

Input JSON rejects duplicate keys and non-finite constants and is read as a bounded regular file. Outputs remain create-exclusive; choose new names rather than overwriting existing results. `INTERNAL_ONLY` rows are absent from the prospect projection, and `OWNER_APPROVAL_REQUIRED` rows cannot satisfy a feature marked required.

Exit codes: 0 means a ready compile or successful requested verification; 2 means a compile completed with missing evidence for a feature marked required (or an argument error); 3 means verification did not match; 4 means invalid input or a file/runtime error. A historical exit 0 is only historical success. Error messages go to stderr.

No dossier authorizes sends, customer contact, deployment, credentials, proposals, pricing or staffing commitments, signatures, contracts, spending, payment actions, acceptance claims, cash assertions or revenue recognition. Currentness is evidence classification, not additional authority.
