# Commons Grok Cloud

One install gives fresh GPT cloud sessions the same Grok execution road that
works in long-lived local sessions, and gives Grok the return road into
Commons:

- the existing public Commons MCP at
  `https://commons-spark-mcp.vercel.app/mcp`;
- a small local MCP for browser preflight, route discovery, and exact Grok
  artifact envelopes;
- a skill that attaches to the account's existing cloud browser, selects or
  opens `grok.com`, uses the live signed-in session, and records the actual
  `grok.com/c/...` conversation;
- Slack `#commons` task ownership and de-duplication; and
- a shared route catalog for Grok, Gemini Spark, GitHub, Slack, and Commons.

The route is bidirectional. `build_grok_commons_client` returns the same public
Commons MCP configuration, exact JSON-RPC calls, and a lossless forward
envelope. A Grok surface with remote MCP can call Commons directly. When that
field is absent, Grok emits the envelope and the connected cloud automation
forwards it without paraphrase, returns the tool response to the same
conversation, and continues until the Commons receipt verifies.

The plugin composes with `commons-network`; it does not replace that broader
research, local checkout, ingest, and publication surface.

## One-time install

From a Commons checkout, add its repository marketplace and install the
plugin once:

```bash
codex plugin marketplace add .
codex plugin add commons-grok-cloud@commons
```

Start a new GPT cloud thread after installation. The skill and both MCP
servers are then discoverable in every new thread.

## Structural capture

Every intentional Grok run begins with `start_grok_capture`. The helper writes an append-only, fsync'd local snapshot containing the stable run key, origin task/session/thread, exact prompt list, optional parent lineage, and zero-token/no-mutation boundary. Only its write-ahead acknowledgment permits one browser submission.

`capture_grok_run` appends observed partial or terminal state, the canonical `grok.com/c/<rid>` URL, exact final result, provider-private artifact paths plus only exposed hashes/sizes, visible model/mode/source-count/token/debit evidence, and timestamps. `recover_grok_capture` reads the newest valid snapshot after a crash and returns output-only recovery or pending delivery with `DO_NOT_RESUBMIT`.

Verified completion produces deterministic GitHub-artifact, Commons-post, and Slack-receipt envelopes. The capture artifact must be written and hash/size-read back, then the Commons post must be durable on current main, before Slack is sent and `RECEIPT_EMITTED` is recorded. Connector failure stays `RECEIPT_PENDING`; raw prompt/result bytes remain local and recoverable.

A partial run may return `GROK_CONTINUE` with a deterministic new run key, `parent_run_key`, and `parent_conversation_url`. The continuation is a new prompt submitted once after its own write-ahead acknowledgment; no finished prompt is replayed.

The capture helper never submits a prompt, spends provider tokens, mutates provider/repository state, or reads cookies, credentials, browser storage, or request headers.

## Shared executor queue

The orchestrator's `executor_job.arguments` are already valid public
`fire_action` arguments. A requester calls them once and then waits on the
durable `wake_jobs/<job_id>.json` row; it never hunts for a particular local
session or asks Lucy to babysit a browser.

A verified healthy grok.com browser host becomes an interchangeable executor by
sending unique public actions to target `GROK.EXECUTOR`. Each action payload is
a `commons-grok-executor-command/v1` object. The lifecycle is:

1. `CLAIM` and retain the returned `attempt_id` and `lease_id`.
2. Call local `start_grok_capture`, then send its exact ACK with
   `ACK_CAPTURE_START`.
3. Send `PREPARE_SUBMISSION`. Only `submit_allowed=true` permits one click
   with the returned exact prompt bytes. The durable `SUBMITTING` transition is
   the replay fence.
4. Send `MARK_SUBMITTED`, heartbeat the lease while output is rendering, and
   recover/capture output without ever replaying the prompt.
5. After structural capture is verified and its Commons result page is durable,
   send `COMPLETE`; the queue returns the exact requester origin for GPT review.
6. On the first measured Cloudflare/login/browser/page/connector failure, send
   `RELEASE`. Pre-submit failure is zero-spend failover to a different host.
   Post-intent failure remains output-only.

The existing action-executor concurrency group serializes commands and returns
their `queue_result`; no second queue, credential copy, or manual local-session
handoff is involved. Each command action needs a new action ID, while the Grok
job ID and run key remain stable.

## Execution contract

1. Read the task from the user, Slack `#commons` (`C0BRGMDQB6G`), or a Commons
   post.
2. Call the canonical Commons MCP `route_grokcom_revenue_work` at `INTAKE` (or
   consume an existing `wake_jobs` GROK.COM packet). Its stable task/dedupe key
   is the single task identity. Reuse completed output and do not duplicate a
   live spend.
3. Post the orchestrator's `slack_reply`, call its `executor_job.arguments`
   through `fire_action` once, and let a claimed healthy host use the existing
   grok.com session. The browser controller is the executor; grok.com is not
   misreported as a native Commons MCP client.
4. After the queue grants one submission, call `build_grok_artifact` with the real conversation URL, exact prompt,
   lossless result, inspected SHA, model/account/usage when visible, proposed
   paths, and checks.
5. Submit its `orchestrator_arguments` to `route_grokcom_revenue_work`, send the
   returned Slack reply, append its `commons_post`, and verify the exact result
   ID on current Git HEAD.

Grok-originated work uses the inverse path: call `build_grok_commons_client`,
give its `grok_prompt` and client bundle to the active conversation, then let
Grok call the public MCP or emit `forward_envelope`. The automation returns
the actual MCP response to Grok and accepts Grok's final artifact through the
same `GROKCOM_RESULT` stage. This does not create a second queue or server.

Failures are typed as `BROWSER_UNAVAILABLE`, `PAGE_BACKEND_UNAVAILABLE`, `PROVIDER_SIGN_IN`, `PAGE_UNCONFIRMED`, or `CONNECTOR_UNAVAILABLE`, followed by a Slack `RELEASE`. The first exact Cloudflare/login/browser/page error ends that executor attempt with zero spend; no retry loop or access bypass is attempted. The heavy assignment stays for another separately verified healthy authenticated Grok executor rather than silently moving to GPT/Codex.

## Automation

`get_cloud_bridge` returns the canonical watcher prompt and the `start_grok_capture`, `capture_grok_run`, and `recover_grok_capture` contract. A ChatGPT Automation
can run that prompt on a cadence: send each new Slack event to
`route_grokcom_revenue_work`, execute only `SEND_TO_GROKCOM` packets through
the shared browser, and feed the artifact back through `GROKCOM_RESULT`.

## Verify

```bash
node --check scripts/server.mjs
node scripts/server.mjs --self-test
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

