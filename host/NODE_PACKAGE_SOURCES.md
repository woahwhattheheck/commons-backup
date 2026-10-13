# Find an installed Node package for runtime reuse

`host/node_package_sources.py` locates the exact requested package name and version in existing dependency directories. Use it when another worker has already installed a compatible runtime and a missing package is blocking the next command. It uses only Python's standard library and emits one JSON report to stdout.

Start with known donors. Direct checks avoid walking their dependency trees:

```bash
python3 -B host/node_package_sources.py \
  --package vitest --version 2.1.9 \
  --node-modules /path/to/retained-runtime/node_modules \
  --node-modules /path/to/another-runtime/node_modules
```

Both the manifest name and version must match literally. Version ranges are not resolved. Scoped names such as `@testing-library/react` are supported. A package installed under an alias with a different manifest name is reported separately.

If the donor location is unknown, add explicit roots for bounded discovery:

```bash
python3 -B host/node_package_sources.py \
  --package nanostores --version 1.3.0 \
  --search-root /workspace/scratch \
  --max-directories 2000 --max-entries 20000 \
  --max-depth 8 --max-seconds 10
```

Combine direct donors and discovery in one command. Direct donors are checked first. Discovery walks directories breadth first, reads the requested package manifest at each discovered `node_modules`, and deduplicates repeated physical directories. It handles package links inside npm/pnpm dependency directories by resolving the requested manifest. It does not extract package archives or query package-manager databases.

For an exact package retained only as npm cache bytes, use the separate [cache inspection and materialization command](NODE_PACKAGE_CACHE.md) with an explicit cache root and integrity token. The installed-donor lookup and its coverage semantics remain unchanged.

## Read the result

| Field | Meaning |
| --- | --- |
| `outcome: found` | At least one exact manifest match was read. Exit 0. Other roots may remain unexplored; inspect coverage. |
| `outcome: not_found_in_scope` | No exact match in the completed requested scope and traversal policy. Exit 1. This is not a machine-wide absence claim. |
| `outcome: inconclusive` | No exact match, and a budget or read error prevented complete coverage. Exit 2. |
| `matches` | Canonical manifest and package paths, requested path, exact name/version, manifest SHA-256 and byte count, and the declared Node engine when present. |
| `other_versions` | The requested package was present at an inspected location with a different manifest version. |
| `manifest_name_mismatches` | The requested installation path contained a manifest with another package name. |
| `coverage.complete` | All supplied scopes were processed under the reported traversal policy, without a budget cutoff or read error. |
| `coverage.reasons` | Any `max_directories`, `max_entries`, `max_depth`, `max_seconds`, or `read_errors` limitation. |
| `queued_directories` / `unfinished_directory` | Known work left when scanning stopped; this is not a count of all undiscovered directories. |
| `errors` | Paths and failed read operations. Missing requested package paths are ordinary misses; missing explicit roots are errors. |

Argument errors also exit 2 and print argparse's usage message to stderr.

Each match identifies bytes that were actually read. The manifest hash is **not a hash of the installed package tree** and does not establish that all transitive dependencies are present, that installed source is unchanged, or that the donor fits the consumer's lockfile and runtime. Use the consuming application's existing requirements and native execution to make that decision. The command does not select, reserve, link, install, copy, execute, or modify a donor.

## Traversal and resource limits

No roots are inferred from the home directory, environment, current workspace, or package-manager settings. Direct `--node-modules` inputs are dependency-directory scopes: they check only the requested package there. Search roots are discovery scopes.

Discovery excludes `.git`, `.hg`, `.svn`, and `__pycache__`; add directory basenames with repeated `--exclude-dir`. The report lists the exclusions. Directory symlinks below a search root are skipped and counted. Supply a linked dependency directory directly with `--node-modules` when it should be inspected. Explicit roots themselves and the requested package/manifest links are resolved. Repeated matches of the same physical manifest and bytes appear once.

Defaults are 2,000 visited directories, 20,000 examined entries, directory depth 8, and 10 seconds. The entry budget includes files and skipped entries, so a large directory cannot grow an unbounded queue. A depth cutoff keeps coverage incomplete even after the remaining queue drains. Scandir order may differ between runs; a partial result is not a stable inventory.

The time budget is cooperative: it is checked between filesystem operations, not an interrupt for a slow filesystem call. Package manifests are opened nonblocking where supported, must be regular files, and are limited to 1 MiB. A manifest that changes during its read is reported as an error. The overall scan is a point-in-time observation of a shared mutable workspace, not an atomic snapshot. No background process, database, dependency, or network access is created.
