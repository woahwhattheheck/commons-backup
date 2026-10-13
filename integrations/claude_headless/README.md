# Headless Claude control (build demand C1)

Lets any Commons harness on this machine drive the installed, already
authenticated Claude Code CLI with no terminal, no browser window, no focus
change and no mouse movement: start a run, watch it, follow up inside the
exact same conversation, cancel that specific run, and pick the conversation
back up after the gateway itself restarts or dies.

Two composed pieces, one calling convention:

- **`gateway.py` (CLEAT)** — loopback HTTP service on `127.0.0.1:8879` with a
  SQLite journal, per-session FIFO, a concurrency cap sized for the owner
  laptop, and `client.py` / `run.ps1` / `manifest.json` / `ACCEPTANCE.md`.
- **`claude_headless.py` (TENON)** — file-backed runner + shell CLI
  (`start / followup / status / wait / events / cancel / recover / session /
  list / doctor / journal`) with `stub_claude.py` and `RUNNER.md`.

```text
peer harness (Codex, Grok bridge, Gemini gateway, a script, curl)
  -> http://127.0.0.1:8879            integrations/claude_headless/gateway.py
  -> claude -p --output-format stream-json --verbose --session-id <uuid>   (new)
  -> claude -p --output-format stream-json --verbose --resume <uuid>       (follow-up)
  -> runs/<run_id>/{prompt.txt, events.jsonl, stderr.txt}   (the child's stdio, as files)
  <- events journaled per run, one global cursor
  <- ~/.claude/projects/<cwd-key>/<session>.jsonl   (the CLI's own durable transcript)
```

Reused, not reminted:

- Print mode, `--session-id`, `--resume` and `stream-json` are the CLI's own
  session mechanism. The session id is the durable handle; the CLI persists
  the transcript on disk regardless of this process.
- The `/health` + async request/events-cursor shape is the one
  `integrations/gemini_slack/peer_tool_gateway.py` already serves on 8878, so
  G2/M3 builders can talk to Claude, Gemini and Grok the same way.
  `POST /v1/message` and `GET /v1/requests/{id}` are accepted as aliases.
- State lives under `~/.commons/claude_headless/` next to the Grok bridge's
  `~/.commons/grok_slack.sqlite3`.

## Start

```powershell
integrations/claude_headless/run.ps1                             # console-free background process, prints /health
python integrations/claude_headless/gateway.py --detach          # same, from Python
python integrations/claude_headless/gateway.py --serve           # foreground, for watching logs
python integrations/claude_headless/gateway.py --stop            # stops the gateway only; children in flight keep running
```

`--detach` uses `pythonw.exe` when available and creates the process with
`DETACHED_PROCESS | CREATE_NO_WINDOW`, logging to
`~/.commons/claude_headless/gateway.log`. Every CLI child is created with
`CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`; the parent's `CLAUDECODE`,
`CLAUDE_CODE_*`, `CLAUDE_PID`, `CLAUDE_EFFORT` session markers are removed
(a desktop-app window carries a host session id, a messaging socket and a
messaging token that must not reach children), `ANTHROPIC_BASE_URL` is left
alone; names to keep can be listed in `CLAUDE_HEADLESS_KEEP_ENV`. The prompt
goes in over stdin from `prompt.txt` (never argv); stdout and stderr go to
files, so a run keeps going if the gateway dies. No secret is minted or
stored; the CLI uses the Max OAuth already on this PC. `allow_reuse_address`
is off on Windows so a second process cannot bind a port that is already
serving (TENON measured that hazard).

## Use

```powershell
python integrations/claude_headless/client.py health
python integrations/claude_headless/client.py submit "Summarize README.md in three lines" --cwd C:\path\to\repo --peer MYSEAT --wait 300
python integrations/claude_headless/client.py followup <run_id> "Now list the risks" --wait 300
python integrations/claude_headless/client.py events <run_id> --follow
python integrations/claude_headless/client.py cancel <run_id>
python integrations/claude_headless/client.py session <session_id>
python integrations/claude_headless/client.py resume <session_id> "continue where you left off" --wait 300
python integrations/claude_headless/client.py recover
```

`CLAUDE_HEADLESS_BASE` overrides the base URL. Or plain HTTP from any language:

| Route | What it does |
| --- | --- |
| `GET /health` | `claude`, `claude_version`, `root`/`runs_dir`, `env_scrub`, `active_runs`, counts by status, global `event_cursor`, recovery report from the last start |
| `POST /v1/runs` | `{prompt, cwd?, model?, tools?, permission_mode?, label?, peer?, partial?, session_id?, wait_ms?}` plus `max_turns?, effort?, allowed_tools?, disallowed_tools?, add_dirs?, mcp_config?, strict_mcp_config?, append_system_prompt?, agent?, fork_session?, retain_prompt?` → `202 {run_id, session_id, status, run}` (or the finished run when `wait_ms` is set). A supplied `session_id` resumes that conversation |
| `GET /v1/runs/{run_id}?wait_ms=` | `{ok, run}`: status, pid, command, `result_text`, `num_turns`, `cost_usd`, `duration_ms`, `child_model`, full CLI result JSON, stderr tail, `events_file`, transcript path + whether it exists, `pid_alive`, `adopted` |
| `GET /v1/runs/{run_id}/events?after=&limit=&wait_ms=` | that run's stream-json lines (`{seq, event, …}`) plus gateway status markers, cursor based, long-poll capable |
| `POST /v1/runs/{run_id}/followup` | new run with `--resume <same session>`; queued FIFO behind any active run of that session |
| `POST /v1/sessions/{session_id}/followup` (alias `/runs`) | continue a conversation when you hold only the session id; `cwd` defaults to where that conversation lives |
| `POST /v1/runs/{run_id}/cancel` | kills that run's process tree (`taskkill /T /F` on Windows) → `{status:"cancelled", killed_pids, tree}`; `409` if already terminal; the session stays resumable |
| `POST /v1/recover` | reconcile rows this process does not own → `{recovered, still_running, finalized_from_disk, interrupted, requeued}` |
| `GET /v1/sessions/{session_id}` | every run of the conversation in order, `resumable`, transcript path and size |
| `GET /v1/events?after=&wait_ms=&run_id=&session_id=` | global cursor across all runs, same shape as the Gemini gateway |

Statuses: `queued → starting → running → completed | error | cancelled`, plus
`interrupted` for a run whose child is gone and whose `events.jsonl` has no
result line. `peer`/`from` and `label` are optional attribution and are only
recorded.

`permission_mode`, `tools` (= `allowed_tools`) and friends pass straight
through to the CLI flags of the same name. In print mode the CLI cannot ask a
human, so a run that needs an interactive answer records that in its result
JSON instead of hanging; pass the mode you want.

## Runs outlive the gateway

The child's stdio are files under `runs/<run_id>/`. On start (and on
`POST /v1/recover`) the gateway looks at every `starting`/`running` row it
does not own: a child that is still alive is **adopted** (its file is tailed
to completion, `exit_code` stays `null` because this process never held the
handle, and it can still be cancelled); a child that finished on its own is
**finalized from disk** with its real result; a child that is gone with no
result line is `interrupted`. Rows still `queued` are dispatched. Because the
CLI wrote the transcript itself, a follow-up on the same session id continues
the conversation in every one of those cases.

## Concurrency and the memory floor

Runs in different sessions execute concurrently up to `--max-concurrent`
(default 1; adopted children count). Runs in the same session are FIFO, which
is what `--resume` needs. Long-polls (`wait_ms`) are capped at 55 s; loop on
the cursor for longer waits.

The owner PC is a 7.24 GB laptop with a DRAM-less NVMe, and on 2026-09-04 at
22:59 EDT it bugchecked `0x154` under memory pressure with seventeen Claude
windows resident. So the dispatcher reads free physical RAM before every
start (`GlobalMemoryStatusEx` on Windows, `MemAvailable` elsewhere) and, while
it is below `--min-free-mb` (default 1024), leaves queued runs queued: one
`held` event per run, `memory_guard` in `/health` (`free_mb`, `min_free_mb`,
`holding`), a `released` event when the run finally starts. `--min-free-mb 0`
disables the floor; an unreadable value never holds.

## Tests and evidence

- `python test_claude_headless.py` (repo root, picked up by the default
  battery) runs the gateway against a stub `claude` that speaks stream-json:
  start, events, follow-up continuity, cwd inheritance, cancel-while-running,
  cancel-before-start, error/crash reporting, per-session FIFO with
  cross-session concurrency, cursor long-poll, Gemini-shaped alias, health +
  env scrub, `tools`/`partial` flags, `/v1/recover`, restart recovery
  (finalize from disk, interrupted, requeue), a run that outlives the gateway
  and is adopted, cancelling an adopted run, and the pure functions. No model
  usage is spent by the tests.
- `python test_client.py` runs `client.py` against a fake gateway that speaks
  exactly the published contract.
- The live acceptance against the real CLI (actual response, follow-up
  continuity, cancel, restart, headless proof) is recorded in
  `ACCEPTANCE.md` and in `p/cleat-c1-headless-claude-20260904-01.md` with the
  exact observed output.

## Limits

- Loopback only, by design, like the Gemini and Grok gateways. A cloud peer
  needs a relay or tunnel road to reach it; that is a separate slice.
- Each run spends the Max subscription's usage on this PC.
- The CLI inherits the user-level MCP servers configured on this machine
  unless `strict_mcp_config` + `mcp_config` are passed.
- `retain_prompt: false` keeps the prompt text out of the SQLite journal (hash
  and byte count stay); `prompt.txt` and the CLI's own transcript still hold it.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
