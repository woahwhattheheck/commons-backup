# UIOWA-101 — verified component entry-point catalog

This package answers a practical operator question: **what can I actually run from the published Iowa RFQ preparation repository, at which source revision, with what input/output contract?**

## Search commands

From the repository root (Python 3.10+; no third-party dependencies):

```sh
python3 revenue/uiowa_rfq_18649_component_catalog/browse.py "rebuild"
python3 revenue/uiowa_rfq_18649_component_catalog/browse.py --id recovered_roadmap
python3 revenue/uiowa_rfq_18649_component_catalog/browse.py --status working --format json
python3 revenue/uiowa_rfq_18649_component_catalog/browse.py --base-only --format markdown
```

`browse.py` searches IDs, titles, work orders, commands and input/output contracts.
All case-insensitive query words must match. It combines the original immutable
catalog with `recovered_components.json`, an additive catalog of completed tools.
Every entry retains its own recorded revision, exact source/readme blobs and
sample-evidence basis. No original entry or original snapshot is silently
refreshed; newly recovered entries have distinct stable IDs.

The output includes the literal command and working directory. Multi-command
examples must be run in order; choose fresh output directories. The browser
never executes commands, imports their engines, fetches dependencies or asserts
that a different checkout has the same source. Consult the linked component
README for input preparation, exit states and remaining evidence gaps.

JSON includes complete original entry fields. Text and Markdown show practical
commands and provenance. `--catalog` and `--supplement` accept explicit local
catalog paths; `--base-only` omits the supplement. No query matches is a valid
empty result (exit 0). Missing exact IDs exit 1; unreadable/malformed catalogs or
duplicate component IDs exit 2. Output goes to stdout; diagnostics go to stderr.

It does not infer readiness from folder names. Every entry is bound to a Git blob SHA. Runnable entries carry a command, working directory, source-contract markers, prerequisites, input/output description, and one synthetic/source-backed sample signal. Static/template/incomplete entries are deliberately separated.

## Files

- `component_catalog.json` — machine-readable catalog bound to snapshot `c853c1422fc3e34aabbb54fe205bd9ea5b48bf34`.
- `RUN_MENU.md` — linked operator menu.
- `verify_catalog.py` — stdlib verifier for byte drift, missing paths, command-contract drift, sample evidence, and incomplete-entry transitions.
- `test_verify_catalog.py` — regression tests proving drift and missing-entrypoint states fail closed.

## Use

```bash
cd revenue/uiowa_rfq_18649_component_catalog
python verify_catalog.py
python verify_catalog.py --json
python -m unittest -v test_verify_catalog.py
```

## Status semantics

- **working** — executable source exists at the recorded blob SHA; its advertised command was checked against the source contract and a sample signal is recorded.
- **static** — useful published data/interface contract, no executable entry point.
- **template** — useful worksheet/document bundle, no executable entry point.
- **incomplete** — documentation advertises or implies a runnable entry point that is absent/unusable in the snapshot.

“Working” here is not a claim that this catalog build independently executed every component. The `sample_result.basis` field distinguishes checked-in outputs, source contracts, provider readbacks, and published validation receipts. This avoids turning second-hand execution receipts into new claims.

## Snapshot discipline

The source snapshot is immutable on purpose. New swarm merges do not silently mutate catalog truth. If a source changes or an incomplete entry point lands, `verify_catalog.py` fails and the next operator creates a refreshed catalog revision.

## Boundaries

Everything is preparation/synthetic unless the underlying component states otherwise. No catalog result is a University of Iowa finding, compliance conclusion, release approval, or individual performance score.
