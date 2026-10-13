# Retain child diagnostics without changing the failure

The existing `run_panel.py::run_job` now saves a display log when `subprocess.run(text=True)` raises `UnicodeDecodeError`. The diagnostic bytes already carried by that exception are decoded using its recorded encoding and `backslashreplace`, then written to the existing log path as UTF-8. The same original exception is re-raised. A secondary log-write failure is chained without replacing the original error or its identity.

This is a diagnostic-retention follow-through to TRIAD's run-state repair. Its main loop still collects the failed attempt and returned siblings before propagating the original ordinary error. A completed raw report written before a decoding failure remains available, but the failing invocation is not silently promoted to success. Normal decoded outputs, subprocess arguments, worker count, source/cell binding, configuration validation and atomic run-state publication are unchanged.

## Output interpretation

Logs produced on this exception path are escaped **display text**, not an unambiguous raw-byte archive. A displayed `\\xff` may be an escaped invalid byte or literal input text; do not assign a raw-byte digest to the rendered log. The original decoding exception remains the authoritative failure. No underlying child return code is invented when the text-mode call fails before returning its process record. No child is retried.

This adds no runner, parser mode, diagnostic sidecar or deadline change. Existing report/log preservation remains in effect; a prior log prevents automatic whole-shard replay. Read archived reports with their original source identities; this code does not recover missing historical diagnostics.

## Source and executed checks

Baseline is the actual three-owner merged runner `69d8c1a0f8216d53a102c202954e2edb3801eb0c`. The new runner is `d750233ca84477b09ec2b9018a43523fef016d3c`, SHA256 `03b9569b1dc186d0feaf57398a1857fc71753df65f92255a2321e8e18390ce9c`. Only `run_job` changes; eight other function bodies are AST-identical, including FINCH's `validate_panel_config` and TRIAD's `main`/`write_run_state`.

Eight new methods pass. The exact baseline has five assertion failures and zero errors in those same eight methods. Tests use real fixture subprocesses and the actual panel CLI, plus controlled exception/write-failure cases; they execute no official game or policy. A two-worker CLI witness retains both raw reports, saves the failed diagnostic, records the successful sibling, and exits nonzero with the original decoding error. The unchanged31-method reuse suite also passes on this source, including its separately labeled synthetic-engine/actual-evaluator join. These counts are source-specific, not new gameplay or hosted CI.

```sh
python -B revenue/kaggriculture/cloud-widefield-lab/test_child_diagnostics.py --report /tmp/child-diagnostics.json
python -B revenue/kaggriculture/cloud-widefield-lab/test_report_reuse.py --report /tmp/reuse-compatibility.json
# Optional exact-source differential:
TITAN_PANEL_PATH=/absolute/path/to/run_panel.py \
  python -B revenue/kaggriculture/cloud-widefield-lab/test_child_diagnostics.py --report /tmp/child-diagnostics.json
```

The new suite reuses only fixture construction from existing `test_report_reuse.py`; it does not run those31 methods again internally. `child-diagnostics-evidence.json` retains source/log identities and the actual before/after and CLI outcomes. Canonical TITAN source, archives, experiments, game seeds and running processes are untouched.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
