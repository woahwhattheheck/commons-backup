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

Identity is canonical sponsor issue key + marketplace platform + funding URL.
This keeps different funded listings and separate payout obligations intact
even when they refer to the same source implementation. A row changes only
when its action, owner, original-author PR source, claim state, competition,
eligibility, funding or advertised amount changes. Fresh timestamps and
formatting alone do not generate new work.

Each material change has an idempotent MOVA-DELTA receipt ID, before/after
action, originating issue, sponsor/fork PR URLs and changed fields.
Same input facts produce the same receipt. To avoid Slack 5000-character
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
