# Business Packs — who buys each tier

Seat: SCOUT (Fable 5.1, Claude Code, owner PC). Owner-assigned marketing research seat, 2026-09-02.
Slack: `#marketing-research` `C0BUFLK7TNY`. Hub claim `scout-marketing-research-20260902-01`.

Grounding: factory scaffold on commons main `3a9e36b6` (PR #7516); laws in [ground/BUSINESS_PACKS.md](../../ground/BUSINESS_PACKS.md) (Bryce, `#business-packs` ts `1788323099.458239` and `1788323180.640899`); tiers in [land/sku-business-packs-20260902.md](../../land/sku-business-packs-20260902.md); first candidate `revenue/pack_keep_sell_candidates/yard-card-route-20260902-01/` (main `54a1f0592`).

This document is research. It names buyers, not businesses. Marketing execution and every dollar of spend stay with Bryce. Nothing here mints a checkout, an odds table, or an earnings claim. Where a number comes from a marketing blog rather than a primary source it is marked `(secondary)`.

Tier note: the channel and catalog name five tiers ($20 · $100 · $200 · $1,000 · $10,000). The owner's brief to this seat also named **$50**. It is profiled below as a recommended rung; whether it becomes a catalog tier is Bryce's call. Owner floor, 2026-09-02 evening: the pack floor is about $250–399 and the old $20/$50/$100/$200 stickers are retired for new mints; the two desk instances list at $250 (`PK-DESK-0001`, `PK-DESK-0002` in pack-market). The desk rows below were re-cut to $250 on 2026-09-04 (receipt `p/capstan-desk-pack-buyers-20260904-01.md`).

---

## 0. What every buyer is actually buying

Across all six tiers the product the buyer pays for is the same thing at different sizes: **the removal of the "what do I start, and what do I do first" decision, plus permission to begin this week.** The assets and the runbook are how that is delivered. The week-1 calendar in `packs/_template/week1.md` is the single most persuasive page in the pack for every tier below $1,000; show it in the ad.

The one marketing wedge the factory law hands us for free: **each sale is a distinct instance.** The market this competes with at the low end is the $17–$149 "prebuilt Shopify store" trade, which is publicly documented as clone-stamped templates with generic AI copy and "all look the same" complaints ([dropshippinghustle](https://www.dropshippinghustle.com/pre-built-dropshipping-stores/), [dropshiplifestyle](https://www.dropshiplifestyle.com/prebuilt-shopify-stores-scam-or-smart-investment/), [identixweb](https://www.identixweb.com/are-pre-built-shopify-stores-worth-it/)). "Nobody else gets this exact one" is true for us and false for them. Per the law, that claim is only usable when `host/business_pack_unique.py` says `UNIQUE` for the instance.

---

## 1. Why the cards skew the way they do: X's audience

- US is X's largest market, roughly 99M active users (Oct 2025) ([demandsage](https://www.demandsage.com/twitter-statistics/)).
- Largest age bloc 25–34 at ~37.5%; 33% of US 18–29s use X ([explodingtopics](https://explodingtopics.com/blog/x-user-stats), [socialpilot](https://www.socialpilot.co/blog/twitter-statistics)).
- Male 63–68% in the US; a 10–11 point gender gap at every age band ([onclusive](https://onclusive.com/resources/blog/x-twitter-statistics-2026/)).
- Household income: ~29% of US X users over $100k, ~20% at $70–99k, ~21% at $30–69k ([socialpilot](https://www.socialpilot.co/blog/twitter-statistics)) `(secondary)`.
- X's own claim: users 32% more likely to try new products and 39% more likely to buy advertised products than non-users ([shno.co](https://www.shno.co/marketing-statistics/twitter-ads-statistics)) `(platform marketing claim)`.

Consequence for spend: X is a strong channel for the **male 22–45 builder/operator** ($20–$1,000 tiers) and for the **SMB owner-operator** ($10,000 tier). It is a weaker channel for the **female 25–44 digital-products buyer**, who lives on TikTok, Instagram, Pinterest and Etsy (Etsy buyers 58–80% female, 25–44 core; digital downloads growing ~30% YoY on Etsy) ([printful](https://www.printful.com/blog/etsy-statistics), [electroiq](https://electroiq.com/stats/etsy-statistics/)). Where a pack's natural buyer is her (yard-greeting rental, planners, templates), X should get a smaller share of that pack's spend, or creative must be built for the minority of her that is on X.

---

## 2. Break-even before persona: what paid X can and cannot carry

Illustrative arithmetic only; Bryce sets prices. Stripe Payment Link fee assumed 2.9% + $0.30. Cold digital-product landing pages convert roughly 1–3%.

| tier | net per sale | max CPC at 1% conv | max CPC at 2% conv | verdict on paid X |
|---|---:|---:|---:|---|
| $20 | ~$19.1 | $0.19 | $0.38 | **Do not buy this tier with ads.** Median X CPC is quoted at $0.18 by agency data but typical is $0.50–2.00 ([autotweet](https://www.autotweet.io/statistics/x-twitter-advertising-statistics), [improvado](https://improvado.io/blog/twitter-ads-guide)). $20 is the organic / upsell entry, not the ad product. |
| $50 | ~$48.3 | $0.48 | $0.97 | Marginal. Works only with tight keyword intent and a strong door. |
| $100 | ~$96.8 | $0.97 | $1.94 | Positive at typical CPC. First tier worth a test budget. |
| $250 (was $200) | ~$242.5 | $2.42 | $4.85 | Positive with room for creative testing. Re-cut 2026-09-04 to the owner's $250 desk floor; the $200 row it replaces read ~$193.9 / $1.94 / $3.88. |
| $1,000 | ~$970.7 | $9.71 | $19.4 | Conversion, not CPC, is the constraint; needs 0.2–0.5% and a trust-heavy door showing the instance. |
| $10,000 | lead-gen | CPL $21–40 quoted for optimized X funnels vs ~$110 LinkedIn `(secondary)` ([christopholivier](https://christopholivierconsulting.com/twitter-x-ads-2026/)) | | Ads buy conversations, not checkouts. At 4% lead→close, CAC ≈ $500–1,000. Matches the sales law: YES first, then owner pastes the Payment Link. |

Spend allocation this implies: **test $100 and $250 first, then $1,000; run $10,000 as lead-gen; never buy $20 directly.**

---

## 3. Tier cards

Each card: who · trigger · job to be done · what the pack must contain to satisfy them · where they are on X (lookalike handles, keywords, conversation topics) · creative angle · words that work · words that break policy or law · objections · disqualifiers · evidence and confidence.

Handle lists are candidates for **follower look-alike** targeting (X recommends ~30 handles per campaign; verify each in Ads Manager autocomplete before use; follower counts move and sources disagree) ([business.x.com](https://business.x.com/en/help/campaign-setup/campaign-targeting/interest-and-follower-targeting)).

### $20 · STARTER · "Devon, 24" — the weekend-curious first-timer

- **Who.** 18–29. Gen Z / young millennial. Student, service job, or first office job. Male-skewed on X. 43% of Gen Z considering starting a business in 2026 (51% "seriously" in the last 12 months), highest of any generation ([lendingtree](https://www.lendingtree.com/business/small/starting-business-study/), [quickbooks](https://quickbooks.intuit.com/r/small-business-data/entrepreneurship-in-2026/)). Roughly 1 in 2 Gen Z runs a side hustle; 34% of Gen Z per Bankrate ([skillademia](https://www.skillademia.com/statistics/side-hustle-statistics/) `(secondary)`, [bankrate](https://www.bankrate.com/credit-cards/news/side-hustles-survey-2024)). Median side-hustle income is about $200/month; 51% earn $500 or less ([surveymonkey](https://www.surveymonkey.com/curiosity/side-hustle-statistics/)). Gen Z solopreneurs average under $10k in year one.
- **Trigger.** Payday, a "business ideas" thread, rent stress, a friend who started something. Impulse window: below ~$25 there is no deliberation; charm pricing lifts conversion 8–12% under $100 and the effect is strongest for impulse buys ([launchmystore](https://launchmystore.io/blog/psychology-ecommerce-pricing-strategies)).
- **Job to be done.** "Hand me something I can start Saturday without having to pick what to start." Not a course. A kit with a first action.
- **Pack must contain.** One-page start; the first three actions; printable or ready assets; a name they can say out loud; the week-1 calendar; nothing that needs more than ~$50 of further spend. A "desk" or "shop" upsell path inside the pack, because this tier cannot pay for its own ads (section 2).
- **On X.** Lookalikes: `@gregisenberg`, `@thejustinwelsh`, `@SahilBloom`, `@thedankoe`, `@levelsio`, `@marc_louvion`, `@tibo_maker`, `@thepatwalls`, `@starterstory`, `@nloper` (Side Hustle Nation), `@IndieHackers`, `@ShaanVP`, `@thesamparr`, `@AlexHormozi`, `@Codie_Sanchez`. Keywords: "side hustle", "side hustle ideas", "business ideas", "start a business", "extra income", "weekend business", "first business". Conversation topics: Entrepreneurship, Small business, Personal finance. Do **not** bid "make money online" or "passive income": they attract the get-rich-quick cohort and pull creative toward claims X prohibits.
- **Creative.** 15-second vertical "here's what's inside" with the week-1 calendar on screen; price anchored to a lunch order; "not a course, a kit"; "yours, nobody else gets this exact one" (only when the instance is `UNIQUE`).
- **Words.** kit · pack · runbook · start Saturday · everything you need · one-time, no subscription · yours.
- **Never.** guaranteed · passive · "$X/month" · quit your job · financial freedom · get rich · "limited spots" (fake-scarcity law) · any result inside a time period (X "Impractical Outcomes" policy; FTC earnings-claim definition).
- **Objections.** "Is this one of those $17 store scams?" → distinct instance, real assets listed on the door. "What if it doesn't work?" → refund policy is an owner decision (see law flags: chargeback thresholds).
- **Disqualify.** Anyone asking for income proof; anyone under 18.
- **Confidence.** High on who; medium on X reach for this buyer (young, male, present on X); high that paid X cannot carry a $20 ticket.

### $50 · recommended rung · "Second-Try Sam" — bought one kit before

- **Who.** 24–38. Has already bought a $17–$47 Gumroad/Etsy/Stan product and stalled. Wants the next one to feel like a real business: a name, printable assets, scripts, a 30-day calendar. The creator economy's median ticket sits right here: over 50% of Stan GMV is downloads priced $4–30 and the average Stan sale is ~$67 ([sacra](https://sacra.com/c/stan/), [netinfluencer](https://www.netinfluencer.com/stan-helped-creators-make-500m-selling-digital-products-its-biggest-lesson-was-that-products-arent-the-problem/)).
- **Trigger.** The first kit is still in Downloads, unopened for a month. A payday. Someone on X posting a "day 30" screenshot.
- **Job to be done.** "Make the second attempt feel less like a PDF and more like a thing with a name."
- **Pack must contain.** Everything in $20 plus a brand/name, one script (door, phone, or DM), a 30-day calendar, and a written "stop / pause" rule (the template already asks for it; it is a trust signal to this buyer).
- **On X.** Same lookalikes as $20 plus `@starterstory`, `@thepatwalls`, `@nloper`. Keywords add intent: "starting a side business", "how to get first customer", "first client". Price at $47 or $49.
- **Creative.** Before/after of the same person: "kit #1 sat in Downloads; kit #2 had a name and a calendar."
- **Words / Never / Objections.** As $20. Add "one price, all files, no upsell inside".
- **Confidence.** Medium; this rung is inferred from creator-economy price data, not from a landed pack.

### $100 · SHOP · "Truck-and-weekend Tyler" — the yard-card route buyer

This is where `yard-card-route-20260902-01` sits (RUNBOOK: print 50 cards, walk one neighborhood two hours, $40 bin-out / $60 tidy / $80 brush pile, cash or check, ~$12–40 to run a weekend).

- **Who.** 20–35, male, suburban or exurban, has a vehicle and free weekends, wants cash this weekend rather than a laptop business. College students home for summer. Parents buying it for a teenager. He follows Nick Huber's "sweaty startup" lane (X following quoted between 245K and 496K depending on date; podcast 1.5M+ downloads; newsletter 22K) ([thegrowthcmo](https://www.thegrowthcmo.co/p/sweaty-startup-nick-huber), [rephonic](https://rephonic.com/podcasts/the-sweaty-startup)) and lawn / pressure-washing / junk-hauling creators. 61% of first-time business buyers want a service business ([bizbuysell](https://www.bizbuysell.com/blog/2025-searchers-who-is-buying-businesses/)).
- **Trigger.** Saturday morning with nothing booked; a "started my lawn business with $200" post; needing $300 by the 1st.
- **Job to be done.** "Give me a route and a price sheet so I am working by noon Saturday."
- **Pack must contain.** Exactly what the runbook has (cards, price sheet, invoice text, route log) **plus the distinct-instance pieces the law requires**: a brand/name, a domain or door, and its own checkout placeholder. Finding for the factory: the current asset set reads like a $20–$50 kit. At $100 this buyer expects a name and a door. Either add the instance brand/door before SELL, or list the current asset set at $20/$50. Marketing cannot say "unique" until the fingerprint is.
- **Naming finding.** "Yard card" reads to most Americans as the yard-greeting-sign rental business (Card My Yard, Sign Dreamers), which is a different vertical with a different buyer (94% female-owned franchise base, birthdays 50–60% of bookings) ([americasbestfranchises](https://americasbestfranchises.com/franchises/card-my-yard/), [reservety](https://reservety.com/guides/yard-greeting/how-to-start-a-sign-rental-business.html)). Door copy should say "weekend yard-help route" so the ad does not buy the wrong buyer. The greeting-rental buyer belongs to the $1,000 card below.
- **On X.** Lookalikes: `@sweatystartup`, `@Codie_Sanchez`, `@thepatwalls`, `@starterstory`, `@ShaanVP`, plus lawn-care and pressure-washing creators found in Ads Manager. Keywords: "lawn care business", "pressure washing business", "junk removal", "sweaty startup", "cash business", "door hangers", "flyers", "side hustle this weekend". Conversation topics: Small business, Home improvement, Entrepreneurship. Age 18–34, US, mobile.
- **Creative.** POV: walking a block leaving cards, then the phone rings, then a $40 bin-out. Show the price sheet as a price sheet. Two-hour time budget on screen.
- **Words.** route · price sheet · cash or check · same-day · two hours · no app · no account.
- **Never.** "make $200 this weekend" or any dollar-per-time promise. Under 16 CFR 437.1 an earnings claim is any representation of a specific level or range of sales or income, express or implied ([govinfo](https://www.govinfo.gov/content/pkg/CFR-2025-title16-vol1/xml/CFR-2025-title16-vol1-part437.xml)). A price sheet is a price, not an earnings claim; "you'll make X" is.
- **Objections.** "I could print cards myself." → the route method, the phone script, the invoice, the name and the door are the product. "Is it legal to leave cards?" → the runbook's mailbox rule is already the answer; keep it on the door.
- **Confidence.** High on who; high that the price/asset mismatch is a real conversion problem; naming finding is a judgment call for the factory.

### $250 · DESK · "Laptop Lena / Desk Dan" — the evenings-and-weekends service business

- **Who.** 28–45, employed, household income $70–100k+, some digital skill or comfortable with AI builders, wants a legitimate second income line that does not need a truck. Codie Sanchez's audience description fits: young professionals and aspiring entrepreneurs, 20s–40s, building wealth outside a job ([castmagic](https://www.castmagic.io/creators/codie-sanchez)). The X income skew (29% over $100k HHI) is on his side.
- **Trigger.** A colleague's agency side-gig; the realization that local businesses have broken sites; a bonus he wants to turn into something.
- **Job to be done.** "Give me a service I can sell to local businesses from my laptop, with the demo and the price sheet already made."
- **Pack must contain.** The best-evidenced desk pack the hive already has parts for: a local-business website/app service. TALLY's `smb-showcase-inventory` (private main `0d91231e`) already has the reusable demo attachments; the SMB lead lane already found dozens of local businesses with observable gaps (broken quote form, "online booking coming soon", 2018 footers, no first-party site) ([#leads, 2026-09-01 00:24–00:31 EDT]). The pack needs: the lead-finding method, the outreach script that follows the sales law (no price in subject, YES first), the $1,500 / $2,500 / $4,000 price sheet already posted in #sales (`smb-finished-site-seven-day-lane-01`), a delivery checklist, a contract template placeholder, brand/domain/door. That is a real business, not a PDF.
- **On X.** Lookalikes: `@thejustinwelsh`, `@gregisenberg`, `@thedankoe`, `@levelsio`, `@marc_louvion`, `@IndieHackers`, `@starterstory`, `@thepatwalls`. Keywords: "web design business", "start an agency", "freelance web", "local SEO", "one-person business", "solopreneur", "AI website builder". Conversation topics: Entrepreneurship, Marketing, Technology. Age 25–44.
- **Creative.** A real (anonymized) broken local-business quote form on screen: "there are thirty of these in your zip code." Then the demo attachment. Then the price sheet.
- **Words.** service · clients · demo included · price sheet · seven-day delivery (only if the pack's runbook actually supports it).
- **Never.** Any client-count or revenue promise ("land 3 clients a month"). Any implication that leads or customers are provided; that would make the pack an FTC "business opportunity" (437.1 prong ii) requiring the 7-day disclosure document. Provide the *method*, not the customers, unless Bryce chooses to comply with 437.
- **Objections.** "I can't code." → AI builders and the showcase; the pack sells the selling method. "Why not just freelance on Upwork?" → Upwork lists $300–$1,500 landing pages and $1,500–$5,000 sites; the pack is the positioning to charge that ([#sales `smb-finished-site-seven-day-lane-01`]).
- **Confidence.** High on buyer; high on demand evidence for his customers (the hive measured it); medium on X reach.

### $1,000 · PLANT · "Corporate-refugee Renee / Kevin" — first-time business buyer who can't spend $35k

- **Who.** 32–52. 59% of BizBuySell's 2025 buyer survey are first-time entrepreneurs; ~42% are "corporate refugees"; Gen X and millennials lead; 61% want service businesses; 91% intend to buy within two years; 78% expect SBA financing ([bizbuysell Q1 2025](https://www.bizbuysell.com/blog/business-buyer-trends-q1-2025/), [bizbuysell searchers](https://www.bizbuysell.com/blog/2025-searchers-who-is-buying-businesses/)). Flippa's "side hustler" buyer averages ~$35k per acquisition ([flippa insights](https://flippa.com/blog/insight-report-december-2022/)); franchises under $10k exist but fees like Card My Yard's $10,350 are still 10x this tier ([entrepreneur](https://www.entrepreneur.com/franchises/these-are-the-top-franchises-under-10000-in-2025/490798), [americasbestfranchises](https://americasbestfranchises.com/franchises/card-my-yard/)). 64% of small businesses start with $10k or less and 33% with under $5k ([business.org](https://www.business.org/finance/loans/the-cost-of-starting-a-business/) `(secondary)`). $1,000 is the price of a whole business for the person who has savings but not $35k and does not want a franchise agreement.
- **Trigger.** A layoff or a re-org; turning 40 or 50; a spouse's "just do it"; reading Codie Sanchez's book (611K X followers; 110K newsletter) ([x.com/Codie_Sanchez](https://x.com/Codie_Sanchez/status/1956377120361361622), [quietlight](https://quietlight.com/podcast/codie-sanchez-talks-about-boring-businesses-and-gaining-1-5m-followers-in-24-months/)).
- **Job to be done.** "Sell me a real, named business with its own domain, booking door, inventory list and calendar, so the only thing I add is my time."
- **Pack must contain.** Brand and domain, booking or checkout door, complete inventory/equipment list with costs, supplier list, insurance/licensing checklist by state (owner review), 90-day ops calendar, support boundary. The distinct-instance law is the entire value proposition here: this buyer will not pay $1,000 for a template.
- **Best-evidenced plant verticals** (for peers; this seat does not pick the business): (a) **yard-greeting sign rental** — independent start $1–5k (some sources $4–9k), $75–150 per setup, birthdays 50–60% of bookings, side-hustle-compatible hours; the franchise version costs $10,350; owner base 94% female, moms/teachers/nurses/sales pros ([reservety](https://reservety.com/guides/yard-greeting/how-to-start-a-sign-rental-business.html), [howtostartanllc](https://www.howtostartanllc.org/how-to-start-a-yard-sign-business/), [fivestarfranchising](https://fivestarfranchising.com/card-my-yard/)). Note: this buyer is female-skewed and X is a weaker channel for her. (b) **home cleaning / turnover service** — the motel lane's TurnProof logic is adjacent. (c) **starter content site** — Flippa buyers under $500 are "buying time, setup and credibility" ([flippa starter sites](https://flippa.com/blog/how-to-generate-roi-from-buying-a-starter-site/)).
- **On X.** Lookalikes: `@Codie_Sanchez`, `@agazdecki` (Acquire.com), `@acquiredotcom`, `@flippa`, `@BizBuySell`, `@sweatystartup`, `@thepatwalls`, `@nickhuber`-adjacent ETA accounts. Keywords: "buy a business", "boring business", "franchise", "franchise under 10k", "acquisition entrepreneur", "ETA", "SBA loan", "business for sale", "quit corporate". Conversation topics: Small business, Investing, Franchising. Age 30–54, HHI targeting on if available.
- **Creative.** "A franchise fee starts at $10,350. This is the whole business for $1,000, and nobody else gets this one." (Comparison must stay truthful and sourced; no earnings.) Show the instance: the name, the domain, the door, the inventory list, the calendar. Trust is the conversion constraint at this price, so the landing page must show more than the ad promises.
- **Words.** your business · your name · your domain · inventory list · supplier list · 90-day calendar · one owner per instance.
- **Never.** Earnings, payback period, "recession-proof", "proven", "turnkey income". Any promise of locations or customers (437.1 prongs i–ii).
- **Objections.** "Why not buy a running business on Flippa?" → those start at ~$35k and come with someone else's problems; this is new, named, and yours. "What support do I get?" → the template's support boundary (public Commons post or mailto); state it plainly.
- **Confidence.** High on who (primary-source buyer surveys); medium on X as the channel for the female-skewed verticals; high that trust/proof on the door is the constraint.

### $10,000 · HEAVY · "Operator Owen" — the SMB owner or would-be franchisee

Channel law says heavy advertising for this tier is later and owner-owned. This card is the plan for when Bryce turns it on.

- **Who.** 35–60. Two overlapping buyers. (1) The **existing SMB owner-operator** (5–50 employees, $1–10M revenue) adding a service line or a second unit; the hive's B2B lanes show exactly where he is: motel owners (RoomShield pilot asks $900–1,500/property), dealer fixed-ops directors, plant managers, lab managers ([#sales motel lane 2026-09-01 06:04 EDT], REV-CATALOG). (2) The **would-be franchisee**: franchise prospects cluster mid-40s to 60; 15–25% already own a business; franchise owners are 69% male, average age 44; the 2025–26 wave is "formerly white-collar, highly educated, wants home-services" ([franchiseinsights](https://www.franchiseinsights.com/category/franchise-prospects/), [zippia](https://www.zippia.com/franchise-owner-jobs/demographics/), [franchiseba](https://www.franchiseba.com/franchise-broker-industry-trends-2026/)). Both compare $10,000 to a franchise fee of $10k–$50k plus royalties.
- **Trigger.** Q4 planning; a franchise discovery day that felt like a trap; a competitor adding a line; a slow season.
- **Job to be done.** "Hand me a business unit that runs: brand, site or app, booking/checkout, equipment list, hiring and insurance checklist, a 90-day plan, and a way to find the first customers, without royalties."
- **Pack must contain.** Everything in $1,000 plus: installer or hosted app where the vertical needs one (the motel suite is the model: portable ZIP + installer, SBOM, hashes), a hiring checklist, an insurance/licensing checklist, sales scripts that follow the sales law, and a defined support boundary. **Owner decision:** whether the pack includes a lead list or any promise of customers. The fleet has Apollo credits (205 lead / 160 direct-dial / 5,000 AI credits per the 2026-09-01 resource route), so it is technically possible, but including customers or accounts triggers 16 CFR 437 (business opportunity) and its 7-day disclosure document and earnings-statement rules. Ship "the method to find customers" or comply with 437; do not drift in between.
- **On X.** Correction to the dated "70% of SMBs use Twitter" figure: a March 2025 survey of 600 SMBs puts Facebook at 82%, Instagram 71%, YouTube 69%, TikTok 58%, with X not in the top ranks ([marketingdive](https://www.marketingdive.com/news/smbs-rely-heavily-on-social-media-for-marketing-and-growth-study-says/748730/)). So most SMB owners do not *promote* on X; the ones who *read* X skew to the tech-literate, finance-literate operator and the would-be franchisee following business creators. X is a precision channel for Owen, not a reach channel. B2B on X: CPL $21–40 vs LinkedIn ~$110 and Google ~$70; visitor-to-lead 0.69% vs LinkedIn 2.74% but at 7–10x lower CPC `(secondary)` ([christopholivier](https://christopholivierconsulting.com/twitter-x-ads-2026/), [growthspree](https://www.growthspreeofficial.com/blogs/power-your-b2b-saas-marketing-engine-with-twitter-ads-in-mins)). Founder-led "build in public" posts promoted as ads outperform polished creative for B2B on X `(secondary)`. Lookalikes: `@sweatystartup`, `@Codie_Sanchez`, `@Jobber`, `@ServiceTitan`, `@QuickBooks`, `@Gusto`, `@SBAgov`, franchise-industry handles. Conversation topics: Small business, Franchising, Home improvement, Business software. Keywords: "buy a franchise", "franchise fee", "second location", "add a service line", "home service business", "HVAC business", "pressure washing business", "cleaning company".
- **Creative.** Bryce on camera (founder-led), one unit, one number that is a price, not a projection. Lead form or booking link, not a checkout.
- **Motion.** Ad → lead form/landing → conversation → YES → owner pastes the Payment Link. Same as the existing sales law (no price in subject, no pre-sale transport). Ads here buy conversations.
- **Words.** business unit · no royalties · you own the brand and the domain · installer · 90-day plan · support boundary.
- **Never.** Revenue or payback projections; "proven system"; "we bring you customers" (unless 437 compliance is in place); anything that sounds like a franchise without the FDD (franchise law is a separate regime; do not use the word "franchise" for the product).
- **Objections.** "Why not a franchise?" → no royalties, you own everything, a fee not a contract. "Who supports it?" → the support boundary, stated. "Is this production-ready software?" → only claim what the private repo's gates have proven; the hive's own truth-table language ("candidate", "not release-authorized") applies.
- **Confidence.** High on who; medium on X as the channel (secondary stats); high that this is a lead-gen motion, not a checkout motion.

---

## 3b. Owner directive 2026-09-02 01:27 EDT — a percentage and partial ownership in the terms of service: how each buyer hears it

Recorded from the hub (Bryce, 01:27:49 EDT). Law side is in LAW_AND_POLICY_FLAGS.md §8. This is the buyer side, so door copy is not written before the owner picks the shape.

| tier | how the buyer hears "tjlabs keeps a percentage and partial ownership" | conversion effect | what softens it |
|---|---|---|---|
| $20 / $50 | Does not read the ToS. If he notices, "they want a cut of my $200/month?" | negligible on purchase; corrosive on word of mouth if enforced | a fixed-term cap; or exempting tiers under the $735 franchise-rule floor entirely |
| $100 Tyler | Cash business. A percentage of profit is unauditable and he knows it; "partial ownership" of his Saturday route reads as absurd | small at purchase; he assumes it is unenforceable | a flat renewal fee for the door and updates instead of a percentage |
| $250 Lena/Dan | Understands rev-share from software and agencies; will ask "for how long, on what base, what do I get for it" | moderate; converts if the answer is a licence with a term and services attached | "X% of gross reported through the door for 12 months, capped, includes updates and the demo kit" |
| $1,000 Renee/Kevin | Is paying $1,000 to *own* a business instead of a franchise. A seller equity stake is exactly what he is avoiding | **largest negative in the ladder**; equity language can kill this tier's paid funnel | a term-limited royalty framed as deferred purchase price; a third-party rating on the door; no equity |
| $10,000 Owen | Compares to franchise royalties of 4–12% gross plus a 1–4% marketing fund and expects franchise-grade support in return; an equity stake in his unit is a no from an existing owner | strong negative for the SMB-owner half; the would-be franchisee half accepts a royalty if support is real | royalty on gross with named support obligations; never "ownership" |

The factory law's best marketing claim ("yours; nobody else gets this instance") and "tjlabs owns part of it" cannot both be on the door. Research finding, not a recommendation: a **term-limited, capped royalty on gross reported through the seller-hosted door, disclosed in one line on the door and the ad**, is the shape that survives every card above; **equity/partial ownership is the shape that fails the two tiers paid X can actually carry at scale.** The owner decides.

## 4. The buyer for everything else already on the shelf

"Anyone for any pricing tier" includes what is already live. Mapped in [PACK_BUYER_MAP.json](./PACK_BUYER_MAP.json):

- **$1/week (sku-weekly), $3/mo tip, $5/mo seat, tips, unlock, boost** — supporters and readers of the Commons itself; not ad buys. Organic only.
- **$199 diagnostics (Dealer Service Lead Rescue, Plant Downtime Handoff, Referral Intake Completeness, Repair Booking Preflight)** with live Stripe links — buyer is a named operations director at a mid-size org; the hive reaches them by verified-route email under the sales law. X role: retargeting and founder-led credibility only; do not run cold X ads to $199 B2B diagnostics, the buyer is not browsing X for them.
- **$2,500 proofs / AquaTrace discovery** — same buyer class, same rule.
- **$250 White Box hour, $12k GGUF diagnostic, $15k survival sprint, $30k White Box pilot, $45k Titan** — technical buyers (open-weight labs, agent operators). X is a real channel for this cohort (developers, founders, PMs are over-represented on X), but the motion is founder-led content and DMs, not conversion ads.
- **Motel SKUs (RoomShield $900–1,500 etc.), SMB sites ($1,500–$6,000+)** — these are the $1,000–$10,000 buyer's cousins and the natural sources for HEAVY packs.

---

## 5. Build demands this research supports

Posted to `#build-demand` by SCOUT (see receipt). Peers decide the businesses; these are the buyer-backed asks.

1. **Yard-card route: add the instance brand/door or reprice.** Buyer evidence says $100 requires a name and a door; the runbook and assets alone read as $20–$50. Also rename door copy to "yard-help route" to avoid buying the yard-greeting buyer.
2. **DESK pack candidate: local-business website service.** All parts exist (TALLY showcase, SMB gap-finding method, #sales price sheet, sales law). Buyer: Laptop Lena / Desk Dan.
3. **PLANT pack candidate: yard-greeting sign rental.** Franchise comparison is sourced; female 30–50 buyer; X share small, so the pack door must convert from other channels too.
4. **Measurement slot for Bryce's spend:** a thank-you page on the pack door that the owner-pasted Payment Link redirects to, with an X Pixel slot the owner fills. Without it, spend cannot be measured (see X_ADS_BRIEF).

---

## 6. What this seat did not do

No spend. No checkout. No ad copy shipped. No odds. No earnings figures. No outreach. Every number above is cited; secondary marketing-blog numbers are marked. The persona names are labels for reading, not real people.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
