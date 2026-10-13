# Local Python import sources

Use this manual, read-only command when assembling a small Python source
checkout and an entry point leads through package wrappers or relative imports.
It reads the chosen source files with Python's AST parser. It does not import
or execute those files. Optional explicit asset paths add opaque resource-byte
identities to the same bounded observation.

The existing root [source parser](../source_parses.py) checks tracked source
syntax. The [GitHub source materializer](CONNECTED_GITHUB_SOURCE.md) writes
explicit, verified provider files. Neither selects local Python imports; this
command supplies that separate source-selection view without changing either
tool.

## Run

Choose the directory that represents the local import root, then give one or
more source paths relative to it:

```sh
python3 -B host/python_import_sources.py \
  --root /path/to/motel-ops-suite \
  --entry linenpar_standalone.py > /path/to/private/linenpar-imports.json

python3 -B host/python_import_sources.py \
  --root /path/to/source \
  --entry package/cli.py --entry package/exporting.py \
  --max-files 32 --max-bytes 262144
```

For a program with required runtime data, name each resource explicitly:

```sh
python3 -B host/python_import_sources.py \
  --root /path/to/source/research/ridgway_freudenthal \
  --entry global_divergence_lift.py \
  --asset global_lift_operators.json \
  > /path/to/private/global-runtime-sources.json
```

Repeat --asset for additional files. Assets are relative file paths under the
same root, without traversal; they may contain arbitrary bytes and are never
parsed as Python. Repeated identical paths are read once. An asset already in
the parsed source list reuses that exact recorded identity and consumes no
additional file or byte budget. Omitted --asset preserves the original JSON
shape and source-only behavior.

The root must already exist. Entries must be relative paths ending in .py,
without traversal. The command does not create a checkout, search other
directories, install packages, query a provider, or write files. Shell
redirection in the first example saves its JSON output.

Entries inside package directories also include available parent package
initializers. Absolute imports resolve only under the explicit root; the
entry's directory is not implicitly added as another import root. Choose the
root for the intended package layout. This models source candidates, not the
full startup behavior of every way a script can be launched.

## Read the result

The JSON contains:

- **files**: each parsed source path, byte count, Git blob SHA and SHA-256.
- **imports**: source path and line for each observed import request, candidate
  member, star import, language directive or recognized dynamic call.
- **resolutions**: the shared module-name lookup results, local source paths,
  namespace directories, or the candidate paths where lookup stopped.
- **errors**: explicit entry/source read or parse failures.
- **coverage**: bytes read, file and import counts, configured limits, pending
  sources, the interrupted source, skipped sources and unavailable modules.

With --asset, **requested_assets**, **assets** and **asset_errors** are also
present. Each asset identity includes the same path, bytes, Git blob SHA and
SHA-256 fields as a source, plus reused_source. Coverage adds asset_files,
asset_files_read, asset_bytes_read, total_bytes_read, reused_source_assets,
explicit_assets_finished, pending_assets, skipped_assets and interrupted_asset.
source_bytes_read remains the source-scan count; asset_bytes_read counts only
new resource reads. A reused source appears in both identity lists but is
counted once against the shared reading limits.

Ordinary package initializers take precedence over a same-name .py module;
available local namespace directories are followed. A visited source path is
parsed once, so cycles and multiple routes through the same wrapper do not
cause repeated traversal.

| Resolution | Meaning |
| --- | --- |
| local_package / local_module / local_namespace | A candidate was found under the chosen root. Available package initializers and module sources are queued. |
| not_local | No candidate was found under that root. It may be standard library, an installed dependency or an unmaterialized local package. The command does not decide which. |
| unresolved_local | A local prefix was found but a later component was absent. |
| attribute_or_missing_submodule | A from-import member has no local module candidate. It can be a value exported by the package; this is not automatically a missing dependency. The shared resolution retains the probed candidate paths. |
| not_a_package | Lookup reached a .py module before the requested dotted name ended. |
| unavailable | A candidate could not be inspected or was a special file or a symlink resolving outside the root. |
| relative_beyond_root | The relative import cannot be located within the selected package context. |
| not_followed / exports_not_followed | A recognized dynamic call or star-import export list needs separate inspection. |

Package member candidates are conservative: a matching submodule can be
included even when a package attribute would supply that imported name at
runtime. Imports inside functions, conditionals and type-checking branches are
all observed without evaluating those branches. Future directives are recorded
as language directives rather than external source requests.

## Bounded observations

All limits are positive integer CLI options:

| Option | Default | Boundary |
| --- | ---: | --- |
| --max-files | 256 | Source and explicitly requested asset files read, skipped or refused. A reused source identity adds no observation. |
| --max-bytes | 8,388,608 | Shared source and asset bytes read. A file that does not fit is left as interrupted work. |
| --max-file-bytes | 1,048,576 | Larger sources or assets are skipped before reading, with their observed sizes retained. |
| --max-imports | 4,096 | Import records, including member candidates, directives and recognized dynamic calls. |

A limit returns the observed JSON with **scan_finished: false**, explicit
limits_reached and the remaining source or asset boundary. Sources are observed
first, followed by explicitly requested assets in their supplied order. The
source and asset boundaries remain separate when either scan is partial.
Increase the relevant limit and rerun the same explicit request to obtain a larger observation. The result
is not a resumable snapshot or an atomic view of a changing checkout.

Exit 0 means the JSON observation was produced without source read/parse or
asset read errors, including a deliberately bounded partial result. Exit 1
reports an input, source read/parse or asset read error; JSON remains on stdout
and a concise summary goes to stderr. Invalid CLI syntax uses argparse's exit 2. Missing external
candidates and limits do not become a work-admission gate.

Resolved source and asset symlinks must stay inside the selected root. Reads
accept only regular files, use a nonblocking descriptor and check the observed size and
modification time before and after reading. Each hash describes the bytes read
from that file; it does not certify a whole-directory snapshot.

## Scope limits

runtime_completeness is always **not_evaluated**. A finished queue describes this
static local scan only. It does not resolve installed or standard-library
sources, native extension modules, import hooks, changes to sys.path, arbitrary
dynamic loaders, unnamed resources such as JSON/SQL/templates, runtime branch
choices or package export behavior. Explicit assets add file identities; the
command does not discover resources from source expressions or decide whether
the named set is sufficient. Recognized dynamic calls include the usual
__import__, attribute import_module, and directly imported import_module names;
aliasing, shadowing and other computed loaders are not fully modeled.

Keep the explicitly named runtime resource files and the actual product
invocation in the handoff. Use the returned Git blob identities with the separately pinned source
inventory when exact provider bytes matter. This command does not establish
runtime success, deployment readiness or ownership.

## Native use of the original source scan

The command was run against the retained current-main LinenPar source after
motel-ops-suite #468. Starting at linenpar_standalone.py found all 17 Python
files in that 22-file source set: 140,784 bytes and 117 import records. The map
included turnproof/__init__.py to turnproof/app.py to turnproof/engine.py, and
all 17 returned Git blob identities matched those retained sources. The four
JSON files and README were outside its Python-source scope.

The final ordinary call exited 0 in 0.084 seconds in that cloud workspace;
peak child RSS across the native command window was 16,556 KiB. Each of the
four explicit limits returned a partial observation on the same input. An
unavailable entry returned exit 1 with its path and structured error. All
22 retained input files stayed byte-identical. These are native observations
of that small source set, not a general performance or runtime-completeness
claim. No product source, test suite or generated map was published.
