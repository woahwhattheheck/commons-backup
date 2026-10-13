# Headless Claude runner (C1, durable primitive)

`claude_headless.py` drives the installed, already-authenticated Claude Code CLI from any
shell or Python process on the machine, with no window, no focus change, and no dependency
on the process that started the run. It is the file-backed spawn/record primitive under
build demand C1; the loopback HTTP service over the same capability is `gateway.py` +
`client.py` (CLEAT's lane, `127.0.0.1:8879`).

```text
python integrations/claude_headless/claude_headless.py start "<prompt>" --cwd <dir> --wait 120
  -> claude -p "<prompt>" --output-format stream-json --verbose --session-id <uuid>
python integrations/claude_headless/claude_headless.py followup <run_id|session_id> "<prompt>" --wait 120
  -> claude -p "<prompt>" --output-format stream-json --verbose --resume <uuid>
  -> ~/.claude/commons_headless/runs/<run_id>/{run.json, prompt.txt, events.jsonl, stderr.txt}
  -> ~/.claude/commons_headless/events.jsonl        lifecycle journal, global cursor
```

Reuse, not invention: the mechanism is the CLI's own print mode, session ids, and resume.

## Why the run record is the truth

The child's stdout goes straight to `events.jsonl` as a file, not a pipe, and the child is
created in its own process group with `CREATE_NO_WINDOW` (Windows) or `start_new_session`
(POSIX). Measured on the owner PC on 2026-09-04:

- a controller that spawned a run and immediately called `os._exit(0)` left a child that
  finished on its own (`result subtype=success`, 3,239 ms) with every stream-json line on
  disk;
- a gateway process killed with `taskkill /F` while a run was in flight left the child
  (pid 6604) alive; a fresh process ran `recover` and finalized that run as `completed`
  from the bytes on disk (151 lines, last line `DONE`), and a follow-up by session id
  afterwards answered correctly;
- `--resume` works from a different cwd than the one the session started in.

So a replacement coordinator reads the same `run.json` and `events.jsonl`; `status`
finalizes a run whenever the child has exited (`completed` / `error` when a `result` event
exists, `cancelled` when a cancel was requested, otherwise `interrupted`); `recover` walks
every active record and finalizes the ones whose child is gone; `followup` is just
`claude -p --resume <session_id>`. Nothing is held only in memory.

## Commands

| Command | Does |
| --- | --- |
| `start "<prompt>" [--session-id U] [--cwd D] [--model M] [--tools T] [--permission-mode P] [--label L] [--peer N] [--partial] [--stdin-prompt] [--wait S]` | new conversation; prints the record |
| `followup <run_id\|session_id> "<prompt>" [same options]` | continue the exact same conversation (`--resume`); inherits cwd/model/tools/permission mode/peer from the parent run unless overridden |
| `status <run_id>` | the record, finalized from disk if the child is gone |
| `wait <run_id> [--timeout S]` | block until a terminal status |
| `events <run_id> [--after N] [--limit K] [--wait-ms MS]` | raw stream-json lines `{seq, event}` and `next_cursor` (1-based line index) |
| `cancel <run_id>` | kill that run's process tree; the session stays resumable |
| `recover` | finalize every run whose child is gone; prints the runs it finalized |
| `session <session_id>` | every run of that conversation, `resumable`, transcript paths under `~/.claude/projects/` |
| `list [--session-id U] [--status S] [--limit K]` | run summaries, newest first |
| `journal [--after N] [--limit K]` | lifecycle events with a global cursor |
| `doctor` | CLI argv and version, root, active runs, env scrub |

Every command prints JSON. `--root` (or `CLAUDE_HEADLESS_ROOT`) moves the runs root; the
default is `~/.claude/commons_headless`. `CLAUDE_HEADLESS_BIN` points at a different
executable (the tests point it at `stub_claude.py`).

As a library: `Runner(root).start(prompt, cwd=..., permission_mode=...)`, `.followup(...)`,
`.status(...)`, `.wait(...)`, `.events(...)`, `.cancel(...)`, `.recover()`, `.active()`,
`.session(...)`, `.list_runs(...)`, `.doctor()`; `Runner.journal.after(cursor, wait_ms=...)`.

Options map to CLI flags: `model` → `--model`, `tools` → `--tools` (`""` disables all
tools), `permission_mode` → `--permission-mode` (default `acceptEdits`; pass
`bypassPermissions` when the run must execute commands unattended), `allowed_tools` →
`--allowedTools`, `disallowed_tools` → `--disallowedTools`, `strict_mcp` →
`--strict-mcp-config`, `mcp_config` → `--mcp-config` (repeatable), `partial` →
`--include-partial-messages`, `extra_args` → appended verbatim. Prompts longer than 8,000
bytes (or `--stdin-prompt` / `via_stdin=True`) are fed through stdin from `prompt.txt`
instead of the command line.

**Permissions in print mode, measured 2026-09-05.** `tools` only restricts the tool set;
it grants nothing. Nothing can prompt in print mode, so a tool that would need approval is
denied and the child reports it under `permission_denials` in the `result` event. Three
research runs started with `--tools WebSearch,WebFetch,Read,Write` and no `allowed_tools`
were denied every web call, refused to fabricate, and wrote nothing ($3.77 of the shared lane
for the lesson). For unattended research use `allowed_tools="WebSearch,WebFetch,Write,Read"`
(or `--allowed-tools …` on the CLI). The child also inherits every MCP server from the user's
configuration (Slack, Gmail, Commons, Titan Hands on the owner PC); pass `strict_mcp=True`
(`--strict-mcp`) unless the run should have them.

**Memory floor (added after the 2026-09-04 22:59 EDT `0x154` crash).** `--min-free-mb N`
(`Runner(min_free_mb=N)`, or `CLAUDE_HEADLESS_MIN_FREE_MB`) makes `start` and `followup` refuse
to spawn a child while free physical RAM is under N MB, with the measured number in the error;
no record, journal entry or child is created. `doctor` reports `memory_floor`
(`free_physical_mb`, `min_free_mb`, `holds`), and every record keeps
`headless.free_physical_mb_at_spawn`. Default 0 = off; the gateway (`gateway.py --min-free-mb`)
uses 1024, so use the same number here to keep the two guards in agreement. An unreadable
reader never holds. Each child is roughly 500 MB of commit on this box.

Statuses: `queued` → `running` → one of `completed`, `error`, `cancelled`, `interrupted`.

## The record

`run.json` keeps: `run_id`, `session_id`, `resume`, `status`, `label`, `peer`, `cwd`,
`model`, `tools`, `permission_mode`, `prompt_bytes`, `prompt_sha256`, `prompt_via`, `argv`
(prompt replaced by `<prompt>`), `env_removed`, `pid`, `pid_create_time` (guards against
pid reuse), `controller_pid`, timestamps, `exit_code`, `result_text`, `result_subtype`,
`is_error`, `num_turns`, `cost_usd`, `duration_ms`, `child_model`, `child_version`,
`event_count`, `error`, `cancel_requested_at`, and `headless`:

```json
"headless": {
  "creationflags": 134218240,
  "stdin": "devnull", "stdout": "events.jsonl", "stderr": "stderr.txt",
  "foreground_before": [722524, "Claude"],
  "foreground_after_spawn": [722524, "Claude"],
  "foreground_at_finalize": [722524, "Claude"],
  "foreground_unchanged": true,
  "child_visible_windows": 0,
  "child_pids_t_plus_1s": [6780, 18636]
}
```

`foreground_*` is the Win32 foreground window handle and title sampled before spawn, after
spawn, and at finalize; `child_visible_windows` counts visible top-level windows owned by
the child process tree one second after spawn. Both are measurements taken on the machine
and recorded per run, so "it stayed headless" is a number, not a promise.

## Nested-session guard

The Claude Code CLI exports `CLAUDECODE` and `CLAUDE_CODE_*` to its children, and a child
that inherits them is treated as part of the caller's session. The runner removes
`CLAUDECODE`, `CLAUDE_PID`, `CLAUDE_EFFORT`, `CLAUDE_AGENT_SDK_VERSION`,
`ANTHROPIC_BASE_URL`, and every `CLAUDE_CODE_*` / `CLAUDE_PREVIEW_*` from the child
environment and records the removed names in `env_removed`. Keep specific names with
`CLAUDE_HEADLESS_KEEP_ENV=NAME,NAME`. `ANTHROPIC_API_KEY`, if present, is left alone: auth
stays in whatever custody the machine already has.

## Tests

```powershell
python -B -W error -m unittest -v test_claude_headless_runner
```

Root-level so the Commons battery discovers it. Every test drives `stub_claude.py`, which
emits the same stream-json shape as the CLI (`system/init`, `assistant`, `result`) and
honours `SLOW`, `CRASH`, `FAIL`, and `ECHOENV` in the prompt. Covered: start → completed,
line-exact event cursors, follow-up on the same session (by run id and by session id),
unknown-session resume error, error and interrupted finalization, env scrub, stdin prompt
path, journal cursor across two runner instances, invalid input refusal, cancel of a live
child with the session still resumable, a replacement controller seeing and cancelling a
run it did not start, recover from forged orphan records, and zero visible windows on
Windows.

The live acceptance against the real CLI (actual Claude response, follow-up continuity,
cancel, controller killed mid-run + recover, follow-up after that, headless evidence) is
recorded in `p/tenon-claude-headless-control-20260904-01.md` with the raw stdout kept in
the run records.

## Two roots on one machine

CLEAT's `gateway.py` (merged 2026-09-05, PR #8778) keeps its own SQLite journal and run files under
`~/.commons/claude_headless/`; this runner's root is `~/.claude/commons_headless/`. They drive the same
CLI and the same `~/.claude/projects/` transcripts, so a `session_id` from either can be resumed by
either (`followup <session_id>` here, `client.py resume` there), but a *run* record started through one
is not visible to the other's `status`, `events`, `cancel` or `recover`. Pick one road per run and hand
the `session_id`, not the `run_id`, across roads.

## Limits measured, not gates

- The child's lifetime is its own; killing the controller does not kill runs. `cancel` is
  the only thing that kills a run, and it kills the whole process tree (the CLI spawns MCP
  helper processes; on the owner PC a cancel took a four-process tree).
- `pid_create_time` protects against pid reuse on Windows and Linux `/proc`; other POSIX
  systems fall back to `os.kill(pid, 0)`.
- Permission prompts cannot be answered in print mode. Tools that would need one are denied
  by the CLI (visible in the `result` event's `permission_denials`); choose
  `permission_mode` per run.
- `claude -p --resume` needs the transcript the CLI wrote under `~/.claude/projects/`; the
  runner does not copy or edit those transcripts.
- Any HTTP server over this runner should set `allow_reuse_address = os.name != "nt"`:
  `http.server`'s default lets a second process bind an already-listening port on Windows
  and silently take its connections (measured on the owner PC with two C1 gateways on 8879).

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
