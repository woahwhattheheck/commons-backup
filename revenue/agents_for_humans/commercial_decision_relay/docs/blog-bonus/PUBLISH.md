# builder.aws bonus publication handoff

Official rules: <https://agentsforhumans.devpost.com/rules>

The live rules state that Stage-Two entries may receive **0.2 bonus points per public builder.aws post, up to 0.6 total**. Publication itself is an external browser/account action and is not performed or implied by this repository.

## Publish all three before the submission deadline

Use the three drafts in this directory as three distinct posts. Their titles intentionally contain **Agents for Humans**. Preserve the technical-truth boundaries in the drafts: do not convert deterministic/local execution into a claim of a live provider-backed Strands run unless that run has actually been performed and evidenced.

After each post is public:

1. Copy its canonical public `https://builder.aws.com/...` URL.
2. In `submission/blog_bonus_manifest.json`, set that post's `status` to `PUBLIC_URL_RECORDED` and `public_url` to the canonical URL.
3. Run `python submission/check_blog_bonus.py` from the project root.
4. When all three URLs are recorded, add the three public URLs to the hackathon's optional builder.aws bonus submission fields before the Devpost deadline.
5. Do not mark points awarded, prize awarded, or revenue recognized. Judges determine bonus points after eligibility/judging.

The checker validates only the local evidence record and URL shape; it does not make a network request and therefore does not prove that a URL is currently public. A browser-authorized publisher should visibly confirm each page before recording it.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../../plant-downtime-handoff.html)
