# Offline Slack TAKE collision advisory

This standalone standard-library tool spots work already claimed concurrently against
one existing original-contributor sponsor PR. The incident driving it was three
same-head source TAKES against SDK PR #461 and two overlapping WebdriverIO source
TAKEs within minutes. Manual coordination was possible, but relied on somebody
happening to read both claims before concurrent commits.

## Inputs and use

Save a timestamped Slack snapshot as JSON (a list, or an object with a
\`messages\` list), or newline-delimited JSON. Each message contains a Unix
Slack \`ts\`, \`text\`, and optionally \`user\`/\`channel\`. Retain each full
message and its original timestamp; don't convert timestamps to local clocks.
The snapshot is read offline; the script does not fetch private messages,
call GitHub, post to Slack, claim a bounty, or alter a branch.

\`\`\`bash
cd tools/swarm_take_collisions
python audit.py /path/to/slack-snapshot.json --format text
python audit.py /path/to/slack-snapshot.json --window-minutes 90 --format json
\`\`\`

A message must have a recognizable \`TAKE · OPERATION-ID\` or
\`RELEASE · OPERATION-ID\` and an explicit GitHub PR URL. A matching completed
operation retires only its own TAKE. Source paths and \`HEAD\` references are
optional clues; missing file lists produce \`source-scope-unknown\`, not a
confident file-level collision. Body-only and explicitly metadata-only work
is reported separately from source-edit overlap. Look at \`pairs[]\` in JSON
to understand why each PR has multiple active TAKEs.

Snapshot time is the most recent message timestamp, not local wall-clock time,
so an old exported log produces a deterministic audit. The 90-minute window
keeps historical TAKES out of fresh coordination results.

**Important:** This is an advisory report for peers, *not* an ownership
registrar or a mechanism to stop another worker. Release information is
conservative: if the operation ID was omitted or altered, the tool cannot
infer it from a similar-sounding message. Similarly, a PR in a TAKE is not
proof of payment, eligibility, or GitHub write permission. Verify source
heads and sponsor records before changing paid work.

## Focused local check

\`\`\`bash
python -m unittest -v test_audit.py
\`\`\`

The four cases cover same-PR collisions, exact-operation releases,
metadata/disjoint-scope distinctions, and stale/other-PR exclusions.

## Proposed-TAKE preflight (before paid source edits)

The companion preflight checks for **active** same-PR TAKEs before a new paid
source change. Supply a Slack snapshot already fetched during normal swarm
coordination. It never fetches, posts, claims, locks, or sends a GitHub request.

```bash
python tools/swarm_take_collisions/preflight.py ./live-slack.json \
  --pr https://github.com/webdriverio/webdriverio/pull/15974 \
  --operation-id WDIO15974-REVIEW-FIX-UNIQUE \
  --path packages/wdio-config/src/node/utils.ts \
  --head b513f666 --format json
```

- `COORDINATE_SOURCE`: a live same-PR operation overlaps known files, has
  unknown source scope, or competes for metadata. Read its latest source and
  release receipt before writing; do not independently rebuild.
- `PARALLEL_SCOPE_ADVISORY`: peers have distinct known source versus metadata
  scopes or disjoint paths. Coordinate the shared branch nonetheless.
- `NO_ACTIVE_OVERLAP_OBSERVED`: no overlap **in this snapshot**, not a
  claim, an exclusive lease, eligibility, or GitHub write authorization.
- `REFRESH_FEED`: empty, unparseable, future-skewed or stale snapshot; refetch
  the live feed before treating the lane as unclaimed.

An exact `--operation-id` ignores the proposed worker's own posted TAKE.
Terminal messages only retire their exact matching operation. By default the
active window is 90 minutes from the latest snapshot event, and the snapshot
must be no older than 15 minutes from wall clock. `--as-of-ts` supports
replaying archived feeds. This avoids duplicate provider reads by using the
existing JSON/JSONL export and does not bypass shared provider rate limits.

Focused unit check when needed:
```bash
python -m unittest discover -s tools/swarm_take_collisions -p test_preflight.py
```
