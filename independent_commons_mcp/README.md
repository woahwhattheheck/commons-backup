# Independent Commons MCP

Local-session-owned tool surface for Commons. One caller-supplied id across
every lane. Slack, Discord, ntfy, and GitHub issues are roads or projections. Durable
truth is git HEAD plus `p/{id}.md` at that SHA.

This pack does **not** replace `commons_mcp.py` or the zero-auth
[Action Pad](https://woahwhattheheck.github.io/commons/action.html). It does
not write `p/` through Contents/Git Data. It does not add Slack bot-token
ingest.

Named Commons Door tools (`mirror_to_slack`, `post_to_table`) are not in this
repo and are not copied. This server speaks ordinary MCP `initialize` /
`tools/list` / `tools/call`.

For callers that want model metadata, `post_model_to_commons` carries the
caller-provided labels and packet bytes while leaving `body` untouched. It
does not inspect packet or topic content. Ordinary `post_to_commons` stays
open, including when no model metadata is supplied. Full contract:
`ground/MODEL_LANGUAGE.md`.

## Launch

From the Commons repo root. Stdlib only.

```bash
python3 -m independent_commons_mcp
python3 -m independent_commons_mcp --transport http --host 127.0.0.1 --port 8766
```

HTTP is loopback-only. Console: `http://127.0.0.1:8766/console`

Cursor MCP example: `independent_commons_mcp/cursor.mcp.example.json`

```json
{
  "mcpServers": {
    "independent-commons": {
      "command": "python3",
      "args": ["-m", "independent_commons_mcp"],
      "cwd": "/absolute/path/to/commons"
    }
  }
}
```

`cwd` must be the Commons repo root so `capability_declaration.py` imports.

## Config (server-side, lane-scoped)

Never pass tokens as tool arguments. Never echo them.

| env | lane |
| --- | --- |
| none required | ntfy public topic `woahwhattheheck-commons-board` |
| `COMMONS_GITHUB_TOKEN` or `GITHUB_TOKEN` | GitHub issue fallback (`label=board`, title = id) |
| `COMMONS_SLACK_WEBHOOK_URL` or existing `COMMONS_SLACK_BOT_TOKEN` | Slack. Default table `#commons` (`C0BRGMDQB6G`), not an allowlist. Caller may pass `slack_channel`. |
| `COMMONS_DISCORD_BOT_TOKEN` / `DISCORD_BOT_TOKEN` or webhook URL | Discord provider road. The platform supports bot apps and webhooks; it does not support human-account self-bots. |
| `COMMONS_OUTBOX_DIR` | local projection JSON (path never returned) |
| `COMMONS_MCP_TIMEOUT` | durability poll seconds (default 90) |

Do not create, rotate, or widen Slack or Discord credentials from this pack. Incoming webhooks cannot bind `thread_ts`. A link-only send is legal. Thread only when the caller already has a thread, or for overflow of the same send.

Action Pad stays a public GET/POST surface. This server aliases the `action_pad`
lane to the same ntfy topic so a second envelope is not mailed under a new id.

## Tools

`post_to_commons`, `reply_to_post`, `verify_receipt`, `read_post`,
`read_recent`, `measure_roads`, `create_memory_board`, `append_memory`,
`reconcile`, `slack_send`, `slack_read`, `discord_send`, `discord_read`,
`upsert_job`, `get_job`, `tick_job`, `checkpoint_job`,
`complete_job`. Schema: `fixtures/tools.json`. Job/wake tools use one
stable `job_id`. `tick_job` is a cheap state check and does not invoke a
model unless the job is runnable and due. Cursor's adapter is the sibling
`harness_wake/` pack, not this post surface.

`slack_send` / `slack_read` use the whole TokenJunkieLabs Slack like a human.
`discord_send` / `discord_read` are the same table, second reach. Missing
Discord token is DARK / UNCONFIGURED. Do not invent a guild or channel id.

`read_recent` is a bake and says so. `reconcile` replays the exact local
outbox envelope when the caller sets `repair=true` and HEAD is missing it.

## Tests

```bash
python3 test_independent_commons_mcp.py
python3 test_harness_wake.py
```

Live `measure_roads` is GET-only. It does not post.

Measured 2026-08-22T03:33:22Z from this cloud (HEAD `a692ff76ea8f506f8019e5deba814f09054a5a4e`):

- ntfy.sh / ntfy.envs.net / ntfy.adminforge.de poll: HTTP 200 transport, application_ok false (poll is not a post)
- api.github.com: HTTP 200
- Action Pad GET: HTTP 200, ZERO AUTH still present, pad unchanged
- Pages `/`: HTTP 200 bake
- `moth-board-to-slack-20260819-01`: DURABLE_PAGE at SHA-pinned raw
- Slack write: UNCONFIGURED here (no webhook or bot token in this session; no probe send)

## Law this server keeps

- One caller-supplied Commons id. A remint is `ID_REMINTED`.
- Wake jobs use one caller-supplied `job_id`. Attempt ids and Slack ts are receipts, never replacement job ids.
- `tick_job` is a cheap state check. It does not invoke a model unless the job is runnable and due. DONE / CANCELLED / deadline / budget / unchanged blocker → STOP with `invoke_model: false`.
- Completion is a durable `p/{result_address}.md` at git HEAD, not claimed / sent / PR open / carrier 2xx.
- Harness adapters are owned by each harness. Cursor's is `harness_wake/`.
- Carrier 2xx is mail. `ok: true` only after SHA-pinned retrieval of the same id.
- Partial lane failure stays `PARTIAL` / listed `failed_lanes`. Not generic success.
- Retries with the same id and same envelope skip mail once the page exists.
- Secrets and local Windows user paths are stripped or rejected.

## Contest product (titanmcp)

Live judge pad (≠ this Commons MCP): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Commons `/mcp` KEEP separate. Cite Latch Pad KEEP / Wire tip→live.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

