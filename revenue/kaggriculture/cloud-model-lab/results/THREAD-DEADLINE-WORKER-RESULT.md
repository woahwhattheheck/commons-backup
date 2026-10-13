# Worker-thread deadline guard: bounded suite run unchanged on the landed increment

Increment: PR #10335, merge `7c50bbfb41027f31a2d4bc9470424e815f1fcef1`, source
`c776ce382ccad74dc32e08cc7bb1fc7da4e6c739`. Canonical archive sha256
**`7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524`** — verified
identical at current main before running. Guard consumed from
`cloud-execution-lab/reference/titan-current/deadline_adapter.py`, sha256
`c8f7c9842ba7e4eb29f6e57a8d6f9ba816140dcbea7817aea2b3efcabe2771c5`
(was `c3bef158…`). CPython 3.11.15, this cloud VM.

Same suite as the pre-landing baseline, run with `--guard` pointed at the real
file. No canonical file edited.

## Correctness: all seven properties pass

| property | main thread | worker thread |
|---|---|---|
| **cancellation identity** | **PASS** — raised object is the timer's own `expired` instance | **PASS** — `identity_preserved=True` |
| **tracer restoration** | **PASS** — entered *and cancelled*; `sys.gettrace` and `threading.gettrace` restored **by identity** | **PASS** — same, by identity |
| **no signal mutation from a worker** | — | **PASS** — guard ran and cancelled on the worker; SIGALRM handler identity unchanged, `ITIMER_REAL` interval unchanged |
| **bounded CPU-loop cancellation** | **PASS** — 50 ms budget, **118 µs** overshoot | **PASS** — 50 ms budget, **59 µs** overshoot |

The worker path cancels a pure-Python busy loop *faster* than the signal path
does (59 µs against 118 µs), which is what an every-64-events trace check should
do: it does not wait on signal delivery. Every previously UNSUPPORTED property is
now exercised and passes.

## Cost: the worker path is 19× on the shipped policy

| measurement | main | worker | ratio |
|---|---:|---:|---:|
| guard enter+exit, isolated | 10.2 µs (median 9.5, p99 36.6) | — | — |
| guard as a share of a shipped action | **0.498 %** | — | — |
| fixed arithmetic body inside the guard | 0.926 ms | 13.461 ms | **14.6×** |
| **shipped policy, real observations, 120 actions** | **1.308 ms/action** (max 4.257) | **24.848 ms/action** (max 51.362) | **19.0×** |

Entry cost on the main thread rose from 6.0–6.4 µs on the previous guard to
**10.2 µs** here — the thread gate and tracer chaining are not free — but that is
still 0.498 % of a 2.043 ms action, so the main path is unaffected in practice.

Reference points from the same run: a plain `sys.settrace` line tracer costs
4.34× on this policy and a call-level tracer 2.98×, so the guard's per-event
check is the dominant term above a bare tracer, not the tracing itself.

**What this means for a 719-action episode.** Policy time goes from about
**0.94 s** on the main path to about **17.9 s** on the worker path. The
per-action maximum is **51.4 ms** against a 1 s RPC — so the worker guard does
**not** breach the deadline on an idle VM, and at the wall/CPU inflation of 1.633
measured earlier under six competing burners it lands near 84 ms, still an order
of magnitude inside the limit. The exposure is throughput and headroom, not
correctness.

Two things follow directly:

1. **Use the worker path only where the main thread is unavailable.** On the main
   thread the guard costs 0.5 % of an action; on a worker it costs 19×. Running
   the policy on the main thread and confining workers to I/O keeps both the
   guarantee and the speed.
2. **If the worker path must carry the policy, arm the tracer late.** The trace
   check only has to run while cancellation is plausible. Installing it once the
   remaining budget drops below a threshold gives the same guarantee at close to
   zero steady-state cost — 51 ms of headroom against 1 s is ample room to arm.

## Scope

Measured on CPython 3.11.15 on this VM; not Kaggle hardware, and the ratios
should be re-measured on the deployment interpreter before anything irreversible
rests on them. ECON owns the full 719-action 3.11 episode — the figure above is a
120-action measurement of the same policy and entrypoint, offered as an input to
that, not as a substitute for it. Async-exc was re-probed only as the alternative
mechanism's reference point (10.6 ms latency, no instance identity); the landed
guard uses no async injection.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
