# OSS sponsor-route evidence map

Operation: `OSS-SPONSOR-ROUTE-EVIDENCE-MAP-20260916`  
Snapshot: `2026-09-17T00:52:00Z`  
Carrier: Commons issue #15145

This carrier answers one revenue question: **where is there a current, documented money road around open-source work that is plausibly adjacent to TJLabs' systems, reliability, security, data-integration, and evidence-engineering proof?**

It is not a generic OSS watchlist, an award ledger, permission to contact a maintainer, permission to submit an application, or permission to start third-party implementation.

## Snapshot

The retained map contains **20 opportunity rows backed by 19 authoritative/program-authoritative source records**. One OTF source supports two distinct current program routes, which is why the counts differ.

Reward truth at this snapshot:

- `ADVERTISED`: 11
- `SUBJECTIVE`: 7
- `UNKNOWN`: 2
- `GUARANTEED`: 0

The validator deliberately rejects `GUARANTEED` in this pre-award research carrier.

## Current map

Priority is a research/fit ordering from 1 (inspect first) to 4 (more conditional). It is **not** an award probability and never overrides a fresh collision/economics check.

| P | Opportunity | Route | Truth | Public economics | Source |
|---:|---|---|---|---|---|
| 1 | SCIBASE.AI open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $6,475 open pool / 11; examples $1,000/$500/$475 | https://algora.io/SCIBASE.AI/home |
| 1 | Dozer Data open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $1,450 open pool / 3; two $600 | https://algora.io/getdozer/home |
| 1 | Unsiloed AI open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $1,915 open pool / 11; $1,000 RAG shown | https://algora.io/unsiloed-ai/home |
| 1 | Tailcall open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $1,000 open pool / 8; $500 task shown | https://algora.io/tailcallhq/home |
| 1 | GitHub Secure Open Source Fund | `SECURITY_GRANT` | `ADVERTISED` | $10,000 per selected project in stated tranches | https://github.com/open-source/github-secure-open-source-fund |
| 1 | NLnet Open Internet Stack | `GRANT` | `SUBJECTIVE` | no individual award asserted here | https://nlnet.nl/news/2026/20260903-call.html |
| 1 | Sovereign Tech Fund | `GRANT` | `SUBJECTIVE` | project-cost threshold is not a promised award | https://www.sovereign.tech/programs/fund |
| 2 | Daytona open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $630 open pool / 16 | https://algora.io/daytonaio/home |
| 2 | tscircuit open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $450 open pool / 10 | https://algora.io/tscircuit/home |
| 2 | ProjectDiscovery/Nuclei open bounties | `OPEN_BOUNTY` | `ADVERTISED` | $200 open pool / 2 at $100 | https://algora.io/projectdiscovery/bounties |
| 2 | OTF Internet Freedom Fund | `GRANT` | `SUBJECTIVE` | selection-based | https://apply.opentech.fund/ |
| 2 | OTF Surge and Sustain | `GRANT` | `SUBJECTIVE` | selection-based; current dated window in retained source | https://apply.opentech.fund/ |
| 2 | OTF FOSS Sustainability Fund | `GRANT` | `SUBJECTIVE` | selection-based | https://www.opentech.fund/funds/ |
| 2 | Microsoft FOSS Fund | `NOMINATION_GRANT` | `ADVERTISED` | up to $12,500 USD for selected projects | https://github.com/microsoft/foss-fund |
| 3 | Codex open source fund | `NONCASH_GRANT` | `ADVERTISED` | up to $25,000 in API credits; **noncash** | https://github.com/openai/codex/blob/main/docs/open-source-fund.md |
| 3 | FOSS United Project Grants | `GRANT` | `SUBJECTIVE` | no individual amount asserted here | https://www.fossunited.org/grants/projects |
| 3 | NumFOCUS Small Development Grants | `GRANT` | `ADVERTISED` | up to $10,000 per proposal; eligible projects only | https://numfocus.org/programs/small-development-grants |
| 3 | LFX Crowdfunding | `FUNDRAISING` | `UNKNOWN` | fundraising rail, not an award | https://crowdfunding.linuxfoundation.org/for-projects |
| 3 | GitHub Sponsors | `SPONSORSHIP` | `UNKNOWN` | sponsor-selected fundraising, not an award | https://github.com/open-source/sponsors |
| 4 | GitHub Fund / M12 | `EQUITY_INVESTMENT` | `SUBJECTIVE` | equity route; fund size is not individual investment | https://github.com/open-source/github-fund |

## Truth vocabulary

`ADVERTISED` means the retained authoritative source publishes an amount, pool, ceiling, or other economic figure, while acceptance/selection/award/payment remains conditional.

`SUBJECTIVE` means the money road is real, but a maintainer/program selector decides whether to accept or fund the work and this carrier does not assert an individual award amount.

`UNKNOWN` means an active money/funding mechanism exists but the individual outcome/value is not deterministic or safely quantified from the retained source.

`GUARANTEED` is reserved for separate retained award/contract evidence creating an actual obligation. This pre-award map refuses it.

## Economic guardrails

Figures that look like dollars are not automatically receivables:

- Algora board totals are currently advertised open bounty value, not money owed to TJLabs.
- Codex OSS Fund is represented as API credits, not cash revenue.
- LFX Crowdfunding and GitHub Sponsors are fundraising/sponsorship rails, not guaranteed awards.
- GitHub Fund is equity financing; its vehicle size is not an individual company payout.
- Sovereign Tech Fund's published project-cost threshold is not treated as an award amount.
- Microsoft FOSS Fund requires a qualifying Microsoft-employee nomination and subsequent selection.

For comparable paid engineering work, the project-level economics/admission layer from `woahwhattheheck/bounty-concierge` PR #216 should be applied before premium implementation spend.

## Public TJLabs proof catalog

Every map row references one public evidence surface instead of relying on generic self-description:

- `agentlily-provider-reliability`: https://github.com/Lilly-Protocol/agentlily-runtime/pull/384 — merged upstream provider-reliability work.
- `paid-work-economics-gate`: https://github.com/woahwhattheheck/bounty-concierge/pull/216 — evidence-bound paid-work admission gate.
- `commons-evidence-systems`: https://github.com/woahwhattheheck/commons — public systems/evidence-engineering corpus.

A public proof establishes only what its source shows. It does not establish eligibility, interest, acceptance, award, or payment for another program.

## Required recensus before implementation

Every retained row binds `RECENSUS_V1`, which expands to:

`RECENSUS_REQUIRED_BEFORE_IMPLEMENTATION_OR_EXTERNAL_ACTION`

Before anyone spends implementation capacity:

1. Re-fetch the authoritative program/bounty page and exact underlying issue/application route.
2. Search Slack and GitHub for exact operation/project/issue plus semantically same work; earlier durable custody wins.
3. Resolve duplicate aliases, already-claimed bounties, closed/repriced work, changed deadlines, and newer program generations.
4. Bind current acceptance/eligibility rules and the exact required artifact.
5. Estimate engineering/model/tool cost and run the paid-work gate where value is comparable.
6. Only a fresh collision/economics-positive result may become a separately claimed implementation lane.
7. Email/DM/form/application/submission or other external communication remains separately authorization- and Muse-gated.

`RESEARCH_ONLY_V1` sets external action, submission, cash/revenue claiming, and vulnerability exploitation to `false`.

## Deliberate exclusions

The research pass did not pad the 20-row target with stale or inaccessible routes. Closed grant windows, historical Algora programs with no current open bounty, older closed NLnet calls, already-closed 2026 grant phases, and programs available only to an existing funded cohort were excluded. A future generation may restore any route whose authoritative source reopens it.

## Files and verification

- `route_map.json` — source ledger, 20 normalized opportunities, action/gate/authority profiles, proof catalog and deterministic summary.
- `validate.py` — strict offline structural/truth validator.
- `test_validate.py` — hostile tests for source, authority, reward and summary drift.
- `downstream_orders.json` — five collision-safe build orders consuming the map without authorizing external action.

Run:

```bash
python research/oss_sponsor_route_map/validate.py
python -m unittest -v research.oss_sponsor_route_map.test_validate
python -O -m unittest -v research.oss_sponsor_route_map.test_validate
python -m py_compile research/oss_sponsor_route_map/validate.py research/oss_sponsor_route_map/test_validate.py
```

The validator is offline by design. Passing it proves consistency of the retained snapshot, not that a web source has remained unchanged after `2026-09-17T00:52:00Z`.
