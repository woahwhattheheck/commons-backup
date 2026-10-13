<!-- provenance: written by a headless Claude run through integrations/claude_headless; session 09d878c9-1f5c-4324-963b-99cfdb1b4fb9, final run 29a84045213d4815, model claude-fable-5, 145 turns, $13.819664000000005, 1350705 ms; tools WebSearch/WebFetch/Write/Read only, no MCP; nobody was contacted. Verbatim child output below. -->

# Open LIMS / lab-software solicitations (US & Canada) — verified 2026-09-05

After ~65 web searches and ~45 page fetches, exactly **three** currently open solicitations met all criteria (LIMS/lab-software scope, US/Canada public buyer, fetched page confirms open, due date on or after 2026-09-15). Two more were fetch-verified open but miss the date cutoff: **City of Billings, MT — Laboratory Information Management System (due Sep 5, 2026)** and **Ohio Department of Health — Whole Genome LIMS (due Sep 10, 2026)**. Most other LIMS solicitations found (OCWD, Montgomery County MD, Houston Health Dept., Abilene TX, MWD Salt Lake & Sandy, U. of Iowa, Kansas DOA, Bureau of Reclamation, MD OCME, Four Rivers, Padre Dam, Olmsted County, Clean Water Services) were fetch-verified as already closed or awarded. A grep of the full CanadaBuys open-tender CSV (fetched 2026-09-05) found no open Canadian federal LIMS/lab-data tender.

| Opportunity | Buyer (org, location) | What they want | Due date | Evidence URL | Rough value | Fit (1-5) | Next useful action |
|---|---|---|---|---|---|---|---|
| Laboratory Information Management System (LIMS) RFP | City of Englewood (municipal utility), Englewood, CO | Procurement of a LIMS for the City's Utilities Department — provision, implementation, configuration, integration, testing, deployment, support and maintenance. Released Aug 20, 2026. | September 17, 2026 (as stated on fetched page) | https://starbridge.ai/rfp/laboratory-information-management-system-lims-rfp-65 | Not stated on posting | 5 — exact target profile: municipal water utility lab replacing its LIMS | Pull the RFP package via Englewood's posting on the Rocky Mountain E-Purchasing System (BidNet Direct, Colorado); procurement contact of record is the City's Procurement Supervisor. Deadline is ~12 days out, so triage immediately. |
| Laboratory Information Management System (LIMS) Replacement and Implementation Services (RFP) | Loudoun Water (water/wastewater special district), Ashburn, VA | Full LIMS replacement plus implementation services for the utility's laboratory operations. Released Aug 3, 2026. | September 17, 2026 (as stated on fetched page) | https://starbridge.ai/rfp/laboratory-information-management-system-lims-replacement | Not stated on posting | 5 — drinking-water/wastewater utility LIMS replacement, the core scenario requested | Register on Loudoun Water's Bonfire portal (loudounwater.bonfirehub.com) to download documents; portal is JavaScript-only so the listing could not be fetched directly, but the opportunity was confirmed open on the evidence page. |
| Laboratory Information Management System (RFP) | City of San Diego (Public Utilities Dept. laboratories), San Diego, CA | A "modern, holistic, and integrated" LIMS supplied and implemented for diverse laboratory operations with complex data management, reporting, and regulatory-compliance needs (the City's Environmental Monitoring & Technical Services division runs eight labs; incumbent per city ordinance O-21652 is Labworks LLC). Released Aug 20, 2026. | September 21, 2026 (as stated on fetched page) | https://starbridge.ai/rfp/laboratory-information-management-system-request | Not stated on posting | 4 — large, high-value municipal water-quality lab system; strong fit but likely a crowded field with an entrenched incumbent | Locate the solicitation on the City of San Diego's PlanetBids vendor portal to get the RFP number and full spec; review the Labworks incumbency (ordinance O-21652 on docs.sandiego.gov) before deciding to bid. |

## Not verified

Found but could not be confirmed by fetching (blocked, JS-only, or no due date obtainable) — status unknown, do not rely on these without checking:

- **Maryland Dept. of State Police — LIMS** — listed under "open bids" on BidNet Direct (https://www.bidnetdirect.com/maryland/solicitations/open-bids/statewide/LABORATORY-INFORMATION-MANAGEMENT-SYSTEM-LIMS/443438440063); bidnetdirect.com returns HTTP 403 to fetches, so open status and due date unconfirmed.
- **U.S. Customs & Border Protection — COTS forensic LIMS** (evidence entry/routing, chain-of-custody tracking) — BidNet Direct abstract (https://www.bidnetdirect.com/public/supplier/solicitations/statewide/2541439752/abstract); 403 on fetch, status unconfirmed; federal/forensic rather than water-lab focus.
- **Michigan MDHHS — Newborn Screening COTS LIMS RFP** — referenced in Starbridge search results; no fetchable page with a due date was found (Michigan SIGMA portal requires login).
- **DemandStar bid #432383 — "Laboratory Information Management System (LIMS)"** (https://www.demandstar.com/app/limited/bids/432383/details) — page is JavaScript-rendered; buyer and dates could not be extracted.
- **TechBids listing #7465 — "Laboratory Information Management System RFP (Updated)"** (https://techbids.com/bids/7465/) — returned HTTP 404 on fetch.
- **New York State Contract Reporter — "laboratory information management system (lims)" ad** (nyscr.ny.gov) — returned 404/login-required on fetch.
- Primary-source portals for the three table rows (Rocky Mountain E-Purchasing for Englewood, Bonfire for Loudoun Water, PlanetBids for San Diego) could not be fetched directly (403/JS); the three rows are verified via the fetched Starbridge listing pages shown in the Evidence URL column, each of which stated open status and the due date on 2026-09-05.

## Search log

WebSearch queries run (condensed; each ran once unless noted):

1. RFP "laboratory information management system" LIMS 2026 proposals due city water utility
2. "request for proposals" LIMS "laboratory information management" due October 2026
3. open bid LIMS software wastewater treatment plant laboratory 2026
4. "laboratory information management system" RFP due "September 2026" OR "October 2026" OR "November 2026"
5. LIMS RFP bids tenders Canada 2026 "laboratory information management system" open
6. "chain of custody" software RFP laboratory 2026 proposals due
7. rfpmart "laboratory information management system" deadline 2026
8. "water quality" laboratory "sample tracking" software RFP 2026 city county
9. university RFP "laboratory information management system" 2026 proposals
10. "public health laboratory" LIMS RFP 2026 proposals due state
11. bidsandtenders LIMS "laboratory information" 2026 Ontario OR Alberta OR "British Columbia"
12. "environmental laboratory" OR "water laboratory" LIMS replacement RFP September 2026
13. SAM.gov "laboratory information management system" solicitation 2026 offers due
14. Bonfire OR OpenGov OR DemandStar LIMS "laboratory information management system" 2026 open RFP
15. canadabuys tender "laboratory information management" 2026 closing (plus fetch + local grep of CanadaBuys newTenderNotice and openTenderNotice open-data CSVs)
16. Loudoun Water LIMS RFP laboratory information management system 2026
17. "City of Billings" LIMS laboratory information management RFP 2026
18. "City of Englewood" LIMS laboratory information management system RFP 2026
19. "LIMS" RFP posted "August 2026" laboratory information management
20. Houston public health laboratory LIMS RFP solicitation 2026
21. Montgomery County cloud-based LIMS solicitation 2026
22. instantmarkets LIMS laboratory information management system RFP due 2026
23. merx "laboratory information management system" 2026 closing RFP
24. Kansas Bureau of Investigation LIMS RFP proposals due 2026
25. "bids.aspx" OR "bid_detail" LIMS laboratory information management 2026
26. "environmental data management system" OR "water quality data management" RFP 2026 proposals due software
27. "LIMS" solicitation "closing date" "2026" laboratory water/environmental/wastewater September/October
28. "LIMS" RFP "pre-proposal" 2026 water/wastewater/environmental laboratory September
29. "laboratory information management system" RFI 2026 water utility responses due
30. "city of" LIMS RFP 2026 laboratory information management -orange -ocwd
31. emarketplace Pennsylvania LIMS laboratory information management solicitation 2026
32. rfpmart LIMS OR "laboratory information" deadline "September" OR "October" 2026
33. govcb "laboratory information management" 2026 bid due September/October/November
34. Allegheny County Health Department "RFP-9025" OR LIMS RFP due
35. "BC Bid" OR "Alberta Purchasing" OR "Ontario Tenders" LIMS 2026
36. LIMS RFP open now september 2026 laboratory
37. sam.gov LIMS "laboratory information management" 2026 "response date" active water OR environmental
38. "starbridge.ai/rfp" laboratory OR LIMS "2026"
39. Michigan newborn screening "LIMS" RFP 2026 proposals due SIGMA
40. civiciq "LIMS" OR "laboratory information management" 2026
41. "sample tracking" OR "chain of custody" "request for proposals" laboratory 2026 due date
42. SEAO appel d'offres LIMS "laboratoire" 2026
43. sandiego.gov LIMS RFP laboratory information management system 2026 Public Utilities
44. Pennsylvania Department of Agriculture LIMS RFP 2026
45. "public health" OR "environmental" laboratory "LIMS" RFP due 2026 state posted August
46. "laboratory" software RFP "due September 30, 2026" OR "due October 1, 2026" OR "due October 15, 2026"
47. RFP "LIMS" OR "laboratory information management" issued "August 2026" OR "September 2026"
48. University of Iowa "tissue and cellular therapy" LIMS RFI OR RFP due September 2026 (plus fetch of UI eBid IonWave open-events list)
49. Maryland State Police "laboratory information management system" solicitation 2026 eMMA due
50. "25448" "DOIT" LIMS laboratory information management RFP
51. mygovwatch LIMS laboratory information management bids
52. "CB-2558" Abilene LIMS proposals due
53. highergov OR openopps OR mygovwatch "Loudoun Water" LIMS replacement 2026
54. "Englewood" LIMS "September 17, 2026" OR "9/17/2026"
55. rockymountainbidsystem OR "rocky mountain e-purchasing" Englewood laboratory information management
56. "Loudoun Water" bonfire "Laboratory Information Management System" OR "LIMS"
57. starbridge.ai "Loudoun Water" laboratory information management
58. "whole genome" LIMS Ohio Department of Health RFP due date 2026
59. "demandstar" OR "opengov" OR "bidexpress" LIMS September OR October 2026
60. "bonfirehub" OR "ionwave" OR "planetbids" OR "publicpurchase" OR "vendorregistry" LIMS 2026
61. "1181605" LIMS laboratory information management system
62. "Laboratory Information Management System (LIMS) Replacement and Implementation Services"
63. LIMS RFP announcement posted this week water utility laboratory September 2026
64. "laboratory information management system" proposals due "October 2026"
65. instantmarkets.com LIMS "laboratory information" due "Sep 2026" OR "Oct 2026" OR "Nov 2026"

Key verification fetches (beyond the three evidence URLs): OCWD RFP list (all three LIMS items due Apr 16 / Jul 31 / Aug 20, 2026 — closed), Montgomery County MD RFP #1181605 via HigherGov (due Mar 2, 2026 — closed), Billings city bids page (no LIMS listed; Starbridge showed due Sep 5, 2026), MWD Salt Lake & Sandy bids page (no LIMS open), University of Iowa eBid list (no LIMS), Allegheny County DHS solicitations (no LIMS), Kansas DOA RFP page (none), Four Rivers Sanitation Authority (closed 2018, awarded), Padre Dam MWD (closed 2023), Olmsted County MN RFP2025-328 (closed Mar 7, 2025), Clean Water Services Bid Locker (award pending, closed), Houston HHD RFP-2025-0047 (closed Dec 12, 2025), Abilene CB-2558 (closed Sep 19, 2025), Bureau of Reclamation LIMS 140R8125Q0224 (awarded Sep 24, 2025), FBI LIMS (pre-RFP forecast only), MD OCME LIMS (post-bid 2023), CanadaBuys open-tender CSV grep (no LIMS matches).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
