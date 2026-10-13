# Water4All 2026 Sustainable Water Management — Consortium Readiness

Operation: `WATER4ALL-2026-SWM-CONSORTIUM-ZRDN7Q4-20260914`

This package is an **offline owner-review compiler** for the Water4All 2026 Joint Transnational Call, *Sustainable Water Management*. It does not contact anyone, create a portal/PIC account, commit an organization to a consortium, pledge self-funding, quote a price, submit a proposal, spend money, or claim an award, payment, or revenue.

## Current source disposition

The exact official packet observed on **2026-09-14** contains a controlling-source conflict:

- The live call page and the linked Call Announcement V2 state a pre-proposal deadline of **2026-11-10 15:00 CET** (`2026-11-10T14:00:00Z`).
- The cover of the same call page's linked National/Regional Regulations V2.0 states **2026-11-12 15:00 CET** (`2026-11-12T14:00:00Z`).

The compiler therefore emits `HOLD_DEADLINE_SOURCE_CONFLICT`, leaves the controlling deadline unset, and exposes **10 November only as a conservative planning date**. It cannot select the later date based on array order, source wording, or caller preference. Clearance requires an issuer clarification or a superseding exact official generation.

Official records retained in `official_sources.json`:

- Call page: <https://www.water4all-partnership.eu/joint-activities/water4all-2026-joint-transnational-call>
- Call Announcement V2: <https://www.water4all-partnership.eu/sites/default/files/2026-09/Call_Announcement_Water4All_JTC2026_20260908.pdf>
- National/Regional Regulations V2.0: <https://www.water4all-partnership.eu/sites/default/files/2026-06/National_Regulations-Water4All_JTC2026.pdf>

The public call material describes an approximate total budget of **€34,221,804.10**, four topics, a two-step application process, and consortium constraints. Those facts are retained as normalized source facts with content commitments; no downloaded PDF digest is claimed because the carrier did not obtain raw PDF bytes through its execution rail.

## Role and commercial posture

A United States entity is not represented as eligible for call funding. The package evaluates three distinct paths:

1. `FUNDED_PARTNER` — must be a verified eligible entity in a participating funding country.
2. `SELF_FUNDED_PARTNER` — limited to one, cannot coordinate, requires a verified commitment, and does not satisfy the funded-partner minimum.
3. `PAID_TECHNICAL_SUBCONTRACT_CANDIDATE` — a **commercial hypothesis only**. V1 always retains owner review because eligibility and procurement authority depend on specific national and consortium rules plus accepted commercial terms.

The intended revenue path is paid technical teaming or subcontract work, not free speculative delivery. `PROPOSED_NOT_ACCEPTED` is not a quote, acceptance, contract, receivable, payment, or revenue.

## Deterministic gates

The compiler validates:

- required exact official-source classes, source fact commitments, completeness, declared currentness, future skew, and current-mode age;
- deadline, full-proposal deadline, and budget agreement across current complete official generations;
- at least three funded partners from three countries and at least two EU/associated funded partners;
- exactly one verified funded coordinator;
- at most seven formal partners, or eight only when a funded undersubscribed-FPO flag is present;
- at most one self-funded partner;
- no partner and no country group above 50% of total person-months (exactly 50% is allowed);
- legal-entity, PIC, participating-FPO, eligibility, and self-funding evidence;
- exact repository/commit/path/content-digest technical evidence descriptors;
- fixed Topic 1 and Topic 3 capability evidence requirements;
- public official partner-search URLs without email, phone, message body, send authority, leading-zero path IDs, or contact-route tokens in retained labels and summaries;
- owner commercial approval without converting it into provider or submission authority.

Decision states are:

- `HOLD_SOURCE_AUTHORITY`
- `HOLD_DEADLINE_SOURCE_CONFLICT`
- `HOLD_CONSORTIUM`
- `HOLD_APPLICANT_ROLE`
- `HOLD_TECHNICAL_EVIDENCE`
- `HOLD_PARTNER_RESEARCH`
- `HOLD_COMMERCIAL_AUTHORITY`
- `HISTORICAL_INTEGRITY_ONLY`
- `READY_FOR_OWNER_REVIEW`

Historical compilation is hold-only and never mints `READY_FOR_OWNER_REVIEW`.
Current `READY_FOR_OWNER_REVIEW` is controlled by an independent `authority_root`.
Even `READY_FOR_OWNER_REVIEW` keeps every external authority bit false.

## Files

- `engine.py` — deterministic orchestration, current/historical separation, semantic verifier, and Markdown owner summary.
- `common.py` — schemas, canonical JSON, timestamps, source commitments, and shared validators.
- `source_validation.py` — official-source generation, currentness, deadline, and budget authority.
- `consortium_validation.py` — partner, coordinator, applicant, funding-role, and workload rules.
- `evidence_validation.py` — concept, exact technical evidence, public shortlist, and commercial gates.
- `cli.py` — strict JSON, bounded retained-fd reads, create-exclusive output, current/historical compile, verify.
- `official_sources.json` — normalized exact source facts and commitments.
- `partner_shortlist.json` — public official partner-search profile URLs only; no contact routes.
- `example_input.json` — deliberately blocked, synthetic-placeholder owner-review input.
- `qualification_matrix.json` — present blockers and exact cure conditions.
- `workplan.json` — proposed work packages, acceptance criteria, risks, and unpriced budget assumptions.
- `concept_note.md` — proposed Topic 1/3 technical concept and evidence boundaries.
- `test_engine.py` — aggregate entry point for 85 authority and filesystem hostiles split across `test_*` modules.

## Run

From the repository root:

```bash
python -m unittest -v revenue.water4all_2026_swm.test_engine
python -O -m unittest -v revenue.water4all_2026_swm.test_engine
python -m compileall -q revenue/water4all_2026_swm

python -m revenue.water4all_2026_swm.cli \
  compile-historical \
  revenue/water4all_2026_swm/example_input.json \
  2026-09-14T04:00:00Z \
  /tmp/water4all.bundle.json \
  --markdown-output /tmp/water4all.owner.md

python -m revenue.water4all_2026_swm.cli \
  verify \
  revenue/water4all_2026_swm/example_input.json \
  /tmp/water4all.bundle.json
```

Current compilation uses process-owned UTC. Historical compilation is explicitly labeled integrity-only during verification. Current packets expire for verification after five minutes and are recompiled at verifier time.

## Filesystem and trust ceiling

The CLI rejects duplicate JSON keys, NaN/infinity, floats, oversized inputs, non-regular inputs, and symlink inputs where the platform exposes `O_NOFOLLOW`. It reads from a retained descriptor with before/after generation checks and writes through a retained create-exclusive descriptor with mode `0600`, `fsync`, and size verification.

This is not a privileged sandbox or multi-user transaction system. A same-privilege actor controlling ancestor directories before open, a hostile filesystem, platform-specific reparse behavior, or mutation after successful return is outside the guarantee. The integrity receipt is a SHA-256 checksum, **not a signature or issuer attestation**.

## Outbound collision fence

`partner_shortlist.json` is research-only. No profile is a lead claim and no profile authorizes a message. Before any future email, form, direct message, call, or partner-search response, the operator must establish fresh organization-and-route custody, inspect current mailbox/provider history, and acquire a last-inch single-writer lease. Ambiguous provider outcomes are do-not-retry until reconciled.
