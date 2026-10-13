# Grok ↔ Slack ↔ Commons connector

Standalone Slack transport for the existing grok.com revenue road. It owns
event claim, ACK, crash recovery, and exactly-once Slack delivery. It does
not mint a second Grok queue, MCP core, capture schema, Slack ingest, or
board-to-Slack mirror.

```text
Slack Socket Mode
  -> integrations/grok_slack/bridge.py
  -> public Commons MCP route_grokcom_revenue_work (INTAKE)
     or current-main integrations/grokcom_revenue/orchestrator.py
     when live tools/list does not advertise that tool
  -> fire_action once with grokcom.executor_job.arguments
  -> wake_jobs/<job_id>.json on SHA-pinned current main
  -> GROKCOM_RESULT / direct Git landing
  -> lossless reply in the originating Slack thread
```

The connector composes:

- `integrations/grokcom_revenue/orchestrator.py`
- `integrations/grok_executor_queue.py`
- `plugins/commons-grok-cloud` capture + Slack receipt envelope
- public Commons MCP `https://commons-spark-mcp.vercel.app/mcp`
- existing GitHub road

It does not rebrand `integrations/gemini_slack/**`. Gemini peers stay Gemini.

Live production MCP may lag current source. Doctor reports
`mcp.production_state` (`LIVE_SOURCE_PARITY` or `STALE_DEPLOYMENT`) and
`mcp.intake_road` (`public_mcp` or `current_main_orchestrator`). That is
not a second MCP core, queue, or endpoint. `fire_action` still uses the
public `/mcp`. GitHub readback prefers Contents; unauthenticated 403 falls
through to `git ls-remote` plus a SHA-pinned raw blob, never `raw/main`.

## Activation

Default: app mention, then subsequent messages in that owned thread. Any
human or peer may invoke it. `#commons` `C0BRGMDQB6G` is the default table,
not an allowlist. Other visible workspace channels use the same transport.

Direct messages are omitted. Current main has no measured private Grok
execution road, so this app does not request `im:history` / `mpim:history`
and does not publish DMs into the public Git-backed Grok queue.

## One delivery owner

`FINAL_DELIVERY_OWNER = grok_slack_bridge`. Status `slack_reply` values from
the orchestrator are posted by this connector when `connector.post_reply` is
true. The final result/receipt uses the commons-grok-cloud `slack_receipt`
envelope when present. The executor automation must not also post a final
Slack receipt for the same event. `host/slack_mirror.py` is not called for a
response this connector delivered.

A `LANDED` line is posted only after:

- requested work is on current main
- changed blobs are read back from that SHA
- `p/{id}.md` exists on that SHA with verified bytes/hash
- the capture includes a real `https://grok.com/c/...` URL

## Secrets

Runtime environment only:

```text
SLACK_BOT_TOKEN
SLACK_APP_TOKEN
```

Never paste tokens, cookies, GitHub credentials, xAI credentials, or
browser storage into Grok chat, Slack, a Commons post, issue, PR, fixture,
or repository file. Doctor reports only present/missing.

Missing credentials return typed `RUNTIME_UNCONFIGURED` with zero Slack or
provider calls. The public Commons road stays open.

## Operations

Create the Slack app from [`app_manifest.yaml`](app_manifest.yaml), install
it, and create an app-level token with `connections:write`. Socket Mode
needs no public inbound server.

```text
python -m pip install -r integrations/grok_slack/requirements.txt
python integrations/grok_slack/bridge.py doctor --json
python integrations/grok_slack/bridge.py serve
```

State DB default: `~/.commons/grok_slack.sqlite3`. Override with
`--state-db`. SQLite stores routing and delivery metadata only: event ids,
timestamps, task/job/run keys, hashes, chunk indexes, Slack `ts` values.
It never stores message bodies, Grok results, tokens, cookies, or private
Slack content.

`serve` runs a restart-recovery pass before consuming new work.

## Always-on host

Run `bridge.py serve` as a long-lived process on a host-neutral VM or
container (systemd, Docker/Compose, Fly, Railway, a small VPS). GitHub
Actions is not an always-on Socket Mode host. Bryce's desktop is not
required to stay alive.

Repository-controlled host pack (no tokens in git):

```text
integrations/grok_slack/env.example
integrations/grok_slack/run.sh
integrations/grok_slack/run-handoff.ps1
integrations/grok_slack/run-handoff.sh
integrations/grok_slack/handoff.py
integrations/grok_slack/Dockerfile
integrations/grok_slack/compose.yml
integrations/grok_slack/commons-grok-slack.service
integrations/grok_slack/commons-grok-slack-handoff.service
```

```text
python integrations/grok_slack/bridge.py health --json
python integrations/grok_slack/bridge.py canary
python integrations/grok_slack/canary.py
```

`health` is cheap liveness (credentials present/missing, state DB, secret
scan, optional loopback probe). `doctor` is full readiness including public
MCP and SHA-pinned GitHub readback. `serve` binds loopback `/health` at
`127.0.0.1:8788` by default (`COMMONS_GROK_SLACK_HEALTH_BIND` or `--health-bind off`).
Socket Mode stays outbound; no public inbound webhook.

Copy `env.example` to a gitignored `.env.local`, systemd `EnvironmentFile`,
or container `env_file`. Process environment wins. Doctor reports
present/missing, never values. `GITHUB_TOKEN` is optional connector
infrastructure for Contents rate limits and is not a Commons admission gate.

Desktop activation is a local browser button, not a command-line paste.
Gemini keeps `127.0.0.1:8780`. Grok handoff binds `127.0.0.1:8789` so the
two bridges coexist and Grok tokens never enter the Gemini process or
`~/.gemini`. Slack app id is `A0BTJMFPTT6`.

```text
# Windows desktop: detached and hidden by default
integrations/grok_slack/run-handoff.ps1

# Explicit diagnostics only: keep the console attached
integrations/grok_slack/run-handoff.ps1 -Foreground

# Cross-platform foreground diagnostics
python integrations/grok_slack/handoff.py serve --open-browser
```

The Windows launcher uses `pythonw.exe` plus a hidden window, and the
handoff starts its bridge child with `CREATE_NO_WINDOW`. Scheduled-task or
watchdog callers must invoke PowerShell with `-WindowStyle Hidden`; routine
health checks must use the HTTP health endpoint rather than relaunching this
script. No automated recovery path should surface a terminal on the desktop.

Open `http://127.0.0.1:8789/`, paste the bot and app tokens once, press
Activate. The page stores a current-user encrypted vault (Windows DPAPI,
otherwise user-bound authenticated ciphertext, mode 0600). Status JSON
reports present/missing and live/not-live only. Tokens are never rendered
back, logged, committed, or written as plaintext. After restart, `serve`
and `handoff.py` reload the vault. Missing vault+env remains honest
`RUNTIME_UNCONFIGURED` / `live: false`.

Windows DPAPI uses `WinDLL` with explicit `argtypes`/`restype` and
`(c_ubyte * n).from_buffer_copy` so ciphertext that contains `NUL` bytes
survives a second process and a restart. `write_vault` verifies the temp
file before replacing the live vault; an unreadable reread never unlinks
the existing `CGSVAULT1W` file. Same-process synthetic roundtrip is not
enough: cross-process and restart reread are the contract.

```text
python integrations/grok_slack/bridge.py table-proof --json
```

`table-proof` is the callable Grok Slack custom tool (`grok_slack_bridge`
on the commons-grok-cloud helper MCP). It runs `auth.test`, a read-only
`conversations.history` of `#commons` `C0BRGMDQB6G`, and a harmless
receipt `chat.postMessage`. Reports never include token values. Gemini
stays on `127.0.0.1:8780`. Cite `grok-slack-dpapi-cross-process-20260828-01`.

`run.sh` and the systemd unit refuse to restart-loop on
`RUNTIME_UNCONFIGURED` (exit 2). Inject tokens via the loopback page or
the host environment, then start. SQLite lives on a durable volume
(`COMMONS_GROK_SLACK_STATE_DB`); `serve` runs `recover_pending` before
consuming new work and on a recovery interval.

## Idempotency

- inbound retry key: Slack `event_id`
- immutable source key: `channel` + native `message_ts`
- task/job/run keys: exactly those returned by `route_grokcom_revenue_work`
- outbound key: `event_id` + phase + chunk index + SHA-256 of exact chunk bytes

The same Slack event produces one queue submission and at most one Grok
spend. Slack edits never mutate an accepted prompt. After `SUBMITTING`,
every recovery path is output-only. Ambiguous Slack timeouts reconcile;
they never blindly repost. Unreconciled sends become `DELIVERY_UNKNOWN`.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
