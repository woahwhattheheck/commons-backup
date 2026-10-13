# Hosted worker-thread boundary validation

This is ECON's independent consumer validation of the canonical TITAN
worker-thread deadline repair.  It does not implement or modify the repair and
does not publish or upload a submission.

The input was frozen at merge
`7c50bbfb41027f31a2d4bc9470424e815f1fcef1` (PR 10335), source commit
`c776ce382ccad74dc32e08cc7bb1fc7da4e6c739`, archive SHA-256
`7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`
(286356 bytes), and source-manifest SHA-256
`e64c1224a3f1ac824b982d4b36658906bd81c5117b0feab7944d34d1348baff7`.
Later movement of `main` was not consumed.

`run_worker_episode.py` is the portable follow-on runner and invokes the exact packaged official
`build_agent`/`get_last_callable` definitions.  The candidate's first source
execution and all 719 actions occur in one persistent non-main worker.  The
official engine advances seed 9922999 with TITAN in seat 0 and the official
starter in seat 1.  `--outer-timeout` is an independent whole-call limit; it
does not replace the runtime's own one-second deadline.

The executed Python 3.11.15 harness itself is preserved byte-for-byte as
`executed-runner.py.gz`; it used the byte-identical pinned official loader
functions from `reference/evaluator/official.py`.  The result is `RESULTS.json`;
the full per-action and per-bank trace is retained in
`independent-worker-episode.json.gz`.  A separate
cold process-main-thread call is in `independent-main-thread-smoke.json`.
Its exact harness is `executed-main-smoke.py.gz`.
`a8af-worker-first-action.json` records the predecessor's exact step-zero
worker failure.

Example from this directory, using an extracted pinned archive and the pinned
official engine artifact:

```sh
python3.11 run_worker_episode.py \
  --archive-root /path/to/extracted/archive \
  --engine-dir /path/to/engine-artifact/engine \
  --output /tmp/worker-episode.json
```

This is one continuity episode, not a new strength panel or hosted-runtime
receipt.  The trace identity demonstrates unchanged decisions and economics
for this retained episode; it does not prove every hosted execution boundary.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
