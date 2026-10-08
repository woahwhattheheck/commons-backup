# Operation scope overlap view

The command center includes a read-only view of operation claims in saved Slack
responses. It lets a worker reuse the same source snapshot to find operations
that name the same source path **or the same explicit sponsor GitHub issue**,
including workers posting through one shared Slack identity.

Run it from the repository root:

```sh
python -m integrations.command_center.claim_overlap /private/state/slack-thread.json \
  --workspace-url "$SLACK_WORKSPACE_URL" \
  --channel-id "$SLACK_CHANNEL_ID" --text
```

Supply the actual workspace URL and channel ID for that source. The command does
not query Slack, refresh collectors, register claims, dispatch work, or write to
the source. Keep saved responses and generated views in the existing private
source-custody location. Do not commit private message bodies or generated
reports to this public repository.

## Input and source scope

Save the complete detailed connector result as JSON. Its MCP content may contain
a JSON object whose `messages` field is the detailed rendered thread, with
`From`, `Time`, and `Message TS` fields. Structured message records and detailed
rendered text are also supported. Multiple snapshot filenames can be supplied
to one invocation; use `-` to read standard input.

The view preserves message timestamps and original claim references. It uses
explicit operation keys as the grouping identity; a shared display name or Slack
user ID does not make two operations the same worker. A permalink is constructed
only when the workspace and channel are available from the input or supplied by
the caller.

Coverage always describes the supplied snapshots. A terminal thread page says
nothing about unobserved channels, other threads, earlier omitted pages, or work
that has not been announced there. Empty results never establish that the fleet
has no remaining work. Unsupported or unreadable input produces a nonzero exit
with a diagnostic.

## Reading the result

The parser recognizes explicit claim declarations and retains the source paths
and any explicit function scope attached to them. Current Slack forms such as
`TAKE · OPERATION-ID` and `TAKE BUILD/SHIP · OPERATION-ID` are parsed as claims.
`DONE / RELEASE · OPERATION-ID` and `COLLISION / RELEASE · OPERATION-ID`
are terminal observations only for that exact operation. A label preceding a
claim must be bounded and followed by a visible bullet; ordinary `TAKE a look`
prose is not a declaration. A potential overlap requires either explicit owned
file paths **or** the same exact sponsor issue identity in different TAKE
declarations (canonical GitHub `owner/repo/issues/123` URL or `owner/repo#123`
shorthand). Matching is case-insensitive for repository names; bare `#123`
could refer to a PR and is deliberately not matched. Issue identities are
extracted from the opening claim paragraph, not later competition references.
When neither identity is present, missing scope remains unresolved.
Mentions of another operation, retained ownership, and unresolved prose are
not permission decisions.

Explicit completion and scope updates are reconciled only with the operation
they name. A terminal statement can put a spaced dash between its operation key
and completion word, as in `OPERATION-KEY — COMPLETE / RELEASED`; its original
source remains attached to the observed terminal state. A shortened operation
core can resolve to one earlier dated claim
when that match is unique, with the alias retained in the evidence. Ambiguous
references remain visible for reconciliation. Operations without a reconciled
terminal statement are `unknown_active`; the view does not infer worker
liveness. The output includes unresolved candidates so a reader can open the
original message instead of mistaking a parser omission for free scope.

A shared path or identical explicitly named sponsor issue produces a **potential
overlap**. The JSON result retains `issue_targets` for each operation and
`issue_matches` for paired claims, with original statement permalinks. In text
mode both the sponsor issue URL and claim links appear even when no file paths
match. Different operations may still own legitimate disjoint follow-up work
on the same issue; this is an advisory, not an ownership veto.

A shared path also produces a **potential overlap**. This is a prompt to read the
existing claims and compose the work. It does not establish a semantic conflict,
revoke custody, select a winner, or prevent execution. Explicitly disjoint
functions can be distinguished when the source supplies them; otherwise the
view keeps the uncertainty. Explicitly different repository contexts are kept
separate. Unknown repositories and unqualified filenames retain their scope
uncertainty instead of silently becoming a fully qualified source identity.

Use `--path` or `--operation` to narrow the result. The default output is JSON;
`--text` provides a compact operator view. Its coverage heading shows the supplied
message count, duplicate count, each snapshot's pagination state, and any active
filters. A zero-match lookup remains scoped to those supplied messages; it does
not hide a partial page or make an observed source-end marker a full-history claim.
It lists every selected operation's
observed state, source scope and statement references, including a single claim
or completed operation with no matched pair. Filtered results retain any
overlapping counterpart so both source statements remain available. Overlaps do
not cause a failed exit: a successful read and projection exits zero.

Existing task ownership continues through `state/claims`,
`host/coordination_state.py`, and the command-center work-item API. This tool is
an additional projection of the existing source, not a replacement work queue.
