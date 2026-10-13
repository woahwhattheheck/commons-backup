# Lantern — community trivia events

Runnable scheduled-community-event product slice for Slack build demand `bm-hive-20260908-038`.
The Python service, browser workspace and SQLite database form one application. There are no
runtime package dependencies, data purchases, payments or cash prizes.

## Run

Use Python 3.10 or newer in an existing cloud environment:

```sh
cd revenue/hive_community_events
python -B app.py --db /path/to/persistent/events.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765` in the same environment. `--host` selects the listen address when
an existing trusted-community host supplies the network route. This source delivery does not
create a hosted deployment or incur infrastructure costs. Keep the database on persistent
storage across server restarts; do not commit participant data to the repository.

## Host a round

1. Expand **Host a new event**, enter room/times/title/questions, and create the event.
2. Lantern returns a random **host recovery key** once. The browser stores it separately from
   participant reconnect references. Back it up before clearing browser storage.
3. Share the event URL. The host key is never put in that URL, event listing, event state,
   leaderboard, results export, or server logs.
4. Participants join with nicknames and submit one final answer per question.
5. Finishing early requires the host key. On another browser, open **Host controls**, paste the
   recovery key, and Lantern verifies it before restoring the finish control.

New events store only a SHA-256 digest of the host capability and compare candidate digests with
`hmac.compare_digest`. The plaintext key cannot be recovered from the server database. Events
created by older Lantern versions are migrated without data loss; because no historical key
exists for those rows, their legacy shared-finish behavior remains until a replacement event is
created.

Times in the host form use the browser's local timezone; the API stores Unix seconds. The server
clock determines whether an event is scheduled, open or finished. End is exclusive: at the end
timestamp, new answers stop. An identical retry of an already recorded answer remains successful
after the event finishes. Finishing is final and idempotent.

## Scoring and persistence

One first answer per participant and question is committed in a SQLite transaction. Concurrent
identical retries return the same saved choice without adding points. A retry with a different
choice returns HTTP 409 and does not replace the original answer. Correct choices receive the
question's configured integer points; all other answers receive zero. There are no speed bonuses.

Questions and correct choices are withheld until the scheduled start and finish, respectively.
Scores are revealed only after finish. Equal totals share rank; the next rank uses competition
ordering (1, 1, 3). Ties have a stable display order using join time and participant reference.
Participants with no answers appear with zero points.

Participant reconnect references are record locators, not passwords or verified identities. Use
nicknames: display names and final scores are visible to the room. Host capabilities protect host
mutations, but Lantern still does not provide account identity, anti-cheat guarantees, or a public
multi-tenant isolation boundary.

## API

All mutation bodies are JSON objects. A question has `prompt`, `choices`, zero-based `correct`,
and optional `points` (default 100).

| Method | Route | Input / result |
| --- | --- | --- |
| GET | `/health` | Service liveness |
| GET | `/api/events` | Event/room list, schedule, participant count, host-protected flag |
| POST | `/api/events` | `title`, `room`, `opens`, `ends`, `questions`; returns `id` + one-time `host_key` |
| GET | `/api/events/{id}` | Phase, visible questions and final leaderboard; never returns host key/hash |
| GET | `/api/events/{id}?member={reference}` | Same snapshot plus that participant's saved answers |
| POST | `/api/events/{id}/join` | `name` for new participant, or `member_id` to resume |
| POST | `/api/events/{id}/answers` | `member_id`, `question`, `choice`; retry-safe first answer |
| POST | `/api/events/{id}/host/verify` | `host_key`; validates host recovery without mutating the event |
| POST | `/api/events/{id}/finish` | `host_key`; finishes protected events and reveals scores |
| GET | `/api/events/{id}/results.json` | Final public-safe results document after finish |
| GET | `/api/events/{id}/results.csv` | Final public-safe CSV after finish |

Creating an event or joining without an existing participant reference is a new record on each
request. Answer submission, resuming and finish are idempotent. On a lost create response, the
server cannot recover the plaintext host key; use the browser copy if it was received, otherwise
create a replacement event before sharing it.

## Optional product surfaces

This directory also contains the demand-038 calendar feed/export, results export, creator-ready
knight packs, and host-authored chess challenge presentation. Those surfaces reuse the same event
database and core scoring/reconnect semantics rather than inventing parallel event stores.

## Validation

Focused host-control/core tests:

```sh
python -B -m unittest -v test_app.py
python -O -B -m unittest -v test_app.py
```

The suite uses real SQLite databases, concurrent transactions and a real loopback HTTP server.
It covers scheduling, retries/conflicts, restart persistence, migration from the pre-host-key
schema, capability secrecy/verification, unauthorized finish denial, ranking, malformed input,
and the create/join/answer/finish workflow. Browser JavaScript is dependency-free and should also
pass `node --check`.

This source change does not claim a hosted deployment, sale, paid subscription, customer adoption,
or public multi-tenant production readiness.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ —
**titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board:
[titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
