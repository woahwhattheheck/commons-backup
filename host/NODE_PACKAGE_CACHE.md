# Recover an exact Node package from a retained npm cache

`host/node_package_cache.py` inspects one package archive already present in an
explicit npm `_cacache` directory. Supply the exact package name, version and
integrity token from the consuming project's retained lockfile. The command uses
only Python's standard library and prints one JSON report to stdout. It can also
materialize the verified package into a new directory you choose.

Use [the installed-package locator](NODE_PACKAGE_SOURCES.md) first when a known
dependency directory can supply the package. A completed installed-donor miss
does not establish that retained archive bytes are unavailable. This companion
provides that additional source without installing dependencies or modifying a
donor. It does not search for a cache or infer one from the home directory,
environment, current directory or npm configuration.

## Inspect retained bytes

This example uses the `react-router-dom` 6.30.4 integrity recorded in the retained
YieldVault frontend lockfile. Supply the cache root that actually exists in your
cloud workspace; `/root/.npm/_cacache` is the root used for the retained recovery.

```sh
NPM_PACKAGE_INTEGRITY='sha512-q4HvNl+mmDdkS0g+MqiBZNteQJCuimWoOyHMy4T/RQLAn9Z29+E91QXRaxOujeMl2HTzRSS0KFPd7lxX3PjV0Q=='
python3 -B host/node_package_cache.py \
  --cache-root /root/.npm/_cacache \
  --package react-router-dom --version 6.30.4 \
  --integrity "$NPM_PACKAGE_INTEGRITY"
```

Without `--destination`, the command only reads and validates. It creates no
package directory. Both the archive's manifest name and version must match
literally; semver ranges are not resolved. Scoped package names are supported.

The integrity argument is one canonical SRI token using `sha1`, `sha256`,
`sha384` or `sha512`, followed by its base64 digest. Multiple tokens are not
accepted. The helper decodes that digest and directly addresses
`content-v2/<algorithm>/<first-two-hex>/<next-two-hex>/<remaining-hex>` below the
supplied root. It does not walk `index-v5`, query npm metadata, choose another
version or try another integrity value after a miss.

Prefer the consuming project's retained lockfile integrity. A matching digest
establishes equality with that supplied value; it does not authenticate a package
publisher or establish that the supplied lockfile is trustworthy.

## Materialize the same package

Choose an owned cloud directory with sufficient space. The destination must be
new, outside the source cache, and its parent must already exist. For example, if
`/dev/shm` has suitable capacity, continue with the integrity variable above:

```sh
NPM_PACKAGE_WORKDIR="$(mktemp -d /dev/shm/npm-cache-package.XXXXXX)" || exit
python3 -B host/node_package_cache.py \
  --cache-root /root/.npm/_cacache \
  --package react-router-dom --version 6.30.4 \
  --integrity "$NPM_PACKAGE_INTEGRITY" \
  --destination "$NPM_PACKAGE_WORKDIR/react-router-dom"
```

The package contents are written directly inside the destination, with
`package.json` at its root. The archive's common top-level directory is removed;
that archive directory may be `package` or another name such as `babel__core`.
Package identity comes from the manifest, not the archive directory's name.

The command validates the entire gzip/tar archive and manifest before creating
the destination. Extraction uses the same immutable in-memory archive bytes whose
integrity was checked. Only regular files and directories are admitted; links,
devices, sparse files, duplicate entries and path traversal are refused. Copied
file modes are normalized to `0644` plus the source executable bits. Directories
are created with mode `0755`, subject to the process umask. Ownership and
timestamps are not restored.

Existing destinations are never reused or replaced. If a write fails after
creation, the partial new destination is left in place and reported as an error;
the helper does not clean it up. The caller retains responsibility for that
owned directory and must not use an incomplete materialization. Do not share the
destination with another writer: the operation is not atomic against independent
writer interference.

## Interpret the result

| Outcome | Exit | Meaning |
| --- | --- | --- |
| `verified` | 0 | The exact cache object, integrity, complete archive and requested manifest identity passed validation; no extraction was requested. |
| `materialized` | 0 | The verified package was written to the new requested destination. |
| `not_found_in_scope` | 1 | The single object addressed by the supplied integrity was absent from the supplied cache. This is not a package-wide or machine-wide absence claim. |
| `error` | 2 | The structured error code/message identifies a root, read, integrity, identity, archive, limit or destination failure. This is not a cache-absence result. |

Argument errors also exit 2 and print argparse usage to stderr. A missing cache
root is an error; it does not establish that the requested content is absent
from an existing cache.

The JSON schema is `commons.node_package_cache/v1`. The report includes the
observation time and original request, with these evidence and progress fields:

| Field | Meaning |
| --- | --- |
| `source.cache_root` / `source.path` | Resolved cache root and the single addressed content object. |
| `source.integrity` / `source.integrity_verified` | Supplied integrity token and whether the compressed bytes matched it. A true value alone does not establish that archive or manifest validation succeeded. |
| `archive.bytes` / `archive.sha256` / `archive.tar_bytes` | Compressed byte count, SHA-256 of those compressed bytes, and expanded tar byte count. |
| `archive.root` / `archive.members` / `archive.files` / `archive.file_bytes` | Archive root name, admitted member count, regular-file count and total declared regular-file bytes. |
| `package` | Exact manifest name/version, manifest SHA-256 and byte count, and declared Node engine metadata when available. This does not evaluate the engine requirement. |
| `destination.path` / `destination.created` / `destination.complete` | Requested or resolved destination and whether this call created and completed it. `destination` is null for inspection alone. |
| `destination.files_written` / `destination.bytes_written` | Materialization progress retained in the report, including on a write failure. |
| `limits` | Effective archive, expanded-tar, member and manifest limits. |
| `error.code` / `error.message` | Failure category and explanation, or null `error` on success or an exact-object miss. |

Source, archive and package details remain null or partial if the command fails
before those stages complete. Read `outcome` and the exit code before using the
package. Failure codes include `CACHE_READ`, `INTEGRITY_MISMATCH`,
`PACKAGE_MISMATCH`, `INVALID_ARCHIVE`, `LIMIT_EXCEEDED`, `DESTINATION_EXISTS` and
`DESTINATION_ERROR`. A write error can report `destination.created: true` with
`destination.complete: false`; preserve that distinction when handling the
partial directory.

## Limits and runtime composition

The command bounds the compressed archive, expanded tar stream, member count and
manifest before writing package contents:

| Limit | Default |
| --- | --- |
| `--max-archive-bytes` | 33,554,432 bytes (32 MiB) |
| `--max-tar-bytes` | 134,217,728 bytes (128 MiB) |
| `--max-members` | 20,000 |
| Manifest read limit | 1,048,576 bytes (1 MiB) |

These are input limits, not a total process-memory reservation or a guarantee of
free destination space. The command performs a bounded compressed read and a
bounded gzip expansion, retaining both byte sequences in memory. It has no
wall-clock timeout. Choose limits and a work directory that fit the current
shared cloud capacity.

The cache remains unchanged. The helper does not install, link, execute package
scripts, access the network or resolve dependencies. Recovering one archive does
not establish a complete or compatible runtime. For example, this router package
also declares `react-router` 6.30.4 and `@remix-run/router` 1.23.3, with React and
React DOM peers. Obtain each required package through its own retained source and
check the consuming application's lockfile, engine and platform requirements
before using the resulting runtime. Preserve the installed locator's manifest
match as a separate observation from archive integrity and actual application
execution.
