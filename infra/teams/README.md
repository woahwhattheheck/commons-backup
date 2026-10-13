# Commons Microsoft Teams transport

This is the first working Microsoft Teams road for Commons. It is additive:
Teams carries Commons events and conversation activities while the existing
Git/issue append roads remain the durable record.

## Outbound: Commons to Teams

Create a Teams Workflow from **When a Teams webhook request is received**, add
**Post card in a chat or channel**, choose the target, and copy the generated
HTTP POST URL into the bridge process as `TEAMS_WORKFLOW_URL`. The Workflow can
use Microsoft's **Anyone** trigger mode; Commons sends no identity header in
that mode and places no caller gate in front of the open table.

Render a card without sending it:

```bash
python infra/teams/commons_teams_bridge.py card \
  --title "Commons shipped" \
  --text "Tests and readback passed" \
  --url "https://github.com/woahwhattheheck/commons/commit/SHA" \
  --event-id "commons-event-id"
```

Send the same card:

```bash
TEAMS_WORKFLOW_URL='https://...' \
python infra/teams/commons_teams_bridge.py send \
  --title "Commons shipped" \
  --text "Tests and readback passed" \
  --url "https://github.com/woahwhattheheck/commons/commit/SHA" \
  --event-id "commons-event-id"
```

The URL is capability-bearing configuration. Keep it out of Git and process
logs. The sender uses the Microsoft Adaptive Card webhook envelope, preserves
the Commons event marker and link, shortens only the free-form body when the
payload reaches 28 KB, and retries HTTP 429/5xx responses with bounded backoff.

## Inbound: Teams to Commons

A Teams **Outgoing Webhook** sends an HTTPS POST when it is `@mentioned` in a
public channel. Its callback has a short synchronous response window. An HTTPS
adapter can use:

- `verify_outgoing_hmac(raw_body, authorization, signing_key_base64)` for the
  Microsoft-generated HMAC-SHA256 wire signature;
- `normalize_outgoing_activity(payload)` to expose stable event fields while
  retaining the complete original activity; and
- `outgoing_response(text)` for the immediate Teams response.

After the immediate response, enqueue the normalized activity onto the same
canonical Commons issue/append road used by the Discord bridge. Do not write a
parallel archive and do not discard caller-defined text or metadata. The HMAC
check belongs only to Microsoft's outgoing-webhook transport contract; it is
not a Commons identity, seat, verb, path, or content restriction.

Outgoing Webhooks are team-level and public-channel only. Personal and private
conversation intake needs a Teams bot or Microsoft Graph adapter as a later,
separate carrier; this first slice does not pretend those surfaces are live.

## Verification

```bash
python infra/teams/test_commons_teams_bridge.py
python -m py_compile infra/teams/commons_teams_bridge.py
```

Microsoft references:

- [Create incoming webhooks with Workflows](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook)
- [Create outgoing webhooks](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-outgoing-webhook)
- [Teams connector limits and throttling](https://learn.microsoft.com/en-us/connectors/teams/)

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
