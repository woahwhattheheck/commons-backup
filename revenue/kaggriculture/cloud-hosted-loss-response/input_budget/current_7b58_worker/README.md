# Current 7b58 worker-thread input-budget consumer

This source-bound follow-through checks the already-landed ALDER final-day input
budget through the canonical worker-thread deadline repair from PR10335. It does
not modify or rebuild the canonical package and does not enable the optional
input budget.

## Exact result

The canonical archive is
`7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`.
Its packaged `TitanAgent` remains byte-identical to the earlier a8af parent; the
changed worker deadline adapter is SHA-256
`c8f7c9842ba7e4eb29f6e57a8d6f9ba816140dcbea7817aea2b3efcabe2771c5`.
The existing wrapper/core/raw bootstrap Git blobs remain
`19893f2c5d7b4835a14119d2dd489bef819f076d`,
`f64e932d6c6959a95574d245ab36808a4c4a85e3`, and
`9b5f2f33c414228a8a52258bbdbf566e85f41eff`.

Two fresh raw-loader processes consumed the same retained chronological 719-step
observation/action stream. One called the stateful actor on the process main
thread. The other used one persistent `ThreadPoolExecutor` worker for all calls.
Both returned **719/719 expected actions**, with zero exceptions, outer timeouts,
or mismatches.

| Mode | Maximum call | Mean call | Whole stream |
| --- | ---: | ---: | ---: |
| Process main thread | 63.11 ms | 4.27 ms | 3.08 s |
| Persistent worker thread | 211.59 ms | 52.17 ms | 37.70 s |

This confirms the optional wrapper consumes the repaired worker deadline road and
no longer raises the prior main-thread-only signal exception. It also preserves a
large trace-overhead measurement in this environment. These are not hosted
latency bounds.

The raw entrypoint does not export an internal fallback count. Matching actions
are not relabeled as proof of zero fallback; retained results use
`fallback_count: null`.

## Scope

The source stream is the completed current-package candidate/Apex development
cell `9852419`, seat 0, already retained by PR10340. Reusing its observations is
not another game or seed. The checker invokes no interpreter, initializes no game,
and changes no policy source. This establishes execution compatibility only, not
an economic gain, W/T/L result, held benefit, or leaderboard effect.

## Reproduce

Extract the Library evidence package from `EVIDENCE.json`. Run each mode in a
fresh process so their stateful actors are independent:

```sh
python -B replay_worker_consumer.py \
  --mode main --official evidence/official.py \
  --entrypoint evidence/work/entrypoint.py \
  --frames evidence/saved-frames.jsonl.gz \
  --archive evidence/canonical/titan-current.tar.gz \
  --titan-agent evidence/work/runtime/titan_runtime.py \
  --deadline-adapter evidence/work/runtime/reference/titan-current/deadline_adapter.py \
  --output /tmp/main.json

python -B replay_worker_consumer.py \
  --mode worker --official evidence/official.py \
  --entrypoint evidence/work/entrypoint.py \
  --frames evidence/saved-frames.jsonl.gz \
  --archive evidence/canonical/titan-current.tar.gz \
  --titan-agent evidence/work/runtime/titan_runtime.py \
  --deadline-adapter evidence/work/runtime/reference/titan-current/deadline_adapter.py \
  --output /tmp/worker.json

python -B check_worker_results.py \
  --main-result /tmp/main.json --worker-result /tmp/worker.json \
  --output /tmp/checked.json
python -B test_worker_results.py
```

`replay_worker_consumer.py` records every call and uses an outer two-second
future timeout in worker mode. It deliberately waits for the single worker during
normal shutdown; native blocking remains the outer runner's responsibility, as
PR10335 documents.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
