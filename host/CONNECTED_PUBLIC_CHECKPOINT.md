# Bank selected public artifacts and a recovery manifest

`host/connected_public_checkpoint.cjs` exports
`bankPublicGitHubCheckpoint(tools, input, options)` and
`PublicCheckpointError`. It banks explicitly selected public UTF-8 strings as
Git blobs, checks every native acknowledgement against the existing independent
identity function, then banks a compact recovery manifest last.

The concrete need is the fleet's observed in-memory state loss. Known immutable
blob locators allowed source and research checkpoints to be recovered afterwards;
missing locators could not be reconstructed honestly. The operation recorder
preserves caller-owned request/result/error custody but does not bank public
artifact bytes. The existing publisher's `recoverGitHubFiles` recovers paths
from a commit or a branch and also does not create these pre-publication
checkpoints. Both existing implementations remain unchanged.

This helper does not execute, validate, decode, or regenerate artifact contents.
It creates no tree, commit, branch, PR, release, or publication claim. It does not
discover old work or recover private Slack/mail records.

## Interface

Input is a plain data object:

| Field | Contract |
| --- | --- |
| `repository_full_name` | Caller-selected public checkpoint repository in owner/name form. |
| `checkpoint_id` | Nonempty caller label, at most 160 UTF-16 code units. No uniqueness or reservation is inferred. |
| `stage` | Nonempty caller stage label, at most 160 code units; not a computation-status assertion verified by the helper. |
| `artifacts` | One through 64 explicitly selected artifact descriptors. |
| `lineage` | Optional array of at most 32 public provenance descriptors. |
| `previous_manifest_sha` | Optional exact Git SHA-1 linking a previous checkpoint; caller-reported, not fetched or authenticated. |

Each artifact is `{path, role, content, expected_blob_sha?}`:

- `path` is a canonical relative logical artifact path, at most 1,024 code units.
  It identifies an entry in the manifest, not an existing repository tree path.
  Duplicate artifact paths are rejected.
- `role` is a nonempty caller label of at most 80 code units, such as source,
  input, plan, result, reader evidence, or publication spec. The label does not
  cause special parsing or execution.
- `content` is the complete exact UTF-8 source string to bank. Empty content is
  valid. The verified identity function rejects unpaired UTF-16 surrogates.
- `expected_blob_sha`, when supplied, must equal the independently computed
  identity before any provider call.

Each lineage descriptor requires `repository_full_name` and optionally permits
`pr_number`, `commit_sha`, `ref`, `path`, `blob_sha`, `bytes`, and
`observation`. PR numbers are positive safe integers, byte counts nonnegative
safe integers, commit/blob values exact 40-character lowercase Git SHA-1 values,
refs at most 256 code units, paths canonical relative paths, and observations
nonempty strings of at most 1,024 code units. Use observations to retain real
limits, such as a source read at a default ref without an observed commit.
The helper does not turn a default-ref observation into an immutable commit.

Options are:

- `git_blob_identity`: required existing verified `gitBlobIdentity` function.
  Commons identity source blob
  `132074b6393afd73a921939ad39789f3a6b38ce5` supplies this function. Its actual
  source path is named by the existing recovery implementation as
  `host/connected_git_blob_identity.cjs`. No cryptographic implementation is
  duplicated in this helper.
- `binding`: optional already-discovered binding name; default
  `mcp__codex_apps__github_create_blob`. This selects the binding before any
  invocation and provides no retry or alternate-routing mechanism.
- `onProgress`: optional awaited callback receiving a fresh JSON copy of compact
  progress metadata. Callback failure stops the operation and throws; it is
  never silently ignored, including after the manifest was acknowledged.

Pass existing recorder-wrapped native bindings. The recorder must retain the
exact request before invocation and the complete returned native envelope before
this helper inspects it. Native journals and recorder keys remain private.
The helper's progress callback is not a substitute for full native custody.

## Public selection and bounds

Only caller-selected, already-public artifact bytes belong here. Do not pass
private Slack/mail envelopes, credentials, account data, raw private errors,
private journal locators, or encoded archives under a source hold. The helper
does not discover content, infer publicity from names, or classify permissions.
Its input type checks are format/integrity bounds, not a new authorization gate.

Fixed bounds are 64 artifact entries, 2 MiB per selected artifact, 16 MiB across
selected entries, 32 lineage records, and 128 KiB for the encoded manifest.
Repeated artifact entries still count against the selected byte bound. Larger
public results need a deliberately authored chunking plan before this call;
there is no automatic splitting, truncation, restart, or larger-bound fallback.

The helper snapshots strings and metadata and independently identifies every
artifact before its first await. It also preflights the complete expected
manifest size and identity before any write. Plain data objects and dense arrays
are required; unsupported fields, accessors, symbols, sparse arrays, duplicate
paths, malformed identities, and budget overruns fail locally before dispatch.
These inputs are ordinary data, not proxies or objects with behavior.

## Native sequence and honest acknowledgement

Distinct artifact contents are banked serially with
`github_create_blob({repository_full_name, content, encoding: 'utf-8'})`.
The helper accepts the actually observed native acknowledgement shape:
`structuredContent.sha`, with no error indication, matching the independently
computed identity exactly. It does not parse a text-only success message as an
acknowledged blob.

If two selected artifacts have exactly equal content and computed identities,
their role/path entries share one acknowledged blob. Distinct strings sharing a
computed SHA are rejected before any write; the helper does not silently
coalesce a collision. The public manifest does not deduplicate logical entries.

Only after all selected artifacts have actual matching acknowledgements does
the helper bank the manifest. Its planned acknowledgement values were
precomputed to bound the entire operation; they become publishable only after
the corresponding real native responses match. Planned or echoed request values
alone are not provider evidence.

The manifest is compact `JSON.stringify(manifest) + "\n"` serialization.
Its fields include repository, checkpoint ID, caller stage label, prior manifest
link, caller-reported public lineage, and each artifact's role/path/byte count/
computed blob SHA/acknowledged native SHA. Its disposition means all selected
artifact blobs were acknowledged, not that their mathematics, source behavior,
publication spec, external acceptance, or provenance claims were validated.

A successful return includes `manifest_content` and a compact
`recovery_locator` with repository, manifest blob SHA, bytes, and checkpoint ID.
It also reports actual artifact/manifest call counts, selected bytes, unique
content count, and compact per-artifact dispositions.

## Failure and custody boundaries

The first thrown native error, MCP error/unknown acknowledgement, identity
mismatch, or rejected progress callback stops the operation. No further artifact
or manifest write is attempted. There is no retry, alternate route, rollback,
or creation of a partial manifest after a provider failure.

`PublicCheckpointError.progress` retains compact partial metadata, known
acknowledged artifact identities, attempted call counts, current phase, and any
acknowledged manifest identity. `toJSON()` preserves those diagnostics across
JSON-based handoffs. Original cause and last native response remain private
nonenumerable fields; they are not inserted into the public manifest or
JSON-safe diagnostic. The original full native request/response belongs in
the recorder's private journal.

A throw or unusable acknowledgement does not establish that a write did not
occur. An unacknowledged artifact remains pending in the compact report; the
original outcome stays available in private custody. If the final progress
callback fails after the manifest acknowledgement, the helper throws with that
acknowledged manifest locator preserved. It does not return silent success or
reinvoke the provider.

The callback's acknowledgement establishes only whatever retention guarantee
the injected callback actually provides. An in-memory `store` acknowledgement
does not become a durability guarantee. This API has no timeout, cancellation,
or rate-reset mechanism. Caller-owned shared quiet intervals and exact route
holds continue to apply before invocation.

## Recovery handoff

Retain the returned repository and manifest SHA outside the volatile working
store, for example in the authorized task handoff and eventual source receipt.
Also retain the identity-module pin and the current exact operation journal
directory privately. A lost manifest locator is not repaired by inventing
searches, scanning objects, or re-running work.

For an independently authorized recovery, use the native fetch-blob operation
with the recorded repository/SHA, preserve the original response, and verify the
complete returned UTF-8 text with the existing identity function. The currently
observed fetch-blob response exposes content, not a separate returned SHA:
the requested locator plus independent byte identity is the qualified evidence.
Parse the manifest only after that check, then recover only explicitly needed
public artifact blobs and independently check their stated bytes/identities.
Do not execute recovered source or repeat completed computations merely to
verify storage.

These are acknowledged Git objects, without a newly created reachable commit or
ref. Neither a blob acknowledgement nor the manifest promises indefinite
retention of unreferenced Git objects. Eventual ordinary publication is a
separate operation under the existing publisher's guards. The manifest does not
prove branch reachability, source acceptance, or complete historical recovery.

## Actual consumer and validation scope

Math's E593 work provided the concrete caller contract: selected public
source/input/plan/result/reader/spec bytes need exact acknowledged recovery
locators. Its 513,427-byte publication spec, independently identified as
`9afee3f871d39b83907c956a24049790eecd9b42`, was banked through its existing
direct route before helper adoption. All those checkpoints remain untouched.
The next genuinely new public completion/recovery receipt is the planned first
consumer after E593's final checks and release; it excludes private native
journals and does not rebank the prior source, results, reader evidence, or spec.

At source preparation, this new helper has not yet been invoked. The first
actual adoption, if completed, must retain its own exact input, native journal,
manifest identity, result and input-unchanged observation. No synthetic fixture,
error injection, old provider replay, verification-only construction, or
application execution is authorized by this source.

The capability assessment used the complete retained publisher
`405da1680c690e75e066ac4d9079d794e9989dbb`, including its path-based
`recoverGitHubFiles`, and operation recorder
`bf0e3e56eae2bbc5da87ea8d92bd3fb04dd34a11`. Neither is edited. Source review and
ordinary exact publication/readback checks remain separate from a successful
new checkpoint consumer; unobserved failure/dedup/limit paths must stay qualified.
