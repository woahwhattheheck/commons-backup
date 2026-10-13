# Source-bound wide-field report reuse

`run_panel.py` still runs the existing evaluator and skips completed matching shards. Reuse now checks the requested seed/opponent/seat cells and declared direct-source identities, rather than accepting any complete report with the same number of rows. The same check examines newly produced reports before labeling the job complete.

## Existing reports and new jobs

A matching report returns `reused-complete`, with its exact parsed-byte SHA256 and the requested `source_binding`; no evaluator is launched and no report or log is rewritten. Duplicate cells cannot substitute for a missing seat. Candidate function, candidate/opponent entry bytes, evaluator/default-loader bytes, all three engine files, episode length, role RNG and limits must match. Terminal scores must be finite numbers, statuses complete, and any progress marker complete.

An existing mismatched, incomplete or malformed report returns `status=failed`, `reason=existing_evidence_not_reusable`, with specific `validation.problems`. Its bytes and prior log remain untouched. A log without a report is also retained rather than overwritten. An unavailable source returns `binding_unavailable`. These dispositions do not relabel or automatically replay historical attempts. Use the already-existing explicitly assigned failed-cell replay for a retry, or a distinct assigned output for a different comparison; do not delete the original evidence to make a reuse check pass.

A job with no prior report/log invokes the same evaluator. The formerly implicit defaults are now explicit: role RNG20260907, action RPC1.0s, startup10.0s, inter-step game deadline120.0s, and the evaluator's existing sibling loader. No timeout is enlarged and no worker scheduling change is made. Source identities are checked again after return; detected changes or unavailable files prevent a completed-job label but preserve the produced report/log.

## Scope of the check

This binds **declared direct files and requested cells**, not every imported module, self-read data file, Python version, host, concurrency condition or actual historical execution. Keep the experiment's existing complete source/environment manifest. A matching stored report is reused evidence, not a newly executed sample. `official_starter` uses the engine identity without inventing a Python entry file. Unknown annotations remain intact.

`valid_report(path, expected)` remains a structural boolean helper; it is not a source-bound reuse verdict. `run_job` always supplies the full binding. The existing CLI and `sha256` bodies remain unchanged in this delivery; TRIAD owns the separate run-state exception/atomic-publication composition. This is not multi-writer protection: do not run competing panel invocations against the same output.

## Executed validation

Original runner blob `f0e6fde861be48a92e8455d7ad6ac69b477a94ad`; new runner `df9c37911f185ec2dabe915e7f8b5ffa522cd0d7`, SHA256 `aea9b62ffd7db9d17dc20f1f46ed6bbd604f87c4eb44550db9806d01a7f98f03`. Test blob `c4769371ea6a8026a3b80d33f8a47b9e9e37a520`.

All31 new methods pass on CPython3.13.5/Linux. Exact original has32 failing assertions/subtests and4 errors across those same31 methods, not36 independent defects. Tests cover same-count wrong identities, duplicate cells, malformed/incomplete evidence, orphan logs, changed sources, exact reuse and real fixture subprocess/CLI behavior. One joined case uses actual evaluator `c5736010` main/play/Actor/worker/report code, with only engine construction replaced by an explicit fixture:2 synthetic episodes and4 fixture-agent calls, no official game or policy panel. Its actual report passes the new reuse path unchanged.

```sh
python -B revenue/kaggriculture/cloud-widefield-lab/test_report_reuse.py --report /tmp/report-reuse.json
# The test normally uses the sibling current evaluator. To bind another exact source:
TITAN_EVALUATOR_SOURCE=/absolute/path/to/evaluate.py \
  TITAN_PANEL_PATH=/absolute/path/to/run_panel.py \
  python -B revenue/kaggriculture/cloud-widefield-lab/test_report_reuse.py --report /tmp/report-reuse.json
```

`report-reuse-evidence.json` records source, test and log identities and the executed outcomes. No existing WIDEFIELD result is asserted to be misbound; the original defect was reproduced on detached fixtures. No official game seed, canonical runtime/release, archived experiment, running process or provider submission was changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
