# Local JavaScript import sources

Use this manual command to select a small local ESM source closure before
materializing or publishing an application. It parses each selected module with
Node's own module parser and records its static imports and re-exports. An
explicit asset list adds opaque file identities under the same limits.

The immediate consumer is the Fleet Fuel CLI: its entry imports two local
modules, which lead to the remaining local engine and JSON reader. Selecting
that closure previously required a caller to enumerate every file manually.

The [Python source mapper](PYTHON_IMPORT_SOURCES.md) remains the canonical
Python AST/import reader. The [GitHub source materializer](CONNECTED_GITHUB_SOURCE.md)
consumes explicit file selections; the root [source parser](../source_parses.py)
checks syntax. This companion handles local ESM selection without changing
those interfaces.

## Run

Use Node with SourceTextModule.moduleRequests support (added in Node 24.4)
and its experimental VM modules flag:

```sh
node --experimental-vm-modules host/javascript_import_sources.cjs \
  --root /path/to/smb-showcase-inventory \
  --entry apps/fleet_fuel_card_reconciliation/cli.mjs \
  > /path/to/private/fuel-source-map.json

node --experimental-vm-modules host/javascript_import_sources.cjs \
  --root /path/to/smb-showcase-inventory \
  --entry apps/fleet_fuel_card_reconciliation/cli.mjs \
  --asset apps/fleet_fuel_card_reconciliation/example.json \
  --asset apps/fleet_fuel_card_reconciliation/example.roots.json \
  --max-files 32 --max-bytes 262144
```

Repeat --entry or --asset as needed. Entries are relative .mjs or .js paths;
they are explicitly parsed as ESM, without consulting package.json type.
Explicit paths cannot contain traversal components. Static relative imports
may use ../ as long as the resulting path stays inside the chosen root.

The root must already exist. The command reads only requested files and the
static local paths reached from them. It creates no files; redirection in the
first example is the caller's choice. It does not install packages, scan other
directories, access the network or start the application.

Node may emit its ExperimentalWarning on stderr. JSON remains alone on stdout.
The command checks that the required parser API is actually available and
returns an input error if it is absent. Runtime admission and execution time
limits remain the caller's responsibility.

## What the parser establishes

SourceTextModule construction parses the source. The mapper reads its
moduleRequests array and never links, instantiates or evaluates a module.
No namespace, import-meta callback or dynamic-import callback is used. Each
successfully parsed file records module_status: "unlinked".

Node's versioned documentation defines
[construction and module requests](https://github.com/nodejs/node/blob/v24.19.0/doc/api/vm.md#class-vmsourcetextmodule).
The request records preserve the parser's specifier, import attributes and
phase. Both imports and re-exports participate in the static dependency list.
This is parser output rather than a textual import-pattern match.

Only local evaluation-phase requests with an empty attribute object and an
exact .mjs or .js extension are followed. Relative, absolute and file: URLs
must resolve within the explicit root. Lexical paths and resolved symlink
targets are both checked. File identities use canonical paths, so an already
read source is not read again through an alias or an import cycle.

Other requests remain visible:

| Request | Recorded behavior |
| --- | --- |
| node:... | Builtin request; no file read |
| Bare package or #package import | Recorded without package resolution |
| Non-file URL | Recorded without a network request |
| Local JSON, TypeScript, JSX, CommonJS or extensionless path | Local request not followed |
| Local request with import attributes or another phase | Attributes/phase retained; request not followed |
| Local file outside the root, missing file or read/parse failure | Structured source error |

There is no extension inference, directory-index lookup, package exports or
conditions resolution, or CommonJS require analysis. Query and fragment
variants retain their request URLs but share the same canonical file-byte
identity. The mapper does not model separate runtime module instances. Node
documents its URL-based ESM resolution separately in the
[ESM reference](https://nodejs.org/docs/latest-v24.x/api/esm.html).

Dynamic import(), require(), environment-dependent loading and runtime file
access are outside this observation. A complete static map cannot establish a
complete or functioning application. Every result therefore keeps
runtime_completeness: "not_evaluated" and module_evaluation: false.

## File identities and explicit assets

Each source file that was read carries its relative canonical path, byte
count, Git blob SHA-1 and SHA-256. Parse status and static request counts are
separate fields. An unread or skipped file never receives a fabricated hash.

Reads open the resolved path without following a final symlink, where the
platform exposes that option, and with nonblocking admission where available.
The open descriptor must be a regular file before allocation or reading.
The reader checks byte count, device, inode, size, modification time and change
time before/after the read. Filesystem races are reported when observed;
this is not an atomic snapshot of a changing tree.

Assets are arbitrary bytes and are never parsed. Repeated identical explicit
asset paths are deduplicated. An asset whose canonical file was already read
as a source reuses that exact recorded identity; aliases to already read
assets also reuse their identity. Reuse consumes no additional read or byte
budget. Asset records identify reused_source and reused_asset explicitly.

The map itself may contain private local paths or filenames. Keep actual
observations in the caller's private work area; publish selected repository
source through the existing GitHub publisher.

## Bounds, output and exit status

The defaults are:

| Option | Default | Meaning |
| --- | ---: | --- |
| --max-files | 256 | Source/asset read attempts, including failed and skipped attempts |
| --max-bytes | 8,388,608 | Total source and asset bytes actually read |
| --max-file-bytes | 1,048,576 | Maximum declared size of an individual regular file |
| --max-imports | 4,096 | Static request records retained across parsed modules |

Limits accept positive safe integers. Requests are visited in parser order,
with local source files visited breadth-first. Duplicate canonical sources
are skipped after their first attempt. Resolution work is restricted to
explicit entries/assets and retained static requests.

A per-file limit records a skipped file and continues other pending work.
A total-byte limit records the interrupted file and pending paths. A file
count limit preserves the pending queue. An import limit records how many
requests were observed, retained and omitted in the interrupted module;
unvisited sources remain pending. Explicit assets are still considered with
the remaining shared file and byte budget.

The JSON schema is commons.javascript_import_sources/v1. Its main fields are:

- files: identities and parser observations for source bytes actually read.
- imports: static request records with local, external, unsupported or error
  disposition; a local target is a candidate path, with canonical aliases
  recorded separately in coverage.
- errors and asset_errors: actual resolution, read, decoding or parse errors.
- requested_assets and assets: explicit resource requests and observed
  identities.
- coverage: source/asset completion, limits reached, pending/interrupted
  paths, skipped files, unrecorded requests, aliases, read counts and bytes.

coverage.source_scan_finished is false if local requests were not followed,
source errors occurred, or source work remains due to limits.
coverage.explicit_assets_finished describes only the explicit asset requests.
coverage.scan_finished combines those two observations. Builtins and bare or
external requests stay outside the declared local-source scope even when that
scope is complete.

Exit codes preserve incomplete observations as useful output:

| Exit | Meaning |
| --- | --- |
| 0 | JSON observation produced, possibly partial due to limits or unsupported local requests |
| 1 | Root/parser/input admission failed, or source/asset resolution, read, decode or parse errors occurred |
| 2 | CLI usage or numeric-option syntax was invalid |

Exit 1 still prints structured JSON to stdout and a short diagnostic to
stderr. Usage errors print usage on stderr. This is a manual source-selection
tool, not a build, deployment or work-admission gate.

## Calling from Node

```js
const { mapSources } = require('./host/javascript_import_sources.cjs');
const result = mapSources({
  root: '/path/to/source',
  entries: ['app/cli.mjs'],
  assets: ['app/schema.json'],
  max_files: 32,
  max_bytes: 262144,
});
```

The process still needs the same VM modules flag. mapSources returns the
observation, including source/asset errors; invalid root/options or an
unavailable parser throw ImportMapError or the underlying filesystem error.
The CLI applies the exit-code policy above.
