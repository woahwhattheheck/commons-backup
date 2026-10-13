# Retained-trace throughput diagnostics

Offline diagnostics for an existing TITAN paired-trace bundle. These tools apply the supplied deterministic mechanics to copies of recorded observations. They do not invoke a policy, initialize games, reserve seeds, edit the bundle, change the canonical agent, or submit to a provider.

`audit_throughput.py` distinguishes productive harvests, earlier-worker depletion, initial zero yield, immature crops, and missing units. It applies the complete same-turn seed preflight before ordered unit actions and accounts for destructive explicit-DROP overflow. Its terminal offer check concerns requested sales, not filled sales.

`audit_boundaries.py` applies the supplied official market processor before automatic inventory deposit. It compares both seats' resulting private state and cash with the next retained observation, and checks terminal cash and remaining products after actual market processing. Outputs contain private game information: keep input bundles and generated reports in participating-owner private storage, not this directory in Git.

## Input and execution

Use Python 3.10 or later in an existing cloud work environment. The programs use the standard library plus the trusted mechanics and evaluator loader supplied in the bundle. Those Python files are executed when imported; use the source-frozen bundle whose provenance you already know. Keep its upstream licenses and notices. No engine or replay is redistributed here.

The expected input layout is:

```text
BUNDLE/
  FINAL-SUMMARY.json
  CURRENT-ARCHIVE.json
  candidate/mechanics.py
  candidate/checks/reference/evaluator/loader.py
  vm/engine/engine/kaggriculture.py
  vm/engine/engine/kaggriculture.json
  vm/engine/engine/utils.py
  ... reports and compressed paired traces referenced by the summary ...
```

`FINAL-SUMMARY.json` supplies `operation`, `archive_sha256`, and a `games` list with `report` and `report_sha256`. Each report supplies `trace_file`, `trace_file_sha256`, `archive_sha256`, and `game` metadata (`status`, `candidate_seat`, `steps`, `scores`, `opponent`, `seed`). Trace files are gzip-compressed JSON lists. A row contains `seat`, `step`, `observation`, `configuration`, and `response.action`.

These are consumers for complete retained paired traces, not generic hosted-log readers. Both seats, next observations at day boundaries, and the terminal turn must be present. Paths and hashes are checked against the retained bundle's metadata; this does not independently authenticate that metadata. Missing frozen engine inputs are rejected before the preserved loader is called. Keep the original bundle unchanged and place all outputs elsewhere.

From this source directory, with `ROOT` set to the extracted bundle:

```bash
ROOT=/mnt/data/retained-titan-bundle
OUT=/mnt/data/throughput-diagnostics
mkdir -p "$OUT"
python -B test_throughput.py --bundle-dir "$ROOT" --report "$OUT/tests.json"
python -B audit_throughput.py --bundle-dir "$ROOT" --output "$OUT/unit-phases.json"
python -B audit_boundaries.py --bundle-dir "$ROOT" --output "$OUT/boundaries.json"
```

The unit-phase command also accepts `--limit N` for a positive prefix of the retained report list. Its count is `games_read`, never games newly executed. The boundary command expects the complete report format above. Existing output files at the specified paths are replaced; choose new output paths to preserve earlier reports.

## Validation and scope

The 24 focused tests use synthetic states with the supplied official primitives, including ordered harvest depletion, atomic seed cancellation, shared DROP capacity, nonmutation, market-before-deposit ordering, and actual sale fills. They passed in the publication cloud run using the frozen engine commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; the test JSON records the loaded engine hashes.

These tests and analyses add zero full games. Diagnostic no-ops or losses do not establish that a replacement action is legal, profitable, or a win-rate improvement. Evaluate an actual policy change separately with its complete funding, downstream sale decisions, and composition effects. This publication contains only reusable diagnostics, their tests, and this interface description; private tactical components, original traces, and economic result packets remain separate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
