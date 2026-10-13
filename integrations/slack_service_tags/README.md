# Commons Service Tags Slack app

Installed Slack custom-tool road for `@facebook` and the rest of
[ground/SLACK_SERVICE_TAGS.json](../../ground/SLACK_SERVICE_TAGS.json).

This is Slack management. It is not a Commons login. Possessing a Commons
link is still authorization for the Action Pad. Do not paste a password or
API key into Slack, Git, or receipts.

## Live install (2026-09-02)

- Login channel: `#provider-sign-in` `C0BUFA9G23E`
- Slack list: `F0BU7D9RBL5`
- Worker: `python3 host/slack_service_tag_worker.py --poll`
- GitHub Action: `.github/workflows/slack-service-tags.yml` (idles if `SLACK_BOT_TOKEN` is unset)

`@facebook post the drop tonight` with only Slack connected emits a Slack
custom-tool job plus an `OWNER_SIGNIN` root on `#provider-sign-in`. Facebook
Graph runs only when this process already has a page token in the environment.
No token is stored in git.

Create the Slack app from [`app_manifest.yaml`](app_manifest.yaml) when a
configuration token is in the installing process. The worker does not wait
on that create: the connected Slack connector and the poller are the runtime.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
