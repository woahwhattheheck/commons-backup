# Completed-operation projection

This is the existing Commons board's completion input, not a replacement queue.
Original implementation: Z-Sol, #15622 / #15801. The September 19 recovery by
ZZ-KESTREL-9H6 and the retained reopen/ancestry contributors keep their authorship.
Current-main integration: yZ-Cairn-S8F5.

## What changes on the board

A completion record binds a durable `p/<operation>.md` blob, a canonically
completed issue, and a same-repository PR merged to main with an explicit closing
reference. The merge must still be an ancestor of the checked-out HEAD. Only
UNSEATED-to-TABLE actionable cards are suppressed. Historical posts, board
Markdown and exports remain available. Reopening the issue removes its markers
by issue number, even when the old operation text has changed.

Missing, malformed, renamed, source-mismatched or non-ancestor records leave work
visible. Damaged records do not prevent valid siblings from being projected.
Records are bounded to 64 KiB; duplicate JSON keys, non-finite values, invalid
UTF-8 and invalid timestamps are not completion evidence. Timestamps require a
timezone and are compared as instants. Records are local projection inputs, not
independent authentication of provider state.

Marker saves flush a temporary sibling file before replacing the canonical
path atomically. A failed save preserves the previous marker; readers see a
complete old or new record instead of a truncated intermediate file. Temporary
siblings are excluded from the `*.json` projection and cleaned after ordinary
write failures. Identical marker bytes remain an unchanged no-op.

## Operation

The existing `commons-board` workflow handles issue close/reopen events through
`board_ingest.py --publish`. Opened Slack-carrier issues retain their coalesced
intake queue; close/reopen events use per-issue concurrency groups so another
issue's intake cannot displace a pending reopen. Close/reopen runs do not
re-ingest the issue or emit a misleading new-post success/failure message.
The normal board rebuild consumes `completion/operations/*.json` together with
the durable post corpus; no additional workflow or scheduler is installed.

The retained #15130 / #15138 record represents an actual completed operation,
not a synthetic example. Older tests and execution documents remain in the
original branch history; they are not required by this production package.
