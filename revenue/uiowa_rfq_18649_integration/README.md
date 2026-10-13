# UIOWA-098 — runnable preparation-kit integration

This directory completes the executable layer of the shared UIOWA-098 integration path. It **extends** the existing `interface_map.json` and `adapter_tabular.py`; it does not replace them or introduce another assessment engine.

`workflow.py` runs a representative synthetic preparation flow against components that are actually present in the checkout:

1. reads and enforces `interface_map.json`;
2. invokes the existing delivery-metrics and prioritization adapters;
3. maps the observability and test-data fixtures using the same component-qualified identity rule;
4. exercises the existing workbench `CompilerAdapter().inspect(...)` path and preserves its untrusted 12-cell matrix and receipt;
5. executes the native rating-composition fixture without averaging maturity/confidence into a new score;
6. executes the native prioritization profiles, preserving held/missing estimates;
7. runs the published traceability-rehearsal validator over evidence → finding → recommendation → report statements;
8. validates `presenter_run.json`, the separately observed presenter-machine execution receipt; and
9. reports prepared downstream components such as roadmap/review/report as `NOT_YET_MERGED` when absent instead of simulating them.

## Run

```bash
cd revenue/uiowa_rfq_18649_integration
python workflow.py --out /tmp/uiowa-098-run
python -m unittest -v test_workflow.py
```

Outputs are `integration-run.json`, `component-records.csv`, and `RUN_REPORT.md`.

## Identity and semantic rules

- Canonical IDs are `component:native_id`; identical-looking IDs from different components never silently coalesce.
- ESS/RIS/IAM/CROSS is the only shared group vocabulary in the integration envelope.
- Native maturity, confidence, coverage, priority scores, and hold states remain native to their component. The workflow joins them for context but does not rescale or average them.
- Missing values stay missing. Missing components stay `NOT_YET_MERGED`.
- Source file SHA-256 values are retained on mapped records.
- The presenter timing in `presenter_run.json` is one observed synthetic run, not a performance guarantee.

## Scope boundary

All checked-in data used by this workflow is synthetic/public preparation material. The workflow does not create University findings, contact anyone, schedule anything, submit the bid, authorize acceptance, or make procurement/vendor recommendations.
