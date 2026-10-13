# Linden Housing Authority RFP 26-07 — owner review packet

Internal qualification carrier only. Source custody remains **Z-SteinhausMoraine-2315-Q4V8**. Recovery/finalization lane: **Z-Sol-Cascade-0119**. Canonical issue: https://github.com/woahwhattheheck/commons/issues/14261

## Source and access status — 2026-10-04

[Canonical issue #14261](https://github.com/woahwhattheheck/commons/issues/14261) closed on September 17 after the internal carrier landed in [PR #15315](https://github.com/woahwhattheheck/commons/pull/15315). This records source delivery, not a submitted proposal, award or cancellation. The September 17 manifest is a retained snapshot; its `canonical_issue.status: OPEN` predates that closure.

The earlier request for a named bidder and Marketplace agent was resolved in the [September 20 owner-decision record](https://github.com/woahwhattheheck/commons/issues/14261#issuecomment-5751503047). Do not repeat that resolved request from older recensus notes. This update does not populate vendor-profile fields or qualification evidence.

| Source checked | Observation and limit |
| --- | --- |
| [Agency advertisement indexed by NJ.com](https://classifieds.nj.com/nj/advert/-general_302105) | The indexed notice lists questions on September 21 at 15:30 and proposals on October 9 at 14:30, matching the retained dates below. Direct retrieval returned HTTP 403 in this pass; no controlling package or current addenda were acquired. |
| [Housing Agency Marketplace](https://ha.internationaleprocurement.com/) | Its public page presents the login/vendor-registration entry point. This read did not establish vendor access or a complete solicitation/addenda set. |
| [Third-party document listing](https://bidreadyrfps.com/rfp/3139-ai-automation--resident-communication---operationa) and its [public archive link](https://bidreadyrfps.com/web/content/6536?download=true) | The page labels the download as PDF, but the reader reported ZIP content. Its October 8 date conflicts with the retained notice. The archive is an **unverified acquisition lead**, not a controlling source or deadline amendment. |

The questions date is past as of this check. The October 9 proposal date remains the retained notice date, subject to the controlling solicitation and addenda. A subsequent authorized acquisition pass can inspect the public archive, then verify its solicitation identity, version and addenda against official sources before binding it. Do not replace the retained deadline, fill requirement/form/evaluation registers, or mark the official package acquired from this third-party listing alone.

## Bound public-notice facts

- Procuring entity: Housing Authority of the City of Linden (NJ)
- Solicitation: RFP **26-07** — AI Automation, Resident Communication & Operational Support Services
- Public notice posted: 2026-09-11
- Questions: 2026-09-21 15:30 ET
- Proposals: 2026-10-09 14:30 ET
- Submission channel: Housing Agency eProcurement Marketplace only; hard copy not allowed
- Published agency contact name on the notice: Dr. Marlena Berghammer, Executive Director

Public notice metadata is **not** the controlling RFP/addenda package.

## Fail-closed gates

The compiler refuses submission, pricing commitment, buyer email, portal registration, credential invention, award, payment, and revenue claims. Those flags stay hard-false even when an owner packet is internally complete.

Until the official package is acquired and hashed:

- evaluation weights stay `null`
- required forms stay `null`
- addenda stay `null`
- posture stays `HOLD_CONTROLLING_PACKAGE` or `HOLD_OWNER_EVIDENCE`
- blockers include `CONTROLLING_PACKAGE_NOT_BOUND`, `EVALUATION_REGISTER_UNKNOWN`, `FORM_REGISTER_UNKNOWN`, `ADDENDA_REGISTER_UNKNOWN`

## Acquisition checklist (owner + Muse gated)

1. Use an already-authorized private session on Housing Agency Marketplace if one exists. Do not register a new vendor account from this carrier.
2. Download the controlling RFP plus every addendum.
3. Hash exact bytes and bind them into `controlling_package.sha256`.
4. Rebuild the requirement / evaluation / form register from those bytes only.
5. Re-run `compile_packet` against current main.

No buyer mutation is authorized by this recovery.
