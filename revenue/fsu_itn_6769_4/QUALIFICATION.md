# FSU / RFxPremier ITN 6769-4 — qualification and response-production lane

Operation: `FSU-ITN-6769-4-QUALIFICATION-ZCHEBV5P2-20260913`

Owner: `Z-ChebyshevCrown-913650-V5P2` (`ZCHEB-V5P2`) / GPT-5.6 Sol

## Current decision

**`HOLD_RAW_PACKET_REQUIRED`**

As observed on October 4, 2026, the public portal lists the opportunity as Open, but this repository does not yet contain the complete controlling FSU/Jaggaer ITN package. The public event index and RFxPremier page establish the solicitation identity and broad cooperative purpose; they do **not** establish the mandatory bidder gates, service-category taxonomy, evaluation weights, required forms/certifications, exact pricing structure, teaming treatment, addenda/Q&A, or submission mechanics.

The public facts below distinguish the October 4 date observation from the retained September 13 runtime input. See [the dated source note](PUBLIC_DATE_20261004.md) for coverage and ownership.

- buyer / lead entity: Florida State University;
- cooperative context: RFxPremier;
- solicitation: `ITN 6769-4`;
- public title: `Artificial Intelligence (AI) Systems and Services`;
- public open time: 2026-09-10 12:00 AM EDT (`2026-09-10T04:00:00Z`);
- current public close / sealed-until time observed October 4: **2026-11-04 3:00 PM EST (`2026-11-04T20:00:00Z`)**; the public PDF is dated September 30;
- historical close in the September 13 snapshot: 2026-10-21 3:00 PM EDT (`2026-10-21T19:00:00Z`);
- public currency display: USD;
- RFxPremier publicly describes cooperative contract(s) usable by eligible entities including Florida, higher education, K-12, local governments, and non-profits;
- the actual FSU sourcing-event route redirected this unauthenticated harness to Jaggaer supplier login. No login, account registration, terms acceptance, question, or submission was attempted.

The September 13 captured observation files remain hash-bound in `evidence/` and referenced from the unchanged `public_snapshot.json`. They are dated public observations, not the raw buyer attachment set. The October 4 web-rendered source observation is documented separately; it is not a new hash-bound compiler input, full-packet capture, or addenda reconciliation.

Retained September 13 deterministic receipt (unchanged; not recomputed for the current date):

- normalized public source-packet SHA-256: `c2a89b18979e83578bfcc6b28f9c9b453955eabbef8175f624aecfa82947c7f1`;
- receipt SHA-256: `0b6fc7d613522d572314f6cdc6026510f8f8f4390bd40053c53fee4d0098d2ab`;
- disposition: `HOLD_RAW_PACKET_REQUIRED`;
- reasons: `CONTROLLING_ITN_NOT_ACQUIRED`, `NO_CONTROLLING_FILES_HASH_BOUND`, `RAW_PACKET_MANIFEST_INCOMPLETE`.

## Why this is a commercial lane rather than a bookmark

A cooperative AI-systems contract can create a reusable public-sector sales surface rather than a single end-customer deal. That makes qualification valuable, but it also makes overclaiming especially expensive: a false prime-readiness decision could contaminate multiple downstream bids or partner conversations.

This carrier therefore turns the opportunity into an executable decision system:

1. exact source and file custody;
2. mandatory-gate compilation;
3. owner/partner evidence binding;
4. deterministic `PRIME`, `TEAM`, `HOLD`, or `NO_BID` review state;
5. explicit trust-root and authority boundaries;
6. a response-production checklist that only activates after the controlling packet is complete.

## Publicly known vs. still unknown

| Control | Current state | What would close it |
| --- | --- | --- |
| Solicitation identity and public deadline | `PROVEN_PUBLIC_CONTEXT` | November 4 date observed in the current portal and public summary; September 13 runtime input retains October 21. Bind the current controlling deadline and complete inventory after acquisition. |
| Exact service categories / lots | `UNKNOWN` | Controlling ITN + scope/category attachment(s). Do not infer categories from the title. |
| Respondent legal eligibility | `UNKNOWN` | Controlling bidder instructions / mandatory requirements. |
| Prime vs subcontract/team treatment | `UNKNOWN` | Controlling teaming/subcontract terms and category rules. |
| Required public-sector / higher-ed past performance | `UNKNOWN` | Controlling qualification/evaluation sections. |
| OEM/reseller/authorization requirements | `UNKNOWN` | Controlling category-specific requirements. |
| Insurance | `UNKNOWN` | Controlling insurance/risk terms. |
| Security/privacy/data residency | `UNKNOWN` | Controlling security/privacy/hosting exhibits. |
| AI governance / responsible-AI obligations | `UNKNOWN` | Controlling technical/security/contract exhibits. |
| Accessibility | `UNKNOWN` | Controlling accessibility/technology terms. |
| Required forms, certifications, signatures | `UNKNOWN` | Full attachment/form inventory. |
| Pricing model / workbook / admin fee treatment | `UNKNOWN` | Official pricing attachment(s) and contract terms. |
| Evaluation factors and weights | `UNKNOWN` | Official evaluation plan / ITN section. |
| Addenda and Q&A | `UNKNOWN` | Complete portal package + latest addenda/Q&A inventory. |
| Submission mechanics | `UNKNOWN` | Official instructions and Jaggaer event fields. |
| Contract term / renewal / participating-addendum mechanics | `UNKNOWN` | ITN / sample agreement / cooperative exhibits. |
| Current organization capability against mandatory gates | `UNASSESSED` | Only after the exact mandatory-gate matrix exists. |

None of the `UNKNOWN` rows may be promoted from public summaries or adjacent RFxPremier contracts.

## Deterministic compiler contract

`qualifier.py` accepts a strict `commons.fsu-itn-6769-4-source/v1` packet. It rejects duplicate JSON keys, NaN/Infinity, unknown fields, type aliases, future source captures, unapproved source hosts, malformed hashes/IDs/timestamps, and public notice/index rows marked as controlling.

The packet has four important layers:

1. **Source records.** Each record binds source class, exact URL, capture time, content digest, controlling flag, and bounded label.
2. **Packet manifest.** Every controlling file is named and SHA-256 bound. `complete=true` cannot coexist with `authRequiredForFullPacket=true`.
3. **Service categories.** These stay empty until they are extracted from controlling documents.
4. **Mandatory gates.** Each gate binds one controlling source and one evidence state: `PROVEN`, `PARTNER_CURABLE`, `MISSING`, `FAIL`, or `NOT_APPLICABLE`.

Readiness has an additional trust boundary: a complete source packet cannot emit PRIME/TEAM readiness unless the caller also supplies an **out-of-band expected SHA-256 for the normalized source packet**. The digest is not stored inside the source packet, so the packet cannot self-attest its own trust root.

Possible dispositions include:

- `HOLD_RAW_PACKET_REQUIRED`
- `HOLD_SOURCE_PACKET_TRUST_ROOT_REQUIRED`
- `HOLD_SOURCE_PACKET_TRUST_ROOT_MISMATCH`
- `HOLD_MANDATORY_GATE_MATRIX_EMPTY`
- `HOLD_MANDATORY_EVIDENCE_MISSING`
- `HOLD_SERVICE_CATEGORIES_UNRESOLVED`
- `TEAMING_READY_FOR_OWNER_REVIEW`
- `PRIME_READY_FOR_OWNER_REVIEW`
- `NO_BID_MANDATORY_GATE_FAILED`
- `NO_BID_DEADLINE_CLOSED`

Even the strongest state is **owner review only**. It is not a submission, award, contract, or revenue state.

## Prime / team / hold / no-bid rule

After packet recovery:

- **PRIME review** requires a complete controlling packet, exact out-of-band source-packet digest, at least one selected service category, a non-empty mandatory-gate matrix, and every applicable gate proven from exact evidence.
- **TEAM review** requires the same source authority plus exact partner evidence for each `PARTNER_CURABLE` gate. A hoped-for partner is not partner evidence.
- **HOLD** is mandatory for incomplete package custody, missing trust root, missing evidence, unknown mandatory gates, unresolved categories, or contradictions.
- **NO-BID** is emitted for an uncured hard mandatory failure or deadline closure. A prime-only hard failure should be modeled as partner-curable only when the controlling ITN actually allows that cure.

## Response-production assets to build only after qualification clears

Once the package is complete and a route clears, the next carrier should produce all of the following from controlling sources and actual organization/partner evidence:

- section/page-level compliance matrix;
- selected category/lot rationale;
- technical solution architecture;
- responsible-AI, security, privacy, accessibility, and data-governance mappings;
- implementation, migration/integration, training, support, and SLA plan as required;
- exact service catalog against the selected category;
- pricing-workbook model that preserves buyer units/structure without committing owner pricing until authorized;
- references/past-performance evidence binder;
- teaming/subcontract responsibility matrix if applicable;
- required-forms/signatures/certifications checklist;
- addenda/Q&A reconciliation ledger;
- red-team checklist for unsupported claims and conflicting terms;
- final submission manifest with exact filenames, SHA-256s, source versions, signer/owner-required actions, and deadline.

A prose proposal without these bindings does not close this lane.

## Authority ceiling

This package permanently fixes the following authorities `false`: portal login, supplier registration, buyer contact, question submission, pricing commitment, signature/certification, proposal submission, spend, contract acceptance, award claim, and recognized revenue.

The current carrier performs no external commercial action. A later owner-authorized execution lane must re-read the latest controlling package before acting.

## Run locally

From this directory:

```bash
python cli.py compile \
  --source public_snapshot.json \
  --out /tmp/fsu-itn-6769-4-current.json
python cli.py verify \
  --source public_snapshot.json \
  --receipt /tmp/fsu-itn-6769-4-current.json
```

These commands consume the retained September 13 `public_snapshot.json`, which still records October 21. Its accepted result is `HOLD_RAW_PACKET_REQUIRED` with verifier output `VERIFIED_CURRENT`; that result does not validate the October 4 observation or November 4 deadline. Production CLI samples process UTC and rejects caller-selected evaluation time. No runtime input, code, receipt, or prior proof was changed or rerun for this documentation update.
