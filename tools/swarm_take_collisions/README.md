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
