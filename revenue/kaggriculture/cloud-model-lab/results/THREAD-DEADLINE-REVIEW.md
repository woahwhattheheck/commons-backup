# Bounded review: a thread-local deadline for the shipped guard

Package under review: `exports/titan-current.tar.gz` sha256
`a8af2b834bb5e1d6486245b9538c2de5a041085be38c7707d08e6d49e6149e89`, confirmed
identical at merge `c7627b63` and at current main. Guard file
`reference/titan-current/deadline_adapter.py` sha256
`c3bef158763cb4f5f8b8436800f442b1acc94be2c407c5db1e740edd3a0d68f0`. Python
3.11.15.

**The worker-thread increment is not available yet.** It is not on main and not in
any open pull request; the only other `deadline_adapter.py` in the tree
(`cloud-economic-stress/`) differs solely by caller-handler restoration inside
`_deliver_outer`, which is not thread support. So three of the five properties
cannot be exercised today and are reported as **UNSUPPORTED**, never as passes.

The suite is parameterised — `test_thread_deadline.py --guard <path>` — so the
identical run reproduces against the increment the moment its owner lands it. It
is test code: it authors no guard and edits no canonical file.

## Baseline on the shipped guard

| test | result |
|---|---|
| **T1 cancellation identity** | **PASS** — the raised object is the timer's own `expired` instance, so `act`'s `error is not timer.expired` discrimination holds |
| **T2 worker-thread availability** | **UNSUPPORTED** — `ValueError: signal only works in main thread of the main interpreter` |
| **T3 tracer restoration, main thread** | **PASS** — guard entered *and cancelled*, `sys.gettrace` and `threading.gettrace` both restored **by identity** |
| **T3 tracer restoration, worker thread** | **UNSUPPORTED** — guard could not be entered, so the property was not exercised |
| **T4 no signal mutation from a worker** | **PASS**, vacuously — the guard cannot be entered on a worker, so it cannot mutate SIGALRM disposition or `ITIMER_REAL`; both verified unchanged by identity |
| **T5 bounded CPU-loop cancellation, main thread** | **PASS** — 50 ms budget, **111 µs overshoot** on a pure busy loop |
| **T5, worker thread** | **UNSUPPORTED** — same `ValueError` |
| **T6 per-call overhead** | **6.0 µs** mean enter+exit (median 5.7, p99 12.0) against a **2.062 ms** shipped action — **0.293% of an action** |

Two of those deserve emphasis. The 111 µs overshoot on a busy loop says the
signal path itself is prompt; the 37–77 ms overshoots measured earlier were
module-execution-bound, not signal-latency-bound. And T4's pass is *vacuous* —
it will only become meaningful once T2 passes.

A correction to this harness, made before publishing it: T3 originally reported
PASS on the worker thread, because a guard that never ran restores a tracer
trivially, and it labelled the expected `DeadlineExceeded` as "guard unusable".
Both were fixed — an unexercised property now reports UNSUPPORTED, and the
cancelling exit is the case actually checked, since that is where a tracer is
most likely to be lost.

## The two candidate mechanisms, measured before anyone writes one

A worker thread cannot receive SIGALRM, so the increment has two realistic
shapes. Both were measured on the shipped default policy rather than argued.

**Tracing.** `sys.settrace` / `threading.settrace` is per-thread and preserves
whatever object the guard chooses to raise, so it satisfies T1 by construction.
Its cost is per-event over the whole guarded body, not once at entry:

| regime | ms/action | multiplier |
|---|---:|---:|
| no tracer | 1.316 | 1.00× |
| call-level tracer | 4.565 | **3.47×** |
| line-level tracer | 6.587 | **5.00×** |

**Async exception.** `PyThreadState_SetAsyncExc` from a watchdog thread has no
steady-state cost and interrupts at a bytecode boundary, the same granularity as
SIGALRM. Probed directly:

| | |
|---|---|
| interrupts a worker busy loop | yes, `threads_set=1` |
| cancellation latency | **10.7 ms** after a 50 ms arm |
| delivers a pre-made sentinel instance | **NO** |

The latency is roughly two default GIL switch intervals
(`sys.getswitchinterval()` = 0.005 s), so it is a floor tied to that setting, not
to the watchdog's timer.

## Advice for the integration

1. **The two mechanisms trade off on exactly the properties under review.**
   Tracing satisfies cancellation identity and costs 3.5–5× on the policy body.
   Async-exc costs nothing in steady state and **cannot** satisfy cancellation
   identity as written, because the interpreter instantiates the type — a
   pre-made `timer.expired` is not deliverable. Choose deliberately; do not
   discover this after the fact.
2. **If async-exc is chosen, `act`'s discrimination has to change.** The
   `error is not timer.expired` test must become a thread-local token check
   (`timer.fired_for is threading.current_thread()` or equivalent), otherwise a
   caller's unrelated `DeadlineExceeded` is silently converted into this guard's
   fallback. That edit belongs in the runtime owner's file, not here.
3. **If tracing is chosen, do not trace continuously.** 5× on every action to
   guard a case that fires rarely is a poor trade. Arming the tracer only once
   the remaining budget falls below a threshold keeps the steady-state cost at
   zero and pays 5× only in the window where cancellation is actually plausible.
4. **Overhead has a concrete budget to fit into.** The current guard is 6.0 µs,
   0.293% of a 2.062 ms action. Anything with steady-state cost should be judged
   against that number, not against the 1 s RPC limit — the RPC has room, but
   spending 5× of it continuously is what makes a contended host miss.
5. **T4 stays vacuous until T2 passes.** A worker guard must be re-checked for
   signal mutation once it can actually be entered; today's pass proves nothing
   about the increment.

## What this does not claim

It does not evaluate the increment — the increment does not exist yet. It does
not measure Kaggle hardware. The trace and async-exc numbers are properties of
CPython 3.11.15 on this VM and should be re-measured on the deployment
interpreter before they decide anything irreversible.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
