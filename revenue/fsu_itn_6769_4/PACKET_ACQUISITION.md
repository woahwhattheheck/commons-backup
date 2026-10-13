# Owner-authorized controlling-packet acquisition runbook

This runbook is a handoff, not authority to register or log in.

## Current public date and retained input

The October 4, 2026 [public-source observation](PUBLIC_DATE_20261004.md) records November 4, 2026 at 3 PM EST (`2026-11-04T20:00:00Z`). The two-page public summary is dated September 30; the full event still redirects to supplier login. This later public deadline does not establish an amendment number, complete attachment inventory, or qualification.

The existing `public_snapshot.json`, `current_hold_receipt.json`, and captured evidence remain the September 13 generation with the October 21 date. Do not describe that frozen input as current. A subsequent acquisition must reconcile the current controlling deadline, every attachment/addendum and exact source bytes before updating the runtime packet and using the existing qualifier. No runtime update or execution was performed in this source-only correction.

## Required acquisition result

Acquire the complete current FSU/Jaggaer package for `ITN 6769-4` only through an owner-authorized supplier session. Before any qualification result is upgraded, capture:

1. the main ITN / solicitation document;
2. every scope/specification/category exhibit;
3. every mandatory form and certification;
4. every pricing worksheet;
5. every sample/master/cooperative agreement or terms document;
6. every security/privacy/accessibility/AI-governance exhibit;
7. every respondent qualification/reference/insurance exhibit;
8. every submission instruction/template;
9. every addendum, amendment, and Q&A published as of the capture time;
10. portal-visible event metadata needed to prove the package inventory is complete.

For each file record the exact filename, byte size, SHA-256, publication/version metadata when visible, source URL/event identifier, and capture UTC. Preserve original bytes outside Git if licensing or sensitivity requires it; the repository only needs the approved hashes and non-sensitive source metadata.

## Completeness fence

Do not set `packetManifest.complete=true` merely because the obvious PDF was downloaded. Completeness requires an inventory of every currently published event attachment/addendum/Q&A and reconciliation of the portal list against the manifest.

If the portal cannot prove there are no additional attachments, leave `complete=false` and keep the disposition on HOLD.

## Trust-root fence

After the source packet is compiled from the acquired files, a separate trusted acquisition/review step must publish the normalized source-packet SHA-256 out of band. The qualifier requires that exact digest before PRIME or TEAM readiness can be emitted.

This is intentional: the same JSON that describes the source package is not allowed to certify itself.

## Mandatory extraction pass

From the controlling package, compile stable gate IDs for at least:

- legal/respondent eligibility;
- exact service categories / lots;
- minimum corporate experience and references;
- key personnel and staffing;
- teaming/subcontract/OEM/reseller rules;
- insurance;
- security, privacy, data handling/residency, records, and breach obligations;
- AI governance / responsible-AI controls;
- accessibility;
- hosting/support/SLA obligations;
- implementation/integration/training requirements;
- financial capacity if required;
- forms, certifications, attestations, and signatures;
- cooperative purchasing / participating-entity duties;
- pricing units, workbook, admin fee, escalation, and price-hold rules;
- evaluation factors / weights / interviews / demonstrations / negotiations;
- Q&A and addenda obligations;
- electronic submission mechanics and exact deadline;
- contract term, renewal, termination, IP/data/license, and public-records terms.

Every mandatory gate must cite a controlling source ID. Public notice/index rows cannot prove gates.

## Capability mapping

Only after the mandatory matrix exists, map TokenJunkieLabs / Commons and any actual partner evidence to each gate. Use only:

- `PROVEN` for exact, supportable evidence;
- `PARTNER_CURABLE` when the buyer allows the cure and exact partner evidence exists;
- `MISSING` for a required gate without evidence;
- `FAIL` for a hard, non-curable miss;
- `NOT_APPLICABLE` only when the controlling source makes it genuinely inapplicable.

Never infer public-sector references, certifications, insurance, OEM status, reseller authorization, staff availability, pricing, or security posture.

## External-action boundary

This runbook does not authorize supplier registration, login, acceptance of new commercial terms, buyer/RFxPremier contact, Q&A, pricing commitment, signature/certification, proposal submission, spend, contract acceptance, award claim, or revenue recognition.
