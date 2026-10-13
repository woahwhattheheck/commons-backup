# Workflow sparse-checkout Python import closure

`tools/workflow_sparse_import_closure.py` compiles a GitHub Actions job's
repository-local Python import closure and compares it with that job's literal
`actions/checkout` sparse checkout.

It exists for a recurring failure class: a workflow selects a wrapper or test
entrypoint but omits a newly extracted sibling module. The workflow then fails
only after a hosted runner imports the missing file. The compiler makes that
mechanical dependency visible before execution.

## Safety and scope

The compiler reads workflow and Python bytes as data. It never imports or
executes repository code and never invokes a workflow. It adds no authentication,
permission check, branch rule, queue, merge action, or workflow.

A `PASS` is deliberately narrow: every repository-local file that can be
mechanically resolved from a discovered Python entrypoint is selected by the
literal sparse checkout in effect for that later step. It is not a statement
that tests passed or that third-party packages exist.

`UNKNOWN` is not green. It records a surface the compiler cannot reduce without
inventing semantics, including dynamic imports, inline/dynamic sparse inputs,
negative or glob sparse patterns, and implicit test discovery. `FAIL` is used for
mechanically proven omissions, malformed configured workflow paths, unreadable
or syntactically invalid local Python, and unresolved relative imports.

Jobs with ordinary full checkout, artifact-only source restoration, or no
recognized Python entrypoint are `SKIP`; the compiler makes no closure claim for
them.

## Recognized entrypoints

The shell extractor recognizes separate commands and ordinary continuation
lines for:

- `python`, `python3`, versioned Python, and PyPy script execution;
- `python -m package.module`;
- `python -m unittest` with explicit file or dotted module selectors;
- `pytest` / `python -m pytest` with explicit Python targets;
- `python -m py_compile` with explicit Python files.

Environment assignments plus `env`, `uv run`, `poetry run`, and `pipenv run`
prefixes are handled. Inline `python -c` source is not reinterpreted.

The AST closure includes:

- ordinary absolute imports that resolve inside the repository;
- relative imports and package `__init__.py` files;
- locally resolvable `from package import child` submodules;
- both sides of `try` / `except ImportError`;
- literal `importlib.import_module()` and `__import__()` calls.

A nonliteral dynamic import is reported as `UNKNOWN`. External standard-library
or installed-package imports are outside this compiler's claim.

## Sparse-checkout semantics

Literal entries are normalized to repository-relative POSIX paths. An exact file
selects that file. An existing directory selects its descendants. Blank lines
and comments are ignored.

Globs, negative entries, expressions, parent traversal, backslashes, and other
unsupported pattern forms are surfaced as `UNKNOWN`; they are never silently
treated as complete coverage.

Checkout state is job-local and step-ordered. A later checkout replaces the
selection used for later run steps. A run before checkout or after an ordinary
full checkout is not represented as a sparse-closure pass.

## Usage

Audit the checked contract:

```bash
python tools/workflow_sparse_import_closure.py \
  --root . \
  --config ci/workflow-sparse-import-closure.json \
  --out /tmp/workflow-sparse-import-closure.json
```

Audit selected workflows without creating a config:

```bash
python tools/workflow_sparse_import_closure.py \
  --root . \
  --workflow .github/workflows/coordination-state.yml
```

Audit every `.yml` and `.yaml` workflow:

```bash
python tools/workflow_sparse_import_closure.py --root .
```

Exit status is `1` only when the report aggregate is `FAIL`, `2` for malformed
invocation/config, and `0` for `PASS`, `UNKNOWN`, or `SKIP`. Consumers must read
the report status rather than equating exit zero with proof.

## Receipt

The output is canonical, stable-order JSON. `receipt_sha256` is SHA-256 over the
same report without the receipt field, encoded as compact UTF-8 JSON with sorted
keys. No timestamps, absolute host paths, traversal order, or process state enter
the receipt.

Every missing sparse dependency includes its entrypoint and import chain. The
checked config currently names the coordination-state and backup-ref workflow
families that produced the motivating wrapper/core omissions.

## Validation

`test_workflow_sparse_import_closure.py` covers direct and transitive omissions,
relative and absolute imports, package initializers, wrapper/core extraction,
both `ImportError` roads, module and explicit test entrypoints, directory versus
file selection, CRLF and ordering stability, syntax failure, dynamic import,
unsupported sparse patterns, full-checkout non-claims, and receipt binding.

Run both interpreter modes:

```bash
python -m unittest -v test_workflow_sparse_import_closure.py
python -O -m unittest -v test_workflow_sparse_import_closure.py
```

When the test runs from a complete Commons checkout, it also compiles the
configured current repository contract and fails on a mechanically proven
omission.
