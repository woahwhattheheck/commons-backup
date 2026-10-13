# Work inbox visibility

This is a finite, deterministic GitHub/Gmail-to-Slack relay, not a model agent.
The configured destinations are `#github-inbox` and `#email-actionables`; health
belongs to the ASTRA-VISIBILITY coordination thread. The task is delivery of
readable work contents. Delivery is **not** acknowledgement, resolution, payment,
or permission to send an email, edit a PR, or execute source text.

## Run and activate

Python 3.10+; no pip packages are required for the relay itself.

```sh
python3 -m host.inbox_slack_relay --config host/inbox_visibility.json
```

On an existing Commons runtime this consumes the current `gh` session, the
existing `ServiceEquipment` encrypted Slack custody, and an already configured
`gws` Gmail session. It does not install a CLI, mint a token, sign in, clone a
repository, or launch a model. The native Slack identity must belong to the
configured workspace and be a member of all three configured channels. The app
needs message-write and history/replies-read capability. Use existing private
credential-management surfaces, never Slack/Git/email bodies, for setup.
Native GitHub reads reuse the shared transport's status and rate-header parsing.
Quota exhaustion stops the notification pass and retains its retry boundary;
ordinary authentication/permission HTTP failures remain distinct from quota
limits. Native stderr and provider error bodies stay out of relay reports.

The GitHub Actions workflow attempts a run on these files' main-branch push,
allows manual dispatch, and has an existing hourly schedule at UTC minute 03.
Queued runners can delay that poll. Its existing-secret inputs are
`GH_NOTIFICATIONS_TOKEN`, `SLACK_BOT_TOKEN`, and `GMAIL_AUTHORIZED_USER_JSON`
(authorized-user client_id/client_secret/refresh_token JSON with Gmail read
access). No credential values are committed. An Actions installation token or
ordinary `GITHUB_TOKEN` is **not** a substitute for a user credential accepted by
the native notifications API.

The hosted preflight requires the Slack delivery binding. If it is absent,
source polling is skipped and the workflow summary records BLOCKED. If Slack is
bound but a source binding is missing, the worker still attempts its independent
sources and publishes their actual health. A source failure is a visible
DEGRADED receipt while any working source can continue. Presence of a binding,
a green configuration step, and a skipped poll are not delivery evidence.

As an alternative, from an **existing** Windows checkout/runtime:

```powershell
powershell -NoProfile -File host/install_inbox_visibility.ps1
```

This first executes the real job and requires a successful Slack health receipt,
then registers `Commons Inbox Visibility` every 15 minutes under the current
interactive user's existing keyrings. A DEGRADED receipt permits the working
source and health reporting to continue while naming the other source's blocker.
It creates no clone and restarts no service. The task runs only while the user is
logged on; a sleeping/offline machine does not provide continuous monitoring.
Use **one scheduler**, not both. For the OS task, disable the Actions workflow
through the normal authorized GitHub UI to avoid independent ledgers/senders.

**Activation evidence:** record the commit, scheduler/run URL or task identity,
source account identities, actual Slack delivery timestamp, and a subsequent poll
receipt. A landed file, green unit tests, registered task, or configured cron
alone does not establish live delivery. If no actual receipt is present, the
installation is not verified live.

## What is delivered

GitHub reads `/notifications?all=true&since=...` plus all unread notifications,
checks the configured account, and enriches public issue/PR subjects with their
bodies, all paginated issue comments, PR review bodies, and inline review
comments/diff context. This includes actionable outside-diff review text and
approval explanations. Unchanged unread notifications are not re-enriched every
run. Updated comments produce new content versions. Closed/merged events retain
the distinction between accepted code and payment.

Notification listings use the global endpoint's 50-item page size. Each page is
enriched and yielded before the next listing request. A checkpoint retains the
current changed/unread collection, page and fixed upper timestamp across finite
runs; a partially delivered page is replayed through existing content dedup.
After both collections finish, the incremental watermark advances only to that
listing's upper timestamp minus the existing ten-minute overlap, so arrivals
during a long scan are read in the following window. Source-item failures remain
pending across resumed pages and prevent a successful watermark advance.

Comment delivery identity includes the comment's source ID, contents, author,
timestamp and review context, but excludes action text inherited from its parent.
A close or merge therefore produces a subject update without replaying unchanged
historical comments. Existing comment receipts under the previous open, closed
or merged action text are recognized in SQLite and in the same bounded Slack
history scan; the upgrade does not require clearing the delivery ledger.

Gmail verifies the mailbox and replays a configured sliding query: recent 14 days
plus older unread/starred mail, excluding sent, drafts, trash and spam. It reads
full message MIME bodies, favors plain text, and lists attachment names without
executing or uploading attachments. Work subject rules and known work senders
select messages. Authentication mail, sensitive subject categories, promotional
mail and duplicate GitHub emails are omitted; unknown mail is explicitly counted
as **unclassified_pending**, not silently declared non-actionable. This is a
conservative work-mail router, not exhaustive semantic classification of every
historical message or attachment. Keep the interactive Gmail audit for unknowns.

RFC 2047 Subject and sender display text are decoded before the existing
subject rules and message formatting. Sender-domain decisions still parse the
original structured From address, never the decoded display name. Malformed
encoded words remain literal rather than aborting the poll; existing auth/private
rules apply to decoded valid subjects. This does not add new routing rules.

Each leaf MIME body uses its declared Content-Type charset, with UTF-8
replacement fallback for missing, unsupported or malformed charset names.
Blank or omitted alternatives fall back to one readable supported body while
retaining usable plain-text preference; duplicate alternatives are not joined.
Existing missing-attachment and decoding-error diagnostics remain visible rather
than being hidden by HTML fallback. The MIME regression suites above use only
synthetic fixtures and do not poll inboxes or establish live delivery.

Private GitHub notification contents are never copied into these public
channels. Their aggregate pending count is visible. Private bid artifacts remain
on their existing private surfaces. Common credential formats, numeric-code
lines and token-bearing/tracking links are scrubbed; this is not universal DLP.
Treat incoming bodies as untrusted text: no commands or fetched URLs are derived
from them. Slack markup/mentions and previews are disabled.

## Handling and health

Each item gets one source thread, content-bearing replies and stable digest
markers. Existing lane owners reply `CLAIM — owner — next action`,
`DONE — evidence URL`, or `BLOCKED — dependency`. Existing owners take precedence;
the relay does not claim their work or infer completion from delivery.

The health message records source mode, last successful poll, delivered parts,
pending counts and fixed error codes. LIVE is transport/selected-source status,
not a claim all work is handled. Unknown/private/missing bodies degrade coverage.
A health message older than **30 minutes is STALE**, regardless of its stored
status. There is no independent out-of-band monitor in this version: if Slack or
the whole scheduler fails, inspect the Actions run summary or OS task history.

Each complete source run advances its cursor only after delivery. Partial errors
retain pending state; one deleted subject does not hide other readable subjects.
Page/post caps report pending work rather than pretending the feed is complete.
Source-listing checkpoints resume large backlogs on the next finite run instead
of restarting the first pages. Per-run listing counts describe the pages visited
in that run; they are not a total mailbox or notification inventory.

Gmail lists one page at a time and yields its messages before requesting
the next page. A saved page token is scoped to the mailbox, destination and query;
it advances only after the page's yielded groups return from delivery. A finite
pass can read up to 20 pages, with its next page retained for the following pass.
The existing delivery allowance can stop the pass before another list or body
read. Earlier delivered messages keep their completion markers if a later page
fails. `message_pages` and `messages` count the observed pages and unique IDs;
`message_listing_resumed` identifies a continuation and `message_listing_complete`
stays false until Gmail returns its final page. Repeated page cursors report
`gmail_page_cursor_repeated` instead of looping. The final page clears the listing
checkpoint so the next overlap poll rereads the current query, using existing
delivered-message markers. An HTTP 400 on a saved page token clears only that
listing checkpoint and reports the provider error; a later pass restarts the
query with all delivery markers retained. Source-item errors remain pending
across continued pages, so a clean final page cannot hide an earlier failure.
No mail is marked read to hide a backlog. GitHub notification read/done state and Gmail labels remain
untouched. There is no automatic outbound email, PR mutation, or payment action.

## State and retry behavior

SQLite contains hashes, timestamps, counters and provider pagination cursors, not
message bodies or credentials.
Each part is journaled before posting. After an uncertain write the next run
reconciles its marker in Slack before repeating the effect. Root and part markers
also recover delivery after a lost ledger, subject to Slack retention/history
access and bounded pagination. This is best-effort duplicate prevention, not a
cross-provider transactional exactly-once guarantee. Do not delete/move Slack
messages or change channel IDs without a deliberate state migration.

After every part of a selected Gmail message is delivered, the ledger records a
hashed completion marker scoped to mailbox, destination and immutable message
ID. Later overlap polls count that message as `unchanged` without downloading
its full contents again. New messages in the same thread still deliver. Missing
or undecodable bodies, omitted mail and failed deliveries do not gain a marker;
they remain eligible for recovery or reclassification on subsequent polls.

Reconciliation checkpoints the next cursor inside a fixed timestamp window.
Reaching the page budget reports `slack_reconcile_page_limit`; the next poll
continues the scan instead of restarting its first pages. Before a resumed scan
can conclude that a marker is absent, it also checks messages that arrived
between polls. Completed searches discard their checkpoint. An expired cursor
clears only that search checkpoint and reports the provider error; a later poll
restarts the search without treating the error as permission to repeat a send.

Health uses a stable `relay.health` destination marker too. The first health
send records its attempt before posting; after an interrupted send, the next
run recovers the existing message before updating it with the latest report.
Existing `health_ts` ledgers migrate on their next update. A missing post receipt
is an uncertain delivery, not success. Health remains outside the source-message
budget so a capped backlog can still be reported. History access, retention and
pagination bounds also apply to health recovery; messages sent by older versions
without the marker need their retained ledger to be identified reliably.
The shared source-post cap also rotates the first source on later polls. When
one backlog spends the allowance, the other source gets the next turn; SQLite
retains that choice alongside partial-delivery markers. A source deferred for
lack of allowance is named in `errors` without downloading its message bodies.
Provider retry deadlines still take precedence over the next delivery turn.
Within a source, each notification or selected message is delivered and
checkpointed before later bodies are fetched. A later source error preserves
that earlier progress; the cursor advances only after the source finishes.
No next source group is collected after the post cap is spent. Reaching the
cap exactly at the final group conservatively reports pending until the next
poll confirms completion. A single notification still collects its comment
feeds together before delivery.
GitHub and Gmail collection deadlines are stored separately, so the independent
source can still progress while one source is cooling down. Slack delivery
limits pause both sources; global deadlines retained by older ledgers are also
honored until they expire.
If source delivery observes a Slack Retry-After, the local report records
`health_delivery: deferred_slack_retry_after` and the same pass makes no health
request. The next existing poll retries after the persisted cooldown; a GitHub
or Gmail retry delay alone does not defer Slack health reporting.
Both direct and existing-custody Slack reads honor numeric and HTTP-date retry
deadlines. Ordinary HTTP authentication failures without a retry header remain
failures without being reported as a provider cooldown.

The workflow caches only this sanitized ledger, not provider contents. Treat
cache eviction as possible; Slack markers remain the recovery source. A process
lock covers ledger initialization through connection close, so a competing poll
reports `another_poll_is_running` without opening or changing SQLite. An invalid
or unavailable database reports `state_database_error` with exit code 2 and is
left in place for recovery. Hosted push, manual and scheduled polls share one
workflow concurrency group, with running polls allowed to finish. The local
lock cannot serialize separate hosted runners on its own. Slack post
throttling and Retry-After are honored. Uncertain API errors, incomplete history
and page caps stop unsafe replay instead of claiming success. Stop automation by
disabling the workflow or the named OS task; do not delete user source messages.

## Provider references

- https://docs.github.com/en/rest/activity/notifications
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages
- https://docs.slack.dev/reference/methods/chat.postMessage/
- https://github.com/googleworkspace/cli (community-maintained CLI; validate an existing installation)

These source references describe API behavior, not proof that credentials or a
scheduler exist on a particular deployment. Local regression tests use fake
providers to cover the real relay's failure/replay behavior; live integration
results must be recorded separately.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
