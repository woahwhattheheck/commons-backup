# Headless Claude gateway — live acceptance (CLEAT's half of C1)

This is the restart / cancel / live acceptance a peer runs through
`integrations/claude_headless/client.py` against the gateway on
`127.0.0.1:8879`. It spends real Claude usage on this PC (one short turn per
step, `--model sonnet` unless the step says otherwise). Every observation
below is copied from actual stdout; nothing is a paraphrase.

Statuses that end a wait: `completed`, `error`, `cancelled`, `interrupted`.

## Procedure

Run from a directory that is *not* the gateway's own state directory, so the
conversation transcript lands where the caller is. The script that produced
Run 2 is the sequence below, verbatim, with each command's JSON saved to a file.

| Step | Command | Pass when |
| --- | --- | --- |
| A. gateway up | `client.py health` | `ok: true`, `claude_version` present, `active_runs` is a list |
| B. real response | `client.py submit "Reply with exactly the token <TOKEN> followed by one space and the word done. Nothing else." --peer <SEAT> --label acceptance-b --model sonnet --cwd <here> --wait 180` | `status: completed`, `result_text == "<TOKEN> done"`, a `session_id` UUID, `exit_code 0` |
| C. continuity | `client.py followup <run_B> "What exact token did you reply with in your previous turn in this conversation? Reply with that token only." --wait 180` | `status: completed`, same `session_id` as B, `result_text == "<TOKEN>"`, command contains `--resume` |
| D. cancel while running | `client.py followup <run_B> "Write a 2500 word essay about the history of rope. Do not stop early." --label acceptance-d` then, once `status: running`, `client.py cancel <run_D>` | cancel returns `status: cancelled` with `killed_pids`; the run's pid is dead within 10 s; a second cancel returns HTTP 409 |
| E. session survives cancel | `client.py followup <run_B> "What was the very first token you replied with in this conversation? Reply with the token only." --wait 180` | `status: completed`, `result_text == "<TOKEN>"` |
| F. gateway restart | `gateway.py --stop`, `gateway.py --detach`, `client.py recover`, then `client.py resume <session_B> "<same question>" --wait 180` | health answers again; `recover` returns without error; the follow-up completes with `result_text == "<TOKEN>"` and inherits the conversation's cwd |
| G. headless | while D is running: foreground window handle/title; the child `claude.exe` `MainWindowHandle`; its children's handles; the gateway's handle | every process in the run's tree and the gateway report handle `0`; the foreground window is whatever the human had, never a run |
| H. gateway killed mid-run | `client.py resume <session_B> "<long essay prompt>"`, wait for `running`, `gateway.py --stop` (gateway only), confirm the child pid is alive, `gateway.py --detach`, `client.py status <run_H> --wait 240`, then `client.py resume <session_B> "<same question>" --wait 180` | health's `recovery.still_alive` names the run; it ends `completed` with `adopted: true`, `exit_code: null`, exactly one `result` line, and the session still answers `<TOKEN>` |

## Run 2 — 2026-09-05 01:28–01:43Z, the gateway landing on main

Gateway: `integrations/claude_headless/gateway.py` as committed on branch
`cleat/c1-headless-claude-20260904-01` for the PR (file-backed child stdio,
adoption, `allow_reuse_address` off on Windows, env scrub), started with
`--detach` (`pythonw.exe`, `DETACHED_PROCESS | CREATE_NO_WINDOW`) as pid 21932,
restarted to 25252 and 25572 during F and to 7000 during H. CLI
`2.1.234 (Claude Code)`, Max OAuth already on this PC. Caller cwd:
`…\scratchpad\live2`. Token: `CLEAT-LIVE-2`. Session for every step:
`c19483b2-9fb9-4649-a335-f867ea021de7`.

| Step | Observed |
| --- | --- |
| A | `ok true`, `claude_version "2.1.234 (Claude Code)"`, `contract "tenon-c1-as-built-20260904-2043 + gemini-shaped aliases"`, `active_runs []`, `event_cursor 126`, `env_scrub` = 21 names (`CLAUDECODE`, `CLAUDE_AGENT_SDK_VERSION`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_HOST_SESSION_ID`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_EFFORT`, …) |
| B | run `a36fb32324b14fff85ceb6615bed7d51`, `completed`, `result_text "CLEAT-LIVE-2 done"`, pid 19468, exit 0, `num_turns 1`, `duration_ms 10640`, `child_model claude-sonnet-5`, 01:29:02.245Z → 01:29:36.494Z (34.2 s wall including CLI start-up), `transcript_exists true` |
| C | run `47eba44119a34d7b8226f2df0630441d`, `kind followup`, command contains `--resume`, `completed`, `result_text "CLEAT-LIVE-2"`, 01:29:38.093Z → 01:29:55.873Z |
| D | run `8e5d48b57b50493f93dab063249fd320` reached `running` (pid 19704) at 01:30:24Z; cancel at 01:30:35Z → `status cancelled`, `killed_pids [22708, 24352, 22560, 19704]` (4-process tree), taskkill exit 0; second cancel → HTTP 409 `already_terminal`, `status cancelled`; final row `cancelled`, `cancel_requested true`, `pid_alive false`, `exit_code 1`, 8 events, ended 01:30:36.862Z; pid 19704 dead on re-check |
| E | run `74c4225eeee444e5a00909d391fee34d`, `completed`, `result_text "CLEAT-LIVE-2"`, exit 0 |
| F | `--stop` → gateway 21932 terminated (gateway only); `--detach` → ready; `recover` → `{recovered: [], still_running: []}`; `resume` → run `3863e8ba467243bb92a1965edf62bbe0`, `completed`, `result_text "CLEAT-LIVE-2"`, `cwd` = the caller's `live2` directory (inherited from the conversation, not the gateway's cwd), 01:41:09.856Z → 01:41:30.138Z |
| G | probe at 01:30:34.939Z during D: child `claude.exe` pid 19704 `MainWindowHandle 0`; its children `conhost.exe` 24352 handle `0` and `python.exe` 22560 handle `0`; gateway `pythonw` 21932 handle `0`; foreground hwnd `722524` title `Claude` (the pre-existing desktop app the human was using, pid 9692); that desktop app is the only Claude window on the box |
| H | run `236cb9fc0fdd4e8e948485096de9feb6` `running` (pid 25180, started 01:41:31.755Z) at 01:41:55Z; gateway 25572 killed with `taskkill /F` (gateway only); `pid_alive(25180) → True`; `--detach` → pid 7000 at 01:42:12.455Z with `recovery.still_alive ["236cb9fc…"]` and `active_runs ["236cb9fc…"]`; final row `completed`, `adopted true`, pid 25180, `exit_code null`, note `adopted by gateway started 2026-09-05T01:42:12.455024Z; child pid 25180 was still alive`, 11 CLI events, `num_turns 1`, `child_model claude-sonnet-5`, ended 01:43:12.406Z, `result_text` 17,125 characters (the essay); gateway statuses `queued → starting → running → adopted → completed`; exactly 1 `result` line in the journal; then `resume` → run `fbc8e0d495a64db0a001ebf63543a0c7`, `completed`, `result_text "CLEAT-LIVE-2"` |
| session | `GET /v1/sessions/c19483b2…` → 8 runs (b, c, d cancelled, e, an extra h2 from the aborted first pass, f, h, h2), transcript on disk 71,928 bytes, `resumable true` |
| health at end | counts `cancelled 4`, `completed 18` (today's whole journal), `event_cursor 194` |

Two defects surfaced in the first pass of Run 2 and were fixed before this
table: the acceptance script read `run_id` at the top level of a status body
(the contract nests it under `run`; the gateway now also mirrors `run_id` /
`session_id` / `status` at the top level), and `client.py resume` passed
`session_id` both as the path and as a body field, raising `TypeError`
(fixed; `test_client.py` now drives `followup`, `resume` and `submit
--session-id` through the CLI). `child_model` also moved from "first key of
the CLI's `modelUsage`" (which named the haiku helper model) to the model in
the `system/init` event.

Cost of Run 2: seven short sonnet turns plus one cancelled and one completed
long run on the Max subscription. Raw stdout for every run is at
`~/.commons/claude_headless/runs/<run_id>/events.jsonl` on the owner PC; the
step outputs are in the scratchpad `live2/*.json` files.

## Run 1 — 2026-09-05 00:36–00:50Z, first gateway build (pipes, before the file-backed rewrite)

Gateway: the first version of `gateway.py` (`c57d689f`, child stdio piped
into the gateway), started with `--detach`. CLI `2.1.234 (Claude Code)`.
Caller cwd: `…\scratchpad\live`. Token: `CLEAT-LIVE-1`. Session
`7ca9261b-35ca-4c0e-8465-78ae580a7745`.

| Step | Observed |
| --- | --- |
| A | `{"ready": true, "listen": "http://127.0.0.1:8879", "pid": 11172, "cli": {"ok": true, "version": "2.1.234 (Claude Code)"}}` |
| B | run `d995a66ff3d84526869e62de94179e88`, `completed`, `result_text "CLEAT-LIVE-1 done"`, pid 20236, exit 0, 00:37:12.299Z → 00:37:30.075Z (17.8 s wall; CLI `duration_ms 8391`, `num_turns 1`, model `claude-sonnet-5`); transcript exists |
| C | run `475c1d508ca04d30ae4d7b934681b2bd`, same session, `--resume`, `completed`, `result_text "CLEAT-LIVE-1"`, 00:39:48.022Z → 00:39:58.833Z |
| D | run `bdea830181a648f5b4feb6232ae6d36c` `running` at 00:40:04Z; cancel at 00:40:17Z → `taskkill /T /F` exit 0: pids 3520, 19280, 20496, 6700 terminated; final `cancelled`, `pid_alive false`, `exit_code 1`, ended 00:40:18.017Z |
| E | run `135eee592ba2488a97d3dee8d54eed6c`, `completed`, `result_text "CLEAT-LIVE-1"`; session view 4 runs, transcript 34,878 bytes |
| F | `--stop` 11172 → `--detach` 16148; resume → run `d6750530ced04b5d8593f97ab1d4cdd9` `completed`, `"CLEAT-LIVE-1"`; second restart 16148 → 21064; resume → run `e97c326d3414478fa92dcd60a1cccf4d` `completed`, `"CLEAT-LIVE-1"` |
| G | before (00:36:15Z): foreground hwnd `197518` title `ChatGPT` pid 14656. During run `fdeaad834c6244a3a8b14d9e6de53add` at 00:47:51Z: child `claude.exe` pid 18468 handle `0`; children `conhost.exe` 20020 handle `0`, `python.exe` 9208 handle `0`; gateway `pythonw` 11172 handle `0`; foreground still hwnd `197518` `ChatGPT` |
| H | run `7b8100d8da2d498f84b4b11ecaf29327` was `running` (pid 22484) at 00:49:44Z; gateway killed ~00:49:49Z; that gateway used pipes, so the kill (`taskkill /T`) took the child with it in the earlier stop path; the child had in fact already emitted its `result` (short reply because the essay prompt was resumed from the gateway's own cwd), so nothing was left to recover. That gap is exactly what the file-backed rewrite closes; see Run 2 step H |

Independent caller, same window of time: a second Claude Code session (peer
TENON) posted four runs to this same 8879 process without any coordination
with me: `b47b12e1` (created `landed.txt`, `result_text "headless write ok"`,
file read back), `f45a60db`, `a76f45ea` (cancelled), `8896dde9`, `5fb3565b`.
Those prove the mechanism and the CLI from a different harness; they were
executed by the first gateway build, and TENON later traced them to the
Windows `allow_reuse_address` hazard, which the landing gateway turns off.

Cost of Run 1: eight short sonnet turns plus three long runs on the Max
subscription.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
