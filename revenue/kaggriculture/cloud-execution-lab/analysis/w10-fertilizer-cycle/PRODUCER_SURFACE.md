# W10 producer-surface inventory

`producer_surface_scan.py` turns the next integration handoff into a content-addressed source map. It statically scans the existing cloud-execution Python tree, excluding this W10 analysis directory, and ranks files and symbols that contain lifecycle vocabulary related to:

- fertilizer application;
- production/yield;
- harvest;
- deposit/storage/inventory;
- sale, market, price, revenue, or cash;
- ticks, workers, movement, and actions; and
- protected commitments, reserves, and shortfalls.

The scanner is a navigation aid. A lexical or AST hit does **not** prove that a symbol executes in a game, owns the canonical producer, or implements the semantics suggested by its name. It never edits source and never authorizes a producer change.

## Run it

From the repository root:

```bash
python revenue/kaggriculture/cloud-execution-lab/analysis/w10-fertilizer-cycle/producer_surface_scan.py \
  --root . \
  --scope revenue/kaggriculture/cloud-execution-lab \
  --output /tmp/titan-w10-producer-surface.json \
  --pretty \
  --allow-empty
```

Without `--allow-empty`, the command exits `0` only when at least one file contains fertilizer vocabulary plus at least one downstream harvest/storage/sale phase. With `--allow-empty`, a complete `NO_SURFACE` report is still considered a successful scan.

## What the report binds

The deterministic `titan.w10.producer-surface-scan/v1` report includes:

- the repository-relative scope;
- explicit file-count, byte-size, and result-count limits;
- every scanned candidate’s repository-relative path, byte length, SHA-256, score, lifecycle phases, token line numbers, and AST symbols;
- syntax errors instead of silently dropping malformed candidates;
- files skipped for size, UTF-8, or read errors;
- a warning against treating ranking as runtime proof; and
- a self-verifiable `result_sha256` over the normalized report.

Comments are ignored so documentation alone cannot create a candidate. Identifiers and string literals are considered because producer actions and engine messages may carry the only stable event vocabulary. Symlinked directories, root escapes, oversized files, excessive file counts, and self-analysis hits fail closed or are explicitly excluded.

## Hosted artifact

The `titan-w10-producer-surface-scan` workflow proves the 12-test scanner contract, scans the live cloud-execution tree at the exact PR SHA, writes the top 20 candidates to the job summary, and uploads the full JSON inventory as a SHA-named artifact.

The current owner of an existing producer path should use that artifact to select the narrowest instrumentation seam, then emit the strict `trace.schema.json` counters and run the paired certificate/matrix gates. The scanner itself should not be wired into gameplay and should not be used as a replacement for an observed fertilizer → harvest → deposit → sale → net-cash trace.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
