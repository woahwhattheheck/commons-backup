# Import exact source from connected GitHub reads

`connected_github_source.py` turns saved native GitHub file/blob responses or
locally recovered exact blob bytes into ordinary source files in an ephemeral
cloud working directory. It needs only
Python's standard library. It performs no network requests or Git/provider
mutations and does not execute imported files.

This is useful when a session can read GitHub through connected tools but does
not have a Git clone. The existing Git source capsule tools remain the route for
collecting source from an already available local Git object database.

## Use

Fetch each needed file with the existing GitHub connector, selecting an observed
commit SHA as `ref` for a consistent source snapshot. Omit `start_line` and
`end_line`: those return excerpts, which cannot materialize a complete file.
Use `encoding: "base64"` for binary files.

Save the complete tool results in a JSON document with this structure:

```json
{
  "files": [
    {
      "path": "host/example.py",
      "response": {"structuredContent": {"content": "...", "encoding": "utf-8", "sha": "..."}},
      "mode": "100755"
    }
  ]
}
```

The response above illustrates the shape only; use the actual complete response
and its actual SHA. `mode` is optional; if provided, copy the observed tree mode
(`100644` or `100755`). New files default to `0644` when mode is omitted.

Then run:

```sh
python3 host/connected_github_source.py source-export.json cloud-source
```

The command prints JSON containing `ok`, the output directory, each file's path,
Git blob SHA and byte count, plus `written` and `unchanged` totals. It exits zero
only when the requested import completes. Errors exit one and report a fixed
code and useful detail without printing source contents or provider error text.
The manifest must be an ordinary file (or a symlink to one). Special files such
as named pipes are rejected with `SOURCE_IMPORT_IO`, `errno_name: "EINVAL"`,
and `operation: "read_manifest"` before reading or creating destinations.

## Recover a bounded pinned source read

A recursive tree request can fail while smaller requests for the same pinned
repository state still succeed. Retain the complete failed request and response.
A transport error does not establish an empty tree, a provider HTTP status,
`truncated`, repository membership, or a service-wide outage. Keep those facts
unknown when the response does not contain them.

Recover only the source needed for the task:

1. Keep the selected observed commit reference. Request its root tree without a
   `recursive` query parameter. GitHub treats any supplied value, including `0`
   and `false`, as recursive; omit the parameter for a nonrecursive request.
   See [GitHub's Get a tree documentation](https://docs.github.com/en/rest/git/trees#get-a-tree).
2. Retain the successful response's tree SHA, `truncated` value and direct
   entries, including each observed path, type, mode and SHA. A nonrecursive
   response lists direct entries; it does not enumerate descendants.
3. Select a needed subtree from an actual returned `type: "tree"` entry and
   request that entry's observed SHA without `recursive`. Repeat only for needed
   paths, retaining the parent-to-child entry evidence and each response's
   truncation state. The existing
   [tree-entry projector](CONNECTED_GITHUB_TREE_ENTRIES.md) can provide a bounded
   view of a supplied response; that view is not a complete repository inventory.
4. Fetch needed files with the original observed commit as `ref`, or request
   their observed blob identities. Capture the full responses and use the
   importer's existing complete byte and Git blob checks described below.

This recovery was observed after recursive reads returned transport errors:
nonrecursive root and selected subtree reads, plus pinned manifest, toolchain
and lockfile reads, succeeded. Tracked build and dependency directories were
visible in the returned entries. Their presence did not establish why the
recursive transport failed, and the selected reads did not reconstruct the
whole source package. Preserve the original failures alongside the successful
bounded captures.

Source recovery also does not establish runtime readiness or successful
execution. Read the selected manifest, toolchain and lockfile requirements
before making an execution claim. In the observed recovery, required runtime
versions were absent, so source intake ended without execution. Keep that
boundary separate from the successful reads.

These are read-only recovery steps. A successful smaller read does not resolve
an uncertain writer effect or authorize replaying a mutation. Reconcile any
previous writer dispatch independently before taking another write action.

## Capture in a tool-enabled JavaScript session

This example uses the actual exposed `fetch_file` action and `apply_patch` to
save one JSON line. `paths`, `repository` and `sourceRef` are values already
chosen from the task and observed repository state. Replace the scratch export
path with a path in the current cloud workspace.

```javascript
const files = await Promise.all(paths.map(async path => ({
  path,
  response: await tools.mcp__codex_apps__github_fetch_file({
    repository_full_name: repository,
    path,
    ref: sourceRef,
    encoding: "base64"
  })
})));
const exportPath = "/workspace/scratch/source-export.json";
await tools.apply_patch(
  "*** Begin Patch\n*** Add File: " + exportPath + "\n+" +
  JSON.stringify({files}) + "\n*** End Patch"
);
```

JSON serialization preserves the source string's line endings and escapes.
Do not pass source bodies into shell command text or rebuild them with
`splitlines()`, `join()`, heredoc interpolation or an extra newline. Keep exports
in private scratch custody; do not commit raw tool results from private sources.

## Supported responses

- Native `fetch_file`, in UTF-8 or base64.
- GitHub GET contents/blob JSON returned directly or inside `github_fetch`'s
  JSON-text and `structuredContent` envelopes. Some connector versions normalize
  these GET responses to decoded text and omit the SHA/encoding. Include the
  observed blob SHA and explicit UTF-8 encoding on the entry in that case too.
- Native `fetch_blob`, which can return only the decoded content. For that
  response, include the original request's `blob_sha` and explicit
  `encoding: "utf-8"` on the file entry. The importer does not guess a SHA or
  silently accept content with missing identity.

A successful `fetch_file` response can still contain an empty `content` string
for a nonempty file. Compare the returned bytes with the observed blob SHA; an
empty body is valid only for the empty Git blob
`e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`. For UTF-8 text, fetch that observed
blob directly and capture it with the entry below. Keep the SHA validation:
`SOURCE_BLOB_MISMATCH` rejects the incomplete response before any destination is
created. This recovery was observed with a 2,318,503-byte text file whose path
read returned no content; the unchanged importer accepted the complete native
blob response with the same expected Git blob. This observation does not
establish a size limit or guarantee that every blob response is complete.

```javascript
files.push({
  path: repositoryPath,
  blob_sha: observedBlobSha,
  encoding: "utf-8",
  response: await tools.mcp__codex_apps__github_fetch_blob({
    repository_full_name: repository,
    blob_sha: observedBlobSha
  })
});
```

For binary blobs, use base64 `fetch_file` or the GET blob JSON response. Source
URLs are retained in the result when the provider includes them. The importer
checks the bytes against the supplied Git blob identity; it does not independently
prove commit ancestry, repository membership, freshness, or snapshot completeness.

## Import recovered local bytes

Some large files exceed the connector transport even when requested through
`fetch_blob`. If an existing cloud Git object database or another already
authorized source route has recovered the complete bytes, import that local
file directly. This avoids embedding another copy in a JSON export.

Use `source_file` with the exact `blob_sha` observed for the requested repository
path at the selected commit. This is an alternative to `response`; do not also
provide `response` or `encoding` on the same entry. The bytes are raw, including
for binary files, and undergo the same complete Git blob identity check before
any destination is written.

```json
{
  "files": [
    {
      "path": "posts.json",
      "blob_sha": "f3343f6a99a70f213b1da74630a58a3e3a4f0eb5",
      "source_file": "/cloud/scratch/recovered/posts.json",
      "mode": "100644"
    }
  ]
}
```

The example SHA identifies an observed 33,424,517-byte source; use the identity
from your own selected snapshot. `source_file` paths are resolved relative to
the process working directory, with `~` expansion. The source file is read only
and remains intact. It must be an ordinary file; symlinks to ordinary files are
supported. Named pipes, directories and devices return `SOURCE_IMPORT_IO`
with `errno_name: "EINVAL"` and `operation: "read_source_file"`. The reader
checks the path before opening and checks the opened descriptor before reading;
where the platform supports `O_NONBLOCK`, that flag also prevents a FIFO swapped
in during open from waiting for a writer. Native-response and local-file entries
may share one
manifest. The importer performs no Git command, network fetch, credential
lookup, or automatic fallback from a failed response.

Keep the original source identity and recovery context with your working
inputs. A matching blob confirms bytes, not repository membership or commit
ancestry. Local-file input avoids JSON serialization overhead; the importer
still retains file bodies in memory while it validates the batch.

A local source read failure exits one with `SOURCE_IMPORT_IO`, the system errno,
`operation: "read_source_file"`, the relative repository `path`, and an empty
`completed_files` list. Source reads precede all destination writes. Raw local
source paths and operating-system exception text are not printed. A byte/hash
mismatch retains `SOURCE_BLOB_MISMATCH` and writes no destination files.

## Existing files and recovery

All source bodies, paths and observed destination conflicts are checked before
writing any file. A content/hash mismatch, including a real line excerpt with a
full-file SHA, reports `SOURCE_BLOB_MISMATCH`. No line-ending conversion occurs.

Existing identical files are left unchanged. Different files, symlinks,
non-directory parents and conflicting explicitly requested modes are preserved
and produce `DESTINATION_CONFLICT`. Use another output directory or reconcile
the existing working copy yourself. There is no overwrite option.

The output directory itself may be a symlink to an ordinary directory. A cyclic
output-directory link instead returns `SOURCE_IMPORT_IO`, `errno_name: "ELOOP"`,
`operation: "inspect_destination"`, and no completed files. The links
remain intact, and no destination is created.

New files are staged beside their destination and atomically linked into place
without replacing a concurrently created file. The destination filesystem must
support hard links. The importer cleans up only its own staging files.

The import is atomic per file, not a transaction across the whole directory.
A storage error or a new conflict after preflight may leave earlier completed
files. Rerun the same export to continue; those exact files become `unchanged`.
Do not interpret a failed import as a complete checkout.

I/O failures retain `error: "SOURCE_IMPORT_IO"` and exit one, with `errno`,
`errno_name` (for example `ENOSPC` or `EFBIG`), a system-derived explanation,
the failed `operation`, and the affected relative source `path` when known.
A manifest-read failure instead identifies the supplied manifest path.
`completed_files` contains the confirmed per-file outcomes before the failure;
it is a completed prefix, not an inventory of every file that now exists. A
failure during staging cleanup can occur after that file was already published.
Recover the reported storage condition and rerun the same retained export to
reconcile existing exact files and continue. Diagnostics do not include raw
exception messages or source contents.
