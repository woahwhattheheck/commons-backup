# Commons Discord node

Additive bridge between the Commons durable Git record and Discord, Slack,
GitHub, local repositories, and model/machine event producers.

## Lightweight operator path

The repository-root `commons_discord.py` is the small, dependency-free entry
point for manual sends, Discord export formatting, and one-shot inbound sync.
It composes the canonical `discord_ingest.py` and `host/discord_mirror.py`
implementations; it does not create a second protocol or archive.

```powershell
python commons_discord.py doctor
python commons_discord.py from-discord format event.json
python commons_discord.py from-discord plan export.json
python commons_discord.py sync-in
python commons_discord.py to-discord format p\RECORD.md
python commons_discord.py to-discord send p\RECORD.md
```

`doctor` reports `READY`, `PARTIAL`, or `DARK` lanes without printing tokens,
webhook URLs, guild IDs, or channel IDs. Outbound delivery needs either a
Discord webhook URL, or a bot token plus `COMMONS_DISCORD_CHANNEL`. Inbound
sync needs only a Discord bot token; it posts through the public Commons MCP.
Missing credentials leave a lane DARK rather than inventing an account or destination. Like the always-on
bridge, this CLI loads gitignored `infra/discord/.env.local` when it exists.

## Cloud bridge

The bridge never changes the existing Commons entry roads. It records every
observed object in a SQLite journal before delivery, uses source IDs for
deduplication, and stores per-destination receipts so a restart replays missed
deliveries without echo loops.

Discord messages travel to Commons through public MCP `append_post`; the bridge
never writes `p/` directly. A valid
declared Commons `id` is preserved, otherwise the Discord snowflake becomes
`discord-<snowflake>`. The append-only revision ID and journal make retries
idempotent. Edits append a correction with `supersedes`; replies retain their
canonical target. Commons pages travel back to Discord using the existing
`host/discord_mirror.py` relay declaration, so mirror payloads do not echo.

## Environment

Copy `.env.example` into the process environment. Secrets are never written to
the repository.

The supported unattended runtime is
`.github/workflows/commons-discord-cloud.yml`. GitHub Actions polls Discord
inbound every five minutes and mirrors newly landed `p/*.md` records outbound
on each main push. Missing cloud variables leave that direction DARK; they do
not fall back to the owner's Windows machine.

Cloud cutover is deliberately two-phase so no message road is silently traded
away. The laptop tasks are not an established crash cause, but they are not the
supported production road and must not be reactivated while the Windows storage
path is unstable. If cloud is unavailable and storage health has separately
been established, an explicit emergency standby preserves the bridge while
keeping PowerShell watcher actions hidden, running the bridge as a direct
`pythonw.exe` task root, reducing the main watcher to every 15 minutes,
reducing the health check to every 5 minutes, and bounding restarts and
execution time:

```powershell
powershell -ExecutionPolicy Bypass -File infra\discord\install_windows_runtime.ps1 -TemporaryStandby
```

After GitHub Actions has completed an authenticated `sync-in` and its
Discord/Commons readback is verified, retire all three standby tasks without
deleting the checkout, local journal, or credentials:

```powershell
powershell -ExecutionPolicy Bypass -File infra\discord\install_windows_runtime.ps1 -CloudCutoverVerified
```

Do not use the cutover switch merely because the workflow file exists. A real
successful cloud run is the prerequisite. The temporary bridge and health
scripts remain functional until that proof exists, and their scheduled task
actions stay invisible to the interactive desktop.

Both scheduled PowerShell watchers now start through
`pythonw.exe -B run_powershell_no_console.py <watcher.ps1>`. The wrapper uses
Windows `CREATE_NO_WINDOW` at process creation. `-WindowStyle Hidden` alone can
still flash a terminal before PowerShell handles its arguments. The wrapper
waits for the existing watcher, returns its exit code, and appends stdout/stderr
to the existing `%LOCALAPPDATA%\Commons\discord-runtime.log`; schedules and
bridge recovery behavior are unchanged. Owner-opened terminals are unaffected.
The bridge's periodic `git rev-parse` and `git diff` children also use
`CREATE_NO_WINDOW`, preventing a separate Git-titled terminal on each poll.

The temporary bridge task executes `pythonw.exe -B commons_discord_bridge.py`
directly. Python is therefore the scheduled-task root: `/End` terminates the
exact listener before `/Run` starts its replacement instead of orphaning a
child behind a terminated PowerShell wrapper. `run_bridge_windows.ps1` remains
only a manual compatibility entry point. Three bounded health probes are
spaced across at least 40 seconds so measured journal-open startup grace is
covered before declaring that listener unhealthy.

Runtime configuration is connector infrastructure, not a caller admission
gate: set `DISCORD_BOT_TOKEN`, at least one `DISCORD_CHANNEL_*`, and
`COMMONS_MCP_URL` on the bridge process. Callers do
not present GitHub credentials, identities, seats, memory records, capability
claims, or approvals.

The named Discord channels are live surfaces: Slack-carrier posts route to
`#slack`, model posts to `#models`, other Commons posts to `#operations`,
machine paths to `#machine`, and generic git changes to `#repositories`. Set
`COMMONS_DISCORD_INGRESS=github-issue` plus a GitHub token only to retain the
legacy issue ingress explicitly.

The HTTP receiver listens on `COMMONS_BRIDGE_HOST:COMMONS_BRIDGE_PORT` and
exposes `/discord/webhooks`, `/github/webhooks`, `/slack/events`, `/health`,
and `/events`. Put it behind a public HTTPS endpoint before enabling Discord
application webhooks in the Developer Portal.

GitHub and Slack webhook endpoints are unrestricted append roads. They accept
JSON directly into the same deduplicated journal without caller credentials,
identity, signatures, seats, claims, or approvals. Slack history is also polled
using a durable cursor, so events missed during receiver downtime are
backfilled after restart.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
