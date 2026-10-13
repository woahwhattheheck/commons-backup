# Commons shipping monitor

Publish `host/paid_shipping/{worker.mjs,rules.mjs,schema.sql,runner.mjs,checkpoint.mjs}` to the
**public** `woahwhattheheck/commons` repository and invoke it from the retained
scheduled workflow. The runner uses Node 22 with no package install, artifact,
or cache upload. Confirm an actual hosted run on this account after updating
the source; a pricing rule alone does not establish execution.

The current worker runs in `read_only` mode with `slack_writes: false`.
It reads and classifies work, persists private state, and returns
`outbound_sender_identity_unverified` for outward delivery. It does not post
to Slack or create a fallback notification. Existing pending, sending, and
uncertain outbox rows are marked held; accepted rows are retained. A held
notice is not a delivered notice, and changing notice content does not clear
the route hold. Sender identity and provider-added footer verification remain
the prerequisite recorded by the worker for re-enabling that route.

Set repository Actions secrets `COMMONS_GITHUB_TOKEN` (the existing shared
GitHub credential with private `commons-ship-enforcer` read/write and publisher
access), `SLACK_BOT_TOKEN`, and `TYPESAFE_API_KEY` from the shared secure vault. Never check token
values into either repository or print them in Actions logs. The runner reads
only the three configured Slack channels. Before touching Slack or state, each
run verifies repository metadata says `private: true` and
`visibility: private`. All persisted state, including
intermediate thread content, lives only in private
`woahwhattheheck/commons-ship-enforcer`, indexed by `paid-work/shipping-state.json`.
It writes that index through the required account publisher `file.put` route
using the previous GitHub Contents SHA and a deterministic operation ID.
No Cloudflare monitor/D1 call is made by this runner. Its SQLite database is
in memory for each tick. Up to 200 thread rows stay in one version 2
gzip+base64 JSON envelope with a raw SHA-256 checksum. Above that, thread
rows are stored 200 at a time as gzip+hex shard files under
`paid-work/shipping-state/`, and `shipping-state.json` is a version 4 index.
Thread and rest-file names include the SHA-256 of their exact encoded bytes.
The loader checks those hashes, envelope checksums, and total thread count.
Legacy version 1 plaintext JSON, version 2 gzip envelopes, and version 3
shard indexes remain readable. Decompression and the aggregate sharded state
are bounded at 32 MiB; an oversized or invalid snapshot fails rather than
silently discarding state. Every planned file is checked against the publisher
byte ceiling before any shard is staged.

New checkpoints never overwrite existing shards. Identical content is reused;
a conflicting file at an immutable path stops the update. After every new
shard is accepted, the index advances using its original Contents SHA. A held
or interrupted shard write leaves the previous index and its referenced files
untouched. A stale writer does not refresh the index SHA to replace a newer
winner. Single-file and sharded transitions use the same final index update.
Old and partially staged shards are retained, not deleted during a tick, so
storage can grow until a separate reader-safe retention policy is implemented.
This prevents new torn checkpoints; it cannot reconstruct an already mixed
legacy version 3 snapshot. Publisher refusals still propagate unchanged: this
format change neither repairs nor bypasses the deployed publication classifier.
The publisher request sets `User-Agent: Commons-Shipping-Enforcer/1.0`.

For each new or changed nonbaseline candidate thread, the runner sends the
peer thread text to TypeSafe System One (`jev-latest`) as one typed choice:
`submit_own_patch`, `follow_existing_pr`, `complete_claim_step`,
`repair_route`, or `no_followup`. These choices remain local analysis while
outward delivery is held; JEV cannot authorize publication or clear the hold.
A temporary JEV API error
uses the original static rules for that thread and reports
`jev_status: degraded_static_fallback` plus call, error, and input-token counts
in the aggregate run log. The required key is checked at runner start.

The free Actions path reserves 145 seconds of each run for at most 120 thread
pages. It alternates newly active/changed work with historical baseline pages
at roughly 2:1 while both queues exist, and gives all spare pages to the queue
that remains. The existing D1-sized loop is retained only for non-Actions
compatibility. A separate recent-history cursor catches new messages while a
48-hour history snapshot is still paginating. Slack 429 `Retry-After` is saved
in the private journal; the runner waits only when the remaining run budget
allows and otherwise defers that method to the next tick without advancing its
cursor. These are per-run timing limits for the hosted job, not agent or
publication admission limits. JEV runs only when the peer thread content has
changed; baseline and unchanged scans remain quiet. Aggregate run logs include
thread pages, recent-history message count, deadline, and rate-limit status
without Slack content. `mode`, `slack_writes`, and `delivery_code` identify
the current route state even when `delivered` is zero and `delivery_error`
is null. `delivery_held` counts legacy outbox rows newly held in this tick;
`operator_held` counts the current bounded slice of unqueued operator notices;
`incident_held` counts newly scanned incidents held in this tick. These are
different populations, not a total backlog or cumulative delivery count.

Native nonincident diagnostic ingress changes from the disabled Cloudflare
`/v1/operator-notice` URL to a private per-notice Git file. For a validated
minimal notice object with exactly the keys `notice_id`, `reason_code`,
`tool_name`, and optional `operation_id`, `repository`, `issue_number`, publish
its JSON as `paid-work/shipping-operator-notices/<notice_id>.json` in the
private repository using the existing central publisher `file.put` operation.
`notice_id` must be lowercase 64-hex, `reason_code` lowercase letters and
underscores up to 80, `tool_name` safe identifier up to 100, repository
`owner/name`, issue number positive integer. Do not include prose, commands,
paths, draft content, or secrets. Use a stable operation ID derived from the
notice ID. A repeated same-ID file is an acknowledged receipt after provider
readback; a different payload at that path is a conflict. The runner imports
up to four unseen notices per tick from the private Git tree. Imported
notices remain unqueued while the route is held; repeated ticks do not import
the same notice again or send it to Slack. Import success proves only local
state persistence, not delivery.

The runner does not read Cloudflare D1 incidents. A private operator notice
does not bypass the outward route hold. The authenticated publisher incident
record and Bryce's private incident email path remain authoritative. Never
send an incident description into this diagnostic ledger.

Run tests from the candidate root:

```sh
node --test --test-concurrency=1 host/paid_shipping/*.test.mjs
```

The test concurrency flag avoids independent suites replacing the global
`fetch` fixture simultaneously. The live read probe confirmed that Slack
`conversations.replies` accepts GET with query parameters and rejects POST
JSON for the same thread; the worker uses GET for both history and replies.

This document describes the retained hosted workflow; it does not authorize
creating a new schedule or moving the job onto the owner's PC. Verify an
actual hosted run and private Git state readback before declaring operation
live. A successful local check does not establish either hosted execution or
outward delivery.

## Manual GitHub author operations

[Cloud author publication](CLOUD_AUTHOR_PUBLICATION.md) records the verified
public Actions credential binding, the existing named-operation contract, and
the observed classifier outage. It provides a concrete carrier for prepared
original-PR descriptions and keeps job completion distinct from target delivery.
