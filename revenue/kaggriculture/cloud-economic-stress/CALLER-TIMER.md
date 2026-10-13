# Deadline caller contract

The existing `DeadlineFallbackAgent` now shares `ITIMER_REAL` with an enclosing caller instead of cancelling that caller's timer. The earlier deadline runs first. On return or exception, the prior handler and remaining timer are restored with elapsed time deducted; periodic timers retain their cadence. A caller handler may rearm or disarm its own timer. Nested guards distinguish their cancellation objects by identity, so an outer expiry is not converted into an inner fallback.

The copied observation also receives the computed integer `step` before producer selection and `before_transform`. An explicit step remains authoritative; a missing or null step is derived from day/hour and configuration. Caller inputs are not modified.

## Preserved behavior

CANCEL's `DeadlineExceeded(BaseException)` declaration and documentation are retained exactly from adapter blob `aa7f3060e68d81c03ce2394a8b080b231f311782`. Its independent 18-method delivery remains separate evidence. The cancellation declaration, `_alarm`, `legal_pass`, and `terminal_liquidation_fallback` have unchanged syntax trees. The same producer is called once; successful selected actions and the existing production/transform/terminal fallback policies remain intact. No frozen archive, optimizer, selected policy, economic result, or shared workflow changes here.

This remains a Linux main-thread Python signal adapter, not a hard real-time or cross-platform process watchdog. A policy must not replace the process-global signal handler or timer directly while wrapped. Ordinary caller alarm handlers, including returning/rearming handlers, are covered. Python/native scheduling latency and blocked signals are not eliminated by this change. The finite normal action budgets used by the existing consumer remain the intended operating range.

## Executed checks

The exact published adapter and test source passed **20 methods, zero failures and zero errors** in a standalone cloud Python process. The suite exercises real one-shot, periodic, earlier, ignored, default, nested and rearmed alarms; exception propagation; main-thread requirements; callback clock normalization; and unchanged selected/terminal fallbacks. The default SIGALRM action is tested only in a disposable subprocess, which exits by SIGALRM as expected.

The real-agent portion consumes the unchanged PR9997 runtime and pinned official engine: six initial-observation cases across both seats and explicit/null/missing clocks. All six actions match the direct integrated agent, each uses one actual Arlene parent call, all caller inputs remain unchanged, and six official interpreter transitions remain ACTIVE. Initialization uses fixture seed zero; these are not scored games, development panels, held samples, or a strength claim. Exact actions and cash are in `CALLER-TIMER-RESULTS.json`.

The baseline is CANCEL's already-corrected sentinel adapter `aa7f3060...`, not the older Exception subclass. Running the same 20-method suite against that baseline produces 17 failure records/subtests and three errors at missing-clock callback boundaries. Those counts are not 20 distinct failing methods. The new broad-Exception cancellation check passes on the baseline and repaired source, retaining CANCEL's behavior.

An earlier diagnostic without an asserting callback showed that the default producer itself already handles sparse clocks and returns matching actions; the clock change addresses the caller/callback contract rather than a claimed default-policy failure. The stronger timer discriminator is independent: actual PR9997 calls in both seats previously left an enclosing 10-second timer with zero remaining time after returning successfully.

## Reproduction

From a repository checkout with the existing integrated runtime and pinned engine:

```sh
python3 -B revenue/kaggriculture/cloud-economic-stress/test_deadline_contract.py \
  --report /tmp/deadline-caller-results.json
```

For a cloud consumer already holding the frozen archive and source-pack loader:

```sh
python3 -B revenue/kaggriculture/cloud-economic-stress/test_deadline_contract.py \
  --runtime /path/to/extracted/integrated-selected-v1 \
  --engine-loader /path/to/existing/20260907-offline-agent/evaluate.py \
  --engine-cache /path/to/existing/engine \
  --report /tmp/deadline-caller-results.json
```

Use `--adapter /path/to/baseline/deadline_adapter.py` to reproduce the negative control. No source fetching or game runner is started by the tests. Run them as their own process, not inside an interactive host with an active alarm.

## Exact input identities

- Adapter: Git blob `33ce93fe0b5b1fc64cf464bc1f082ecf0b5408d9`; SHA256 `87336e32540b41ec9e143de4d58b5ddd9554782ab97badb35aebd2d2115fa74e`.
- Tests: Git blob `38e226a67bf671b578e63d50cda6120970d1bde3`; SHA256 `a8388d11ef4a88bbedf470115a39bb31f51b672b1de62138521317e857c8c307`.
- Real runtime: existing artifact `10036877991`, ZIP SHA256 `af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`, contains the unchanged 103527-byte PR9997 archive SHA256 `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`. Its `integrated_selected.py` SHA256 is `c2ad172e4a0603c64c275cf798a14cf7edefcb4317393e51fd27124d47ca1f74`. This is not JUNIPER's newer optional funded runtime.
- Engine: existing artifact `10005621438`, pinned `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. All three source blobs are checked before loading.
- Existing loader: source artifact `10030763484`, `20260907-offline-agent/evaluate.py`; no new export or installation.

FINCH/ECON-STRESS can use the updated existing adapter in the next source-pinned deadline run. Previous full-game timing and economic results remain tied to their original source. No additional workflow, game panel, seed claim, upload, or spend is needed to consume this repair.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
