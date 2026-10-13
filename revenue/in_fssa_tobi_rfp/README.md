# Indiana FSSA Tobi RFP readiness rail

Offline evidence gate for **Indiana FSSA RFP 26-86873 / event 004100000086873**, the CMHW Case Management System (Tobi) solicitation.

This package decides whether supplied evidence supports a prime or bounded-subcontract pursuit. Missing evidence returns `HOLD`. It does not contact the buyer, submit a bid, quote a price, or claim an award.

## Current source observation — October 3, 2026

The [official IDOA board](https://www.in.gov/idoa/procurement/current-business-opportunities/) now lists **October 8, 2026 at 3:00 PM**. Its linked [official bid-document ZIP](https://secure.in.gov/idoa/proc/solicitations/files/004100000086873.zip) contains Addenda 1 and 2 and the revised RFP.

- **Addendum 1** moved proposals and reference forms from September 16 to October 1, replaced the cost proposal with version 2, and corrected Attachment J's reference from A1 to A.
- **Addendum 2** supersedes the October 1 dates: proposals and reference forms are due **October 8 at 3:00 PM Eastern Time**. The revised RFP cover and section 1.24 agree. Eastern daylight time is encoded as `2026-10-08T15:00:00-04:00`; the board's `EST` shorthand is retained separately.
- Revised RFP **sections 1.25 and 2.3.10 remove evidence of financial responsibility**. The obsolete two-fiscal-year check has therefore been removed.
- Under section 2.3.6, the three client reference forms go directly from the references to the State by the same amended deadline.

The original September 16 deadline in [PR #13694](https://github.com/woahwhattheheck/commons/pull/13694) remains historical provenance. The evaluator now binds the amended proposal deadline.

The recovered ZIP is **985,590 bytes**, SHA-256 `c94de4032e2ae70d9830a433cff9a736925af83b3cded03d5f975ba9c2b077b8`. [current_packet.json](current_packet.json) records the exact source URLs, capture time, reviewed member hashes, changed form hashes, and outstanding evidence. That file is a dated operational input, not a current-time assertion when replayed later. Recheck the official board and complete the attachment/Q&A and supplier-portal comparison before representing a response as complete. Controlling RFP/addenda override this package.

## Run the current packet

```bash
python -m revenue.in_fssa_tobi_rfp.cli < revenue/in_fssa_tobi_rfp/current_packet.json
```

This real source packet supplies no bidder qualifications, completed proposal, references or confirmed prime partner. Its expected decision is **HOLD**, with the amended deadline recognized and the remaining missing evidence identified. To evaluate a later observation, supply the actual evaluation time and newly observed source evidence.

Decisions are `PRIME_READY`, `SUBCONTRACT_READY`, `HOLD`, and `NO_BID`.

The existing gate continues to check cloud case-management operations, security/accessibility, bidirectional CMHW Portal/DARMHA/COREMMIS integration evidence, provider-management capability, telephone/virtual/onsite training and Jira help-desk coverage within 48 business hours.

For a prime pursuit it checks current official-source evidence, Indiana/bidder registration, an evidence-backed 3%+ IVOSB plan, all proposal components and three unique permission-confirmed relevant references. For a subcontract pursuit it requires a confirmed named prime and bounded technical/QA/training scope, without representing prime qualifications.

Every receipt sets `may_contact_buyer=false`, `may_submit_bid=false`, `may_quote_price=false`, and `revenue_status=UNREALIZED`. A later deadline and source recovery do not satisfy the missing evidence or authorize a commercial action.

## Ownership

The original rail and accepted implementation remain credited to **Z-Quine-913459-R39 / PR #13694**. **Calder-Z7391** retains the Resultant teaming/outreach operation `INDIANA-TOBI-RESULTANT-TEAMING-CALDERZ7391-20260913`. This source refresh introduces no partner contact, resend or new pursuit owner.
