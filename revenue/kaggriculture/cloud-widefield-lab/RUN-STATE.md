# Wide-field run-state retention

The existing `run_panel.py` CLI now records all returned sibling job results after
an ordinary runner exception, then re-raises the first exception with its original
traceback. All jobs were already submitted before collection in the original
implementation; the thread-pool context already waited for them. This change
collects their results instead of dropping them. It adds no retry, evaluator,
policy invocation, seed, thread count or new runner.

The previous actual-source witness used two evaluator subprocess fixtures. One
emitted an invalid UTF-8 byte in its diagnostic output; the other wrote a complete
synthetic report. The successful report existed, but `future.result()` stopped
collection before `run-state.json` was written. The corrected source preserves a
failed-attempt row and the successful row, while the original decoding exception
still causes a nonzero exit. These are executable transport fixtures, not games.

## Existing command, additive failure row

No new option is needed. Continue using the existing invocation:

```sh
python revenue/kaggriculture/cloud-widefield-lab/run_panel.py \
  --config /path/to/existing-config.json --output /path/to/output --jobs 2
```

Returned successful, reused and failed job dictionaries are retained unchanged.
When a worker raises an ordinary exception instead of returning a dictionary,
its run-state row contains the original job fields, `status="failed"`, and:

```json
{"failure":{"kind":"runner_exception","type":"ValueError","message":"original diagnostic"}}
```

This records a failed runner attempt, not a completed game or an inferred score.
`KeyboardInterrupt` and `SystemExit` are not converted into result rows. A failed
checkpoint still raises; if there was already a worker failure, that original
exception remains primary and the publication failure is chained to it. The
normal returned-failure exit code remains 1. No claims are made about uncollected
results after cancellation, output failure, process death or a hanging worker.

## Single-file publication

`write_run_state(path, records)` serializes the entire UTF-8 payload first, writes
and flushes a same-directory temporary file, checks its write length, fsyncs it,
and atomically replaces the destination. The checkpoint is written before its
stdout notification, so a broken display pipe cannot erase that returned row.
Serialization, staging, short-write, fsync or replacement failure leaves the
previous destination unchanged. A real child exiting during partial staging
leaves the old whole JSON rather than truncating it.

This is not a transaction with raw reports/logs, a multi-writer protocol, or a
power-loss durability guarantee. A hard exit or failed cleanup can leave an
unreferenced temporary file. Existing output ownership and separate
candidate/opponent/evaluator identity checks still apply. TANDEM's independent
reuse/result-binding work in `valid_report`/`run_job` is a different change.

## Reproduce the changed boundary

```sh
python -B revenue/kaggriculture/cloud-widefield-lab/test_run_state.py -v
TRIAD_PANEL_SOURCE=/path/to/baseline/run_panel.py \
  python -B revenue/kaggriculture/cloud-widefield-lab/test_run_state.py -v
```

Executed on Python 3.13.5: 19 final methods pass, with no failures or errors.
The same suite on original Git blob `f0e6fde861be48a92e8455d7ad6ac69b477a94ad`
fails 11 methods; five explicitly require the new staging boundary, so this is
not eleven independent defects. `RUN-STATE-VALIDATION.json` records exact source,
test and log identities plus the separate original/changed real-subprocess
witnesses. The final process test substitutes only a fixture worker under the
real `main` and thread pool, so future changes to report eligibility do not
silently redefine this checkpoint test. No policy or official engine is loaded.

The `sha256`, `valid_report` and `run_job` ASTs are identical to the original for
this patch. Only imports, `main` collection/publication, and the new writer change.
The canonical TITAN runtime/archive and all historical game results are untouched.
Full original/final logs, baseline witness and exact patch are retained in the
separate TRIAD run-state evidence delivery. Hosted checks, when available, remain
separate from these local tests; no whole-repository CI result is implied.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
