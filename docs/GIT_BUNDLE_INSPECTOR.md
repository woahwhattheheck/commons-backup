# Recover available Git-bundle objects without a network

`host/git_bundle_inspect.py` inspects a Git bundle and exports the objects it can
reconstruct, even when a thin bundle depends on unavailable base objects. It is
a Python 3.10+ standard-library command: it does not call Git, run payloads,
contact a service, change refs, create a checkout, or mutate a repository.

This complements [the full backup/restore tool](../host/repo_backup.py). It does
not replace that tool or Git's verification of a complete, restorable repository.

## Inspect or extract

From the Commons repository root:

```sh
python3 host/git_bundle_inspect.py handoff.bundle
python3 host/git_bundle_inspect.py handoff.bundle --output recovered-handoff
```

The output directory must not already exist. Successful export creates
`manifest.json` and raw object payloads under `objects/<git-object-id>.<type>`.
Object types are `commit`, `tree`, `blob`, and `tag`. A blob is its original bytes,
not a compressed loose-object file. No tree-supplied pathname is followed or
created. An I/O error during export can leave an incomplete output directory;
only a completed command with a manifest is a successful export.

Inspect the manifest before using recovered data. `references` and
`prerequisites` preserve the header's advertised refs and required history.
Every resolved pack entry includes its Git object ID, raw-content SHA256, type,
and size; unresolved deltas retain the required base ID or pack offset. Checksums
establish byte consistency, not the author's identity or trustworthiness. Treat
recovered data as untrusted and potentially private. The utility does not scan
for secrets; do not automatically publish extracted objects.

## Text-carried bundles and an expected hash

For whitespace-wrapped base64 transport:

```sh
python3 host/git_bundle_inspect.py handoff.bundle.b64 --base64 \
  --sha256 "$EXPECTED_BINARY_SHA256" --output recovered-handoff
```

The supplied SHA256 applies to the **decoded binary bundle**, not the base64 text.
Invalid base64 or a mismatched hash fails before export. Without `--sha256`, the
bundle's embedded PACK checksum is still checked, but the outer bundle header is
not covered by that PACK checksum. The manifest always reports the whole binary
bundle's SHA256 so it can be compared with a separate trusted receipt.

## Partial recovery is useful, but is not a restore

`PARTIAL_THIN_PACK` means that at least one delta could not be resolved from the
bundle and explicitly supplied base contents. Independently stored objects and
resolvable delta chains remain available. A missing old source blob need not
prevent recovery of a newly added test file.

`PACK_OBJECTS_RESOLVED` means all entries in this pack were reconstructed. It
**does not** mean all referenced history or trees exist. `git_restore_verified`
is always `false`: this tool does not traverse the object graph, validate Git
object semantics/ref names as Git does, or certify repository restoration.

For an actual restore, provide the prerequisite history in an isolated receiving
repository, use `git bundle verify`, fetch through Git, and perform the normal
repository checks. A prerequisite is required history, not permission to silently
discard missing ancestors. See the [Git bundle format](https://git-scm.com/docs/bundle-format)
and [pack format](https://git-scm.com/docs/gitformat-pack).

## Supply available delta bases

When raw base-object contents are available independently, supply them by type:

```sh
python3 host/git_bundle_inspect.py handoff.bundle \
  --base-object blob:old-source.bin \
  --base-object tree:old-tree.raw \
  --output recovered-with-bases
```

The tool computes each supplied object's Git ID using the bundle's object format.
Only an actual matching base resolves that reference. An unrelated supplied
object is not exported merely because it was supplied. Repeat `--base-object`
for more bases; use raw object payloads rather than `.git/objects` compressed
files. The original bundle remains unchanged.

## Exit codes and limits

Exit `0` means inspection succeeded, including partial recovery by default.
Add `--fail-on-unresolved` to return `3` when some objects remain unresolved;
available objects and the manifest are still exported. Exit `2` means malformed
or unsupported input, a configured limit, an argument error, or an I/O failure.
Do not count a partial result as a complete repository restore.

Default limits are 64 MiB input, 1 MiB header, 64 MiB per inflated/reconstructed
object, 256 MiB aggregate payload accounting, and 100,000 pack entries. The three
byte limits exposed on the CLI can be adjusted with `--max-input-mib`,
`--max-object-mib`, and `--max-total-mib`. The input limit also covers the encoded
file when `--base64` is used. The Python `Limits` API additionally exposes header
and object-count limits, including zero limits for callers that need them.

Aggregate accounting includes inflated representations, reconstructed deltas,
and supplied base contents. It is a data limit, **not a peak-process-memory
budget**: Python objects, buffers and temporary copies use additional memory.
Base-file input is bounded while each file is read. Compressed objects are fed
to zlib in bounded chunks, and declared-size overruns fail before the extra
inflated payload can be retained. No machine-wide process or disk limits are
changed.

## Supported formats and verification scope

The implementation supports bundle v2/v3, SHA-1/SHA-256 object formats, PACK
v2/v3, ordinary commit/tree/blob/tag entries, REF_DELTA and OFS_DELTA, forward
reference chains, and explicitly supplied raw bases. It records the known v3
`filter` capability without pretending to supply omitted promisor objects.
Unknown required capabilities are reported as unsupported rather than guessed.

Validation runs with:

```sh
python3 -m pytest -q tests/test_git_bundle_inspect.py
python3 -m py_compile host/git_bundle_inspect.py tests/test_git_bundle_inspect.py
```

The tests require `pytest` and Git with SHA-256 repository support. They generate
full and thin bundles in temporary Git repositories and compare reconstructed
payloads and IDs with Git itself. Deterministic cases cover forward and offset
deltas, multi-byte offsets, default 64 KiB copy lengths, malformed instructions,
checksums, truncated streams, resource limits, export behavior, and errors.
See [the executed validation receipt](../evidence/rivet-git-bundle-inspector-20260906.json).
This is tested format interoperability, not full Git compatibility, a security
audit, an authenticity service, or exhaustive fuzzing.
