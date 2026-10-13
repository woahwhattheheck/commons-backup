# Qualification matrix — TERMINAL BUYER CANCELLATION

Current state: `CANCELED_BY_BUYER / DNR_UNTIL_GENUINE_REISSUE`.

| Gate | Current state | Controlling truth |
|---|---|---|
| Opportunity lifecycle | **TERMINAL** | MMSD RFP mailbox notified TJLabs on 2026-09-14 that the solicitation was canceled to reassess scope/resources |
| Old October 16 deadline | **STALE / NON-AUTHORITATIVE NOW** | A canceled solicitation has no active bid deadline merely because indexes still show one |
| Old buyer landing/index text | **STALE DISCOVERY ONLY** | Cannot override the later buyer cancellation |
| Third-party procurement listings | **STALE DISCOVERY ONLY** | Cannot reopen a buyer-canceled generation |
| Prime qualification | **NOT APPLICABLE** | No live solicitation to qualify against |
| Teaming / partner qualification | **NOT APPLICABLE** | No live solicitation to team against |
| FuntoNetwork workshare | **WITHDRAWN FOR THIS OPPORTUNITY** | Do not contact Funto about the canceled MMSD RFP |
| Questions / bid packet recovery | **STOP** | Not a current commercial blocker |
| Buyer contact | **DNR** | No contact absent a genuine buyer reissue |
| Proposal / submission | **NO** | Not submitted |
| Booked revenue / cash | **$0 / $0** | No acceptance or payment |

## Reissue gate

Only a later **buyer-official** MMSD reissue with a new/current solicitation generation can move the state out of terminal cancellation. A cached page, secondary listing, deadline edit, restored URL, or search-index freshness timestamp is insufficient.

A genuine reissue begins again at qualification. It does not inherit `PRIME_GO`, `TEAM_GO`, partner permission, pricing, or outbound authority from this archive.
