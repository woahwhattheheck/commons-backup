# Paperwork inside the pack — what each buyer faces, what we may hand them, and how to say it

Owner direction (Bryce, hub `C0BU51F1PL3`, 2026-09-02 01:43:36 EDT), verbatim: *"Make business packs help the customer out with all the required paperwork for each pack as well."*

Build side: `cursor-business-pack-paperwork-20260902-01` owns `packs/_template/paperwork.md`. This file is the research that build and the door copy should stand on. Research only; the unauthorized-practice-of-law line below is a counsel question, flagged **OWNER/counsel**.

## 1. Why this is the biggest conversion lever on the shelf

Every buyer card says the buyer is paying for the removal of the "what do I do first" decision. Paperwork is where that decision actually dies: entity, EIN, permits, insurance, contracts. A pack that hands the buyer a state-specific, ordered checklist with the exact portals, the exact fees, and pre-filled templates is the single strongest substantiation of "we did most of the work for you" (MESSAGING_ANGLE §2) and the thing no $17 prebuilt-store seller has ever shipped. At $1,000 and $10,000 it is also what the corporate refugee and the operator expect from anything they compare to a franchise.

## 2. What each vertical actually needs (planning ranges, US; every item varies by state and city)

| pack / vertical | entity | federal | state / local | insurance | contracts | typical cash to be legal |
|---|---|---|---|---|---|---|
| **$100 yard-help route** (cash service, one person) | sole proprietorship is enough; optional DBA if a business name is used ($10–$100 by state) | none required (SSN works for a sole prop; EIN free if wanted) | general business licence in some cities ($25–$100); **services are not sales-taxable in most states**, so usually no seller's permit; check local yard-waste rules | general liability optional but wise: lawn-care GL averages ~$46/month (~$550/year); many homeowners never ask, commercial accounts always do | a one-page invoice/receipt (already in the candidate's assets) | **$0–$200** |
| **$100–$200 pressure-washing or similar equipment route** | sole prop or LLC | EIN if LLC | business licence $25–$100; contractor licence in a few states ($300–$500 with exam); **stormwater/wash-water rules** and environmental permits $50–$300 | GL $500–$2,500/year; $1M/$2M limits are the floor for commercial and municipal accounts | invoice, simple service agreement | **$100–$800** licensing, plus insurance |
| **$200 DESK website service** | sole prop or single-member LLC ($50–$500 state fee) | EIN (free) for banking and W-9s | business licence where required; sales tax on digital/web services varies by state | professional liability optional; GL rarely demanded | client agreement template, W-9, invoice; ownership/handoff clause for domains and accounts | **$50–$600** |
| **$1,000 yard-greeting sign rental** | LLC is the norm ($50–$500) | EIN (free) | general business licence or home-occupation permit; **seller's permit: rentals of tangible property are taxable in many states**; **sign ordinances** for temporary yard signs; HOA rules if home-based; realtors and commercial clients require proof of insurance | GL $300–$600/year; inventory cover for the signs | rental agreement with damage/weather terms, booking confirmation | **$150–$1,200** plus inventory |
| **$10,000 HEAVY unit (home service or similar)** | LLC | EIN; payroll registrations if hiring | state/local licences by trade (some $300–$500 with exam); environmental permits; vehicle/commercial insurance; workers' compensation once there is an employee | GL at $1M/$2M; commercial auto; workers' comp | service agreements, employment paperwork, subcontractor agreements, W-9s | **$1,000–$5,000** before equipment |

Sources for the ranges: [Jobber pressure-washing guide](https://www.getjobber.com/academy/pressure-washing/how-to-start-pressure-washing-business/), [Housecall Pro lawn-care guide](https://www.housecallpro.com/resources/how-to-start-landscaping-business/), [US Chamber DBA guide](https://www.uschamber.com/co/start/strategy/doing-business-as-dba-guide), [US Chamber seller's permit guide](https://www.uschamber.com/co/start/strategy/sellers-permit-and-tax-id), [TechInsurance lawn-service cost](https://www.techinsurance.com/landscaping-insurance/lawn-service/cost), [MoneyGeek pressure-washing insurance](https://www.moneygeek.com/insurance/business/contractor/pressure-washing/cost/), [Reservety sign-rental guide](https://reservety.com/guides/yard-greeting/how-to-start-a-sign-rental-business.html), [howtostartanllc yard sign](https://www.howtostartanllc.org/how-to-start-a-yard-sign-business/), [ZenBusiness lawn-care LLC](https://www.zenbusiness.com/lawn-care-llc/) `(secondary)`.

**Factory consequence:** paperwork is a *state-specific instance attribute*. The buyer's state (and often city) decides the list, so the pack's paperwork page must be generated per instance from the buyer's location, not written once. That is the build note for `cursor-business-pack-paperwork-20260902-01`: a checklist template with state slots, not a national list.

## 3. The line we must not cross — unauthorized practice of law (OWNER/counsel)

What non-lawyers may hand a buyer, under the "self-help" exemption courts have recognized in the LegalZoom litigation: **checklists, ordered steps, links to the official portals (Secretary of State, IRS EIN, state Department of Revenue, city licensing), fee tables, and blank or generically pre-filled templates the buyer completes and files themselves** ([Georgetown Journal of Legal Ethics on LegalZoom UPL claims](https://www.law.georgetown.edu/legal-ethics-journal/wp-content/uploads/sites/24/2019/11/GT-GJLE190045.pdf)). What crosses into the practice of law in many states: **choosing the entity for a specific buyer, filing on their behalf as a service, drafting or tailoring contracts to their situation, or answering "what should I do in my case."** LegalZoom fought North Carolina, California and Missouri over exactly this boundary, settled with limits, still discloses UPL as a risk in its 2025 SEC filings, and moved into a licensed law-firm structure in Arizona in 2025 ([NerdWallet LegalZoom review](https://www.nerdwallet.com/business/legal/learn/legalzoom-review), [JD Supra LegalZoom UPL](https://www.jdsupra.com/topics/legalzoom/unauthorized-practice-of-law/)).

Consequences for the pack and the door:
- The pack provides **the checklist, the portals, the fees, the templates, and the order of operations.** The buyer files. The door says so.
- Entity choice is presented as **information, not advice** ("most operators in this vertical use X; here is why some choose Y; your accountant or attorney decides").
- Filing-as-a-service is **referred out** to a licensed formation service (below), never performed by tjlabs or a peer.
- Contract templates carry a plain "template; have a professional review for your state" line.

## 4. Formation-service partners can pay for the help

The filing step the pack cannot do is exactly what formation services sell, and they pay referrers per formation. Published or trade-reported payouts `(secondary)`: ZenBusiness $12–$100 per conversion with volume tiers (Awin/FlexOffers) ([ZenBusiness affiliate program](https://www.zenbusiness.com/affiliate-program/), [FlexOffers ZenBusiness](https://www.flexoffers.com/affiliate-programs/zenbusiness-pbc/)); Bizee (formerly Incfile) up to ~$175 per sale via ShareASale/Awin ([Bizee affiliates](https://bizee.com/affiliates)); Northwest Registered Agent $100 per sale ([Northwest affiliate program](https://www.northwestregisteredagent.com/affiliate-program)); LegalZoom $15–$150 per sale depending on service, formations at the high end ([LegalZoom affiliate via UpPromote](https://uppromote.com/affiliate-directory/legalzoom/)).

Research shape: the paperwork page links one formation partner for "file it for you" with an FTC-compliant disclosure ("if you use this link, they pay tjlabs; you pay the same"). At $60–$175 per formation, the paperwork help can be revenue-neutral or positive on the $1,000 and $10,000 tiers, and it removes the filing step from tjlabs' hands, which is also the UPL answer. **OWNER:** partner program signup and disclosure language are his; the FTC Endorsement Guides require the material-connection disclosure to be clear and conspicuous, on the page, near the link.

## 5. How "paperwork included" is claimed truthfully

| say | do not say |
|---|---|
| "Your state's paperwork checklist, in order, with the official links and fees, is inside." | "We handle your legal paperwork." |
| "Templates for the invoice, the client agreement, and the booking confirmation; you fill in your details." | "Contracts drafted for you." |
| "Entity options explained; you or your accountant choose." | "We set up your LLC." (unless a licensed partner does it, disclosed) |
| "Insurance: what to ask for, typical cost, who to call." | "Fully insured business" / "compliant in all 50 states." |
| "We did the paperwork homework so you do the filing in an afternoon." | "Legal compliance guaranteed." |

The middle column is also what X's "non-existent features" clause and TikTok's disclaimer rule punish: promising a service the pack does not perform.

## 6. Per-buyer read

- **Devon ($20) / Sam ($50):** a one-page "you probably need nothing but this" sheet removes the fear entirely; the sole-prop truth is the reassurance.
- **Tyler ($100):** "no LLC needed to start; here is when you would want one and what it costs" keeps him moving Saturday.
- **Lena/Dan ($200):** the client agreement template and the W-9 are the deliverables he values most; EIN and invoice next.
- **Renee/Kevin ($1,000):** the ordered checklist with state fees is the proof this is a business and not a PDF; the seller's-permit and sign-ordinance items in particular are what she did not know she needed.
- **Owen ($10,000):** expects the full stack (licences, insurance limits, hiring paperwork, workers' comp trigger) as a table, and expects the support boundary to say who answers paperwork questions after the sale.

## 7. Law notes that ride along

- Paperwork help is "significant assistance" under the Franchise Rule's second element; harmless while the first element (a tjlabs trademark on the buyer's business) stays absent (LAW_AND_POLICY_FLAGS §8a).
- A paperwork page that includes the buyer's location and entity data is personal information the door collects; it belongs under the same privacy notice the pixel work already requires (DATA_BUYING §6).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

