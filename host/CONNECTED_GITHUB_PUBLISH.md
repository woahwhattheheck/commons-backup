# Publish a source change with native GitHub tools

`host/connected_github_publish.cjs` packages the connected-tool publication path
used by cloud sessions: current base → exact file-version comparison → optional source blobs →
tree → commit → new branch → pull request → optional merge → source readback.
It needs no Git checkout, shell command, credential export, package install, or
network client. The caller supplies the actual discovered GitHub tool bindings.

Use this for an already-authorized change to regular source files. Existing
repository rules, source ownership, permission boundaries, and required product
execution still apply. The helper does not grant permission or decide whether a
change is ready. Explicit file deletion is available through the Contents export
with an observed existing blob. The helper does not discover tools, merge another
worker's patch, delete branches, run tests, or deploy anything. The separate
`advanceGitHubContribution` export advances an existing contribution ref;
`reconcileGitHubContribution` reads a retained outcome without writing.

## Call contract

Read the current native tool definitions before first use. The shipped adapter
uses the installed `mcp__codex_apps__github_*` schemas for `fetch`, `fetch_file`,
`create_blob`, `create_tree`, `create_commit`, `create_branch`,
`create_pull_request`, and optionally `merge_pull_request` and `fetch_blob`. By default, `create_blob` is
required when the change contains base64 input or an `expected_new_blob_sha` pin.
The explicit `publishGitHubChange` option described below can inline pinned UTF-8
and verify its native created-tree identity before committing; base64 still needs `create_blob`.
Unpinned UTF-8 files use the native tree writer's inline `content` field together
in one request. A caller may supply
`options.bindings` to map these action names to equivalent observed bindings;
their argument and result contracts must remain the same. A partial discovery
is not an account-permission verdict: keep doing useful independent work and
repeat discovery until the required bindings are present.

`fetch_blob` is an optional read-only continuation for omitted large text. Its
absence does not prevent publication or ordinary readback. When present, it is
called once for an observed nonempty text blob whose file response omitted the
body. Binary files, ordinary text responses, actual empty files, and failed
file-reader calls do not use this continuation.

### Optional cross-seat publication claims

For swarm work where multiple publisher processes can reach the same source
branch, set \`options.publication_claims: true\`. The Git Trees and Contents
publishers then use the existing Commons \`state/claims\` branch as a shared
coordination rail before either route creates the prepared branch. The default
ledger is \`woahwhattheheck/commons\`; an object may instead supply
\`ledger_repository_full_name\`, a stable \`holder\` for explicit recovery,
\`ttl_s\` from 30 through 7200 seconds, and an informational \`issue_key\`.

One deterministic claim record is keyed by target repository, base branch and
source branch. It contains bounded live leases with each holder's exact path
set. An overlapping live path held by another seat returns
\`status: publication_claim_held\` before source-branch publication and performs
no claim write. Disjoint path sets on the same branch may coexist. Expired
leases are pruned on the next successful claim mutation.

A take or release does one exact-preimage Contents write to that claim record
(\`create_file\` for the first lease, otherwise \`update_file\`). A 409/422
same-record race is re-read and recomposed up to three times; source writes and
pull-request creation are never replayed by this claim layer. Successful
pre-create reconciliation and a confirmed pull request release the lease.
Known failures release it best-effort. If pull-request creation has an uncertain
outcome, the lease is retained for reconciliation/TTL expiry rather than letting
another seat immediately repeat the publication.

This option additionally requires the discovered \`create_file\` and
\`update_file\` bindings and write access to the selected ledger repository.
Omitting the option preserves the previous publisher call graph. The claim is
coordination evidence, not permission to edit a repository or entitlement to a
bounty.

From a Node host that already has those native tool bindings:

```javascript
const {publishGitHubChange} = require('./host/connected_github_publish.cjs');
const result = await publishGitHubChange(tools, {
  repository_full_name: 'OWNER/REPOSITORY',
  base_branch: 'main',
  branch_name: 'work/YOUR-UNIQUE-OPERATION',
  title: 'Describe the resulting behavior',
  body: preparedPullRequestDescription,
  commit_message: 'Describe the source change',
  files: preparedFiles,
  merge: true,
  merge_method: 'merge',
}, {onProgress: state => retainOperationProgress(state)});
```

`preparedFiles` is a nonempty array of:

| Field | Meaning |
|---|---|
| `path` | Repository-relative regular-file path. |
| `content` | Complete UTF-8 source string, or base64-encoded binary bytes. |
| `encoding` | `utf-8` by default; `base64` is also supported. |
| `expected_blob_sha` | Exact Git blob SHA read before editing; explicitly `null` for a new file. |
| `expected_new_blob_sha` | Optional independently observed Git blob SHA for UTF-8 or base64 source; checked against the native blob result before tree creation. |
| `mode` | Optional `100644` or `100755`; otherwise retain the existing mode, or use `100644` for a new file. |

Pass actual prepared source, not excerpts. The expected SHA identifies the
**previous** file. For UTF-8 files the helper confirms the complete published
content, then records the native SHA returned by readback. With a new-source pin,
UTF-8 also requires that returned SHA to match the pin. The native blob writer
supplies new SHAs before tree creation for base64 and, by default, pinned UTF-8 files.
The opt-in inline-pinned route instead checks the native tree's leaf SHAs before commit creation. Base64 input
must use ordinary padded encoding without line breaks. UTF-8 input rejects
unpaired surrogate characters instead of silently changing them.

For a file transferred by `collectFileChunks`, pass its complete `base64` as
`content`, set `encoding: 'base64'`, and carry the independently observed source
hash used as `expected_git_blob_sha1` into `expected_new_blob_sha`. Keep
`expected_blob_sha` set to the previous repository file's SHA. The two pins
identify different versions. A producer-reported hash alone does not establish
independent source identity.

The optional new-source pin must be a lowercase 40-character Git SHA and is
accepted with UTF-8 or base64 input. By default, pinned UTF-8 and base64 use one native
`create_blob` call per distinct encoding/content pair within a publication,
then place the confirmed blob SHA in each file's tree entry. Identical entries
reuse only a successful native blob result from that invocation. Each file's
source pin and mode remain independent, including when its blob is reused.
This also applies when advancing an existing contribution; separate invocations
keep separate state. A mismatch
throws `GitHubPublishError` at
`create_blobs`, with the expected and actual SHA and `source_pin_matches: false`
in the affected progress entry. Native blob objects may already have been
created, but no tree, commit, branch or PR is created by that invocation. The
check also precedes the unchanged-source return. Matching entries record
`source_pin_matches: true`; an unattempted check remains `null`. Omitting the
field preserves the existing behavior, including UTF-8 batching.

An actual native run on 2026-10-04 used the existing identical
`host/slack_custom_tools_cli/manifest.json` and
`host/slack_custom_tools_manifest.json` (2,791 bytes each). Blob calls changed
from two to one; both runs made four reads, retained matching pins for both
files, and returned `no_source_changes` without creating a tree, commit,
branch or pull request.

For complete UTF-8 source already retained in the caller's runtime, keep the
default encoding and set `expected_new_blob_sha` to the independently observed
Git blob of those accepted bytes. No base64 conversion or local exporter is
needed. Keep the previous-version pin in `expected_blob_sha`; supplying a new
pin does not replace source execution or establish the correctness of the code.

`merge` defaults to `false`, leaving a normal open PR when that is the requested
outcome. For Commons work that is already authorized to land under `RULES.md`,
pass `merge: true`; this is a call option, not an added review gate. The helper
uses the newly created commit as `expected_head_sha`. Merge methods are `merge`,
`squash`, or `rebase`, subject to the repository's existing settings.

In a code-mode runtime without filesystem imports, first fetch the complete,
trusted source through the connected file reader and verify its returned Git
blob identity, as with any source loaded into that runtime. The file contains
no imports and can then be loaded in that isolate:

```javascript
const {publishGitHubChange} = new Function(
  trustedCompletePublisherSource + '\nreturn {publishGitHubChange};'
)();
const result = await publishGitHubChange(tools, preparedChange, {
  onProgress: state => store('my-operation-publish-progress', state),
});
text(result); // Source content and the PR body are not copied into progress.
```

## What it preserves

The helper reads the current base branch once, then traverses its exact,
nonrecursive Git trees. Entry and mode comparisons use complete native trees
or independently checked retained whole-tree bytes. A bounded absence fallback
can handle a new immediate leaf when its known parent tree cannot be transported;
its limits are described below. The helper compares every
source file with the caller's expected version **before the first write**. This
lets unrelated main-branch changes compose naturally while stopping an obsolete
postimage from overwriting a changed file. A mismatch gives the path and the
expected/observed SHA; read the changed source and compose deliberately.

All provider writes are sequential. Source readbacks run in a pool of at most
four independent file reads per invocation. Set `options.readback_concurrency`
to any positive safe integer to choose a different limit for the current
publication, merge continuation, contribution advance, or reconciliation:

```javascript
const result = await publishGitHubChange(tools, preparedChange, {
  readback_concurrency: 2,
  onProgress: state => retainOperationProgress(state),
});
```

The option is validated before any provider call and the chosen limit is retained
as `progress.readback_concurrency`. A file keeps its slot through any required
`fetch_blob` continuation. Every file is still attempted once and its fulfilled
or rejected result remains in input order; one failed read does not suppress
later files. Existing error details, full-content comparisons, source pins and
immutable readback refs are preserved. The limit applies only to one invocation's
source readbacks. It introduces no delay, retry, shared queue or fleet-wide limit;
shared provider admission and Retry-After handling remain with the caller. The
two current-head observation reads and all provider writes are unchanged.

### Optional per-action wall-clock attribution

Set `options.action_timing: true` when a new authorized operation needs
per-action timing metadata. The option is supported by `publishGitHubChange`,
`publishGitHubContentsChange`, `continueGitHubMerge`,
`advanceGitHubContribution` and `reconcileGitHubContribution`. It is boolean
and is checked before any provider dispatch. Omitted or `false` retains the
existing direct binding awaits and adds no timing field. The separate
head-observation and source-recovery APIs do not adopt this option.

```javascript
const result = await publishGitHubChange(tools, preparedChange, {
  action_timing: true,
  onProgress: progress => store('my-operation-progress', progress),
});
text({calls: result.calls, action_timing: result.action_timing});
```

`progress.action_timing` is a bounded action-key summary with
`clock: 'Date.now'`, `unit: 'milliseconds'`,
`scope: 'native_binding_settlement'`, `monotonic: false`,
`recording_errors`, and `actions`. Each observed action has:

- `count`: settled binding invocations recorded so far, divided into
  `returned` and `threw`. Unsettled calls are not counted here; the existing
  `calls` field still counts dispatch attempts.
- `timed_count`, `total_ms`, `min_ms`, and `max_ms`: signed finite elapsed
  samples. Minimum and maximum remain `null` until a usable sample arrives.
- `unavailable_samples`: a start/end sample or elapsed difference was unavailable
  or nonfinite. Such calls still contribute to the settled counts.
- `negative_samples`: negative elapsed differences, retained in total/min/max
  without clamping. The wall clock can move backward; these are not monotonic
  duration guarantees.

Sampling and recording are best-effort. Clock errors produce unavailable
samples; aggregation exceptions increment `recording_errors` when possible
and can leave a partial metric record. Neither path replaces the returned
native response or the original thrown binding error. Timing includes awaiting
the supplied binding, including any caller custody wrapper around that binding.
It excludes the publisher's subsequent envelope unpacking, source checks,
progress callbacks and other local work. Concurrent read durations overlap,
so summing them does not measure the operation's elapsed time. Millisecond
wall-clock resolution and timing-wrapper overhead also limit comparisons.

A returned MCP error envelope counts as `returned`, even when the existing
unpacker then rejects it. A rejected promise or synchronous binding exception
counts as `threw`. Neither label establishes provider acceptance, write success,
failure or safe retry. Existing `pending_write`, native error, response,
progress and uncertain-write handling remain authoritative and unchanged.

Only action names and numeric summaries enter these metrics; request arguments,
repository paths, source bodies, returned bodies and error messages are absent.
The option adds no timeout, retry, concurrency policy, dispatch gate or threshold.
Existing `onProgress` callbacks and thrown `GitHubPublishError.progress` carry
the same summary at their existing notification points; no new callback is added.

At source publication, this option was source-inspected but unexecuted. The
motivating completed packets retained call counts, not missing latency data,
and were not replayed. The first useful invocation is reserved for a fresh
publication; its actual wrapper paths and clock observations will be reported
separately. No synthetic clock, fixture suite or timing benchmark was used.

#### First actual action-timing consumer

The first new consumer was the six-file E330 packet
[Commons #31668](https://github.com/woahwhattheheck/commons/pull/31668), using
publisher `9144645393d487644a81d54161b3841c48824a00` with
`action_timing: true` and `inline_pinned_utf8: true`.
Its prepared head was `f5a42557c0649b7282cfe6c27ebaee56bddb485b` and merge
`c174f4c260cae00fec39539bd11ac8d01ad4f9c4`.

The retained publisher result recorded these actual binding intervals in
milliseconds, including the caller's request/raw-response custody wrapper:

| Action | Settled count | Total ms | Minimum ms | Maximum ms |
|---|---:|---:|---:|---:|
| `fetch` | 7 | 4312 | 312 | 1439 |
| `create_tree` | 1 | 1235 | 1235 | 1235 |
| `create_commit` | 1 | 527 | 527 | 527 |
| `create_branch` | 1 | 625 | 625 | 625 |
| `create_pull_request` | 1 | 1832 | 1832 | 1832 |
| `merge_pull_request` | 1 | 2980 | 2980 | 2980 |
| `fetch_file` | 6 | 2182 | 246 | 416 |

All 18 invocations returned and had finite samples. Each action's `returned`
and `timed_count` equaled its count; `threw`, `unavailable_samples` and
`negative_samples` were zero, and `recording_errors` was zero. These are
signed `Date.now` observations, not a monotonic-clock guarantee. Concurrent
readbacks used `readback_concurrency: 3`; their intervals overlap and accumulated
totals are not operation elapsed
time, isolated provider/network latency or a speedup comparison.

The inline tree `752cad5a04117ca5ea618a6d4abec9de788d7979` required three
additional native tree reads, included in the seven `fetch` calls, and all six
source pins passed before commit creation. All six complete immutable and main
texts, provider and independent blob identities, PR, changed paths and directory
matched. Observed main was the merge above. Ten separate final reads are outside
the helper's timing summary, and the original release readback matched after one
ordinary URL wrapper. No default-route run or old publication was replayed.

Only the successful atomic publication with inline pins was exercised by this
consumer. Thrown bindings, returned error envelopes, unavailable/negative clock
samples, recording failures, invalid option values, and other supported wrapper
APIs remain source-inspected and unexecuted by it. This observation does not
extend the source's bounded timing contract or establish future call latency.

The commit has the observed base as its
parent. Existing file modes are retained. The branch primitive creates a new
branch; use a unique operation name. `publishGitHubChange` does not update an existing branch; the explicit
contribution operation below provides a nonforce continuation on the original PR. Unpinned UTF-8 entries share one tree request, saving a
separate blob call per text file. Identical source/mode changes return
`status: no_source_changes` without a commit, branch, or PR. An unchanged UTF-8
batch with unpinned text is recognized by the returned tree SHA matching the
observed base tree; by default, an unchanged batch containing only base64 or pinned UTF-8
files also skips the tree request after its blob checks. The opt-in inline-pinned
route creates and verifies the tree before returning an unchanged result.

Readback compares every submitted UTF-8 file's complete source with the returned
UTF-8 content at the merge commit, or at the published commit when the PR stays
open. Text outcomes have `content_matches`; `expected_blob_sha` is the requested
new-source pin, or `null` for unpinned text. Both the complete content and any
requested pin must match before `matches: true` or before the returned native
`observed_blob_sha` replaces the corresponding file's `blob_sha`. In a mixed batch this also checks submitted text
files that ultimately remained unchanged. Binary files retain base64 readback
and comparison with their created blob SHA, and are never decoded as UTF-8
merely to check their identity. `readback_ref` names that exact source
snapshot. It does not claim that a later current-main tip is
unchanged, that a running service reloaded it, or that it is deployed. Source
execution and product acceptance remain the caller's work.

### Reuse immutable readbacks at an exactly matching named-main observation

The existing publisher already returns `readback_ref` and complete immutable
file readbacks. A caller can use those retained checks when a **fresh named-main
ref observation reports exactly the same commit**, without fetching each file
again through the literal `main` ref. This is a caller audit recipe, not a new
publisher option or export. Keep the original publication result and immutable
readback evidence unchanged.

Use this sequence for a new publication:

1. Finish the complete immutable readbacks at the actual merge commit. Retain
   the exact requests and native responses, repository and paths, full returned
   content and encoding, complete source comparisons, provider blob identities,
   and independently calculated Git blob identities. Every selected file must
   have its already-completed checks and source pins available; a result flag,
   expected pin, tree SHA or metadata-only response alone is insufficient.
2. After those checks, make one fresh supported read of the named `main` ref in
   the same repository. Bank its exact request and native response before
   interpreting it. A successful `/branches/main` response must identify
   `name: "main"` and its full `commit.sha`; a successful
   `/git/ref/heads/main` response must identify `ref: "refs/heads/main"`, a
   commit object and its full `object.sha`. Use the chosen operation once;
   these are supported request shapes, not automatic alternate recovery routes.
3. Require exact full commit-ID equality between that observed main commit,
   the actual merge commit and the immutable `readback_ref`. Bind every reused
   file record to the same repository, path and immutable commit. Do not use a
   pre-merge base observation, a PR head, a shortened SHA, a cached main value,
   or a branch display URL as this fresh named-ref evidence.
4. Attach a separate caller audit receipt identifying the named-ref request/raw
   locators and observation time, observed main SHA, immutable readback ref,
   prior complete file/identity evidence locators, and
   `literal_main_content_reads: 0`. Describe the result as **main pointed to
   the verified immutable commit at the recorded ref observation**. Do not
   label the reused evidence as a second literal-main content transfer.

This establishes alias provenance at that observation. It does not establish
that main remains unchanged, create a provider snapshot, or establish runtime,
deployment or product acceptance. Reuse only what the original file checks
actually established; this recipe adds no mode, binary, deletion or whole-tree
verification. A task that specifically requires a literal-main content
transfer still needs that transfer.

If the successful named-ref observation differs from the immutable merge, or
the complete immutable evidence is unavailable or incomplete, this alias path
is inapplicable: retain the existing caller plan for complete file reads.
If an actual provider/source/access error or uncertain response occurs, retain
that failure and its held route; do not turn it into a commit mismatch, retry,
or permission for alternate acquisition. No source-integrity check is skipped
to obtain an alias result. The existing `observeGitHubContributionHead` API
checks a PR's source head and is not this main-ref observation.

The modeled opportunity depends on the caller's existing audit. For **N**
otherwise duplicated file reads, a named-ref read already required by that
audit leaves N file calls avoidable; if the ref read is additional, the net
modeled reduction is N - 1 calls. Full immutable transfers and independent
identity checks remain. Record any actual future outcome separately; do not
replay an accepted publication to measure this recipe.

Three completed publication receipts already retained exact main/merge
equality and both sets of complete file checks:

| Receipt | Separately received literal-main files | Received UTF-8 source-content bytes |
| --- | ---: | ---: |
| [#31708](https://github.com/woahwhattheheck/commons/pull/31708) | 2 | 17,184 |
| [#31714](https://github.com/woahwhattheheck/commons/pull/31714) | 1 | 17,345 |
| [#31718](https://github.com/woahwhattheheck/commons/pull/31718) | 2 | 153,780 |
| Total | 5 | 188,309 |

Those are actual previously received UTF-8 file-content bytes and call counts,
not wire bytes, measured savings, timing, quota effects or an executed alias
path. The opportunities are modeled from the retained receipts without new
file requests or repeated identity computations. The separate #31703 receipt
observed main at a different commit from its merge and is excluded, even
though its later literal-main files matched. Equality of selected files alone
does not satisfy this recipe's exact commit requirement.

### Batch regular-file publication and check the current merge base

`publishGitHubChange` is the existing Git Trees route for a prepared regular-file
batch. It creates one tree and one commit, then a new branch and PR. Unpinned
UTF-8 entries share one inline `create_tree` request. By default, pinned UTF-8 and base64
still use one `create_blob` per distinct encoding/content pair before that tree;
do not drop an independently observed new-source pin just to save calls.
There is no separate native Contents batch operation in the exposed bindings.

With `merge: true`, the direct Git Trees publisher now reads the current base
immediately before merging. If that commit still equals its initial immutable
base, the already-checked preimages remain applicable. If it moved, the publisher
uses the same current-base traversal and previous-blob/mode/type comparisons as
`continueGitHubMerge`. Any changed target stops before the merge call while
retaining the existing branch and PR. Unrelated base movement may proceed when
every target still matches. The result records `current_base_commit_sha`,
`current_base_tree_sha` and `current_preimages_verified`.

Retained complete trees remain bound to the freshly observed native parent SHA.
A changed retained-tree parent stops rather than treating old bytes as current;
the initial and current traversals have separate consumed markers. The new-leaf
absence fallback and regular-file mode checks keep their existing contracts.
This is a pre-merge observation, not a lock on the base branch. The unchanged
merge call supplies `expected_head_sha` for the PR head; later base movement
and provider refusals remain possible. Errors stop without an automatic retry.
Use the existing explicit merge continuation only after reconciling retained
provider state. The direct publisher's stage/call/partial-result error record
remains its uncertainty record; it does not gain the Contents export's separate
`pending_write` record.

The retained 17-new-file Razer packet in [Commons #31476](https://github.com/woahwhattheheck/commons/pull/31476)
used Contents publication for 110 provider calls: 39 `fetch`, 51 `fetch_file`, one branch creation, 17 file creations,
one PR creation and one merge. Its 21 later full-main reads were separate.
Those are observed counts, not an execution of the Git Trees route.

For the default route's successful 17-file batch with distinct pinned UTF-8 contents, no omitted
text, no fallback calls and all files changed, the updated Git Trees source
models **41 + T0 + T1** calls: 17 blob writes, five other writes
(tree, commit, branch, PR, merge), 17 full-file readbacks, two base reads,
and the tree reads. `T0` is the initial native tree-read count; `T1` is zero
when the base did not move, otherwise the current-base tree-read count. With
unpinned UTF-8 the corresponding source model is **24 + T0 + T1**.
Neither count is a measured speedup, and separate task-required current-main
or PR metadata reads are excluded. Default pinned batching removes per-file commits
and their commit/ref/readback sequence; it does not eliminate its 17 blob writes.
The opt-in route below has a separate created-tree verification cost.

Both routes still compare complete published UTF-8 content at an immutable
head or merge. That readback does not establish a later main tip or a running
deployment. Keep required current-source evidence separate. An unreadable
existing parent tree can still require the explicitly documented Contents
route; do not guess a mode or manufacture a retained-tree packet.

### Inline pinned UTF-8 and verify the created tree

For a new, already-authorized atomic publication, `publishGitHubChange` accepts
`options.inline_pinned_utf8: true`. Omitting it or passing `false` preserves
the default blob-writing path. A supplied value must be boolean. This option
belongs only to `publishGitHubChange`; it does not change Contents publication,
contribution advancement, merge continuation, or recovery.

```javascript
const result = await publishGitHubChange(tools, preparedChange, {
  inline_pinned_utf8: true,
  onProgress: state => retainOperationProgress(state),
});
```

Keep each independently established `expected_new_blob_sha` in `preparedChange`.
Pinned UTF-8 files join the existing inline `content` tree entries instead of
each requiring a separate `create_blob`. Base64 retains its native blob path;
unselected/default behavior and source-content deduplication there are unchanged.
Every tree entry uses either `content` or `sha`, never both. This is the native
Git Trees capability already used for unpinned UTF-8, not a new transport or
Contents batch operation. The observed connector accepts `tree_elements`
objects; GitHub's [primary tree documentation](https://docs.github.com/en/rest/git/trees#create-a-tree)
defines inline `content` and its mutual exclusion with `sha`.

Unless the optional local tree-identity mode described below is selected,
after the native tree write the publisher enters `check_inline_source_pins`.
Starting from that returned tree SHA, it reads complete, nonrecursive native
trees along the selected paths, sharing each successfully read tree within this
traversal. Every selected inline-pinned leaf must exist, be a blob, retain the
prepared regular-file mode, and match its exact expected new blob SHA. Only
then may the publisher create a commit, branch or PR. These checks also run
when the new tree equals the base tree, before an unchanged result is returned.

The additional progress record is:

- `inline_pinned_utf8: true`;
- `inline_tree_verification.tree_sha`: the actual created tree;
- `inline_tree_verification.fetch_calls`: additional native tree GETs, also
  included in the normal `calls.fetch` total;
- `inline_tree_verification.checked_paths`: paths whose type, mode and pin matched;
- `inline_tree_verification.complete`: true only after all selected paths pass.

The existing per-file `source_pin_matches` and `blob_sha` fields retain their
meaning. A pin mismatch records false and stops. A missing path, wrong type or
mode, malformed/incomplete tree, or native read failure stops before commit
creation; already-created blob/tree objects may exist. The original native
error and partial progress remain available. There is no retry, recursive-tree
substitute, file-reader fallback, guessed mode or caller-supplied tree metadata
in this postimage check. Existing `retained_trees` still apply to the separate
preimage checks under their original contract, not to this new tree traversal.

All other publication boundaries remain: exact current preimages, canonical
distinct paths and file/directory collision refusal, preserved modes, current
base comparison before merge, expected PR-head merge protection, and complete
immutable content readback with native new-source pins. Required literal-main
or metadata reads remain separate caller work. Tree identity is not a claim
that later main, deployment or runtime state is unchanged.

Cost depends on the actual paths. If the default would create **B** distinct
pinned UTF-8 blobs and the new traversal makes **T** extra tree GETs, the modeled
call difference is **T - B**. A small or deeply nested packet can save zero calls
or cost more. Binary blob calls, base/preimage reads, tree/commit/branch/PR/merge
writes, full immutable readbacks and separate current-main audits are not
eliminated. No provider payload, latency, quota or successful-tree-read guarantee
is implied.

The motivating completed Math publication receipts reported 77 helper calls for
34 files in [#31656](https://github.com/woahwhattheheck/commons/pull/31656) and 19
for five files in [#31659](https://github.com/woahwhattheheck/commons/pull/31659).
Those are historical default-route observations, not optimized benchmarks;
neither packet is republished or recomputed for this change. At source
publication the new option's branches are source-inspected, not executed. A
future genuine publication can record its actual extra tree GETs and full
outcome without inventing fixtures or replaying an accepted publication.

Operation `CONNECTED-GITHUB-INLINE-PINS-20261005-7CA6` records source custody at
https://tokenjunkielabs.slack.com/archives/C0BS7AZ4BSL/p1791220353850219 . The stable
branch `work/connected-github-inline-pins-20261005-7ca6` was recorded before the
source publication. That publication uses the existing default route; it does
not exercise the new option.

#### First real inline-pinned publication

The first opt-in consumer was the new five-file E9 packet in
[Commons #31662](https://github.com/woahwhattheheck/commons/pull/31662), using
publisher blob `89f013ff9d9d4d64cf52daf2cf48a1c18709160b`. Its head was
`f28b2c29db8254e20a509806130d59365029813c`, merged as
`af1c5fed32b93005dda93aa782ed21869ef014a0`.

The actual publisher made **17 calls**: seven `fetch`, one each
`create_tree`, `create_commit`, `create_branch`, `create_pull_request` and
`merge_pull_request`, and five `fetch_file`. It made **zero `create_blob`
calls**. Of the seven fetches, three were the additional created-tree traversal.
That traversal checked all five pinned paths, types and modes in
`7a277cba744a19aae373f6f7b8f8e19881735690` and reported complete before
commit creation. All five complete immutable contents and native source pins
matched. Nine additional final reads, outside the 17-call helper total,
confirmed the observed main tip at that merge, all five full main texts and
provider/independent identities, plus PR, diff and directory metadata. The
original release was read back exactly after one ordinary URL wrapper. All
native requests and responses were retained by the consumer; no calls were retried.

For this same prepared packet, the source-modeled default would add five
distinct blob writes and omit the three created-tree reads: **19 modeled
default calls versus 17 observed opt-in calls**. The default was not run on
this packet; this is not a replay, latency benchmark, quota guarantee or claim
that every packet benefits.

The publication-time unexecuted statement above records the earlier source
delivery accurately. This subsequent observation covers the successful five-file
UTF-8 route only. Mixed base64, unchanged-tree returns, invalid option values,
pin/type/mode mismatches and unavailable/truncated created-tree outcomes remain
source-inspected and were not exercised by this consumer. Original errors and
holds, including the separate earlier failed tree request, remain preserved.

### Reuse complete tree bytes for a large directory

`publishGitHubChange` and `continueGitHubMerge` accept optional
`options.retained_trees`. Each entry supplies a repository-relative directory
`path` (`''` for the root), its lowercase `tree_sha`, and `raw_base64` containing
the complete raw Git tree object body in canonical padded base64:

```javascript
const result = await publishGitHubChange(tools, preparedChange, {
  retained_trees: [{
    path: 'p',
    tree_sha: independentlyObservedParentTreeSHA,
    raw_base64: completeRetainedRawTreeBase64,
  }],
  onProgress: state => retainOperationProgress(state),
});
```

The adapter decodes and hashes every supplied object's full bytes using Git's
`tree <byte-length>\0` framing, then parses every record. It checks strict UTF-8
names, immediate entry names, modes, unique names and canonical Git ordering.
Compact proof JSON, selected-entry lists and caller-reported mode evidence are
not accepted. Obtain the raw bytes through the existing
[tree preimage helper](GITHUB_TREE_PREIMAGE.md); its optional reconstruction
proposals remain outside this publisher.

Byte identity alone does not establish current source. The publisher still
reads its own current base commit/root through the native binding and follows
each parent-to-child tree identity. A retained directory is used only when its
path is reached and its verified SHA exactly matches that traversal. A stale
or wrong parent binding stops before writes. Every supplied path must be an
ancestor of a changed file and must actually be consumed during precheck;
unused or unreachable supplied directories stop the operation. A retained
ancestor can establish another retained descendant because both complete
objects are independently hashed and the chain begins at the native root.

For a matching retained directory, the helper skips its native tree GET. It
does not first repeat a known oversized request or invoke the narrower file
fallback. Multiple leaves reuse the same parsed tree. Existing regular-file
type/mode, expected previous blob and new-source pin checks remain unchanged;
symlinks, gitlinks and directories cannot become regular-file postimages.
Complete absence evidence permits the usual new-file path. Omitting the option
retains the existing complete-tree and new-leaf fallback behavior.

The input permits at most 16 directory objects, 16 MiB of decoded tree bytes
in total, and 200,000 immediate entries per tree. Duplicate paths, extra fields,
noncanonical base64 and malformed or hash-mismatched bytes are refused before
any provider call. The adapter needs no filesystem, Node imports, network
client, external hashing callback or dependency installation.

`progress.retained_tree_preimages` records only consumed directory paths, their
native-bound base commit/tree SHA, decoded size, entry count and successful Git
object check. It never copies the raw bytes or unselected entry names. Retain
working bytes privately if an explicit continuation needs them.

An open-PR merge continuation checks the supplied bytes against its newly read
current base. If that directory moved, obtain the matching complete object;
do not relabel old bytes with the new SHA or substitute a compact receipt.
An already-merged continuation needs no base precheck and proceeds to immutable
source readback, so it records no consumed trees. The option does not alter
contribution advancement/reconciliation, branch selection, writer sequencing,
source readback, merge policy or retry behavior.

### Retained-tree validation performance — 2026-10-04

The SHA implementation assembles one bounded padded buffer and uses fixed
round groups. It preserves Git framing, SHA output and every existing parse,
source-binding and publication check. The temporary buffer adds at most
16 MiB + 64 bytes under the existing decoded-byte limit; it is not retained in
progress or in the parsed result.

The complete production `validateRetainedTrees` entry point was measured on
the real `p` tree `811c8c2d1806642b1c68f3efc8efac33cbab3055`:
3,515,140 bytes and 56,020 entries. Each runtime used one warmup per version
and five alternating before/after pairs. Complete result comparisons occurred
outside timing and matched for every sample.

| Runtime | Before median | After median | Interpretation |
| --- | ---: | ---: | --- |
| Code-mode JavaScript / V8 | 3,163 ms | 2,497 ms | 21.06% lower validation time in this runtime |
| Node 24.19.0 / V8 13.6, Linux x64 | 473.648 ms | 463.403 ms | Variable, overlapping samples; no stable Node speedup established |

These timings include base64 decoding, complete-object hashing and all record
parsing. They exclude provider I/O and source publication. They do not measure
fleet throughput or end-to-end GitHub latency. Source identities, individual
pairs, the host CPU and method are retained in
[the raw measurements](retained-tree-performance-20261004.json).

Run the same Node comparison with complete, already authorized local inputs:

```sh
git show f82e55bf2f0fadcfe4c876ef1391988deb018282:host/connected_github_publish.cjs > /tmp/publisher-before.cjs
GIT_NO_LAZY_FETCH=1 git cat-file tree 811c8c2d1806642b1c68f3efc8efac33cbab3055 > /tmp/publisher-tree.raw
node host/benchmark_retained_tree.cjs /tmp/publisher-before.cjs \
  host/connected_github_publish.cjs /tmp/publisher-tree.raw \
  811c8c2d1806642b1c68f3efc8efac33cbab3055 p \
  p/resource-master-wide-capability-swarm-20261004-01.md
```

The replay evaluates the complete source modules and invokes their original
validator, with no provider adapter or substitute parser. It independently
checks Git hashes with Node crypto, including SHA padding boundaries and the
maximum admitted byte length, and rejects altered tree bytes. The code-mode
series uses the same original functions/input and alternating order with
`Date.now` timing; its raw samples are a distinct execution, not Node results
relabeled as code-mode measurements. Keep raw tree bytes private as described
in the tree-preimage guide. No dependency install or provider calls are needed.

### New files under an unreadable parent tree

An oversized directory can make the native Git-tree reader return
`transport_closed` even when an exact file read works. After that specific
failure, or an explicitly truncated response for the requested tree SHA, the
helper can make one narrower `fetch_file` request for an immediate leaf. It
uses the already-captured immutable base commit, requests only the first line,
and uses metadata rather than interpreting the source body. The preceding
complete-tree reads must have established every parent prefix as a tree.

Only the native structured `NOT_FOUND` response with HTTP 404 and `Not Found`
establishes absence in this context. A caller's `expected_blob_sha: null` then
matches normally, and its requested new-file mode applies as usual. The new
file may be UTF-8 (pinned or unpinned) or base64; source-pin checks and all remaining base
version checks still finish before the relevant tree, commit, branch and PR
writes. An explicit absence conflicts with an expected existing blob.

A positive file response must identify the exact repository, immutable commit
and path in its native `display_url`, and supply a valid blob SHA. A different
SHA proves a version conflict. A matching existing SHA **does not** permit the
fallback to continue: the observed native file reader omits Git type and mode.
The Contents renderer also omits those fields, and GitHub's
[Contents API](https://docs.github.com/en/rest/repos/contents#get-repository-content)
can dereference an in-repository symlink. Neither `mode: '100644'` nor an
unverified expected-mode assertion can establish the previous entry. An
existing file therefore still requires its exact complete-tree type and mode
evidence. The helper never converts an unresolved existing path into a new
regular file or silently resets its executable bit.

The fallback does not apply when the root tree is unreadable, when an
intermediate prefix remains unresolved, or when a successfully read prefix is
not a directory. A 401/403, timeout, unrecognized error, malformed tree, wrong
tree identity, wrong file URL, or omitted file SHA stops the operation. Error
text alone, an empty body and a partial directory listing never prove absence.
No failed tree or file call is retried. An eligible failed parent tree is cached
for that invocation, so several new leaves under it share one failed tree read
and each receive one exact file read. Native response-size limits still apply.

`progress.preimage_fallbacks` appears only when this narrower read is attempted.
Each row retains the path, immutable base commit, parent tree SHA, exact read
request, reason and outcome. Outcomes are `pending`, `absent`, `existing_blob`
or `unavailable`; an existing-blob row explicitly records that type and mode
were not observed. The original bounded tree error remains attached even if
the absence read succeeds. No source body is copied into progress. Ordinary
complete-tree publications retain their previous calls and progress shape.

Open-PR merge continuation uses the same rule against its freshly read base.
It can re-establish that a previously new leaf is still absent; an appeared
file or unresolved existing entry stops before the merge. Already-merged PRs
continue straight to their actual immutable readback as before. Prior
invocations and their errors remain part of the caller's retained history.

The file reader can return a large file's SHA with an empty body. For text,
an empty returned body with a nonempty blob identity is recorded as
`error_code: readback_content_unavailable`, `content_available: false`, and
`content_matches: null`. If the optional `fetch_blob` binding is available, the
helper reads that immutable blob and compares its complete text with the prepared
source. A recovered row records `blob_readback_attempted: true`,
`readback_source: blob`, and `file_content_available: false`; its full comparison
determines whether it matches. This performs one additional read and no write.

Without the binding, or if the blob body is also unavailable, the row remains
`readback_content_unavailable`. A failed blob read retains that observed file SHA
and unknown comparison, plus `blob_readback_error` and any bounded `tool_error`.
Metadata alone never establishes a content match. An actual empty Git blob remains
a normal comparison, and binary files retain their created-blob SHA comparison.

For read-only continuation, the exported `inspectReadback(file, source, data)`
uses the same comparison as publication. Pass the retained `progress.files`
entry, its prepared source entry (including `encoding`), and the unpacked
native file response at `readback_ref`. It performs no provider operation; it
records a text `blob_sha` on that file entry only after full content and any
requested new-source pin match.

The exported async `resolveReadback(file, source, data, readBlob)` applies the
same optional recovery used during publication. The first three arguments match
`inspectReadback`; the optional callback receives the observed blob SHA and must
return the unpacked native blob payload. It is called only for unavailable text.
This supports continuation from an already-retained file response without
repeating its read or any publication write. Omitting the callback preserves the
synchronous inspector's outcome.

### Native Contents updates when an existing tree cannot be read

The matching-blob stop above belongs to this helper's Git Trees writer. It is
not a repository-wide requirement to retrieve a complete tree before using
GitHub's separate, authorized
[Contents create/update API](https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents).
For a prepared UTF-8 content change, the native `github_update_file` operation
takes the current blob SHA and complete replacement text; the caller does not
choose a Git mode. This is a separate publication route, not a successful
`publishGitHubChange` result or a `retained_trees` fallback.

Read the actual tool schemas and retain the earlier failed operation. Create a
unique branch at the observed base commit using
`github_create_branch({repository_full_name, branch_name, sha})`. On that
branch, the observed native arguments are:

```javascript
await tools.mcp__codex_apps__github_update_file({
  repository_full_name,
  branch: branch_name,
  path: existing_path,
  sha: observed_existing_blob_sha,
  content: complete_replacement_utf8,
  message: prepared_commit_message,
});
```

The update returns the resulting commit SHA and `content_sha`; the latter is
the previous-version pin for a later deliberate update to that same file.
The native `github_create_file` takes the same fields except `sha`, requires
an absent path on an existing branch, and returns only the resulting commit
SHA. For an existing-file update plus a new companion, perform these writes
serially and retain both responses. They create separate commits, not one
atomic multi-file change. If a later operation fails, preserve the earlier
commit and reconcile that branch.

Check each returned commit's sole parent against the previously observed
branch head, complete changed-file listings for the expected paths, complete
immutable file contents and blob identities, and the observed final branch head.
For several writes, also compare
the aggregate path set from the original base to the final head. The native
Contents call guards the existing file's blob; it does not accept an
expected branch-head parameter or independently check the entry's mode.
Stop and reconcile unexpected parentage or an
unknown write outcome before any further mutation. Do not resend merely
because a response or readback failed. Then use the task's ordinary PR,
expected-head merge and immutable/current-source readbacks.

These checks establish the observed content and commit chain. They do not
independently establish the prior or resulting Git mode, or compare the entire
repository tree. Record those unperformed checks explicitly. The Contents
endpoint documentation does not explicitly promise preservation of the existing
entry's mode; this route is unsuitable when independent mode proof or a deliberate mode
change is part of the task. Do not convert a positive Contents response into
proof that a path is a regular file, since a read can dereference an
in-repository symlink. Existing permission, source-ownership and product-use
requirements remain in effect.

On 2026-10-04, [ASMFC #31219](https://github.com/woahwhattheheck/commons/pull/31219)
used this route after two transport failures on its exact large parent tree.
One native update changed only the prepared Markdown file; its sole parent,
complete file text/blob, branch head and merged/current-source readbacks
matched. Independent mode and complete-tree verification were not performed.

[Burbank #31220](https://github.com/woahwhattheheck/commons/pull/31220)
then used one native update and one native create on the same isolated branch.
The two returned commits formed the expected sole-parent chain; comparison
against the starting base showed exactly the existing carrier and new companion.
Both complete texts/blobs, branch head, PR and merged/current-source readbacks
matched. This mixed case made no parent-tree request and no independent Git-mode
verification claim. These are observed content publications, not evidence of
mode behavior for every file type.

### Explicit Contents publisher

`publishGitHubContentsChange(tools, change, options?)` automates the native
Contents route above in this same module. Select this export deliberately for
prepared UTF-8 content changes and explicitly requested file deletions. It does
not invoke the Git Trees publisher or convert a failed tree read into a successful
mode check.

```javascript
const {publishGitHubContentsChange} = module.exports;
const result = await publishGitHubContentsChange(tools, {
  repository_full_name: "owner/repository",
  base_branch: "main",
  branch_name: "source/prepared-content-change",
  title: prepared_title,
  body: prepared_body,
  commit_message: prepared_commit_message,
  files: [{
    path: prepared_path,
    expected_blob_sha: observed_previous_blob_sha, // null only for an absent path
    expected_new_blob_sha: prepared_git_blob_sha,  // optional exact source pin
    content: complete_replacement_utf8,
    encoding: "utf-8",
  }],
  merge: true,
  merge_method: "merge",
}, {
  onProgress: progress => store("contents-publication-progress", progress),
});
```

The same `bindings`, `onProgress` and `readback_concurrency` conventions apply.
Available native bindings are checked before mutation; only the create, update
and delete operations selected by the prepared files are required. Blob recovery
is optional.
Keep the source, prepared change, actual response/progress records and operation
identity beside the result. Nothing is written to the filesystem by the helper.

This export accepts at most 300 distinct paths, each with either prepared UTF-8
text or the explicit deletion shape below. It accepts no `mode` field and rejects
`retained_trees`; that option belongs to the separate Git Trees contract.
Existing paths require the observed blob SHA and new paths require a confirmed
absence. An exact complete preimage/content match can be skipped for an ordinary
content change. Deletions are never treated as empty-content no-ops. Missing
large-file text is not treated as an empty file or a proven no-op.

The observable publication sequence is:

1. Read the base ref and check every prepared preimage at that immutable commit.
   Create the new branch there and read its ref. Ref names are escaped by path
   segment in the established `/git/ref/heads/` route, including names with slashes.
2. Perform each required Contents write serially. Native update responses contain
   `{commit_sha, content_sha}`; native create and delete responses contain
   `{commit_sha}`. A deletion supplies the expected old blob as `sha` and sends
   no content. Record the returned commit before following reads.
3. Require each commit to have the previously observed head as its sole parent
   and exactly one expected added, modified or removed path. For a content write,
   match the commit's file blob to the update response when present and read the
   entire prepared text at that immutable commit. For a deletion, require the
   removed blob to equal the expected old blob and confirm the path is absent at
   that immutable commit. Read the branch head before the next write.
4. Check the original-base-to-final-head comparison's complete path set, final
   content blobs or removed old blobs, and native commit counts. The per-commit chain establishes serial
   lineage; the aggregate comparison separately checks the resulting change.
   The 300-path input bound matches GitHub's documented
   [first-page comparison file limit](https://docs.github.com/en/rest/commits/commits#compare-two-commits).
   It does not mistake the paginated `commits` array length for the total.
5. Open the PR at the observed final head. Before a requested merge, read the
   current base ref and require the target preimages/absences still to match.
   Unrelated base movement is allowed. Then use GitHub's expected-head merge.
6. Read every prepared path at the immutable head or merge commit. Compare the
   complete text and blob for content writes, and confirm absence for deletions.
   Retain the task's ordinary literal-current-source and PR metadata readbacks
   as well.

Each Contents write creates its own commit. The branch-head checks detect
unexpected movement; the Contents API itself offers a file-blob guard, not an
atomic expected-parent guard. A concurrent branch edit can therefore be detected
after a write has happened. Stop and reconcile the retained branch in that case.
The pre-merge base check is also an observation: GitHub's expected-head merge
pins the PR head and does not freeze later base movement. Final source readbacks
remain necessary.

Progress includes `serial_writes`, the current `commit_sha`, per-commit source
readbacks, `aggregate_paths_verified`, the current-base check, PR/merge identities
and the final `readback_ref`. `pending_write` is announced before mutation and
records whether a response was received. Exceptions preserve progress and any
typed provider error. Callback failures are recorded separately and do not
repeat a provider action. The helper makes no automatic write retries.

#### Explicit deletion with an observed preimage

Supply this file entry only when deletion of the existing source is authorized:

```javascript
files: [{
  path: observed_existing_path,
  expected_blob_sha: observed_previous_blob_sha,
  delete: true,
}]
```

`delete` must be a boolean when supplied. `delete: true` requires a non-null
`expected_blob_sha` and rejects `content`, `encoding`, `mode` and
`expected_new_blob_sha`, including explicitly present undefined values. An
already absent path is a preimage mismatch; it is not successful deletion.
`delete: false` follows the ordinary content contract. The other publisher
exports do not accept `delete: true`.

A batch may mix content writes and deletions on distinct paths within the same
300-path bound. Only deletion entries require the native `delete_file` binding.
The publisher keeps create, update and delete requests serial, as required by
[GitHub's Contents API](https://docs.github.com/en/rest/repos/contents#delete-a-file).
This is not a rename API: both per-commit and aggregate checks refuse unexpected
rename status or `previous_filename` metadata.

Deletion readback accepts absence only from that specific read's typed native
`NOT_FOUND` response with HTTP 404. Authentication, transport, rate-limit and
other failures remain unresolved reads. Each read keeps its own native response,
including when final readbacks run concurrently. The serial record retains
`removed_blob_sha`; the file record keeps `delete: true` and its original
`previous_blob_sha`, and receives `blob_sha: null` only after absence is confirmed.
Final readback includes `expected_absent`, `observed_absent` and the removed blob.
The current-base pre-merge fence still compares against the original old blob,
not the null postimage.

If deletion returns a commit but a later read fails, retain that commit and the
old blob for reconciliation. Do not reissue the deletion or restart the batch.
The branch-only resume option below also binds each file's deletion marker, and
never resumes after any file write. These checks do not independently verify
file type, Git mode or the whole repository tree; the result reports those
limitations explicitly.

#### Resume a confirmed branch creation before any content write

A narrow recovery option handles an already-confirmed branch creation followed
by a read failure, when no Contents or PR write has begun:

```javascript
const result = await publishGitHubContentsChange(tools, prepared_change, {
  resume_created_branch: retained_branch_only_error.progress,
  onProgress: progress => store("contents-publication-progress", progress),
});
```

The retained progress must identify the same repository/branches and ordered
preimage/source pins and deletion markers, confirm branch creation, have no
pending write, no serial file writes or PR, and retain the base as its head.
The helper re-reads the
prepared versions and requires the actual branch ref still to equal that base
before writing any content. Its new call counts omit `create_branch`, and
`branch_creation: "retained"` distinguishes reuse from a new provider mutation.
Keep the earlier attempt separately; this result does not erase its failure or
claim it created the branch.

This option does not resume partial file publication or an uncertain write.
For those outcomes, retain the branch and reconcile the actual commit/PR state
before any deliberate continuation. Likewise, a PR that is open after a refused
or uncertain merge is an existing publication, not a reason to run this writer
again. Use the observed PR/head and current target preimages for an explicit
native merge continuation, or finish readbacks if it is already merged.
The existing `continueGitHubMerge` export remains specific to its Git Trees
progress and mode checks; Contents progress is not interchangeable with it.

The result explicitly reports `mode_verification: "not_performed"` and
`whole_tree_verification: "not_performed"`. It establishes observed content,
path changes and commit lineage; it does not independently prove entry type,
Git mode preservation or the complete repository tree. Use the Git Trees
route when the task requires an independently verified or deliberately changed
mode. Existing permission and source ownership continue to apply.

#### Actual first consumer

On 2026-10-04, the prepared
[Redmond historical-row handoff, #31224](https://github.com/woahwhattheheck/commons/pull/31224)
used this export for one existing Markdown file beneath the large `p/` directory.

The first candidate created its isolated branch at
`afd01207ceac84d8950e69f1901cccce5f9e5ee1`, then its slash-encoded
`/branches/` read was rejected with native `INVALID_ARGUMENT` before any file
write. The corrected implementation used the established Git ref route.
An actual read confirmed the retained branch still equaled the original base;
the narrow recovery then performed no second branch creation.

The continuation made one update, one PR creation and one expected-head merge.
The returned commit `85c18fe7b04705bf969bc8f1e6b8184a080e3392` had the expected
sole parent and sole changed path. Complete source, update/commit blob,
aggregate paths and final branch head matched. Main had advanced without
changing the target; the pre-merge preimage fence passed. Merge
`bfd2d6154a72a8aad9fadf614af0cc300e3681af` and the literal-current-main file
both matched prepared blob `c1e7e2385b9e687740c059fd3a628e22cafd391e`.
The PR title, body, head, merge and one-path `+4/-0` diff also matched.

This observation covers the actual existing-file update and branch-only
recovery, including unrelated main movement. The earlier Burbank create/update
case above was a manual native operation, not an execution of this export.
No parent-tree fetch, native compiler run, tests, fixture or workflow was involved.
The accepted source documents and earlier consumer publications were not replayed.

### Recover omitted UTF-8 content by blob identity

For a text row still marked `readback_content_unavailable`, the separate native
`github_fetch_blob` reader can retrieve content by the observed blob SHA.
Use the SHA retained from the file read at `readback_ref`, and compare the
complete returned text with the original prepared source:

```javascript
const pending = progress.readback.find(
  row => row.error_code === 'readback_content_unavailable'
);
if (!pending) throw new Error('No omitted text readback is pending');
const file = progress.files.find(row => row.path === pending.path);
const source = preparedChange.files.find(row => row.path === pending.path);
if (!file || !source || (source.encoding ?? 'utf-8') !== 'utf-8') {
  throw new Error('Retain the original prepared UTF-8 source for this path');
}
const response = await tools.mcp__codex_apps__github_fetch_blob({
  repository_full_name: progress.repository_full_name,
  blob_sha: pending.observed_blob_sha,
});
if (response.isError || typeof response.structuredContent?.content !== 'string') {
  throw new Error('The blob reader did not return complete text');
}
const continued = inspectReadback(file, {...source, encoding: 'utf-8'}, {
  // This is the immutable SHA requested above; the blob response supplies content.
  sha: pending.observed_blob_sha,
  content: response.structuredContent.content,
});
store('my-operation-readback-continuation', {
  readback_ref: progress.readback_ref,
  publication_status: progress.publication_status,
  ...continued,
});
text(continued);
```

Load `inspectReadback` from the same trusted helper as `publishGitHubChange`.
Keep each remaining readback outcome explicit; one recovered file does not
complete a batch with other unresolved files. This continuation performs one
read and no publication write.

This route recovered the complete 2,237,659-byte `delta.json` at Commons commit
`3e01b7a7c9e5feb2f9659e67ba909e999214ab6b`. The bytes matched the independently
retained source and its Git blob `77b7cdede94f84346e9020f96c8962bc00818023`;
`inspectReadback` then recorded a full content match. The blob reader is
UTF-8 oriented: the observed binary archive call failed decoding. Do not use
this text continuation as evidence that binary bytes were retrieved.

## Failures and continuation

No provider error is automatically retried. The helper throws
`GitHubPublishError` with `progress`, the original `cause`, and the last native
`response` when one is available. Progress records the stage, call counts,
previous/new file SHAs (unpinned text SHAs become available at readback), tree/commit,
branch creation, PR, merge result, and all
readback outcomes. `publication_status` records a confirmed `pull_request_open`
or `merged` independently of `status`, which stays `incomplete` when readback
fails. `readback_status` is `complete`, `content_unavailable`, or `incomplete`.
The failure also sends the latest progress to `onProgress`, including these
outcomes and the frozen `readback_ref`. It does not include source contents or
the PR description.

```javascript
try {
  const result = await publishGitHubChange(tools, preparedChange, options);
  text(result);
} catch (error) {
  store('my-operation-publish-progress', error.progress);
  text({message: error.message, progress: error.progress});
  // Inspect error.cause / error.response privately when needed.
}
```

Sequential native tool refusals add a bounded `tool_error` object to the thrown error and
failure progress, with the action, a stable error code, an HTTP status when the
native structured response supplies one (or the exact GitHub connector prefix
below reports HTTP 403), and its connector error code when available. The message is generated locally; raw provider bodies are not copied
into progress. Failed parallel readback rows retain their own `tool_error`
objects so their provider facts stay attached to the affected file.

The exported `inspectToolError(action, nativeResponse)` returns the same metadata
for an already-retained native tool error, or `null` for a non-error response. It
performs no provider call. Current specific codes are `base_branch_modified`
for GitHub's explicit HTTP 405 base-move refusal and `transport_closed` for the
native transport failure; other reported errors remain `native_tool_error`.
These describe observations, not retry permission or account-wide capability.

The same `tool_error` also preserves available provider timing fields:
`retry_after` (numeric seconds or a valid HTTP-date), `retry_after_seconds`
(an explicit connector interval), `rate_limit_remaining`, `rate_limit_reset`
(Unix seconds), and `rate_limit_resource`. Fields are omitted when absent or
malformed. Header names are case-insensitive. Only these named fields are inspected; dates and
numbers in a provider message or source body are never treated as retry evidence.
Provider `error_data.headers` takes precedence, followed by `error_data`,
structured headers/metadata, then outer headers/metadata. Explicit connector
seconds remain separate from a provider Retry-After value; when that value is
absent, `retry_after` uses the connector seconds. Retry-After and primary reset
remain separate so the caller can honor both delay floors instead of discarding
a later reset. Existing error codes, raw-response retention and write uncertainty
are unchanged; this extraction does not retry or schedule a provider action.

#### Explicit secondary-limit evidence

The inspector additionally reports `rate_limit_kind: 'secondary'` only when
the provider's structured `error_data.message` is a string of at most 8,192
UTF-16 code units beginning exactly with
`You have exceeded a secondary rate limit.`. A recognized message can also
supply `github_request_id` from its exact final
`please include the request ID ….` support phrase: five uppercase hexadecimal
groups, each 1–16 characters, separated by colons. Differently worded, longer,
or differently formatted messages remain unclassified. An ordinary 403,
`FORBIDDEN`, documentation URL, or primary remaining count alone does not
establish a secondary limit. Missing classification does not establish access
denial, available quota, or absence of throttling.

If structured status is absent, only the anchored connector-generated
`GitHub API error 403: {` prefix can supply `http_status: 403`. Structured
status keeps precedence, and this fallback applies only after the existing
classification leaves `native_tool_error`. Thus a transport error retains its
old null-status/cache behavior; the 405 base-move path is unchanged. A secondary
refusal still has
`error_code: 'native_tool_error'`.

Each newly extracted fact has a `provider_evidence` entry with
`source_path`, zero-based half-open UTF-16 `source_range`, and `format`.
Paths address the original response supplied to the inspector. MCP envelopes
use `structuredContent.error` and `structuredContent.error_data.message`;
the existing direct GitHub envelope uses `error` and `error_data.message`.
Publication error handling passes that original envelope through to the
inspector. Evidence contains positions and format labels, not copied error
bodies. Keep the complete native response, exact native tool arguments and
tool name under separate caller-owned custody keys; `action` is the caller's
label and does not reconstruct an unrecorded request.

This remains an advisory projection. It does not schedule a retry, turn
“a few minutes” into a deadline, infer a reset, declare a global outage or
recovery, or authorize repeating an uncertain write. Retry/reset fields keep
their existing named-field extraction and omission rules.

Two actual retained native errors supplied the first pure projections, once
each, with no failed-route call or fabricated input:

- The complete `github_fetch` error observed at 2026-10-05 10:20:52 UTC was
  projected once with candidate `4d9981af89c4368ad6393751864e76686f7ba65b`.
  Its exact native request arguments were retained separately. The result
  reported HTTP 403, `native_tool_error`, `FORBIDDEN`, secondary limit and
  request ID `F25F:29D1F9:40F425:DA1F8A:6AC379F6`. Evidence addressed
  `structuredContent.error[17:20]` for status and
  `structuredContent.error_data.message[0:41]` / `[341:375]` for kind/ID.
- Source review then restricted fallback status extraction to the existing
  generic-error branch, preserving transport-error cache semantics. The final
  source `421d1697d498b14669b041cd86acdec2028b64d4` projected the separately
  retained 09:42:02 UTC error once. It reported the same kind/codes/status and
  request ID `F78F:33860D:9CDD4:2043AA:6AC370C3`, whose exact ID span is
  `[341:374]` in `structuredContent.error_data.message`. Status/kind paths
  and spans are the same as above. The original serialized native
  request/binding was not recoverable; `retained_ci_error` was only a caller
  label, and that custody gap remains explicit.

Neither native response supplied retry-after, reset, remaining or resource
fields; none was invented. Complete inputs were unchanged, and the first
request object was unchanged. Provider calls for the projections were zero.
Both clocks are external observation metadata, not fields supplied by the
native error. Direct-envelope, ordinary-403, conflicting-status, malformed
and length-bound branches were source-inspected only; no test suite, fixture
or runtime acceptance is claimed.

Pass the retained interval and applicable reset evidence to the existing
[shared provider budget](../integrations/command_center/PROVIDER-ADMISSION.md)
with the original observation ID. Confirm primary quota exhaustion before using
its primary-core option. A 403 alone does not establish a rate limit or permission
to repeat a write.

For `base_branch_modified`, read the named PR and current base first. If the PR
has already merged, continue its readback. Otherwise, confirm its retained head
and reconcile the affected file versions before continuing that same intended
merge with `expected_head_sha`. Keep the existing branch and PR; do not restart
the publication sequence. The publisher does not automatically continue or retry
an error. The separate explicit continuation below packages those native steps.

### Continue the same known pull request

`continueGitHubMerge(tools, preparedChange, previousProgress, options)` finishes
the merge of a pull request already confirmed by this publisher. Invoke it only
when that same merge is authorized. Keep the original prepared source and file
versions, the complete retained progress, and set `merge: true` explicitly. This
also supports an intentional open-PR publication followed by an authorized merge.

```javascript
const {continueGitHubMerge} = require('./host/connected_github_publish.cjs');
const result = await continueGitHubMerge(tools, {
  ...preparedChange,
  merge: true,
}, retainedPublishProgress, {
  onProgress: state => retainOperationProgress(state),
});
```

Load this export from the trusted source in code mode in the same way as the
publisher. It reads the canonical REST pull request through the native `fetch`
binding, using `/repos/{owner}/{repo}/pulls/{number}`. It accepts the same
`options.bindings` override convention; custom callers now supply `fetch` even
for an already-merged PR. The `get_pr_info` binding is not used. It also needs
`fetch_file` for source readback, optional `fetch_blob` for omitted UTF-8, and
`merge_pull_request` only when the PR is still open. It never calls a blob, tree,
commit, branch, or PR writer.

The PR observation remains one GET. Using the canonical response avoids the
connector's normalized snapshot, which has returned an older head after a
confirmed branch write. It does not guarantee immediate convergence of GitHub's
own state. The existing repository/branch/head checks, expected-head merge,
error handling and source readback remain in place; there is no polling or retry.
For a separate read-only observation, see [Connected GitHub PR state](CONNECTED_GITHUB_PR_STATE.md).

The continuation validates that the retained repository, branches, commit, PR
head, and previous file versions belong to the prepared change. The original
prepared contents must remain unchanged; binary identity uses the native new
blob SHA retained by publication. It then reads the named PR from GitHub and
requires the same head commit, base branch, and source branch in that repository.
An already-merged PR goes directly to its actual merge commit's source readback,
recording `merge_skipped: already_merged`; no merge binding or call is needed.

For pinned UTF-8 or base64 source, continuation compares the retained blob SHA
with `expected_new_blob_sha` before any native call. A retained pin cannot be
changed or removed. Older unpinned progress remains supported: an optional new
pin can be added only when a valid retained blob SHA exists and matches. For
unpinned UTF-8, that SHA becomes available after complete content readback; an
omitted or failed earlier readback does not establish the missing identity.
Adding a pin checks identity for this continuation; it does not assert that the
original publication checked a pin before creating its tree. The check compares
SHA values directly, without trusting a saved match flag.

For an open PR, it reads the current base and its exact nonrecursive trees,
using the same bounded new-leaf absence fallback if eligible, then compares
every affected previous blob and file mode. An unrelated base
change can proceed; an affected-file change must be composed deliberately.
It makes one merge call with the original `expected_head_sha` and requested
merge method. A concurrent base or head change may still be refused by GitHub.
That native result is retained without a retry. A later explicit invocation
starts with provider reconciliation again, including checking whether the
previous call actually merged.

The result has `operation: merge_continuation`, fresh per-invocation call counts,
the retained publication identities, any observed `current_base_commit_sha` and
`current_base_tree_sha`, and the same frozen content readback and error metadata
as publication. UTF-8 comparison, optional immutable-blob recovery, binary SHA
comparison, and `onProgress` behavior use the existing contracts. A confirmed
merge remains `publication_status: merged` even if its readback is incomplete.
Retain the prior progress as well when keeping the history of earlier calls;
this result does not combine call counts from separate invocations.

**Do not blindly rerun a failed publication.** A timeout can occur after a
provider accepts a write. Reconcile the named branch, PR, or merge before
continuing with the existing native tools. For example, a readback failure after
`merge_result.merged: true` does not mean the merge failed; finish the readback.
A branch-creation failure does not authorize replacing that branch. An account
or integration-scope error is specific to the observed operation, not a reason
to invent a new login or declare all tools unavailable.

The optional `onProgress` callback receives copied metadata after completed
steps. Its errors are collected in `progress_callback_errors` and do not block
the already-authorized publication. This is an observer, not a dispatch or
approval mechanism. Durable execution/restart is not built in; retain progress
using the existing host and reconcile provider truth after interruption.

### Retain complete bytes across a session handoff

The `store()` examples retain values in the caller's current runtime. A key,
successful callback or scratch path does not establish that another isolate can
retrieve those bytes after replacement. Progress deliberately omits source,
descriptions and input content; hashes and filenames cannot recover them.

When an already-authorized operation needs portable custody, preserve its
complete prepared command and every required input byte in an existing durable
carrier appropriate to the payload's visibility. Review that payload for secrets
and private data before using a Git repository. Source-publication authority
does not authorize publishing private runtime inputs. Retain the original bytes
and encodings, immutable source/input identities, expected versions and heads,
existing guards, and the actual unattempted, held or executed state. Read back
the complete payload at immutable locations and give the next owner those
locators; a branch name or a list of hashes alone is insufficient.

Keep this byte custody separate from the publisher's progress and confirmed
provider outcomes. A durable command does not establish runtime compatibility,
execution, allocation or acceptance. On interruption, recover the original
prepared contents and reconcile the existing operation rather than starting
publication again. If the exact command or required inputs are unavailable,
record the specific custody gap and keep their transport/execution pending;
do not reconstruct missing bytes from a summary or substitute new inputs under
the old identities. Continue independent authorized work while that gap remains.

### Keep native journal locators on the private receipt

Source/result custody and native-envelope discoverability are different. In
one actual completed publication, the complete prepared specification, progress
and result survived compaction, but no known key located its original
`create_tree` response. They could not establish that response's fields.
A later, distinct publication retained a discoverable journal; its exact native
`create_tree` envelope supplied only a tree SHA, with no leaf entries, modes,
blob identities or completeness flag. That fresh observation did not recover
the older envelope and did not justify removing the created-tree verification
reads.

Keep the existing caller's private request/raw-response journal. Give it one
stable, operation-specific directory key before dispatch, and retain that key
in the operation's handoff and final receipt. A small metadata directory can
record the operation ID, exact entry prefix, suffix/key format, and highest
assigned call index. Each indexed metadata entry identifies the actual tool,
request key, returned-response or thrown-error key when present, and custody
state. It need not duplicate request arguments or returned bodies.

Assign each call's index synchronously before awaiting its binding, so parallel
readbacks retain independent keys. Bank the exact arguments before dispatch and
the returned envelope before parsing it. A returned MCP error is still a
returned envelope; a thrown binding has an error locator and no invented native
response. Mark a locator as stored only after that store succeeds. An assigned
index alone does not establish dispatch, settlement or successful custody.
Keep journal-storage failures distinct from native errors and preserve the
original native return/error when available; a post-write custody failure is
never authority to repeat the writer.

For example, attach this bounded locator projection to the existing private
completion receipt, using values from the actual caller directory:

```javascript
const privateReceipt = {
  publication: result,
  native_journal: {
    directory_key: journal.directory_key,
    entry_prefix: journal.entry_prefix,
    assigned_count: journal.assigned_count,
    key_suffixes: journal.key_suffixes,
    storage_scope: 'current_runtime; durability_not_established',
  },
};
store(operationReceiptKey, privateReceipt);
```

Attach the same locator projection when retaining the existing outer
`GitHubPublishError`, its progress, cause and response. This is caller receipt
metadata, not a mutation of publisher progress or a new helper API. Keep
separate final/audit reads under their own identified directory so they are
not silently counted as publisher calls. If an existing journal uses a
different naming format or an explicit list of keys, retain that exact format
or list; do not rename or reconstruct historical keys from a convention.

Print only the selected metadata needed for coordination. Do not print the
directory wholesale if its existing entries also contain arguments, nor copy
raw envelopes, full source, credentials or private provider payloads into a
public receipt or repository. Directory size can be kept constant by retaining
a prefix, key format and index range; inspect only the needed existing entry
metadata when selecting a response.

Known keys improve discoverability only while their stored values remain
available. They are not a durable backup, cross-agent storage guarantee or
provider evidence. Where portable byte custody is already needed, use the
authorized carrier described above and preserve its exact locator privately.
If an envelope is unavailable, record the narrow gap; do not substitute the
request, a summary, a different publication's response, or another provider
call. This guidance adds no automatic logging, acquisition, retry, permission
gate or whole-operation acceptance claim.

## Advance an existing contribution pull request

Use `advanceGitHubContribution` for an already-authorized continuation on the
original contribution branch. It does not create a branch or PR, edit the PR
body, merge upstream, or rewrite prior commits. The new commit's sole parent is
the exact observed contribution head.

```javascript
const {advanceGitHubContribution} = require('./host/connected_github_publish.cjs');
const result = await advanceGitHubContribution(tools, {
  repository_full_name: 'CONTRIBUTOR/FORK',
  pull_request_repository_full_name: 'UPSTREAM/REPOSITORY',
  pull_request_number: existingPullRequestNumber,
  branch_name: existingContributionBranch,
  base_branch: observedUpstreamBaseBranch,
  expected_head_sha: observedContributionHead,
  expected_base_sha: observedUpstreamBase,
  commit_message: preparedCommitMessage,
  files: preparedFiles,
}, {onProgress: state => retainOperationProgress(state)});
```

The two repositories may be the same. Branch names may also be the same when
the contribution is in a fork. Both SHAs and both branch names are required:
they identify the PR context that the caller actually inspected. `files` uses
the existing complete-content, previous-blob, encoding, optional new-blob pin,
and mode contract. Supply no title, body, merge options, or force option to this
operation. PR description publishing and external acceptance remain separate
operations with their own existing permission boundaries.

The native bindings are `fetch`, `fetch_file`, `create_tree`, `create_commit`,
and `update_ref`, plus `create_blob` when base64 or a source pin needs it, and
optional `fetch_blob` for omitted UTF-8 content. The generic reader accesses the
full native PR, Git commit, tree and branch-ref resources. It uses the same
`options.bindings`, `onProgress`, `GitHubPublishError`, and bounded native-error
diagnostics as the other exports.

The operation performs these steps:

1. Read the original PR and compare its repositories, branches, open/unmerged
   state, head and base with the supplied observations.
2. Read that immutable head's commit and complete recursive tree. Compare every
   affected previous blob and regular-file mode before creating any object.
3. Create the prepared tree and a commit with that head as its sole parent.
   Pinned UTF-8 and base64 use the existing native blob checks; unpinned UTF-8
   stays in one inline tree request. An identical tree returns
   `no_source_changes` without a commit or ref update.
4. Read the created commit and complete recursive tree. Require the intended
   sole parent, tree and exact commit message. Compare every unrequested leaf
   and its mode/type, as well as directories outside the prepared paths'
   ancestors. Record `tree_comparison.changed_paths` and
   `unchanged_leaf_count`; do not copy the complete tree into progress.
5. Read every prepared file at that immutable commit. UTF-8 must match the
   complete submitted text and the tree's blob SHA. Base64 retains the existing
   native-created-blob identity comparison. Optional immutable blob recovery
   handles omitted text as in ordinary publication.
6. Read the PR and original branch ref again. Both must still identify the
   observed old head; the PR must remain open/unmerged at the observed base.
   Persist the known commit and an uncertain ref-update state, then make one
   native `update_ref` call with `force: false`.
7. By default, read the same PR and ref again. Both must identify the prepared commit.
   The earlier content comparison remains bound to that immutable commit; the
   helper does not duplicate those file reads. The final PR state and
   `base_changed` observation remain explicit.

This is a fresh-head comparison plus GitHub's nonforce update, not an atomic
compare-and-swap API. The exposed ref writer has no expected-old-head argument.
A concurrent divergent branch update can cause GitHub to refuse the write.
A concurrent base movement after the last comparison can appear in the final
observation. A PR closure or merge by someone else is reported as observed;
this helper never requests either action. No failed or inconclusive operation
is automatically retried, and no previous ref is restored.

Both recursive tree responses must be complete and identify the requested
immutable tree. A truncated, malformed, oversized, or unavailable tree stops
the operation. This full unchanged-path comparison does not infer coverage
from partial listings and does not use the new-leaf fallback described for
`publishGitHubChange`. Before the first object write, an unreadable parent
therefore leaves the original branch untouched. A later failure may leave
unreferenced prepared objects; their known identities remain in progress.

Progress has `operation: contribution_advance`, the original PR and repository
identities, `parent_commit_sha`, `parent_tree_sha`, prepared `tree_sha` and
`commit_sha`, file versions/modes, immutable readback and per-call counts.
Each bounded current-head observation records the PR head/base/state and
branch-ref SHA. Source strings and commit-message contents are not copied.

| Outcome | Meaning |
|---|---|
| `status: contribution_branch_updated` | Both final reads identify the prepared commit, and immutable source readback is complete. |
| `publication_status: update_confirmed` | The native ref writer returned success; a later readback may still be incomplete. |
| `publication_status: unknown` | The ref request was about to be sent or did not return a confirmed result. Reconcile provider state before another write. |
| `ref_update_state: not_converged` | Current PR/ref observations do not both identify the prepared commit. Their actual SHAs remain available. |
| `status: no_source_changes` | No contribution commit or ref update was needed; any earlier native blob/tree creation is still counted. |

### Defer only the final head observation

An existing contribution can opt into `defer_head_observation: true` in the
`advanceGitHubContribution` options. Omission or `false` preserves the complete
default path, including the two final PR/ref reads. A supplied non-boolean
value is refused before provider calls. This option belongs only to advancement;
it does not change the read-only reconciliation or head-observer exports.

```javascript
const pending = await advanceGitHubContribution(tools, preparedContribution, {
  defer_head_observation: true,
  onProgress: state => retainOperationProgress(state),
});
retainOperationProgress(pending);
```

The option can return early only after all immutable commit/tree/full-file
checks, the current old-head comparison, and one successful native
`update_ref` with `force: false`. Its result separates these facts:

| Field | Meaning |
|---|---|
| `status: contribution_head_observation_pending` | This advancement stopped before its final current-head reads. |
| `stage: head_observation_deferred` and `head_observation_status: deferred` | Neither final PR nor final ref GET was requested. |
| `publication_status: update_confirmed` and `ref_update_state: confirmed` | The native ref writer acknowledged its one update. |
| `commit_verified: true`, complete `tree_comparison` and `readback_status: complete` | The same immutable source evidence required by the default path is retained. |
| `head_observation_target` | The seven validated PR/ref/expected-commit fields for the separate head observer. |

The retained `pull_request` and earlier `observations` still describe reads
before the write; they are not observations of the new head. No
`contribution_branch_updated` or current PR convergence is claimed. Keep the
pending progress and source proof. When the remaining head observation is due,
call the existing reader once with the supplied target:

```javascript
const observation = await observeGitHubContributionHead(
  tools, pending.head_observation_target,
  {onProgress: state => retainHeadObservation(state)}
);
retainHeadObservation(observation);
```

Only use that target when the returned status is
`contribution_head_observation_pending`; a `no_source_changes` result has no
new commit or deferred target. The observer makes the two current PR/ref reads
and reports its own observed heads, base movement, PR state and errors.
Its source/publication verification remains `not_performed`: keep it alongside,
not in place of, the separately retained immutable proof and writer outcome.
The caller decides how to report their combined evidence. An inconclusive
head observation does not authorize another write.

An unconfirmed or failed ref update still throws with its existing uncertain
state before the deferred return is reachable. Use the unchanged reconciliation
procedure below; this option adds no retry, recovery write, sleep, poll, timer,
or atomic expected-old-head guarantee. It does not affect the ordinary
new-branch/PR publisher or its merge continuation.

This option removes two immediate GETs from the advancement itself. It does
not remove the later observer's two reads or guarantee that GitHub's PR index
has converged by then. It is useful when the caller already has other required
work between a confirmed write and its final head observation, particularly
where immediate reads have repeatedly returned different PR/ref heads.

### Reconcile a retained contribution without writing

After an uncertain update or incomplete readback, retain the same complete
prepared change and all progress. Call `reconcileGitHubContribution` explicitly:

```javascript
const {reconcileGitHubContribution} = require('./host/connected_github_publish.cjs');
const result = await reconcileGitHubContribution(
  tools, preparedContribution, retainedContributionProgress,
  {onProgress: state => retainReconciliationProgress(state)}
);
```

This export requires a known prepared commit and tree. It does not require or
call any writer binding. It checks the retained operation identity and previous
versions/modes, re-reads the original parent and prepared commit/trees, compares
the complete prepared text, and reads the current original PR/ref. Requested
source pins cannot be changed or removed; adding a pin needs a matching
retained blob identity. Base64 uses the original native-created blob identity,
so the caller must retain the original binary input rather than substituting
new base64 under an old progress record.

If both current heads equal the prepared commit, the result is
`contribution_branch_updated`. If both equal the original parent, it is
`contribution_branch_not_updated` with
`publication_status: previous_head_observed`; the prepared objects exist,
but this read-only call did not publish them. Any other combination stays
incomplete with the actual observations. Current upstream base movement is
recorded without blocking these read-only checks. Historical confirmed/uncertain
writer status remains in `previous_publication_status` and
`previous_ref_update_state`.

There is deliberately no automatic write continuation. When a later deliberate
publication is appropriate, use the existing native tools with the retained
commit and freshly reconciled branch/PR context. Do not rerun the object
creation path, create a replacement PR, force the branch, or infer successful
maintainer checks from source publication. Reconciliation can finish a known
source/readback outcome; it cannot establish deployment, sponsor acceptance or
test execution.

## Observe only the remaining contribution heads

`observeGitHubContributionHead` reads the current PR and original branch ref
without repeating an accepted immutable source comparison. Use it when the
caller retains the earlier commit/tree/full-file verification and write result
and needs only these remaining observations. It is also a read-only view of a
specified existing PR/branch; it never infers that any prior publication occurred.

```javascript
const {observeGitHubContributionHead} = require('./host/connected_github_publish.cjs');
const observation = await observeGitHubContributionHead(tools, {
  repository_full_name: retainedContribution.repository_full_name,
  pull_request_repository_full_name: retainedContribution.pull_request_repository_full_name,
  pull_request_number: retainedContribution.pull_request_number,
  branch_name: retainedContribution.branch_name,
  base_branch: retainedContribution.base_branch,
  expected_commit_sha: retainedContribution.commit_sha,
  expected_base_sha: retainedContribution.expected_base_sha,
}, {onProgress: state => retainHeadObservation(state)});

retainHeadObservation(observation);
// Keep the native response bodies privately; print only the needed projection.
show({
  status: observation.status,
  source_verification: observation.source_verification,
  heads_agree: observation.heads_agree,
  base_changed: observation.base_changed,
  pull_request: observation.observations.pull_request,
  branch_ref: observation.observations.branch_ref,
  errors: observation.errors,
});
```

All seven target fields are required. `expected_commit_sha` is the prepared
commit whose current visibility is being checked, rather than the old
`expected_head_sha` used to authorize an advancement. The repositories, PR
number, branches and lowercase 40-character SHAs are validated before any
provider call. Extra target fields, including source files or retained writer
state, are refused so they cannot be mistaken for evidence this reader checked.

The reader starts exactly two concurrent native `fetch` calls after validation:
the upstream PR resource and the contribution repository's branch-ref resource.
It reuses the publisher's native-error decoder and contribution PR identity
checks. It requires the ref response to identify the requested short branch
and a commit object. Both outcomes are consumed even when one fails.

| Status | Meaning |
|---|---|
| `expected_head_observed` | Both valid resource responses identify `expected_commit_sha`. |
| `not_converged` | Both responses are valid, but at least one identifies another commit. Their actual SHAs are retained; no cause is inferred. |
| `incomplete` | At least one fetch, response decode, or resource-identity check failed. Successful independent observations and per-resource errors remain available. |

`source_verification` and `publication_verification` are always `not_performed`;
`writes` is always zero. The function does not return the full publisher's
success status, alter the retained publication record, or prove commit
parentage, tree contents, file bytes, authorization, CI, merge or acceptance.
A matching head can accompany a closed/merged PR or a changed base. The observed
PR state and `base_changed` flag remain explicit; base movement does not change
the meaning of the head comparison. The base flag is retained even when only
the PR read succeeds; agreement flags remain null until both resources are valid.

`requests` records the two exact URLs. `responses.pull_request` and
`responses.branch_ref` preserve each original returned tool envelope, including
a returned native error; a thrown call has no invented response. `observations`
contains only validated resource identities, and `errors` records the failed
resource separately. The raw PR response can contain a long body, so two calls
are an operation-count bound, not a response-byte limit. `snapshot: false`
records that independent GitHub reads are not an atomic snapshot.

Only `options.bindings.fetch` and `options.onProgress` are supported. There is
no writer binding, retry, sleep, poll, local process or new timeout policy;
native connector deadlines apply. Invalid targets/options or a missing binding
throw `GitHubPublishError` with zero-call progress. Read/identity failures return
`incomplete` after both outcomes settle. Progress callback errors are retained
without changing the read result.

Keep using `reconcileGitHubContribution` when the immutable source comparison
itself is missing, uncertain, or needs to be established again. Its complete
source/tree reconciliation remains unchanged.


## Recover selected immutable source after losing transient state

`recoverGitHubFiles(tools, input, options)` is a read-only source-custody API.
Use it when a real recovery or delivery needs the complete original source of
explicitly selected files. It reuses the publisher's native envelope/error
handling and complete parent-tree path reader, and the existing
[Git blob identity module](CONNECTED_GIT_BLOB_IDENTITY.md). It does not infer
a prepared change, PR title/body, acceptance record, or an entire operation
from whichever commit happens to be the latest.

Before a long publication, record the stable repository/branch locator in the
original activity and retain the complete prepared source through an authorized
durable carrier. The atomic publisher banks its tree and commit before creating
the source branch and PR. Contents publication may leave several serial commits;
the last commit's changed-file list is not the whole operation. A transient
store key, progress record or source hash cannot reconstruct missing bytes.
This reader can recover bytes that actually reached Git; it cannot recover
source that was never banked.

```javascript
const recovered = await recoverGitHubFiles(tools, {
  repository_full_name: repository,
  operation_id: originalOperationId,
  commit_sha: observedFullCommitSha,
  files: selectedPaths.map(path => ({path})),
}, {git_blob_identity: verifiedIdentityModule.gitBlobIdentity});

// Retain the full result privately; display only the required metadata.
show({
  status: recovered.status,
  commit: recovered.commit,
  coverage: recovered.coverage,
  files: recovered.files.map(file => ({
    path: file.path, status: file.status, blob_sha: file.blob_sha,
    mode: file.mode, bytes: file.bytes, error: file.error
  })),
  calls: recovered.calls,
  error: recovered.error,
});
```

Supply exactly one selector:

- `commit_sha`: a complete lowercase 40-character immutable commit SHA.
- `branch_name` plus `expected_head_sha`: a short branch and its observed full
  commit SHA. The reader fetches that exact ref once, records both expected
  and observed heads, and stops before source reads if they differ. All later
  reads are pinned to the accepted commit, even if the branch subsequently moves.

`operation_id` is a caller-supplied stable identifier of 1–160 ASCII letters,
digits, underscores, periods, colons or hyphens. It is a custody label, not
independently verified operation history or authorization. `files` must contain
1–64 distinct canonical repository-relative paths, each at most 1,024 UTF-16
code units, in the caller's chosen order. A file may include an
`expected_blob_sha`; when present, it must match the blob observed at that path.
Null pins, source content, encoding, deletion and mode input are not accepted.
No selected path may also be a selected parent directory.

The reader gets the immutable Git commit, its parent SHA list and root tree,
then walks only the parent trees needed for the selected paths. Each tree must
be complete, identify the expected SHA and contain valid unique entry names,
types, modes and blob references. Shared parent trees are read once. An absent
entry is recorded only from a complete parent tree. Symlinks, directories and
submodules are refused as source files; only regular modes `100644` and `100755`
are recovered. Modes are native tree observations anchored to the commit, not
caller guesses or an independently rehashed Git tree object.

For each file, one full native `fetch_file` at the immutable commit must return
the same blob and UTF-8 content. The supplied identity function measures and
hashes the entire exact string once. Its Git blob SHA and any native byte size
must agree with the tree; line endings and Unicode spelling remain unchanged.
Empty text is accepted only for the real empty Git blob. A missing body is
`RECOVERY_CONTENT_UNAVAILABLE`, not an empty source. There is no blob fallback,
base64 decoding, snippet assembly, symlink following or second source route
after a failed read.

### Connected V8 and dependency custody

The old publisher exports remain self-contained. The recovery API alone uses
`./connected_git_blob_identity.cjs`. In CommonJS, it lazily requires that module
only when `options.git_blob_identity` is absent. Connected V8 can supply the
already verified function explicitly, without Node, filesystem or network
imports:

```javascript
const identityBox = {exports: {}};
new Function('module', 'exports', completeIdentitySource)(
  identityBox, identityBox.exports);
const publisherBox = {exports: {}};
new Function('module', 'exports', completePublisherSource)(
  publisherBox, publisherBox.exports);

const recoverGitHubFiles = publisherBox.exports.recoverGitHubFiles;
// Pass identityBox.exports.gitBlobIdentity in options.git_blob_identity.
```

Read and identify both complete module sources before using them. The existing
identity module's accepted Git blob is
`132074b6393afd73a921939ad39789f3a6b38ce5`; it exports
`gitBlobIdentity(string) -> {bytes, git_blob_sha}` and rejects unpaired UTF-16
surrogates. An injected function is a trusted caller dependency: checking that
it is callable cannot independently prove its implementation. The reader does
not acquire source modules, credentials or a substitute runtime.

Only `fetch` and `fetch_file` native bindings are required, optionally mapped
with `options.bindings`. No writer binding is used. Invalid inputs, limits,
missing bindings or a missing identity function throw before provider reads.
The options object accepts only `bindings`, `git_blob_identity` and `limits`.

### Bounds, partial custody and evidence

| `options.limits` field | Default | Maximum |
|---|---:|---:|
| `max_calls` | 128 | 512 |
| `max_file_bytes` | 2,097,152 | 16,777,216 |
| `max_total_bytes` | 8,388,608 | 67,108,864 |
| `max_metadata_chars` | 2,097,152 | 8,388,608 |
| `max_tree_entries` | 10,000 | 100,000 |
| `max_elapsed_ms` | 60,000 | 300,000 |

Each limit is a positive safe integer. Metadata characters and tree entries
are cumulative across decoded native JSON resources. Byte limits govern
verified recovered content, with native tree sizes checked before content
reads when available. The elapsed limit is checked between steps and after
reads; it cannot cancel an in-flight native call. Connector deadlines still
apply. These are processing/admission bounds, not guarantees on provider
response size, transient transport memory, or total wall time.

Reads are serial and stop at the first read, identity, unsupported-file or
budget failure. No retry, poll, sleep, branch update or alternate transport is
performed. `status: 'recovered'` means every requested file has complete,
hash-verified content. Otherwise `status: 'incomplete'` preserves all already
recovered files, the current error, any observed absence, and explicit pending
paths. Each successful file contains `content`, `encoding`, `bytes`, `blob_sha`,
`mode`, `type`, `commit_sha`, `git_blob_sha_verified: true`, and `tree_path`.
The latter identifies every observed directory tree and selected entry on the
immutable path. `commit` includes the observed commit, immediate parent SHAs
and root tree; parents are recorded, not recursively inspected.

`reads` retains exact requests and returned tool envelopes before decoding,
including a provider error, or the thrown error when no response exists.
Do not print the entire result: raw envelopes can contain full source, commit
messages and provider diagnostics, and can exceed accepted content budgets.
`preimage_fallbacks`, if present after a transport failure at an immediate
parent tree, records the reused path reader's unavailable diagnostic only:
its one-line fallback is deliberately disabled and performs no provider call.
Actual calls are enumerated in `reads` and `calls`.

The result always reports `writes: 0`, `snapshot: false`,
`publication_verification: 'not_performed'`,
`execution_verification: 'not_performed'`, and
`whole_operation_custody: 'not_inferred'`. Immutable path/blob agreement is
source custody. It does not establish current branch freshness, writer outcome,
PR metadata, validation, merge, deployment or ownership clearance. Keep prior
write errors and acceptance records separately; source recovery does not
authorize replaying an uncertain writer.

This addition follows actual loss of older in-memory publication/source
journals while newer keys survived. Its branches were source-inspected and
its publication was read back; the recovery API itself was not invoked on old
accepted packets, fixtures or fabricated provider responses. Runtime
acceptance remains unperformed until a real subsequent recovery/delivery
needs this API.

A distinct actual subsequent atomic publisher consumer, Commons PR #31485,
published five pinned UTF-8 files (18,407 bytes) in 20 helper calls: five
metadata/tree fetches, five blob creates, one tree, one commit, one branch,
one PR, one merge and five complete merge-file reads. The base did not change.
Nine separate main/PR/path reads were outside that count. This is an observed
different packet, not a replay, like-for-like benchmark or execution of the
changed-base preimage branch.

## Predict the exact inline tree from complete base trees

A caller preparing a genuinely new Git-data publication may opt into local
created-tree identity verification:

~~~javascript
const result = await publishGitHubChange(journaledTools, preparedChange, {
  inline_pinned_utf8: true,
  inline_tree_identity: true,
  onProgress: retainProgress,
});
~~~

This option belongs only to `publishGitHubChange`. It must be boolean and requires
`inline_pinned_utf8: true`, UTF-8 content and an independently established
`expected_new_blob_sha` on every selected file. The existing regular-file mode,
path, preimage and file/ancestor collision checks remain in force. Mixed,
unpinned or base64 inputs do not satisfy this particular format contract;
they retain the existing publication routes when this option is not selected.
This mode does not install a caller permission or ownership gate.

Omitting `inline_tree_identity` or setting it to false retains the existing
created-tree GET verification path for pinned inline text. Selecting it is a
deliberate pre-publication choice. An unavailable input, mismatched identity,
unsupported entry or budget failure stops the selected operation; the helper
does not switch routes, repeat a write, fetch a substitute postimage or retry.

### Complete preimages and local postimages

The ordinary precheck already observes the named base commit and root tree and
follows complete, nonrecursive tree entries along every changed file path.
In the new mode, those successful whole-directory observations are copied into
a private path-bound map, including SHA-cache hits at another directory path.
An explicitly supplied `retained_trees` object remains eligible only under its
existing full-byte hashing and native-parent binding rules. Neither original
native arrays nor the shared SHA-keyed reader cache is mutated.

Every captured directory is serialized and passed through the existing strict
retained-tree parser, which hashes its complete bytes and requires equality
with the observed parent-bound tree SHA. This both checks the serialization
premises and retains exact modes and object IDs for unrelated entries. Separate
directory paths receive independent mutable copies even when their original
tree SHA is identical.

An existing directory without a complete entry set cannot participate.
The initial precheck therefore disables its per-file preimage fallback in this
mode: a truncated/unavailable tree stops before that narrower read, because it
could not supply the missing directory. The default path keeps its existing
fallback behavior. A genuinely absent child directory is different: absence
must be demonstrated by its complete, SHA-verified parent's entry set, after
which the local postimage creates that directory from an empty entry set.

The publisher applies the selected regular-file modes and pinned new blob IDs
to these copied entries. It then computes changed directory identities from
the deepest directory up to the root. Untouched children keep their original
object IDs and modes; their contents need not be acquired. New descendant
directories are included in that same bottom-up calculation. A changed file
cannot also be an ancestor of another changed path.

This produces one expected created-tree SHA before the native tree write.
The actual `create_tree` request remains the existing inline-content request
against the observed base tree. Its native acknowledgement supplies the
created SHA; echoed request fields or an assumed response entry list are not
used as evidence. A differing SHA stops before commit, branch or PR creation.
The tree object itself may already exist, and the original response/progress
must remain retained. Only an equal SHA qualifies all prepared leaf paths,
types, modes and pins and permits the existing commit/branch/PR steps.

### Exact byte premises and bounds

This is Git's SHA-1 object format, matching the publisher's existing lowercase
40-hex object-ID contract. It does not support a SHA-256 repository format.

- Each immediate entry uses canonical mode text, one ASCII space, its strict
  UTF-8 name bytes, NUL, then the 20 binary bytes of its object SHA.
- A native directory mode `040000` is serialized as Git's `40000`. Supported
  untouched modes/types are tree `40000`, regular blobs `100644`/`100755`,
  symlink blob `120000` and gitlink commit `160000`. Existing symlinks, gitlinks
  and directories still cannot be replaced as regular-file source changes.
- Names are nonempty immediate components, not `.` or `..`, with no slash or
  NUL. Unpaired Unicode surrogates, invalid UTF-8 reconstruction, duplicate
  names, inconsistent type/mode pairs and unknown modes stop the operation.
  No case folding or Unicode normalization is performed.
- Git order compares bytes through the common prefix, then uses NUL for a
  non-tree or `/` for a tree at end-of-name. JavaScript string ordering and
  locale collation are not used.
- The object SHA hashes `tree`, an ASCII space, the decimal body byte length,
  NUL and the body. It is not a hash of JSON metadata or a blob-framed hash.
  The existing `retainedTreeSHA` implementation and strict parser are reused;
  no additional cryptographic implementation or external callback is added.

The fixed local bounds are 256 touched directory paths, 200,000 immediate
entries per directory, 16 MiB per encoded tree body, and 64 MiB of encoded tree
bodies in total across base verification and computed postimages. A name must
fit 4,096 UTF-8 bytes; its UTF-16 input length is also bounded before encoding.
Limits are checked before admitting the corresponding local object/body.
These are local representation limits, not cancellation or transfer limits
on an already in-flight provider response.

The primary references are Git's
[object framing and tree explanation](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects),
the [git-mktree manual](https://git-scm.com/docs/git-mktree), and the byte comparator
in [Git tree.c at babb4e5d7107ba730beff8d224e4bcf065533e0b](https://code.googlesource.com/git/+/babb4e5d7107ba730beff8d224e4bcf065533e0b/tree.c).
The separately failed sibling mktree.c acquisition is not evidence for this
implementation and was not retried.

### Receipt and unchanged downstream checks

Progress records `inline_tree_identity: true` and uses these additional
`inline_tree_verification` fields:

- `method: 'local_git_tree_identity'`;
- the observed `base_commit_sha` and `base_tree_sha`;
- `expected_tree_sha`, the native `tree_sha`, and `tree_identity_matches`;
- `base_trees` summaries with directory path, SHA, byte/entry counts and
  successful object-hash verification;
- `computed_trees` summaries with directory path, previous SHA or null for a
  new directory, computed SHA and byte/entry counts;
- `body_bytes_encoded`, the cumulative local serialized-body bytes, and
  explicit fixed `limits`;
- `fetch_calls: 0`, referring only to additional created-tree verification
  GETs, not the publication's ordinary preimage reads;
- `checked_paths` and `complete`, filled only after the native root SHA matches.

Progress contains no whole entry arrays, unrelated leaf names or source bodies.
Local failures retain the existing partial progress and cause through
`GitHubPublishError`; uncertain native outcomes retain the original writer
semantics. There is no automatic recovery or fallback after a failed dispatch.

The expected SHA applies to the created branch tree. It is not an equality
claim about a later merge tree after another change advances the base.
Current-base/preimage checks before merge, expected-head merge protection and
the existing merge-continuation contract remain unchanged. All complete
immutable source-content readbacks still run and compare the prepared bytes
and native blob pins. Independent caller hashing and separate current-main
observation/readback remain their existing responsibilities.

### Observed opportunity and first-use scope

The completed E366 publication required four created-tree verification GETs
for its fourteen pinned inline entries within twenty-nine publisher calls.
Its create-tree acknowledgement supplied only a SHA. That completed operation
was not reconstructed or replayed to develop this change.

For a future eligible operation, the existing traversal would require T
created-tree GETs for its actual selected paths; this mode replaces those
additional reads with local encoding and hashing. It does not remove ordinary
base-tree reads, source banking or immutable content readbacks. T is a modeled
avoided-call count unless the genuinely new operation's retained receipt
supports that comparison. Local CPU/memory cost is real; no elapsed-time,
wire-byte or general speedup claim follows from removing calls.

At source authoring, the new path had no executed consumer, synthetic fixture,
test suite, old-tree replay or accepted-publication replay. Its intended first
consumer is the genuinely new publication of this source and guide, using
the source banked before that operation and retaining all native envelopes.
The publication receipt and release carry any actual first-use outcome.
Unsupported-name/mode/limit, mismatch, missing-tree and error branches remain
unexecuted unless separately identified by a genuine future observation.
