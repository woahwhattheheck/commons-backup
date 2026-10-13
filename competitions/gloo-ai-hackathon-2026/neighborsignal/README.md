# NeighborSignal

**Gloo AI Hackathon 2026 — Agents track candidate**

NeighborSignal is a local-first care-coordination agent for churches, nonprofits, and community organizations. It turns a minimal structured help request plus an owner-vetted resource catalog into an evidence-backed plan that a human can review.

The differentiator is authority design: the AI is useful without being the decider. A deterministic policy engine owns eligibility, evidence, action classes, and receipts. Gloo AI Studio can explain matches and draft a non-sensitive follow-up question, but its output is advisory and cannot increase authority.

## Problem

Community organizations often receive needs through fragmented forms, email, or conversations. Staff then spend time checking resource availability, requirements, and volunteer capacity. Generic AI can make that faster, but it can also invent eligibility, over-promise aid, or leak sensitive information.

NeighborSignal separates **reasoning assistance** from **organizational authority**:

1. Staff create a minimal, PII-avoiding structured request.
2. The organization maintains a bounded resource catalog with explicit evidence refs, capacity, requirements, and expiry.
3. The deterministic planner computes what the evidence actually supports.
4. An optional Gloo AI Studio advisory explains the plan; it cannot alter the plan or receipt.
5. Humans decide whether to contact anyone, commit resources, spend funds, or promise aid.

## What is built

- strict v1 request/resource schemas and privacy field rejection;
- deterministic current-mode planner using trusted process time;
- explicit historical replay mode that cannot masquerade as current authority;
- action classes: `INFORMATION_ONLY`, `VOLUNTEER_TASK_DRAFT`, `OWNER_REVIEW`, `HOLD`;
- no external-send, spending, or promise-of-aid authority anywhere in the product;
- SHA-256 content-addressed receipts with semantic replay verification;
- Gloo AI Studio adapter using documented OAuth2 client credentials (`api/access`) and the guarded OpenAI-compatible V2 completions endpoint;
- validated, non-authoritative Gloo tool calls limited to explaining a cited match or drafting one internal question;
- dependency-free local simulator and browser demo;
- fail-closed competition readiness compiler;
- hostile tests for stale evidence, missing facts, injection-shaped text, tamper/replay, privacy leaks, resource-generation changes, and model overreach.

## Run

```bash
cd competitions/gloo-ai-hackathon-2026/neighborsignal
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python -m neighborsignal historical fixtures/request.json fixtures/resources.json --at 2026-09-14T00:00:00Z --output /tmp/ns-plan.json
python -m neighborsignal verify /tmp/ns-plan.json
python -m neighborsignal readiness fixtures/readiness.json
```

Run the local browser demo:

```bash
python -c 'from neighborsignal.webapp import serve; serve()'
# open http://127.0.0.1:8765
```

The demo uses synthetic data only and makes no external call.

## Optional Gloo AI Studio integration

NeighborSignal follows Gloo's public API documentation:

- OAuth2 token endpoint: `https://platform.ai.gloo.com/oauth2/token`
- grant: `client_credentials`, scope `api/access`
- guarded completions: `https://platform.ai.gloo.com/ai/v2/guarded/chat/completions`
- credentials: `GLOO_CLIENT_ID` + `GLOO_CLIENT_SECRET` environment variables only

Then:

```bash
export GLOO_CLIENT_ID=...
export GLOO_CLIENT_SECRET=...
python -m neighborsignal plan fixtures/request.json fixtures/resources.json --advisory gloo
```

No live Gloo call has been claimed by the source carrier. API access requires an account and provider-side billing/spend configuration; that remains a separate owner/provider gate.

## Authority / privacy boundary

NeighborSignal is **not** a pastoral-care bot, benefits eligibility engine, medical triage system, legal adviser, financial adviser, crisis service, or automated outreach agent. It rejects direct identifier/secret-shaped fields in the durable v1 schema. It does not infer protected or sensitive traits. Request summaries are treated as opaque text, so prompt-injection-shaped text cannot expand authority.

Every action emitted has `external_execution_authorized=false`. Even an eligible resource remains `ELIGIBLE_FOR_OWNER_REVIEW`, never “approved.”

## Competition truth

First-party Gloo materials say the 30-day build window opened September 8, 2026 and the in-person finale is October 6–8 in Boulder. Public Gloo pages currently describe a $200k cash pool, while the May 28 corporate release describes $250k across Agents, Ministry Resourcing, and Bible tracks. Those are advertised prizes, not earned revenue.

See `SUBMISSION.md` for the exact provider/account/attendance/submission gates that remain open.
