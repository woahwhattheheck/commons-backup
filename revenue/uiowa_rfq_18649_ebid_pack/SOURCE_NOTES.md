# UIOWA-001/UIOWA-131 source notes

## Field-layout source

**University of Iowa RFQ 18649 — Software Development, Security, Deployment, and AI-Readiness Assessment**  
Original issue date: August 31, 2026  
Original public eBid URL: `https://uiebid.ionwave.net/PublicDetail.aspx?bidID=7825&SourceType=1`

The session could not retrieve the IonWave detail page directly. A public cached copy of the original 17-page Bid Invitation was therefore used to reconstruct the submission-field layout:

`https://bqohpheioaljycjpwbjd.supabase.co/storage/v1/object/public/documents/documents/unique/059ee9822c014f2f247504ad8872ebaf8d754ccf785e45873466afeb83c07e85?download=Bid-Invitation.pdf`

The cached invitation is explicitly **not current for deadline authority**: it prints September 22, 2026. It is retained here only as evidence of the original field layout and instructions.

### Page map

- page 2: Attributes 1–2
- pages 3–7: Attributes 3–8
- page 8: Attributes 9–10
- page 9: Attributes 11–14
- page 10: Attributes 15–19
- page 11: Attributes 20–23
- page 12: Attributes 24–27
- page 13: Attributes 28–30
- page 14: Attributes 31–35
- page 15: Attribute 36 and Fee for Services / Fee Details
- page 16: Supplier Information / binding-submission certification
- page 1: required Proposal and Audited Financial Statements attachments

## Current deadline overlay

Commons current preparation records document **September 29, 2026, 3:00 PM Central** in:
- `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_CHANGELOG.md`
- `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`
- `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT_REDLINE.md`

Those files state that the controlling RFQ, amendments, Q&A, and eBid instructions supersede preparation artifacts.

## Commercial source

`COMMERCIAL.md` and the acceptance exhibit record a $24,000 fixed TJLabs base workshare, optional $4,000 readout support, and travel excluded from the TJLabs carrier. The RFQ requires the Supplier’s fixed-price engagement to include expected expenses. The renderer therefore treats $24,000 as a candidate workshare input, not an automatically submission-ready Fee for Services.

## Deliberately unresolved facts/certifications

The carrier does not infer bidder references, legal company/contact/signature information, named personnel, financial statements, offshoring posture, payment methods, agreement selections, compliance certifications, or legal exceptions. Each is mapped to an explicit owner action.

## Final-source rule

Before paste/submission an authorized operator must re-open the controlling University eBid RFQ 18649 record, inspect amendments/addenda/Q&A and confirm field layout/required status/limits, record the exact current source/version in `source-state.json`, resolve all certification/contact/reference/attachment/price blockers, and rerun `python render_ebid.py --mode submit-ready`.

This carrier performs no portal action.
