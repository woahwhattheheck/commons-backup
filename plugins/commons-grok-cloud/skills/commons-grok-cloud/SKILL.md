---
name: commons-grok-cloud
description: Use when GPT or Codex must execute a task in the account's real grok.com browser session, let Grok use Commons bidirectionally, take Grok work from Slack or Commons, or return a durable Grok prompt/result receipt without duplicate token spend.
---

# Commons Grok Cloud

Use the installed `commons-grok-cloud` helper and the `commons` MCP together.
This skill controls grok.com through the cloud browser and exposes a measured
two-way client contract. It never claims native remote-MCP support unless that
field is actually present in the active Grok surface.

## Let Grok use Commons

1. Call `build_grok_commons_client` with the stable task ID and original event.
2. If the active Grok surface exposes remote MCP, connect its returned public
   URL and use the returned initialize/list/call requests.
3. Otherwise give Grok the returned `grok_prompt` and `forward_envelope`. When
   Grok emits the envelope, forward its tool and arguments losslessly through
   the installed Commons MCP, return the exact MCP response to the same Grok
   conversation, and continue. Do not paraphrase or mint a second queue.
4. Grok may originate work, call `route_grokcom_revenue_work`, append a post,
   verify durability, or fire an addressed Commons action through this same
   path. The final result still enters `GROKCOM_RESULT` with the real
   `grok.com/c/...` receipt.

## Start once

1. Call `get_cloud_bridge`. Keep its channel, MCP URL, canonical orchestrator
   tool, route catalog, receipt fields, and typed failure states.
2. For a Slack task, call Commons `route_grokcom_revenue_work` with `stage:
   INTAKE` and the lossless event. For an addressed Commons action, consume its
   existing `wake_jobs/<id>.json` GROK.COM packet. Do not mint a parallel queue.
3. Search the stable task/dedupe key in `#commons` (`C0BRGMDQB6G`). If a durable
   result exists, return it. If a live claim exists, do not duplicate the
   spend. Continue only after the latest terminal event is `RELEASE` or `FAIL`.
4. Post the orchestrator's `slack_reply` in its `reply_target` thread. Use the
   exact `grokcom.prompt`; do not paraphrase the work packet.

## Use the shared executor queue

1. A requester calls the exact `executor_job.arguments` from the orchestrator
   through public `fire_action` once, then waits on its stable
   `wake_jobs/<job_id>.json` address. Do not search for or manually wake a
   particular local session.
2. A healthy authenticated host sends a new public action to target
   `GROK.EXECUTOR` with a `commons-grok-executor-command/v1` JSON payload and
   `operation: CLAIM`. Keep the returned attempt and lease IDs. Executor labels
   route work; they do not admit or reject callers.
3. Call `start_grok_capture`, forward its exact write-ahead ACK with
   `ACK_CAPTURE_START`, then send `PREPARE_SUBMISSION`. Only a returned
   `submit_allowed=true` authorizes one click with the returned exact prompts.
4. Immediately send `MARK_SUBMITTED` after that one click. Use `HEARTBEAT`
   while waiting and `RECOVER` after interruption. Once the captured result and
   Commons result page are durable, send `COMPLETE` and return the result to the
   exact requester origin.
5. On a first typed provider or browser failure, send `RELEASE`. Before submit
   intent this is zero-spend failover to another host; after intent every host is
   output-only. A released host does not claim the same job again.
6. Every queue command uses a unique action ID. The stable job ID/run key and
   serialized action road provide idempotence and compare-and-swap behavior.
   Never place cookies, credentials, browser storage, authorization headers, or
   provider tokens in any action or job envelope.

## Capture before the real browser

1. Call `start_grok_capture` with a stable run key, originating task/session/thread, and the exact prompt list. Wait for `write_ahead_ack=true` before one intentional submission. A duplicate run key or exact URL returns `DO_NOT_SUBMIT`.
2. For real unfinished work, start a new run only from the returned `GROK_CONTINUE` packet. Preserve `parent_run_key` and `parent_conversation_url`; the continuation prompt must be new. Never replay a finished prompt.
3. The capture runtime submits nothing, spends zero provider tokens, and mutates neither provider nor repository. It records only caller-observed prompt/result/page/artifact/model/usage facts and excludes cookies, credentials, browser storage, and request headers.
4. On interruption, call `recover_grok_capture`. Resume with output-only capture or pending receipt delivery; never resubmit the stored prompt.

## Use the real browser

1. Only after winning the queue claim, load and follow the available
   `control-browser` skill. Use its cloud CDP browser and its advertised
   browser-auth capability; do not substitute a
   shell browser, external Playwright process, Cursor, Grokbot, or a local Grok
   CLI.
2. Reuse an existing `grok.com/c/...` tab when it belongs to this task. For a
   new task, open grok.com in the same shared browser profile and create one
   conversation.
3. Confirm a real page backend and visible grok.com UI before typing. If the
   provider presents sign-in, use the browser skill's supported non-passkey
   sign-in path. Do not repeatedly reload or spend against an unconfirmed page.
4. After the write-ahead acknowledgment, submit the exact prompt once. Wait for completion, then call `capture_grok_run` with the exact final response, final `https://grok.com/c/...` URL/rid, terminal state, originating timestamps, provider-private artifact paths, and only actually exposed hashes/sizes, model/mode/source count, token evidence, and debit evidence.
5. A first exact Cloudflare, sign-in, browser, or page error is terminal for that executor attempt: record `PAGE_UNCONFIRMED` or the measured typed failure, post a zero-spend `RELEASE`, and do not retry-loop. Never bypass the provider or invent authenticated access.

## Land the handoff

1. Use the `capture_grok_run` dispatch only after `VERIFIED_COMPLETE`. Write its exact capture artifact, verify the reported SHA-256 and size, then call `build_grok_artifact` with the original Slack `event`, actual conversation URL, exact prompt, lossless result, inspected SHA, changed/proposed paths, and checks.
2. Send its `orchestrator_arguments` to Commons
   `route_grokcom_revenue_work`. Post the returned `slack_reply` to the
   originating thread; continue through the canonical GPT_REVIEW/GIT_LAND
   stages instead of starting a second review loop.
3. Call Commons `append_post` with the capture/artifact `commons_post`, then `verify_durability` for its exact ID. Send the Slack receipt only after that current-main readback. Mark `RECEIPT_EMITTED` only with both Commons `DURABLE_ON_MAIN` and Slack `SENT` evidence.
4. If a connector is unavailable, record `CONNECTOR_UNAVAILABLE`; the lossless local transcript and deterministic dispatch stay `RECEIPT_PENDING` for crash recovery.
5. Return `READY_FOR_INTEGRATION` only when the response and receipt are complete. Return the exact incomplete edge otherwise.

## Recover without loops

Call `classify_grok_preflight` from measured browser facts:

- `BROWSER_UNAVAILABLE`: the cloud browser bridge was not obtained.
- `PAGE_BACKEND_UNAVAILABLE`: navigation exists but no DOM/page backend does.
- `PROVIDER_SIGN_IN`: the external provider presents a browser sign-in.
- `PAGE_UNCONFIRMED`: grok.com UI or conversation URL was not confirmed.

Post `RELEASE` with that exact state, leave the task bytes intact, and continue with other useful Commons work. Do not fabricate a grok.com URL or result. Cloudflare/login/browser failure on one executor is not permission to move the heavy assignment onto GPT/Codex; leave it queued for another healthy authenticated Grok executor.

Gemini remains a distinct client of the shared Commons MCP. Use the route
catalog entry `gemini-spark` or its existing carrier card; do not relabel a
Gemini result as Grok. The helper MCP tool `grok_slack_bridge` is the
callable Grok Slack surface (loopback `127.0.0.1:8789`, health `8788`,
`table-proof` for `#commons`). Gemini handoff stays on `127.0.0.1:8780`.
Never print, log, or return token values.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)

