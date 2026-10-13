# X Ads brief for the business-pack tiers

Seat: SCOUT (Fable 5.1). Research for Bryce's own spend decisions. Nothing here is executed by this seat. Numbers from marketing blogs are marked `(secondary)`; platform-published facts cite business.x.com.

## 1. What X Ads is in September 2026

- **Ads Manager overhaul, April 2026.** X described it as its largest ad-system change: AI-driven contextual and semantic targeting, faster optimization ([mediapost](https://www.mediapost.com/publications/article/414738/x-overhauls-ad-platform-again-this-time-via-ai.html)).
- **Grok inside Ads Manager.** "Prefill with Grok" turns a URL into copy, image and CTA; "Analyze Campaign with Grok" explains performance; a July 2026 beta lets advertisers ask Grok for approach guidance ([socialmediatoday](https://www.socialmediatoday.com/news/x-adds-grok-powered-insights-to-ads-manager/825497/), [socialsamosa](https://www.socialsamosa.com/news-2/x-beta-testing-grok-ai-integration-ads-manager-12172642)). Stated direction: full automation including safety checks and content matching, and ads inside Grok answers.
- **No minimum daily budget** for standard campaigns; practical floors quoted at $20–50/day awareness and $50–100/day conversions `(secondary)` ([stackmatix](https://www.stackmatix.com/blog/x-twitter-ads-cost), [heyoz](https://heyoz.com/blogs/are-x-twitter-ads-worth-it-for-businesses)).

## 2. Costs to plan with

Ranges disagree across sources; plan with the pessimistic end and let the pixel tell the truth.

| metric | range quoted | source |
|---|---|---|
| CPC | $0.18 median (agency aggregate, avg spend $385/mo); $0.50–2.00 typical; $3–5 competitive topics | [autotweet](https://www.autotweet.io/statistics/x-twitter-advertising-statistics), [improvado](https://improvado.io/blog/twitter-ads-guide) `(secondary)` |
| CPM | $3–9 broad; $8–16 B2B; $18–25 competitive verticals | [shno](https://www.shno.co/marketing-statistics/twitter-ads-statistics), [christopholivier](https://christopholivierconsulting.com/twitter-x-ads-2026/) `(secondary)` |
| CPL (B2B, optimized) | $21–40 vs ~$110 LinkedIn, ~$70 Google | [christopholivier](https://christopholivierconsulting.com/twitter-x-ads-2026/) `(secondary)` |
| Engagement rate | ~0.1–0.6% (lowest of the majors; TikTok ~4–6%) | [creaticalc](https://creaticalc.com/engagement-rate-benchmarks) `(secondary)` |
| vs Meta | X CPC ~$0.74 vs Meta ~$1.41; CPM $6.46 vs $7.19 | [autotweet](https://www.autotweet.io/statistics/x-twitter-advertising-statistics) `(secondary)` |

Cross-platform context: TikTok has the cheapest CPM and highest engagement but curiosity clicks; Meta has the highest ROAS (~4.2x quoted) and buyers closer to purchase; X is cheapest per click for the male builder/operator cohort `(secondary)` ([digitalapplied](https://www.digitalapplied.com/blog/social-media-advertising-roi-2026-platform-guide), [trendtrack](https://www.trendtrack.io/blog-post/tiktok-vs-meta-cpm)). For female-skewed packs, the money is on TikTok/Instagram, not X.

## 3. Targeting that fits each tier

X targeting types ([business.x.com campaign targeting](https://business.x.com/en/help/campaign-setup/campaign-targeting)):

- **Follower look-alikes** — people who behave like followers of chosen handles; ~30 handles per campaign recommended. Strongest signal for our buyers (see handle lists per tier in BUYER_TIERS.md).
- **Keywords** — users who recently posted, searched, or engaged with terms; bulk import under Targeting → Audience features ([keyword targeting](https://business.x.com/en/help/campaign-setup/campaign-targeting/keyword-targeting), [aikenhouse](https://www.aikenhouse.com/post/keyword-targeting-on-x-twitter-how-does-it-actually-work-in-2026)).
- **Conversation topics / interests** — broad; use as a ceiling, not the base.
- **Custom audiences** — website visitors (pixel), engagers of past posts, lists. Retargeting is where X earns its keep for $1,000 and $10,000 tiers.

Recommended layering: look-alike base → keyword intent layer → geo US → age band per tier → exclude prior purchasers (pixel).

Per-tier summary (details in BUYER_TIERS.md):

| tier | base handles (verify in Ads Manager) | intent keywords | age |
|---|---|---|---|
| $100 SHOP | sweatystartup, Codie_Sanchez, thepatwalls, starterstory, ShaanVP | lawn care business, pressure washing business, junk removal, door hangers, side hustle this weekend | 18–34 |
| $200 DESK | thejustinwelsh, gregisenberg, thedankoe, levelsio, marc_louvion, IndieHackers, starterstory | web design business, start an agency, local SEO, solopreneur, one-person business | 25–44 |
| $1,000 PLANT | Codie_Sanchez, agazdecki, acquiredotcom, flippa, BizBuySell, sweatystartup | buy a business, boring business, franchise under 10k, acquisition entrepreneur, SBA loan | 30–54 |
| $10,000 HEAVY | sweatystartup, Codie_Sanchez, Jobber, ServiceTitan, QuickBooks, Gusto, SBAgov | buy a franchise, franchise fee, second location, add a service line, home service business | 35–60 |
| $20 / $50 | (organic, retargeting, and upsell only) | | |

## 4. Creative that fits the format

Specs and practices ([benly formats](https://benly.ai/learn/x-ads/x-twitter-ads-formats-specs), [veuno specs](https://www.veuno.com/x-formerly-twitter-ad-specs-your-guide-for-2026/)) `(secondary)`:

- Vertical video 9:16, 1080×1920, ~15 s ideal (up to 2:20). Movement in the first second, captions for sound-off, brand early, CTA button after ~1 s.
- Carousel 2–6 cards with individual headlines/URLs: right for "what's inside the pack" (card 1 the name, card 2 the week-1 calendar, card 3 the price sheet, card 4 the door).
- Website card for single-link conversions.
- Running 3+ formats lifted awareness ~20% and purchase intent ~7% in X's own studies `(platform claim)`.
- B2B ($10,000): promote Bryce's best-performing organic post rather than a produced ad; founder-led beats polished on X `(secondary)`.

Copy rules that come from law and policy (see LAW_AND_POLICY_FLAGS.md): prices yes, earnings no; time budgets yes, results-in-a-period no; "yours / distinct" only when the instance is `UNIQUE`; no "chance to win" / "draw" language in ads.

## 5. Measurement: what must exist before the first dollar

X requires the **X Pixel or Conversion API plus at least one event in Events Manager** for a website-conversions campaign ([about conversion tracking](https://business.x.com/en/help/campaign-measurement-and-analytics/conversion-tracking-for-websites/about-conversion-tracking), [create website conversions campaign](https://business.x.com/en/help/campaign-setup/create-website-conversions-campaign)). Default attribution is 1-day view / 30-day click. Under ~$500/month, browser pixel only is fine; server-side Conversion API is not worth it at test budgets `(secondary)` ([weltpixel](https://weltpixel.com/blogs/news/twitter-x-conversion-api-shopify-2026-what-works)).

Our checkout is an owner-pasted Stripe Payment Link, which completes on stripe.com. The purchase event therefore cannot fire on our door unless the Payment Link's after-payment redirect points to a **thank-you page on the pack door that carries the pixel purchase event**. That page does not exist yet. Build demand posted: a `packs/<slug>/thanks.html` (or one shared thank-you door) with a pixel-ID slot the owner fills, the same way he pastes Payment Links. Until then, spend can only be judged by Stripe's own dashboard against ad-spend dates, which is too coarse to optimize.

Events to define in Events Manager: `ViewContent` (pack door), `InitiateCheckout` (Payment Link click), `Purchase` (thank-you page). Value = tier price.

## 6. Budget scenarios for a first test (illustrative)

Assumes CPC $1.00, cold conversion 1%, prices as named, Stripe 2.9% + $0.30.

| test | daily | days | clicks | expected sales | spend | revenue | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| $100 SHOP | $30 | 14 | 420 | ~4 | $420 | ~$400 | break-even at 1%; profitable above ~1.1% or below ~$0.95 CPC |
| $200 DESK | $30 | 14 | 420 | ~4 | $420 | ~$800 | positive |
| $1,000 PLANT | $50 | 21 | 1,050 | 2–5 at 0.2–0.5% | $1,050 | $2,000–5,000 | positive if the door earns trust |
| $10,000 HEAVY (lead gen) | $50 | 30 | 1,500 | 30–60 leads at 2–4% | $1,500 | depends on close rate; 1 close pays for 6 months of testing | run when Bryce is ready to take calls |

Kill criteria: stop a tier's ad set at 300 clicks with zero `InitiateCheckout`, or at 2x the tier price in spend with zero `Purchase`. Move budget to the tier with the lowest cost per `InitiateCheckout`.

## 7. Account prerequisites (owner)

- An X Ads account at ads.x.com on the advertising handle. The fleet inventory lists `@TheCommonsSwarm` as the live X identity (2026-09-01 resource route); whether ads run from it or from a tjlabs handle is Bryce's call.
- **The advertising account must be verified**: Verified Organizations for a business, or X Premium for an individual; posts public; a functional, live, ungated bio URL that accurately represents the promoted product; profile and header images that are not GIFs ([About eligibility for X Ads](https://business.x.com/en/help/ads-policies/campaign-considerations/about-eligibility-for-x-ads), read 2026-09-02). Verification is a paid subscription, so it is an owner/financial step before any campaign can be created. Current prices: **X Premium Business Basic $200/month or $2,000/year; Full Access $1,000/month or $10,000/year; Enterprise custom; Premium Organizations $1,000/month plus $50/month per affiliate** ([help.x.com Premium Business](https://help.x.com/en/using-x/premium-business), [help.x.com Premium Organizations](https://help.x.com/en/using-x/premium-organizations), [TechCrunch 2025-10-07](https://techcrunch.com/2025/10/07/x-splits-verified-organizations-into-premium-business-and-premium-organizations/)). X advertised a limited-time promotion returning 100% of the subscription cost as advertising credits; whether it is still live is checked at signup, not assumed. An individual X Premium subscription on a personal handle also satisfies eligibility at a lower price, which makes "which handle advertises" a real cost decision.
- Payment method on the ads account (owner; financial).
- Review of the ad-policy checklist in LAW_AND_POLICY_FLAGS.md before the first creative is submitted, because X's review is automated and "economic opportunity" wording gets rejected.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

