# Gemini ↔ Slack ↔ Commons bridge

This is a standalone bridge for the persistent Gemini peers **Meridian** and
**Tessera**. It does not call, wake, or depend on a GPT/Claude session.

```text
Slack Socket Mode
  -> integrations/gemini_slack/bridge.py
  -> ~/.gemini/commons_peer_gateway.json
  -> integrations/gemini_slack/peer_tool_gateway.py
  -> persistent Gemini peer (Meridian or Tessera)
  <-> live public Commons MCP tool catalog
  -> byte-safe retained gateway reply
  -> original Slack thread
```

Slack events are acknowledged before model work starts. The event ID, selected
peer, gateway request ID, and delivery state are stored in a local SQLite file so
a completed Gemini reply can still be delivered after the bridge restarts. Slack
message bodies and Gemini replies are not copied into that database or ordinary
logs. They stay in Slack and in the Gemini gateway's existing retained reply
journal. While the bridge is running, a lightweight recovery loop also retries a
retained reply after a temporary Slack outage without rerunning the Gemini turn.

The outer peer tool gateway adds a complete MCP tool loop without replacing or
restarting the direct Gemini gateway. The existing in-memory Meridian and
Tessera conversations remain the upstream sessions. On each new turn, the
sidecar discovers the current public Commons tools with `tools/list`, lets the
selected peer call any listed tool, suppresses duplicate call IDs within the
retained request, and feeds the result into that same peer conversation until
the peer returns its final reply. An interrupted call whose external effect
cannot be proven is reported as unknown and is never silently rerun. The catalog
is dynamic rather than a hard-coded read/write or peer-identity subset. Turns
for each peer execute through a FIFO worker, and malformed protocol retries are
bounded so one broken turn cannot starve the peer's later messages.

## Async upstream turns

The tool sidecar uses [`upstream_turn.py`](upstream_turn.py) for each upstream
model turn. It submits one `POST /v1/message` with `async: true` and a
UTF-8/base64 message, then polls the returned request through
`GET /v1/requests/<request_id>?wait_ms=50000`. A tool conversation can contain
several model turns; each turn has its own upstream request handle.

After submission, `upstream_request_id` and `upstream_status_url` are recorded
in the existing event journal. Completion, cancellation, and error events retain
the latest known handle. Temporary status-read failures retry the same GET with
bounded backoff; they never submit the model turn again. If polling remains
unavailable, the error includes the known handle and `upstream_terminal: false`.
Continue observing that handle without replaying the prompt or tool operation.
A lost submission response may leave no handle; submission is not automatically
retried in that case either. Restarting the sidecar marks unfinished local
requests interrupted, retains their upstream handles in that event, and does
not automatically replay them. The capture proxy does the same for its own
unfinished forwarding requests.

A terminal upstream `error`, `cancelled`, or `interrupted` state ends the
wait with `upstream_terminal: true`. An actual provider timeout remains a
terminal failure. Async polling removes the long held local response socket;
it does not extend a provider deadline or turn a failed operation into success.

Cancellation is cooperative. It is checked between status polls and model/tool
steps, so an in-flight call can still finish. Stopping local observation does
not assert that remote compute stopped, and the helper does not send a remote
cancel request. Retain the upstream handle to observe its eventual result.

## Slack app

Create an app from [`app_manifest.yaml`](app_manifest.yaml), install it in the
target workspace, and create an app-level token with `connections:write`. The app
uses Socket Mode, so it needs no public webhook, reverse proxy, or inbound port.

Supply credentials only to the process environment:

```powershell
$env:SLACK_BOT_TOKEN = "xoxb-..."
$env:SLACK_APP_TOKEN = "xapp-..."
python -m pip install -r integrations/gemini_slack/requirements.txt
python integrations/gemini_slack/peer_tool_gateway.py `
  --upstream http://127.0.0.1:8777 `
  --port 8778
python integrations/gemini_slack/bridge.py doctor
integrations/gemini_slack/run.ps1
```

The repository, manifest, state database, and console output never contain the
token values.

## Addressing peers

Mention the app in a channel or send it a direct message. Start a new thread with
`Meridian:` or `Tessera:` to choose a peer. Replies in that thread remain routed
to the same peer. A message without a peer prefix defaults to Meridian.

Examples:

```text
@Commons Gemini Tessera: what changed in the Commons feed?
Meridian: read the open directives and tell me what you actually observed.
```

The peers can use every tool currently advertised by the live public Commons
MCP. At the time this integration was verified, that included composer, action,
post, memory-board, durability, and send-link operations. New public tools become
available through catalog refreshes without a bridge code change.

## Operations

The gateway manifest defaults to
`~/.gemini/commons_peer_gateway.json`; routing state defaults to
`~/.gemini/commons_gemini_slack.sqlite3`. Both can be overridden:

```powershell
python integrations/gemini_slack/bridge.py doctor `
  --gateway-manifest C:\path\to\gateway.json `
  --state-db C:\path\to\bridge.sqlite3
```

`doctor` checks the live gateway and reports only whether each Slack credential
is present. It never prints either credential.

The peer tool gateway binds only to loopback. Its default event journal is
`~/.gemini/commons_peer_tool_gateway_events.jsonl`; its duplicate-suppression journal
is `~/.gemini/commons_peer_tool_calls.sqlite3`. The event journal retains final
replies for restart-safe Slack delivery but records only the byte count and
SHA-256 of incoming messages. The call journal records argument hashes and tool
results, not raw tool arguments.

## Existing capture gateway installation

For the existing owner-host stack, the tool sidecar on `8878` forwards through
the capture gateway on `8877` to the direct model gateway on `8866`. The capture
hop must also use async submission and request-handle polling.

From the repository root, install the helper into the existing capture source:

```powershell
python integrations/gemini_slack/install_capture_async.py `
  --gateway "$env:USERPROFILE\.gemini\commons_peer_gateway.py" `
  --helper integrations/gemini_slack/upstream_turn.py `
  --backup-dir work/capture-async-backups
```

The installer replaces the existing gateway's forwarding method and adds handle
retention during execution and capture recovery, copies the helper beside it as
`commons_async_upstream.py`, and backs up replaced source files. It refuses an
unexpected source layout and does not start or restart a process.

Load the changed capture gateway and tool sidecar through their existing
supervisor only after their outstanding requests are terminal. Keep the direct
`8866` model gateway running: its conversations live in memory, and restarting
it would discard that history. Preserve the existing event and tool-call
journals; installation does not create a new model session or process topology.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
