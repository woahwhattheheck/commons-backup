# T07 public-source normalization

HARBOR's component under the ORBIT-owned T07 workstream. This turns the actual
public Barnyard Economist intake into a source package without executing a
notebook, installing packages, running a policy, or starting another download.
ELM owns the existing intake workflow and lineage tool; ORBIT owns runtime,
results, controls, and every T07 game seed.

## Reproduce the actual source package

Download the existing GitHub Actions artifact with the connected GitHub tool:

```text
GitHub.download_workflow_artifact(
  repo_full_name="woahwhattheheck/commons",
  artifact_id=10031005553,
  file_name="titan-t07-public-intake.zip")
```

The ZIP is 424,547 bytes, SHA-256
`06df0f8dcc38d67720526e804ad9f2ad2d58ed39f26e8cdf4f7b5c2c1534e35c`.
Safely extract it into a new cloud directory, retaining its paths. It comes from
[ELM's read-only intake run 34156092496, attempt 1](https://github.com/woahwhattheheck/commons/actions/runs/34156092496),
workflow source `3a866554acf42d81b76d1849c58797375a239f9e`. This component does not
reuse the intake's engine files: use the separately verified official-engine
artifact and the existing evaluator for games.

From this directory:

```sh
python3 normalize_barnyard.py --intake /cloud/intake --output /cloud/barnyard-v7
```

Use actual cloud paths in place of the examples. The destination must be new.
The command binds the receipt to both response bodies, checks the exact notebook
identity and public/version fields, compares every cell's type and source, and
normalizes the fixed-version notebook. It records version number **7** separately
from script-version ID **341074820**. The expected source hash is the inspected
V7 hash, not a latest-version selector.

The actual replay produced `main.py`, 27,244 UTF-8 bytes, SHA-256
`997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6`.
All 31 cell types and source strings match between fixed download and latest
pull. Only cell 15 has a literal `%%writefile` directive. The extractor removes
that directive line and preserves its entire body, unchanged. The other code
cells (visualizations, package generation, examples and games) are not executed.
No adjacent runtime file was emitted by this notebook; static imports are
`base64`, `copy`, `json`, `math`, and `zlib`. That static finding is not a runtime
or dependency-completeness claim.

The output includes `provenance/SOURCE.raw`, the unmodified public pull response
as `provenance/METADATA.json`, `MANIFEST.json`, `INTAKE.json`, and `BINDING.json`.
The binder checks intake-body SHA-256 and size records; these checks preserve the
existing provider receipt, not independent cryptographic authentication of the
provider. Raw notebook metadata and output cells may differ between export
formats; the comparison explicitly covers **cell types and source**, not entire
notebook byte identity.

## Reusable normalizer

Python callers may use `normalize.normalize(Path(...), Path(...), Path(...), ...)`.
The equivalent command for the observed pull schema is:

```sh
python3 normalize.py \
  --input /cloud/intake/barnyard-pull.json \
  --metadata /cloud/intake/barnyard-pull.json \
  --source-pointer /blob/source \
  --version-pointer /metadata/currentVersionNumber \
  --expected-version 7 \
  --output /cloud/barnyard-pull
```

`--format python` preserves a UTF-8 Python input exactly. JSON inputs are either
nbformat-4 notebooks or provider wrappers with an explicitly selected JSON
pointer. The normalizer does not guess source, license or version fields. A
string at the source pointer may itself hold a notebook JSON document or Python
source.

For literal `%%writefile` notebooks, files are resolved in cell order; overwrite
and `-a`/`--append` semantics are retained and documented in the manifest.
Adjacent Python, data, and source files are included. An absolute notebook path
requires an explicit `--notebook-root`, for example `/kaggle/working`. Relative
paths stay inside the new package, and generated files cannot overwrite its
provenance records. File/directory collisions and invalid extracted Python are
reported before publishing the package.

For a notebook with plain Python cells rather than file magics, explicitly
select reviewed cells with repeated `--code-cell INDEX`. Those cells must parse
as ordinary Python and are joined with two newlines in the requested order.
There is no automatic notebook execution, shell expansion, dependency install,
or evaluation of source-building expressions. Compilation checks syntax only.

`--entrypoint` changes the required emitted filename (default `main.py`); it does
not invent an agent wrapper. `--license PATH` retains exact supplied license bytes
and may be repeated. `--license-pointer` records an observed metadata field.
Version comparison reports MATCH/MISMATCH/MISSING/UNCOMPARED; MATCH describes the
selected field comparison only, not a title, URL or legal conclusion. Missing
explicit pointers, duplicate JSON keys, and non-finite JSON evidence are errors.
The tool never replaces an existing destination. It reserves a fresh destination
exclusively and removes its own partial package if the final transfer fails.
Callers must use a destination where they control concurrent writes.

## Source and license evidence

Public pull: <https://www.kaggle.com/api/v1/kernels/pull/romanrozen/strong-barnyard-economist>.
Fixed download: <https://www.kaggle.com/kernels/scriptcontent/341074820/download>.
Author: Roman Rozen. Notebook ID: 129253091. Public pull fields are
`/metadata/isPrivate=false` and `/metadata/currentVersionNumber=7`.

The pull, downloaded page HTML and notebook metadata contain no explicit license
field. Kaggle's indexed legacy notebook page states Apache 2.0; opening that
legacy URL redirects to the exact current URL with `scriptVersionId=341074820`.
`LICENSE-EVIDENCE.json` preserves both observations and their limitation: license
text was visible in the public search excerpt, while the rendered page body was
empty. This is not a claim that the pull API returned a license field. Do not
relabel Arlene's or the engine's license as Barnyard's. Retain author/source
attribution and the applicable Apache license when redistributing the normalized
agent. The standard Commons root Apache license covers this utility's own code;
ORBIT retains ownership of the third-party runtime package and notices.

## Validation and limits

```sh
python3 -m unittest -v test_normalize.py test_barnyard.py
python3 -m py_compile normalize.py normalize_barnyard.py
```

31 local regression methods passed. The real fixed and pull payloads were both
normalized independently and yielded the exact hash above; the pinned intake
binder also passed on the real artifact. Synthetic fixture tests are labeled as
such and do not stand in for that replay. `VALIDATION.json` records the exact
source/test hashes and observed inputs. No source import, policy action, game,
held-seed consumption, Kaggle write, new spending, or owner-PC operation occurred
in this component. No whole-repository CI or leaderboard result is asserted.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
