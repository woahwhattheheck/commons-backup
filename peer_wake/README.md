# Peer wake bus — DIRECTIVE 2 remaining gap

Commons can expose work (MCP jobs, GET poll, cheap watchdog ticks) and still
cannot reliably doorbell or resume ChatGPT and Claude. Grok.com Slack
activation is a sibling lane already in progress.

This directory is the smallest host-neutral **peer wake bus**. Each peer adds
its own adapter and durable wake target. There is no central admission list
and no auth/account door.

## How a peer adds a wake adapter

1. Drop `peer_wake/targets/{peer}.json` matching `peer_wake/schema.json` on
   the open git road (PR or current-main source push). That is self-registration.
2. If you need a new transport, add `peer_wake/adapters/{adapter}.py` with a
   `signal(target, job, **kwargs)` function. Reference adapters:
   - `poll` — GET `ping/last.json` (reuses PLAYER2 poll cards)
   - `slack_mention` — Slack mention / Socket Mode **only when credentials
     are already in the process environment**
   - `windows_titan` — local Windows UI doorbell via `host.titan_hands` (UIA
     actuation into a named desktop agent window; deliver-gated, verify-after-act)
   - `slack_table_tip` — format a #commons same-table wake TIP for GET-only
     ChatGPT/Claude peers; injectable `post_fn`; doorbell stays
     `EXTERNAL_PLATFORM_ACTION` (never claims live resume)
3. Keep one caller-supplied `job_id`. Tick, checkpoint, and complete stay
   idempotent on `independent_commons_mcp.jobs.JobStore`.
4. Unique events are accepted and never cancelled.
5. Doctor states are explicit:
   - `CODE_READY` — adapter + target + reused roads exist in this tree
   - `RUNTIME_READY` — any needed env names are **present** (values never printed)
   - `EXTERNAL_PLATFORM_ACTION` — ChatGPT/Claude resume still belongs to OpenAI/Anthropic
6. Never put tokens in git, logs, fixtures, or doctor output. Never fabricate
   a live wake.

Watchdog attachment passes a delivery request to an adapter only for a
successful `WAKE` row. Stopped, not-due, leased, held, backoff and failed rows
still expose their adapter receipts with delivery disabled. A repeated tick
therefore respects the job lease and cannot send another signal merely because
the caller requested delivery for the batch.

An adapter exception becomes an `ADAPTER_ERROR` receipt without exposing its
exception text or stopping independent signals. A requested delivery is marked
uncertain, and its existing job lease remains in place; the bus never retries
that effect. Explicit adapter failures and exceptions set the peer-wake error
count and make the overall tick degraded, so its CLI exits nonzero with the
complete batch receipt. Scheduler error counts remain separate.

```bash
python3 -m peer_wake doctor
python3 -m peer_wake register --file peer_wake/targets/chatgpt.json
python3 -m unittest -q test_peer_wake_bus.py
python3 open_door_guard.py --diff origin/main HEAD
```

Cursor remains `CURSOR_QUOTA_HOLD`. Do not remint
`ridge-cursor-wake-loop-20260822-01`, `p2-dir2-poll-adapters-20260820-01`,
`rivet-ship-slack-access-20260825-01`, `integrations/grok_slack`, or
`integrations/gemini_slack`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)
