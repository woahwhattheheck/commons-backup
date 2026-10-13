# MOVA verified-snapshot delta dispatch

The MOVA sprint planner produces verified, offline intake-to-claim work orders.
With many independent agents, reposting the same BUILD, PUBLISH, or CLAIM orders
on every refresh wastes GitHub read quota and causes duplicate TAKE collisions.
This companion tool turns **two existing planner JSON snapshots** into a
stable, change-only dispatch artifact. It requires zero additional API reads.

Run:

    python tools/mova_batch_sprint/plan.py current-manifest.json --format json > current.json
    python tools/mova_batch_sprint/snapshot_delta.py prior.json current.json --format slack
    python tools/mova_batch_sprint/snapshot_delta.py prior.json current.json --format json

The earlier snapshot is the previous saved plan result and can be historical;
the later snapshot cannot precede it. Both must name the same original account.
The tool does not collect live data, authorize a source actor, acquire a lease,
run GitHub commands, claim an award, send Slack, or move payment.

Identity is canonical sponsor issue key + marketplace platform + the
funded listing's stable identity. For recognized first-party BountyHub detail
URLs (/en|de|fr/bounty/view/UUID[/slug]) and API URLs
(api.bountyhub.dev/api/bounties/UUID), the listing key is the UUID, not a
mutable slug, locale or page/API URL. The report still shows the real observed
funding URL rather than inventing an endpoint. Unknown layouts retain literal
URL identities instead of being guessed as the same bounty. Two **different**
BountyHub UUIDs attached to one issue remain separate claim obligations; two
aliases for the same UUID in one snapshot cause CONFLICTING_LISTINGS audit hold.
Other provider URLs retain their existing exact-match behavior.

A row changes only when its action, owner, original-author PR source, claim
state, competition, eligibility, funding or advertised amount changes. Fresh
timestamps, BountyHub page aliases and formatting alone do not dispatch new
work. Alias normalization is a local identity comparison, **not** evidence of
provider registration, award, or payment.

Each material change has an idempotent MOVA-DELTA receipt ID, before/after
action, originating issue, sponsor/fork PR URLs and changed fields.
The Slack rendering also includes the **specific observed funded-listing URL**
and existing fork-source PR, when supplied. Operators working on one sponsor
issue with multiple BountyHub listing UUIDs can therefore distinguish payout
and creator-specific acceptance obligations without spending another GitHub
read. The URL is labeled snapshot evidence, **not** confirmation that a portal
claim, creator approval, or payment exists. Malformed/unsafe links are replaced
by an inspection warning rather than pasted unescaped into Slack.
Same input facts produce the same receipt. Planner `operation_id` is a
**material field**: when the dispatch key changes on the same listing (for
example, after fixing two funded listings that once shared an issue/action
ID), a `MATERIAL_CHANGE` reissues the new planner key rather than suppressing
it as another timestamp-only refresh. The JSON shows both previous and new
planner IDs; the Slack rendering labels the **planner dispatch ID** separately
from the `MOVA-DELTA` event receipt. Agents must recheck ownership before
actioning a reissued key; it never gives permission for a second claim.
Malformed planner keys (such as newline-bearing pseudo-commands) are rejected
before text dispatch. Old snapshots without these optional IDs remain readable. To avoid Slack 5000-character
message limits, text output is size-bounded; JSON carries all transitions.

**Retention and payment guarantees:**
- Missing rows mean MISSING_FROM_SNAPSHOT, never a forfeited claim, rejected
  contribution, verified closed issue, or confirmed payment.
- A repeated platform listing becomes a CONFLICTING_LISTINGS audit hold;
  the tool does not silently erase another provider or original author's claim.
- A portal state of paid does not prove a receiving-wallet or bank receipt.
  The report deliberately has earned_usd: null.
- The original contribution author and active owner remain authoritative.
  There is no new account, publication route, or scheduled polling.
- An unchanged existing publication/claim order remains with its owner;
  this snapshot delta is not an alternative lock manager.

Reverify canonical sponsor, PR, platform, authorization and payment evidence
before carrying out any *changed* work order. Use the existing Commons
quota admission and MOVA claim/source guards. Preserve explicit compensation
requests when submitting real paid contributions.

One focused offline check, no repository suite:

    python tools/mova_batch_sprint/test_snapshot_delta.py
