# Queue CLI input preservation

Prepared repair to the existing `queue_delta.py` command line. **Not published
or merged.** No comparator, simulator, decision rule, controller, or canonical
release is added or changed.

Before loading the engine or parsing the input, `main` checks whether `--output`
resolves to the same path or filesystem object as the engine source, input JSON,
or the executing CLI file. Direct paths, symbolic links, hard links, directory
aliases and normalized relative paths are covered. An alias returns the usual
usage error (exit2) without modifying an input or running a market comparison.
A symbolic-link cycle produces a clear usage error instead of a traceback.

A separate report file, an existing unrelated report, and stdout remain usable.
Unknown comparisons still write the original unknown report and return exit2;
they are not converted to successful selections. Runtime function/class bodies
other than `main` are AST-identical to the baseline.

## Executed validation

11 focused methods pass. The exact original CLI (Git blob
`b95dff0010cf70941cc96e7f416798d36a8aa57d`) produces 12 failing subcases and one
error subcase in the same tests. These are multiple cases of input preservation
and error reporting, not thirteen independent defects. Every destructive
negative control ran only on fresh temporary copies; retained inputs and source
archives remained unchanged. The first implementation's symlink-cycle failure
is retained separately from the passing final result.

Two existing development market states retain complete before/after reports,
excluding the newly measured elapsed time. The buyer case remains +17 own/-17
rival; the seller case remains -70 own/+70 rival. Both keep action_selected=false.
No full game, policy, fresh seed or held-out evaluation was run. These market
stage checks are not competitive or whole-agent performance results.

## Reproduce with the delivered fixture closure

```sh
python test_queue_cli_input_aliases_iris.py \
  --engine-source /path/to/engine/kaggriculture.py \
  --case /path/to/fixtures/seller-case.json
```

For the deliberate negative control, add `--source /path/to/baseline/queue_delta.py`.
The original engine and retained cases are in the companion private delivery;
no opponent-private state is inferred or used as a runtime feature. Existing
engine and source licenses are preserved. Full hashes, logs and actual result
counts are recorded in `CLI-INPUT-PRESERVATION-IRIS.json` and the archive manifest.

The patch is based on the exact published blob above. It has been git-apply
checked and byte-verified locally; compose with any newer owner change rather
than overwrite an entire current file from this archive.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
