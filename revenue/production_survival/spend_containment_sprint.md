# Agent Spend Containment Sprint — one recommendation

R&D return for Astra's demand of 2026-09-05 00:17 / 00:25 EDT (Slack `C0BU51F1PL3` thread
`1788572190.262029`, `1788581879.680349` and `1788582309.748069`). Business lane, zero paid
social. Written by CAPSTAN (Claude Fable 5.1, Claude Code desktop, owner PC) on 2026-09-05 from
primary sources fetched that day and from what already exists on commons main. Status:
`CANDIDATE`, pending Astra's source review; nothing here is published to a buyer, priced on a
public page, or sent.

The machine-readable twin is [`spend_containment_sprint.json`](./spend_containment_sprint.json).
This offer is the cost-specific rung of the ladder that already exists here: it sits above the
$2,500 Same-Day Agent Survival Proof and below the $15,000 Production Survival Sprint in
[`offer.json`](./offer.json), and it reuses that offer's contract, canary, schemas and intake
runbook rather than adding a platform.

## The recommendation

**Agent Spend Containment Sprint. $9,500 fixed. Five business days. One provider, one
workflow, one staging harness the buyer runs.** We install, inside the buyer's own agent loop,
the checks that run *before the next provider call*: a per-call cost meter, a per-run and
rolling dollar ledger, a step cap, a wall-clock deadline, a per-tool quota, a no-progress
detector, and an external abort; we wrap every external effect in an idempotency key; a halt
writes a resumable incident record and an alert; and we prove it with a staged runaway that
stops under the agreed ceiling while a normal run still passes. Buyer keeps the code, the
tests and the receipts.

Everything below is the why and the exact boundary.

## Qualifying trigger

One number the buyer already has: a provider bill for one agent workflow that rose at least
3× month over month, or one incident of at least $1,000 inside seven days, shown to us as
the provider's own cost report (OpenAI project costs, Anthropic `cost_report`, or their
gateway's spend view) with amounts only. No number, no sprint; "we are worried about cost"
is the $2,500 proof or the free intake, not this.

Observed instances of the trigger, all public, none contacted:

| where | what was published | source |
| --- | --- | --- |
| Incident report, Nov 2025 | four LangChain agents; Analyzer and Verifier in mutual recursion; eleven days; $47,000; dashboards showed it climbing, nothing stopped the next call | jatinbansal.com, fetched 2026-09-05 |
| Same report | 35-engineer SaaS company, $87,000 April 2026 bill; one developer's autonomous refactoring weekend, $4,200 in three days | same |
| Governance write-up | billing-dispute agent retried 247 tool calls across three services over a weekend, 38 errors, duplicate refund attempts, 50 leads queued behind it; a second pipeline burned $800 on one unresolvable lead | dvarahq.com, fetched 2026-09-05 |
| Hiring post, Upwork | "Senior Python Engineer for LLM Cost Optimization Across 4 Production Features": OpenAI bill $2,140 in February to $13,890 in July while usage rose about 40% | recorded on main in `revenue/muhlnickel_inference/offer.json` (Upwork returns 403 to fetches) |
| Requisition | Drata role names "cost/quality monitoring" for agents in production alongside rollback semantics | `prospect_signals.md` on main, verified 2026-08-26 |

## Exact buyer

The engineering lead who owns one production agent workflow at a company of roughly five to
two hundred engineers, paying OpenAI or Anthropic directly (or through a gateway they run),
with a staging copy of that workflow they can execute themselves. They have a bill with a
number on it and a boss who has seen it. Framework does not matter (LangGraph, CrewAI,
AutoGen, n8n, or a plain SDK loop); what matters is that the loop is theirs to change.

Not the buyer: a consumer chat app with no tools; a team whose workflow spans two providers
they cannot pin; a team that wants a dashboard product; anyone who cannot run staging.

## What is delivered, mapped to the primary source

The seven enforcement predicates come from the $47,000 incident write-up, which states that
budgets "must stop the next action" from inside the request path, not from an asynchronous
alert. The sprint installs them in the buyer's loop, in the buyer's language (Python or
TypeScript), as a small module plus tests, not a service:

| component | what it does in the buyer's harness |
| --- | --- |
| cost meter | provider usage fields → USD per call from a pinned price table; every call writes one append-only usage event with `idempotency_key`, `correlation_id` (run), model, tokens, dollars (shape: `revenue/outcome_commerce/metering-event.schema.json`, `USAGE_RECORDED`) |
| per-run and rolling ledger | dollars and tokens per run, per workflow per day; ceilings agreed in writing (for example $20 per run, $200 per day in staging) |
| predicates before the next call | step cap · wall-clock deadline per run · token ceiling · dollar ceiling (per run, rolling) · per-tool quota with mutating tools counted separately · no-progress detection (identical call repeated, or an A-B-A-B oscillation) · external abort flag read at every iteration |
| clean abort | on any predicate: stop before the call, write an incident record (run id, spend at halt, predicate that fired, last N calls, resumable state pointer), send one alert to the buyer's channel |
| idempotency for external effects | every mutating tool call carries a key derived from run + operation; a repeat returns the recorded result instead of firing again (the pattern already landed in `survival_canary.py`) |
| tests | (1) staged runaway from the catalogue below halts under the ceiling; (2) a normal run of the same workflow completes inside its budget; both receipts hash-stable on re-run |
| handoff | source snapshot at an exact commit, one-command run, dependency versions, the two receipts and their hashes, a short walkthrough, keep/change/stop note |

Runaway shapes we stage from the catalogued public failures (`public_pain_signals_20260830*.json`):
mutual recursion between two agents; structural error retried as transient; healthy-looking
iteration with no progress until the turn cap; timeout cascade eating the budget.

## One-provider, one-harness boundary; access and security

- One provider account (OpenAI **or** Anthropic), one named workflow, one staging harness,
  one language. A second provider or workflow is a second sprint.
- The buyer runs everything. Provider keys never leave the buyer; we never hold, see, or
  proxy them. We deliver a pull request into their repository or a tarball; they execute.
- Evidence we receive: traces and logs with secrets redacted, cost reports as amounts. No
  production data, no PII/PHI, no customer records. Staging only; no production writes.
- Pairing over screen-share is allowed; remote access to their machines is not.
- Excluded, and not traded for a shorter clock: credentials, production migration, hosting,
  SLA, ongoing monitoring, multi-tenant chargeback, any model-file or White Box work.

## Price and payment schedule, justified

**$9,500 fixed**, two milestones on the invoice rail already recorded for this ladder
(`revenue/outcome_commerce/catalog.json`, `CUSTOMER_SPECIFIC_INVOICE`):

| milestone | amount | when |
| --- | --- | --- |
| M1 | $4,750 | on the buyer's written acceptance of the scope (trigger evidence seen, workflow and provider named, ceilings agreed, staging confirmed) |
| M2 | $4,750 | on acceptance PASS below; if MISS by window end, M2 is refunded or the buyer elects in writing one free repair attempt in the next five business days, the same remedy as the sibling contract |

Fulfilment scope: about four engineer-days to install and stage the controls in a harness we
did not write, plus one day for the two proofs and the handoff, roughly 40 hours. At the
senior-specialist band already cited on main for the White Box hour ($250–$350 per hour,
Aristek 2026), that is $10,000–$14,000 of labour; $9,500 sits at the bottom because the
predicates, idempotency wrapper, receipt schemas and acceptance tooling are already landed
here and are reused, not rebuilt.

Buyer economics: the documented incidents cost $4,200 in three days and $47,000 in eleven; the
recorded Upwork buyer's monthly bill grew by about $11,700. For any workflow whose baseline
exceeds roughly $300 a day, one prevented weekend covers the sprint. The price is inside
Astra's $5k–$15k band, below the $15,000 rung (which also implements retry and rollback
beyond cost), and above the $2,500 proof (which proves one failure on our infrastructure,
not theirs).

Fees and tax are the buyer's invoice terms; nothing here claims cash.

## Acceptance test, binary

Written before M1, in the sibling contract's form:

> Given the buyer's staging harness with the sprint's controls installed and a per-run ceiling
> of C dollars and a rolling daily ceiling of D dollars agreed in writing, when the staged
> runaway (named shape) is started, the run halts before cumulative spend reaches C, and its
> incident record names the run id, the spend at halt, the predicate that fired and a
> resumable state; every mutating external effect in that run fired at most once. And when a
> normal run of the same workflow is started, it completes, its receipt attributes cost per
> run and per model, and the receipt is byte-identical on a second run of the same input.

PASS only if all of it holds inside the agreed window. No "mostly".

## Disqualifiers

- No staging harness the buyer can run, or the failure only reproduces on production data.
- The workflow already runs behind a gateway with per-session budgets and iteration caps
  that the buyer has tested (LiteLLM agents expose `max_budget_per_session` and
  `max_iterations`); then the sprint is at most the staged proof, which is the $2,500 offer.
- More than one provider or an unpinnable model router.
- PHI or regulated data in the traces we would receive.
- The buyer wants us to hold keys, host anything, or sign an SLA.
- The buyer wants a dashboard; we install control, we do not build observability.

## Fulfilment owner and backup

Roles are transferable and the holder is written, not assumed (`INTAKE.md` pattern). Proposed,
pending each seat's word in the hub:

| step | proposed holder | backup |
| --- | --- | --- |
| intake, trigger evidence check, written scope (M1 terms) | SEXTANT (owns intake and terms for the sibling proof) | WELD |
| build and staged proofs in the buyer's harness | TENON or SEXTANT (owner-PC runner) | CLEAT |
| invoices M1 / M2 | SURETY (Stripe) or Bryce | Bryce |
| CRM row (`crm.md` stages, `Offer SKU` = `agent-spend-containment-sprint`) | LEDGER | — |
| buyer research and the acquisition page below | CAPSTAN | — |

Silence does not transfer a row.

## Why buyer-native controls are not enough for this workflow (primary sources, 2026-09-05)

| control the buyer already has | what it does | why it does not stop the next call |
| --- | --- | --- |
| OpenAI project / organization spend limits | monthly limit per project or organization; alerts at thresholds; optional "Enforce a hard limit" returning `429 project_spend_limit_exceeded` | monthly and per-project, not per run or per workflow; the page itself says "Enforcement is not instantaneous… can process a small amount of extra usage while the limit state propagates" |
| OpenAI Usage / Costs API | reporting by project, user, key, model | reports; enforces nothing |
| Anthropic Console workspace spend limits | monthly cap per workspace, alerts at thresholds; cannot exceed the organization limit; per-user limits only in the Claude Code workspace | monthly and per workspace; a runaway inside one workflow shares the workspace with everything else |
| Anthropic Usage & Cost Admin API | `usage_report/messages` in 1m/1h/1d buckets by key, workspace, model; `cost_report` daily | reporting only; "typically appears within 5 minutes", polling once a minute; by then the $47,000 loop has made its next hundred calls |
| Claude Code LLM-gateway guidance | a gateway is "one place to… enforce budgets and rate limits" | gateway budgets are per credential or team; the loop inside the workflow is invisible to them |
| LangSmith cost tracking | per-run and per-trace token cost; the only cap documented is on evaluator spend | tracks; does not stop |
| LiteLLM proxy | hard-stop `max_budget` per key, user, team, model, customer, global with `budget_duration`; `tpm`/`rpm`; agents: `max_budget_per_session`, `max_iterations` | the nearest substitute; budgets are per key/session, not per tool or per external effect, no no-progress detection, no idempotency for the buyer's own mutating tools, and it has to be adopted and proven by the buyer; if they have done that, see disqualifiers |
| Portkey budget limits | USD or token budgets per key, weekly/monthly reset, key expiry on breach, alerts; enterprise-only | per key, periodic; no per-run limit documented |

The sprint's value is exactly the gap these leave: enforcement inside the buyer's loop, per
run and per tool, with the buyer's own mutating effects made idempotent, and a staged proof
that it works in their harness. That is installed control, not a dashboard.

## Demand: observed versus hypothesis

Observed: the incidents and hiring posts in the trigger table; three catalogued public pain
signals on cost (`sig-jatinbansal-47k-loop`, `sig-clyro-executing-into-bankruptcy`,
`sig-conectia-fails-as-a-bill`, `sig-dvara-weekend-retry-loop`); vendor products built on the
same gap (LiteLLM budgets, Portkey limits, the "prevention stack" vendor). All of that is
strangers' public text and nobody has expressed interest in buying from us.

Hypothesis, unmeasured: that an engineering lead with a bill number will pay $9,500 for the
controls installed and proven in five days rather than adopt a gateway's key budgets
themselves. The first three intakes decide it. Nothing above is a forecast of sales.

## First high-intent acquisition path (draft, no spend)

One page on Commons, indexable, no pixel, no paid social: working title
"Your monthly cap did not stop the $47,000 loop. Seven checks that run before the next call."
It carries the trigger table above, the seven predicates, the acceptance test verbatim, the
price, and the free intake: the failure sentence plus a screenshot of the provider cost report
with amounts only. Intents it is written to answer, taken from the vocabulary in the sources
and the catalogued threads, not from a keyword tool (volumes unmeasured): "openai spend limit
not enforced", "project_spend_limit_exceeded", "anthropic workspace spend limit per run",
"agent stuck in loop cost", "langgraph budget limit per run", "crewai infinite loop tokens",
"litellm max_budget_per_session", "agent circuit breaker cost".

Measurement: page views → intake mails → written scopes (M1) → M2 PASS. Kill criterion: 30
days or 200 organic visits with zero intake mails, rewrite or drop; no paid traffic to it.

Two direct routes exist and are owner decisions, not part of this draft: bidding the recorded
Upwork listing at the buyer's stated budget, and answering in the catalogued public threads
(AutoGen #7409, the CrewAI freeze issues) where cold pitching is spam-adjacent.

## Reuse, not rebuild

- `acceptance.py` (`record-intent` → `issue-terms` → `record-acceptance` → `invoice-gate`)
  for M1; the same evidence-root discipline.
- `survival_canary.py` idempotency and receipt pattern for the external-effect wrapper.
- `receipt.schema.json` and `proof-v1.schema.json` shapes for the two receipts.
- `revenue/outcome_commerce/metering-event.schema.json` for the per-call usage events.
- `INTAKE.md` for who does what, and `crm.md` for the Airtable stages.
- The invoice rail and milestone structure already recorded in the catalog for the $15,000
  rung. No new checkout, no new page until Astra's source review, no new platform.

## Sources (fetched 2026-09-05 unless noted)

- https://jatinbansal.com/ai-engineering/agent-budgets-and-runaway-prevention/ — $47,000 / 11 days / four LangChain agents (Nov 2025); $87,000 April 2026; $4,200 in three days; seven predicates
- https://dvarahq.com/blog/agentic-ai-governance-production — 247 tool calls, 38 errors, weekend retry loop, duplicate refunds, $800 on one lead; loop-detection thresholds, session kill switch, approvals
- https://conectia.pro/en/blog/loop-engineering-production-guardrails — ~15× tokens for multi-agent runs (attributed to Anthropic's research system), six guardrails, no-progress detector
- https://developers.openai.com/api/docs/guides/spend-limits — monthly project/organization limits, alerts, "Enforce a hard limit", `429 project_spend_limit_exceeded`, "Enforcement is not instantaneous"
- https://platform.claude.com/docs/en/manage-claude/workspaces — workspace monthly spend limits and alerts; per-user limits only in the Claude Code workspace
- https://platform.claude.com/docs/en/manage-claude/usage-cost-api — buckets 1m/1h/1d, grouping, "typically appears within 5 minutes", once-a-minute polling
- https://code.claude.com/docs/en/llm-gateway — gateway as "one place to… enforce budgets and rate limits"
- https://docs.langchain.com/langsmith/cost-tracking — run/trace cost tracking; evaluator spend cap only
- https://docs.litellm.ai/docs/proxy/users — `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit`, `max_budget_per_session`, `max_iterations`
- https://portkey.ai/docs/product/ai-gateway/virtual-keys/budget-limits — cost/token budgets, periodic reset, key expiry, enterprise-only
- https://aristekconsulting.com/it-consulting-hourly-rates/ — senior specialist $250–$350/hour (as already recorded in `land/sku-whitebox-hour-20260826.md`, fetched 2026-08-26)
- On main: `revenue/production_survival/public_pain_signals_20260830.json` and `_b.json`; `prospect_signals.md`; `revenue/muhlnickel_inference/offer.json` (Upwork listing); `revenue/outcome_commerce/catalog.json`; `revenue/arbitrage/kimi-agent-survival-proof-20260830-01.json` (Stripe fee arithmetic)
- Not fetched (HTTP 403 on 2026-09-05): help.openai.com article 6614457, platform.openai.com usage reference, clyro.dev prevention-stack post; their claims are carried only as already recorded on main

## Limits

No buyer was contacted and none has expressed interest. Search volumes for the intents are
unmeasured. The 40-hour scope is an estimate from the component list, not from a delivered
sprint. Provider documentation changes; every row in the controls table carries its fetch
date. The price is a recommendation for Astra and Bryce; it is not on any page.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
