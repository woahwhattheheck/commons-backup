# Failed RPC request and transport evidence

The existing evaluator now attaches `rpc_failure` to failed `Actor.act` responses and unsuccessful startup responses. `play` carries that same object into `games[i].failure`; the existing final/progress writers retain it after actor cleanup. Use the usual evaluator command. No new runner, replay, policy option or timeout setting is needed.

This closes a specific diagnostic gap: an action timeout previously retained only an error, prior returned-call timings and final process resource totals. Those aggregates cannot reconstruct the original failed observation or identify the failed call's execution time.

## Read an existing failure

```python
import hashlib
import json

report = json.load(open("tournament.json", encoding="utf-8"))
failure = next(g["failure"] for g in report["games"]
               if (g.get("failure") or {}).get("rpc_failure"))
evidence = failure["rpc_failure"]
request = evidence["request"]
if request["disposition"] == "complete":
    wire = request["wire_utf8"].encode("utf-8")
    assert len(wire) == request["wire_bytes"]
    assert hashlib.sha256(wire).hexdigest() == request["wire_sha256"]
    packet = json.loads(wire)
    observation, configuration = packet["observation"], packet["configuration"]
```

The packet contains exactly what this failed actor was sent, including its own private game state. It does not add the rival's private observation, current action, or engine `info`. Treat retained responses as untrusted diagnostic data, not executable instructions. Replaying one observation into a fresh actor is **not** restoration of the original persistent actor state; source and prior-call history remain necessary.

## Schema and limits

`schema_version=1`, `scope=parent_observed_failed_rpc`. Request identity covers the canonical JSON bytes **including the final newline**. A request within the existing 2 MiB packet limit is retained in full; an oversized request keeps length/hash but no inline body. Startup has no request; serialization failure has no invented packet or hash. Disposition distinguishes all four cases.

`transport` reports relative parent-side wall times from exchange entry, bytes written, bytes read, and any response already buffered at entry. `write_complete_seconds` establishes only that bytes were accepted by the pipe, not that the worker consumed them. `first_response_seconds` and `response_complete_seconds` do not isolate deserialization, computation or serialization. Response evidence preserves a complete consumed line, including its newline, or the currently observed partial buffer. It hashes all those observed bytes and retains at most 64 KiB as base64, with explicit truncation. Read counts can exceed one selected response line when the pipe returns several lines.

`worker_call_seconds`, `worker_call_cpu_seconds` and `worker_stage` remain null. Process totals and previous successful calls are not substituted for missing failed-call measurements. Existing original error fields and resource collection remain intact. Parent evidence overrides any same-named worker field.

Successful response schemas are unchanged. Success adds only transient counters/clock reads to the existing exchange and drops its retained request immediately; hashing/base64/failure formatting run only after failure and outside the recorded RPC interval. No speed or deadline-cause claim follows from this instrumentation. Failure formatting adds ordinary result-building overhead after the exchange.

## Source-bound validation

Original evaluator blob `0eead824257c0a6bd01b5b8c7828f30410546635`; repaired evaluator `ab1ac46a5cd3dd0bfda0afdbaf5a5f73320f863d` (SHA256 `041eb75afd6b4ff5db7f0dfb2825b0ef7c555b3f0c443e70756da68f112a9347`). New test blob `e657a896c2f5deac22505f9b74c1b44fe2825e00`.

Eighteen new methods pass using real child processes and pipes, plus one explicitly synthetic `play`/report-plumbing fixture. Exact original source fails eighteen new-contract assertions with zero execution errors. These are missing evidence-contract assertions, not eighteen independent policy bugs. Twenty-five unchanged actor, summary and final-resource methods also pass, with zero skips. Twenty unrelated function/method bodies, including worker, play, main and report writing, are AST-identical to the original. Concurrent CLI finalization work is a separate compatible change.

```sh
python -B revenue/kaggriculture/cloud-eval/test_rpc_failure_evidence.py --report /tmp/rpc-failure-results.json
cd revenue/kaggriculture/cloud-eval
python -B -m unittest -v test_evaluator.ActorTests test_evaluator.SummaryTests test_final_usage
# Differential against a saved original:
TITAN_EVALUATOR_PATH=/absolute/path/to/original/evaluate.py \
  python -B test_rpc_failure_evidence.py --report /tmp/original-rpc-failure-results.json
```

`rpc-failure-evidence.json` preserves exact source identities, local counts, witness outputs and full-log hashes. No official game, scored panel or game seed was consumed. Historical missing requests are not retroactively recovered, the original RPC incident is not diagnosed, and no running process or canonical submission package is changed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
