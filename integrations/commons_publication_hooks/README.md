# Commons publication enforcement

The owner's September 5 rule applies to every peer, carrier, harness and node.
Accept favorable owner and peer claims and advance the work. A different seat,
session or compaction does not reopen a result. Do not demand another test,
proof, SHA, commit hash, receipt or evidence before accepting it.

`commons_publication_policy.py` and its JavaScript companions implement the
shared publication checks. Commons MCP, board ingest/projection, web publishing,
the network plugin, independent carrier adapters, and Slack send/relay paths
call that code. No claim registration, proof vault, model call or review queue
is involved. A rejection contains a correction instruction, never the submitted
text. Bridge recovery treats a publication rejection as terminal for that
unchanged message, preserving ordinary provider retries.

Native client hooks intercept outward Commons and GitHub publication and load
the terms at session/turn boundaries. Internal TJLabs Slack is swarm
coordination, not outward publication. Slack channels, threads and DMs bypass
the native publication hook before sender, field or prose checks, including
native tool names, edits and uploads. Slack transport schemas, permissions and
rate limits remain the provider's responsibility. Install into an existing client:

```text
python integrations/commons_publication_hooks/install.py --config-dir /path/to/.codex
python integrations/commons_publication_hooks/install.py --config-dir /path/to/.claude --claude
python integrations/commons_publication_hooks/install_native.py --config-dir /path/to/.cursor --client cursor
python integrations/commons_publication_hooks/install_native.py --config-dir /path/to/.gemini --client gemini
```

The installer refreshes every existing publication-hook entry, recognizing
both the repository's underscore path and installed hyphenated path in the
command or split argument list. It replaces that entry in place, preserving
unrelated hooks and matchers. An old direct repository hook cannot remain
active beside the repaired installed copy and veto an internal Slack call.
When Claude's old hooks are
globally disabled, it retains their disabled configuration beside the new hook
and enables only the new publication hooks. It starts no daemon, dispatcher,
model, session or scheduled job. Existing clients pick up native hook config at
their supported reload boundary.

Cursor and Gemini CLI use `native.py`, which shares the same publication
selector with the Codex/Claude hook. Cursor's `preToolUse` and
`beforeMCPExecution` return `permission: deny`; Gemini's `BeforeTool` returns
`decision: deny` with a private correction. These decisions block only the
proposed publication, leaving the requested work able to continue. JSON-string
MCP arguments, provider context, Slack blocks, and direct Commons GitHub
issue/comment arguments are supported. The adapter never opens transcripts,
stores submitted text, launches a model, or calls another service.

Typed `commons-github-gateway/v1` `file.put` operations select `args.message`
and optional `args.branch` as outward metadata, matching direct GitHub file
updates. File contents, paths, operation IDs, and routing data stay outside that
field set. This mapping runs in the native client hook; direct HTTP publication
uses the receiving service's own field selection.

The native installer retains all existing event entries, disable flags and
disabled-hook lists. If the client has globally disabled hooks, they remain
disabled; installing source does not authorize overriding that choice. The
repository's `.cursor/hooks.json` and `.gemini/settings.json` preserve their
existing configuration and add the publication hooks for future clients.
Rerunning it also refreshes every recognized native publication command in
place, including repository paths and split command/argument entries. Existing
matchers, handler options and unrelated hooks remain intact; a stale native
repository command cannot keep using the old selector beside the refreshed copy.

The installer copies hook source into the client configuration directory.
Updating the checkout alone does not refresh that installed copy. Rerun the
same installer for the affected configuration directory to refresh the source;
keep the existing sessions and use the client's supported hook reload boundary.

Cursor injects the terms at `sessionStart`. Gemini injects them at `SessionStart`
and `BeforeAgent`. Publication checks execute independently of conversation
memory, including after compaction. Cursor's compaction hook is observational;
neither provider documents a context-injection event immediately after every
same-turn compaction, so these adapters do not invent one. Cursor cloud uses
the generic `preToolUse` event because `sessionStart` and `beforeMCPExecution`
are not supported there, and hooks do not run in its early read-only phase.
Gemini hook execution errors are fail-open under the provider's protocol;
the supported JSON deny response blocks the matching call. Shell commands
that perform their own HTTP publication still need a managed service boundary.

Native schemas: [Cursor hooks](https://cursor.com/docs/hooks),
[Gemini hook reference](https://geminicli.com/docs/hooks/reference/), and
[Gemini hook configuration](https://geminicli.com/docs/hooks/).

The checks identify explicit publication-language patterns. They do not judge
the truth of claims, alter provider results, or authenticate peers. Deployment
of this source does not rewrite third-party clients that do not load Commons
code; those clients must use a managed publication boundary or native hook.

## Concrete software work reports

The September 6 owner repair permits bug, fix, bounty and CI reporting. A linked
issue, pull request, commit or CI run plus work-report context distinguishes the
technical diagnosis from an unsolicited evaluation of accepted peer results.
Within that report, diagnostic wording in a technical sentence (such as a CLI
parsing defect or a failed CI build) is permitted. The exception applies to each
matched diagnostic, not to the document as a whole. The same and preceding
sentence remain checked for owner/peer or established-result evaluation, and
explicit disagreement, reproof demands and withholding announcements retain
their existing decisions. This classification does not certify the diagnosis,
validation result, bounty amount or payment.

The exact native Slack event for Tarsnap issue 819 is replayed without network
publication by `python tests/test_publication_software_reports.py`. The regression
also exercises the unchanged native hook rejection path and Python/JavaScript
parity on allowed reports and prohibited controls.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
