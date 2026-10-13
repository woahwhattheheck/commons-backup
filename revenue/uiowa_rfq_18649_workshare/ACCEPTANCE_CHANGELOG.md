# UIOWA-005 — clause-to-source change log

Status: **PROPOSED / NOT ACCEPTED**. This log documents the correction carrier; it does not authorize submission, signature, buyer contact, spend, invoicing, payment, or revenue recognition.

| Clause / artifact | Prior state | Revised state | Source / authority | Verification |
|---|---|---|---|---|
| RFQ response deadline | Sent v1.0 and older repository context said Sep. 22, 2026, 3:00 PM CT. | Sep. 29, 2026, 3:00 PM CT. | University eBid RFQ 18649 public solicitation state for the current work order; official portal remains controlling: https://uiebid.ionwave.net/PublicDetail.aspx?bidID=7825&SourceType=1 | Clean exhibit header + final authority paragraph + README updated. |
| WP4 product/vendor language | Sent v1.0 allowed “no vendor/product prescription unless Clark's explicitly directs it.” | Prime direction alone cannot authorize a specific-product/vendor recommendation. | RFQ 18649 scope/out-of-scope boundary excludes recommendations for specific commercial products/vendors. | New §4.5 scope lock; draft acceptance criterion 5 hardened. |
| Product/vendor change control | Sent v1.0 said product/vendor selection was outside workshare unless separately authorized in writing. | Specific product/vendor recommendation or selection is not an ordinary change-control item; only a formal controlling-solicitation amendment can reopen it. | Controlling RFQ scope outranks subcontract-side change control. | §7 explicitly separates RFQ scope lock from ordinary change control. |
| Prime recommendation responsibility | Prime retained final recommendations without an explicit product/vendor caveat. | Prime retains final in-scope practice/process recommendations; specific commercial product/vendor recommendations remain excluded. | RFQ scope boundary + existing prime/TJLabs responsibility split. | §9 clarified without moving bidder/submission authority. |
| Acceptance authority ceiling | Vendor endorsement was implicitly bounded but not enumerated in the repository exhibit. | Explicitly unauthorized: recommendation, ranking, shortlist, endorsement, selection, or prescription of a specific commercial product/vendor. | RFQ scope + sent-exhibit authority boundary. | §10 enumerates the prohibition. |
| Commercial milestones | $24k base; $9.6k / $9.6k / $4.8k; optional $4k; travel excluded. | **No change.** | `COMMERCIAL.md` and prior sent exhibit. | Existing §2 economics preserved byte-for-substance. |
| Work package / review shape | Five base production packages, optional readout, responsibility split, consolidated comments, artifact conformance/cure. | **No change to underlying shape.** | Prior sent exhibit v1.0 + current acceptance exhibit. | Redline records these as intentionally preserved. |

## Source register

1. **Controlling public solicitation:** University of Iowa RFQ 18649 eBid public detail, bidID 7825. Re-read immediately before any proposal submission; a later University amendment supersedes this carrier.
2. **Sent baseline:** `TJLabs-UIowa-RFQ18649-Technical-Workshare-Exhibit.pdf`, version 1.0, prepared September 13, 2026; private outbound record used only to identify the stale deadline and permissive product/vendor clause.
3. **Commercial baseline:** `COMMERCIAL.md` in this directory.
4. **Clean corrected exhibit:** `ACCEPTANCE_EXHIBIT.md` in this directory.

## Decision rule

If the controlling RFQ later changes its deadline or product/vendor scope, update the clean exhibit and this log from the official solicitation before any external submission. Do not infer permission from a prime request where the University solicitation itself is narrower.
