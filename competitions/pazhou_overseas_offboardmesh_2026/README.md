# OffboardMesh — Pazhou Overseas AI Product carrier

Competition-grade source/evidence carrier for `PAZHOU-OVERSEAS-OFFBOARDMESH-ZPFM6R2-20260914`.

OffboardMesh is an AI-assisted client-offboarding control plane. A model can emit `PROPOSAL_ONLY` tasks; the deterministic layer digest-binds caller-asserted evidence for owner review, rejects contact/secret-shaped identifiers, applies request-time structural checks, and keeps present-time freshness under native UTC clock/currentness dependencies captured when the module initializes. The carrier does **not** claim that evidence provenance is independently owner-authenticated and never exposes an external execution API.

## Truth boundary

This repository state proves a runnable synthetic control-plane demo and source-bound product/business-plan carrier. It does **not** prove: organizer registration, terms acceptance, identity/SMS verification, owner-authenticated evidence provenance, business-plan upload, customer adoption, accepted buyer intent, production model-provider inference, organizer score/rank, prize, payment, or revenue.

The official topic page shows registration through 2026-09-15; a newer organizer event article says through 2026-09-30. The manifest preserves both and uses Sep 15 as the conservative owner-action deadline.

## Run

```bash
python competitions/pazhou_overseas_offboardmesh_2026/offboardmesh.py compile \
  competitions/pazhou_overseas_offboardmesh_2026/example-candidate.json > /tmp/offboardmesh-packet.json
python competitions/pazhou_overseas_offboardmesh_2026/offboardmesh.py verify-current \
  competitions/pazhou_overseas_offboardmesh_2026/example-candidate.json /tmp/offboardmesh-packet.json
python competitions/pazhou_overseas_offboardmesh_2026/offboardmesh.py verify-historical \
  competitions/pazhou_overseas_offboardmesh_2026/example-candidate.json /tmp/offboardmesh-packet.json
python competitions/pazhou_overseas_offboardmesh_2026/rubric.py
python -m unittest discover -s tests -p 'test_pazhou_offboardmesh*.py' -v
python -O -m unittest discover -s tests -p 'test_pazhou_offboardmesh*.py' -v
```

Expected current demo verifier while the synthetic request/evidence remains inside its freshness + closeout window (canonical one-line JSON):

```json
{"candidateValid":true,"compilerProjectionMatches":true,"currentEvidenceFresh":true,"externalSendAuthorized":false,"packetIntegrityValid":true,"sameEngagement":true,"samePlanVersion":true,"sourceMatches":true,"validCurrent":true}
```

Expected historical-integrity replay for the same exact candidate/packet bytes is independent of present freshness:

```json
{"candidateValid":true,"compilerProjectionMatches":true,"externalSendAuthorized":false,"packetIntegrityValid":true,"sameEngagement":true,"samePlanVersion":true,"sourceMatches":true,"validHistorical":true}
```

`validCurrent` samples a native UTC clock captured when the module initializes. Its supported signature is only `(candidate, packet)`; ordinary post-import rebinding of module helper names cannot change the evaluation clock or 14-day currentness policy. A packet that was fresh when compiled becomes non-current when its evidence exceeds that window or its requested closeout window ends. This is a correctness boundary for the supported verifier API, not a claim that arbitrary code execution inside the same Python process cannot replace Python objects or functions. `validHistorical` only establishes exact replay/integrity against the supplied historical candidate; it never asserts present freshness or execution authority.

The internal rubric result is a preparation/evidence-coverage score, explicitly **not** an organizer score.

## Evidence provenance

The input field `ownerSupplied` is retained as a caller assertion for the synthetic carrier, but it is **not** treated as an authority root. Packet truth explicitly emits:

- `evidenceDigestBound: true`
- `ownerEvidenceBound: false`
- `evidenceProvenance: CALLER_ASSERTED_UNVERIFIED`

Every task is `OWNER_REVIEW_REQUIRED`, not execution-ready, and every external/destructive authority bit stays false. A caller setting `ownerSupplied:true` cannot mint independent owner provenance.

## Files

- `submission_manifest.json` — official-source/deadline/award/rubric snapshot, exact product pins, submission nonclaims, owner-input gates.
- `offboardmesh.py` — model-proposal adapter contract, digest binding, authority firewall, captured verifier-owned current clock/currentness policy, explicit historical-integrity replay and CLI.
- `example-candidate.json` — entirely synthetic demo input; `ownerSupplied` values are caller assertions only.
- `rubric_evidence.json` / `rubric.py` — evidence-backed 100-point rubric gap audit with team/customer/revenue gaps left visible.
- `business_plan.md` — submission-ready business-plan body pending truthful owner/team fields.
- `pitch_deck.md` — 8-minute presentation narrative for later-stage use.

## Upstream product pins

- Client Offboarding Desk: `woahwhattheheck/smb-showcase-inventory@1d851fae645d8518ede247d4a4c35f9219b26c78`
- Buyer-neutral control sprint carrier: `woahwhattheheck/smb-showcase-inventory@321d25ded135cf0580297c32e1c9ea8d9102c41b`

Original product/source credit is preserved; this carrier is additive competition packaging and a stronger AI-control adapter, not a rewrite of the shipped product. ZPF-M6R2 authored the original six-file Pazhou carrier; ZSM-U7P5 recovered the stale lane by supplying the missing executable, business-plan, hostile-test, and path-CI acceptance artifacts without rewriting the original product paths. Z-Sol later repaired the recovered verifier's current-time, compiler-correspondence, and evidence-provenance trust boundaries after exact-head source review. ZVM-Q5K8 hardened the production CURRENT callable against post-import module-global clock/currentness rebinding and converted the hostile suite to live-window/historical fixtures; those repairs do not change original product authorship.
