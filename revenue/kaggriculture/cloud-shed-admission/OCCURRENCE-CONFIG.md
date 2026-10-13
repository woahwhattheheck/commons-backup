# Admission occurrence and configuration contracts

Two in-place compatibility repairs; no current-agent release or policy promotion.

Baseline runtime Git blob: `516330c5fb09507a57fdb2a06cd73d247ed25d82`.
Repaired runtime Git blob: `fe2f631b47c8245097aa4a7c5863138ce2826a62`.

`_liquidate` treats each SELL slot as a separate execution occurrence. Shared Python list objects no longer let zeroing a duplicate rewrite the first sale. Slot order and the original input are preserved; unchanged non-SELL aliases retain their old behavior.

`TerminalAdmissionAgent` passes the supplied configuration through to the existing scenario callback without converting its Mapping class into a dict. Missing configuration still defaults to `{}`. Public day/hour normalization, optional configuration, original exception propagation, and one producer call remain intact.

## Retained executed validation

The exact repaired source passed 12 occurrence + 10 configuration + 23 original admission + 6 actual-PR9997 integration methods: 51 total, 22 newly authored and 29 compatibility methods. Original runtime fails both new suites and the existing attribute-access callback test. The occurrence suite records 81 queue comparisons, 8 full-transform comparisons, and 56 native terminal transitions. The original occurrence suite reports 51 failed assertions/subtests across 12 methods, not 51 failing methods; the configuration baseline has 5 failures and 1 error across 10 methods.

The constructed capacity-3 idle-rival witness returns 600 rather than 73 after repair, matching the equal JSON-valued queue in both positions. This is conditional mechanics evidence, not a natural-game win. Eight previously saved natural terminal states reproduce identical cash and actions via 16 final transitions. No full games, held seeds, or rating evidence were added.

Publication consumes the already-executed source and reports, not a newly rerun panel. All 158 original package manifest entries and all three published Python blob identities were verified during delivery. The older SOURCE.json, RESULTS.json, INTEGRATED evidence and original suites remain unchanged and retain their original source scope.

## Reproduction

Set the existing `TITAN_REPO_ROOT`, `TITAN_ENGINE_DIR` and `TITAN_INTEGRATED_ROOT` variables, then run:

```sh
python -B revenue/kaggriculture/cloud-shed-admission/test_order_occurrences.py
python -B revenue/kaggriculture/cloud-shed-admission/test_scenario_configuration.py
python -B revenue/kaggriculture/cloud-shed-admission/test_terminal_admission.py
python -B revenue/kaggriculture/cloud-shed-admission/test_integrated_consumer.py
```

`TITAN_ADMISSION_SOURCE` binds either new suite to an exact historical runtime; optional `TITAN_OCCURRENCE_REPORT` / `TITAN_CONFIGURATION_REPORT` save source-bound JSON. The existing replay_evidence.py consumes the unchanged reached-terminal-cases.json.xz.b64 to reproduce the eight saved states.

Complete original/intermediate/final sources, logs, interpreter witnesses, licenses and offline fixtures remain in `TITAN-admission-repair-evidence-20260908.zip`, SHA256 `3c90327dc66c575a4926f6c30a1309ccf74bfb75a0441cffaf6cfcda1970ef6b`. Its `run_checks.py --include-before` reproduces all four suites, saved-state correspondence, and historical failing controls without network access. The package's historical LOCAL_TESTED_NOT_LANDED record describes its state before this delivery and is preserved, not rewritten.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
