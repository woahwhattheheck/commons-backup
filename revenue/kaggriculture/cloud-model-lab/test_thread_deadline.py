"""Bounded review harness for a thread-local deadline guard.

Written against the CURRENT shipped guard so the five review properties have a
measured baseline, and parameterised by `--guard` so the identical suite runs
unchanged against the worker-thread increment when its owner lands it. This is
test code only: it authors no guard, and edits no canonical file.

Properties under review, in the order they were specified:

  T1  cancellation identity -- the raised object must be the timer's own
      `expired` instance, because `act` discriminates on `error is not
      timer.expired` and a guard that raises a fresh exception silently turns a
      caller's unrelated DeadlineExceeded into this guard's fallback.
  T2  worker-thread availability -- can the guard be entered off the main thread
      at all, and if not, what exactly does it raise.
  T3  tracer restoration -- a line/opcode-traced guard must leave `sys.gettrace`
      and `threading.gettrace` exactly as it found them, by identity, or it
      silently disables a coverage tool or profiler that was already running.
  T4  no signal mutation from a worker -- a guard entered on a worker thread must
      not touch SIGALRM disposition or ITIMER_REAL, since those are process-wide
      and belong to the main thread.
  T5  bounded CPU-loop cancellation -- a pure-Python busy loop must be cancelled
      within a bounded overshoot, reported rather than asserted.
  T6  per-call overhead on the shipped default policy -- the guard's own
      enter/exit cost, and that cost as a fraction of a real measured action.

  python -B test_thread_deadline.py [--guard /path/to/deadline_adapter.py]
"""

import argparse
import importlib.util
import json
import os
import signal
import statistics
import sys
import threading
import time
import traceback

LAB = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "cloud-execution-lab"))
DEFAULT_GUARD = os.path.join(LAB, "reference", "titan-current", "deadline_adapter.py")

RESULTS = []


def record(name, status, detail, **extra):
    row = {"test": name, "status": status, "detail": detail}
    row.update(extra)
    RESULTS.append(row)
    print(f"{status:9s} {name}: {detail}", flush=True)


def load_guard(path):
    spec = importlib.util.spec_from_file_location(
        f"guard_under_review_{time.time_ns()}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- T1
def t1_cancellation_identity(G):
    timer = G._DeadlineTimer(0.02)
    caught = None
    try:
        with timer:
            t = time.perf_counter()
            while time.perf_counter() - t < 1.0:
                pass
    except G.DeadlineExceeded as exc:
        caught = exc
    same = caught is timer.expired
    which = "the timer's own expired instance" if same else "a DIFFERENT instance"
    record("T1 cancellation identity", "PASS" if same else "FAIL",
           f"raised object is {which}", raised_is_timer_expired=bool(same))
    return same


# --------------------------------------------------------------------------- T2
def t2_worker_thread_availability(G):
    box = {}

    def run():
        try:
            timer = G._DeadlineTimer(0.02)
            with timer:
                t = time.perf_counter()
                while time.perf_counter() - t < 0.5:
                    pass
            box["outcome"] = "completed_without_cancellation"
        except G.DeadlineExceeded as exc:
            box["outcome"] = "cancelled"
            box["identity"] = exc is timer.expired
        except BaseException as exc:                      # the interesting case
            box["outcome"] = "raised"
            box["error"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=run)
    th.start()
    th.join(5.0)
    outcome = box.get("outcome", "hung")
    usable = outcome == "cancelled"
    record("T2 worker-thread availability",
           "PASS" if usable else "UNSUPPORTED",
           f"outcome={outcome}" + (f" error={box.get('error')}" if box.get("error") else "")
           + (f" identity_preserved={box.get('identity')}" if "identity" in box else ""),
           outcome=outcome, error=box.get("error"),
           identity_preserved=box.get("identity"))
    return usable


# --------------------------------------------------------------------------- T3
def t3_tracer_restoration(G, on_worker):
    """A sentinel tracer must survive the guarded scope, by identity."""
    def sentinel(frame, event, arg):
        return sentinel

    box = {}

    def body():
        sys.settrace(sentinel)
        threading.settrace(sentinel)
        before_sys, before_thr = sys.gettrace(), threading.gettrace()
        try:
            timer = G._DeadlineTimer(0.02)
            with timer:
                t = time.perf_counter()
                while time.perf_counter() - t < 0.4:
                    pass
        except G.DeadlineExceeded:
            # Expected: the guard fired. That is the case worth checking, since
            # a cancelling exit is exactly where a tracer is most likely lost.
            box["entered"] = True
        except BaseException as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
        else:
            box["entered"] = True
        after_sys, after_thr = sys.gettrace(), threading.gettrace()
        box.update(sys_restored=after_sys is before_sys,
                   threading_restored=after_thr is before_thr,
                   sys_after=repr(after_sys), thr_after=repr(after_thr))
        sys.settrace(None)
        threading.settrace(None)

    if on_worker:
        th = threading.Thread(target=body)
        th.start()
        th.join(5.0)
    else:
        body()
    entered = bool(box.get("entered"))
    ok = entered and box.get("sys_restored") and box.get("threading_restored")
    where = "worker" if on_worker else "main"
    # A guard that never ran restores a tracer trivially. That is UNSUPPORTED,
    # never a pass -- otherwise an unexercised property reads as a green tick.
    status = "PASS" if ok else ("UNSUPPORTED" if not entered else "FAIL")
    record(f"T3 tracer restoration ({where} thread)", status,
           (f"guard could not be entered here ({box.get('error')}), so the "
            f"property was NOT exercised" if not entered else
            f"guard entered and cancelled; sys.gettrace restored by identity="
            f"{box.get('sys_restored')} threading.gettrace restored by identity="
            f"{box.get('threading_restored')}"),
           guard_entered=entered, **{k: v for k, v in box.items()})
    return ok


# --------------------------------------------------------------------------- T4
def t4_no_signal_mutation_from_worker(G):
    """Process-wide SIGALRM state must be untouched by a worker-entered guard."""
    before_handler = signal.getsignal(signal.SIGALRM)
    before_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.setitimer(signal.ITIMER_REAL, *before_timer) if before_timer[0] else None
    box = {}

    def run():
        try:
            with G._DeadlineTimer(0.02):
                t = time.perf_counter()
                while time.perf_counter() - t < 0.4:
                    pass
            box["entered"] = True
        except G.DeadlineExceeded:
            box["entered"] = True          # expected: the guard fired
        except BaseException as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=run)
    th.start()
    th.join(5.0)
    after_handler = signal.getsignal(signal.SIGALRM)
    after_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    unchanged = (after_handler is before_handler) and (after_timer[1] == before_timer[1])
    entered = bool(box.get("entered"))
    # Only meaningful once the guard actually runs on a worker. A guard that
    # cannot be entered leaves signal state alone for the wrong reason.
    status = "PASS" if (entered and unchanged) else (
        "FAIL" if entered else "UNSUPPORTED")
    record("T4 no signal mutation from a worker", status,
           (f"guard could not be entered on a worker ({box.get('error')}), so the "
            f"property was NOT exercised" if not entered else
            f"guard ran and cancelled ON THE WORKER; SIGALRM handler identity "
            f"unchanged={after_handler is before_handler}, ITIMER_REAL interval "
            f"unchanged={after_timer[1] == before_timer[1]}"),
           guard_entered_on_worker=entered, worker_error=box.get("error"),
           handler_identity_unchanged=bool(after_handler is before_handler),
           itimer_interval_unchanged=bool(after_timer[1] == before_timer[1]))
    return unchanged


# --------------------------------------------------------------------------- T5
def t5_bounded_cpu_loop(G, on_worker, budget=0.05, spin=2.0):
    box = {}

    def body():
        t0 = time.perf_counter()
        try:
            with G._DeadlineTimer(budget):
                while time.perf_counter() - t0 < spin:
                    pass
            box["outcome"] = "not_cancelled"
        except G.DeadlineExceeded:
            box["outcome"] = "cancelled"
        except BaseException as exc:
            box["outcome"] = "raised"
            box["error"] = f"{type(exc).__name__}: {exc}"
        box["elapsed_s"] = time.perf_counter() - t0

    if on_worker:
        th = threading.Thread(target=body)
        th.start()
        th.join(spin + 5.0)
    else:
        body()
    where = "worker" if on_worker else "main"
    outcome = box.get("outcome", "hung")
    over = None if "elapsed_s" not in box else round(box["elapsed_s"] - budget, 6)
    record(f"T5 bounded CPU-loop cancellation ({where} thread)",
           "PASS" if outcome == "cancelled" else
           ("UNSUPPORTED" if outcome == "raised" else "FAIL"),
           f"outcome={outcome} budget={budget}s elapsed={box.get('elapsed_s')} "
           f"overshoot={over}" + (f" error={box.get('error')}" if box.get("error") else ""),
           outcome=outcome, budget_seconds=budget,
           elapsed_seconds=box.get("elapsed_s"), overshoot_seconds=over,
           error=box.get("error"))
    return outcome == "cancelled"


# --------------------------------------------------------------------------- T6
def t6_per_call_overhead(G, samples=2000):
    """Guard enter/exit cost in isolation, then as a share of a real action."""
    costs = []
    for _ in range(samples):
        t = time.perf_counter()
        with G._DeadlineTimer(1.0):
            pass
        costs.append(time.perf_counter() - t)
    costs.sort()
    guard = {"mean_s": statistics.mean(costs), "median_s": costs[len(costs) // 2],
             "p99_s": costs[int(0.99 * len(costs)) - 1], "max_s": costs[-1],
             "samples": samples}

    action = None
    try:
        if LAB not in sys.path:
            sys.path.insert(0, LAB)
        import cards as cards_mod
        import titan_runtime as T
        import arlene_arm, route_cards
        A, _ = route_cards.load_arlene()
        opp, _ = arlene_arm.make_opponent("apex", A)
        agent = T.TitanAgent(T.Features(**json.load(
            open(os.path.join(LAB, "TITAN-CONFIG.json")))))
        env = cards_mod.make_env(9902241)
        env.reset(2)
        elapsed, n = [], 0
        while not env.done and n < 200:
            acts = [None, None]
            for i in range(2):
                o = env.state[i].observation
                if i == 0:
                    t = time.perf_counter()
                    acts[i] = agent.act(o, env.configuration)
                    elapsed.append(time.perf_counter() - t)
                else:
                    acts[i] = opp(o, env.configuration)
            env.step(acts)
            n += 1
        elapsed.sort()
        action = {"actions": len(elapsed), "mean_s": statistics.mean(elapsed),
                  "median_s": elapsed[len(elapsed) // 2], "max_s": elapsed[-1]}
    except Exception as exc:
        action = {"error": f"{type(exc).__name__}: {exc}"}

    share = (None if not action or "error" in action
             else round(100.0 * guard["mean_s"] / action["mean_s"], 3))
    record("T6 per-call overhead on the shipped default", "MEASURED",
           f"guard enter+exit mean {guard['mean_s']*1e6:.1f} us "
           f"(median {guard['median_s']*1e6:.1f}, p99 {guard['p99_s']*1e6:.1f}); "
           + (f"shipped action mean {action['mean_s']*1e3:.3f} ms over "
              f"{action['actions']} actions; guard is {share}% of an action"
              if share is not None else f"policy timing unavailable: {action}"),
           guard=guard, shipped_action=action, guard_share_percent=share)
    return guard, action


# --------------------------------------------------------------------------- T7
def t7_trace_cost_on_shipped_policy(actions=120):
    """What a trace-based cancellation would cost, before anyone writes one.

    A worker thread cannot receive SIGALRM, so a thread-local guard is normally
    built on `sys.settrace`/`threading.settrace`. That is a different cost model
    from a signal: the interpreter pays per event for the WHOLE guarded body, not
    once at entry. This measures the shipped default policy under three regimes
    so the decision is made on a number rather than on preference.
    """
    if LAB not in sys.path:
        sys.path.insert(0, LAB)
    import cards as cards_mod
    import titan_runtime as T
    import arlene_arm, route_cards
    A, _ = route_cards.load_arlene()
    cfg0 = json.load(open(os.path.join(LAB, "TITAN-CONFIG.json")))

    def run(install):
        opp, _ = arlene_arm.make_opponent("apex", A)
        agent = T.TitanAgent(T.Features(**cfg0))
        env = cards_mod.make_env(9902241)
        env.reset(2)
        el, n = [], 0
        while not env.done and n < actions:
            acts = [None, None]
            for i in range(2):
                o = env.state[i].observation
                if i == 0:
                    install()
                    t = time.perf_counter()
                    acts[i] = agent.act(o, env.configuration)
                    el.append(time.perf_counter() - t)
                    sys.settrace(None)
                else:
                    acts[i] = opp(o, env.configuration)
            env.step(acts)
            n += 1
        return statistics.mean(el), len(el)

    def call_level():
        sys.settrace(lambda frame, event, arg: None)

    def line_level():
        def tr(frame, event, arg):
            return tr
        sys.settrace(tr)

    base, n = run(lambda: None)
    call_mean, _ = run(call_level)
    line_mean, _ = run(line_level)
    record("T7 trace-based cancellation cost on the shipped default", "MEASURED",
           f"no tracer {base*1e3:.3f} ms/action; call-level tracer "
           f"{call_mean*1e3:.3f} ms ({call_mean/base:.2f}x); line-level tracer "
           f"{line_mean*1e3:.3f} ms ({line_mean/base:.2f}x), over {n} actions",
           actions=n, no_tracer_mean_s=base, call_tracer_mean_s=call_mean,
           line_tracer_mean_s=line_mean,
           call_multiplier=round(call_mean / base, 3),
           line_multiplier=round(line_mean / base, 3))
    return base, call_mean, line_mean


# --------------------------------------------------------------------------- T8
def t8_async_exc_mechanism_probe(spin=2.0, fire_after=0.05):
    """The other candidate mechanism, probed for the properties under review.

    This is a MECHANISM PROBE, not a guard: no context manager, no reusable API,
    nothing another module could import and depend on. It answers one question
    the integration needs before choosing: can the zero-steady-state-cost
    alternative to tracing preserve cancellation identity?

    `PyThreadState_SetAsyncExc` takes an exception TYPE and the interpreter
    instantiates it, so a pre-made sentinel instance cannot be delivered. If that
    holds, a worker guard built on it cannot satisfy T1 as written, and `act`'s
    `error is not timer.expired` discrimination has to become a thread-local
    token check instead.
    """
    import ctypes

    class ProbeCancel(BaseException):
        pass

    sentinel = ProbeCancel("pre-made instance")
    box = {}

    def body():
        t0 = time.perf_counter()
        try:
            while time.perf_counter() - t0 < spin:
                pass
            box["outcome"] = "not_interrupted"
        except ProbeCancel as exc:
            box["outcome"] = "interrupted"
            box["is_sentinel_instance"] = exc is sentinel
            box["delivered_type"] = type(exc).__name__
        box["elapsed_s"] = time.perf_counter() - t0

    th = threading.Thread(target=body)
    th.start()
    time.sleep(fire_after)
    ident = ctypes.c_ulong(th.ident)
    fired = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ident, ctypes.py_object(ProbeCancel))
    th.join(spin + 5.0)
    if fired != 1:                      # never leave a stray pending exception
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ident, None)
    outcome = box.get("outcome", "hung")
    over = None if "elapsed_s" not in box else round(box["elapsed_s"] - fire_after, 6)
    record("T8 async-exc mechanism probe (identity and latency)", "MEASURED",
           f"outcome={outcome} threads_set={fired} fired_after={fire_after}s "
           f"elapsed={box.get('elapsed_s')} latency={over} "
           f"delivered_is_pre_made_instance={box.get('is_sentinel_instance')} "
           f"delivered_type={box.get('delivered_type')}",
           outcome=outcome, threads_set=int(fired), fire_after_seconds=fire_after,
           elapsed_seconds=box.get("elapsed_s"), latency_seconds=over,
           preserves_instance_identity=box.get("is_sentinel_instance"),
           delivered_type=box.get("delivered_type"))
    return box


# --------------------------------------------------------------------------- T9
def t9_worker_steady_state_cost(G, reps=400):
    """The number ECON's 719-action episode actually depends on.

    T6 measures the guard's cost on the main thread, where cancellation is a
    signal and the body runs untraced. A worker-thread guard cancels by tracing,
    so its cost is not the entry cost -- it is whatever the trace check adds to
    the guarded BODY. This times an identical fixed workload inside the guard on
    the main thread and on a worker, and reports the ratio.
    """
    def workload():
        total = 0
        for i in range(20000):
            total += i * i % 7
        return total

    def timed(on_worker):
        out = {}

        def body():
            samples = []
            for _ in range(reps):
                t = time.perf_counter()
                with G._DeadlineTimer(5.0):
                    workload()
                samples.append(time.perf_counter() - t)
            samples.sort()
            out["mean"] = statistics.mean(samples)
            out["median"] = samples[len(samples) // 2]
            out["p99"] = samples[int(0.99 * len(samples)) - 1]

        if on_worker:
            th = threading.Thread(target=body)
            th.start()
            th.join(300)
        else:
            body()
        return out

    bare = []
    for _ in range(reps):
        t = time.perf_counter()
        workload()
        bare.append(time.perf_counter() - t)
    bare_mean = statistics.mean(bare)
    main = timed(False)
    worker = timed(True)
    record("T9 guarded-body cost, main thread versus worker", "MEASURED",
           f"unguarded body {bare_mean*1e3:.3f} ms; guarded on main "
           f"{main.get('mean', 0)*1e3:.3f} ms ({main.get('mean', 0)/bare_mean:.2f}x); "
           f"guarded on worker {worker.get('mean', 0)*1e3:.3f} ms "
           f"({worker.get('mean', 0)/bare_mean:.2f}x), {reps} reps each",
           unguarded_mean_s=bare_mean, main_thread=main, worker_thread=worker,
           main_multiplier=round(main.get("mean", 0) / bare_mean, 3),
           worker_multiplier=round(worker.get("mean", 0) / bare_mean, 3))
    return bare_mean, main, worker


# -------------------------------------------------------------------------- T10
def t10_shipped_policy_on_a_worker(actions=120):
    """The real question behind T9, measured instead of extrapolated.

    T9's workload is a tight arithmetic loop, which is the worst case for any
    event-counting tracer. What matters is the SHIPPED policy: the same
    `TitanAgent.act`, over real observations, driven from the main thread and
    then from a worker thread, so the worker guard's cost on the actual body is
    a measurement rather than an inference from a microbenchmark.
    """
    if LAB not in sys.path:
        sys.path.insert(0, LAB)
    import cards as cards_mod
    import titan_runtime as T
    import arlene_arm, route_cards
    A, _ = route_cards.load_arlene()
    cfg0 = json.load(open(os.path.join(LAB, "TITAN-CONFIG.json")))

    def run(on_worker):
        opp, _ = arlene_arm.make_opponent("apex", A)
        agent = T.TitanAgent(T.Features(**cfg0))
        env = cards_mod.make_env(9902241)
        env.reset(2)
        el, n, err = [], 0, None
        while not env.done and n < actions:
            acts = [None, None]
            for i in range(2):
                o = env.state[i].observation
                if i != 0:
                    acts[i] = opp(o, env.configuration)
                    continue
                box = {}

                def call():
                    try:
                        t = time.perf_counter()
                        box["out"] = agent.act(o, env.configuration)
                        box["dt"] = time.perf_counter() - t
                    except BaseException as exc:
                        box["err"] = f"{type(exc).__name__}: {exc}"

                if on_worker:
                    th = threading.Thread(target=call)
                    th.start()
                    th.join(30)
                else:
                    call()
                if "err" in box:
                    err = box["err"]
                    return {"error": err, "actions": len(el)}
                el.append(box["dt"])
                acts[i] = box["out"]
            env.step(acts)
            n += 1
        el_sorted = sorted(el)
        return {"actions": len(el), "mean_s": statistics.mean(el),
                "median_s": el_sorted[len(el_sorted) // 2],
                "p99_s": el_sorted[int(0.99 * len(el_sorted)) - 1],
                "max_s": el_sorted[-1]}

    main_r = run(False)
    worker_r = run(True)
    ratio = (None if "error" in main_r or "error" in worker_r
             else round(worker_r["mean_s"] / main_r["mean_s"], 3))
    record("T10 shipped policy driven from a worker thread", "MEASURED",
           (f"error: main={main_r.get('error')} worker={worker_r.get('error')}"
            if ratio is None else
            f"main thread {main_r['mean_s']*1e3:.3f} ms/action "
            f"(max {main_r['max_s']*1e3:.3f}); worker thread "
            f"{worker_r['mean_s']*1e3:.3f} ms/action (max {worker_r['max_s']*1e3:.3f}) "
            f"= {ratio}x, over {main_r['actions']} actions each"),
           main_thread=main_r, worker_thread=worker_r, worker_multiplier=ratio)
    return main_r, worker_r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guard", default=DEFAULT_GUARD)
    ap.add_argument("--out", default="results/thread-deadline-review.json")
    a = ap.parse_args()
    path = os.path.realpath(a.guard)
    import hashlib
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    print(f"guard under review: {path}\nsha256 {sha}\n"
          f"python {sys.version.split()[0]}\n", flush=True)

    G = load_guard(path)
    t1_cancellation_identity(G)
    worker_ok = t2_worker_thread_availability(G)
    t3_tracer_restoration(G, on_worker=False)
    t3_tracer_restoration(G, on_worker=True)
    t4_no_signal_mutation_from_worker(G)
    t5_bounded_cpu_loop(G, on_worker=False)
    t5_bounded_cpu_loop(G, on_worker=True)
    guard, action = t6_per_call_overhead(G)
    try:
        t7_trace_cost_on_shipped_policy()
    except Exception as exc:
        record("T7 trace-based cancellation cost on the shipped default", "ERROR",
               f"{type(exc).__name__}: {exc}")
    try:
        t9_worker_steady_state_cost(G)
    except Exception as exc:
        record("T9 guarded-body cost, main thread versus worker", "ERROR",
               f"{type(exc).__name__}: {exc}")
    try:
        t10_shipped_policy_on_a_worker()
    except Exception as exc:
        record("T10 shipped policy driven from a worker thread", "ERROR",
               f"{type(exc).__name__}: {exc}")
    try:
        t8_async_exc_mechanism_probe()
    except Exception as exc:
        record("T8 async-exc mechanism probe (identity and latency)", "ERROR",
               f"{type(exc).__name__}: {exc}")

    summary = {"guard_path": path, "guard_sha256": sha,
               "python": sys.version.split()[0],
               "worker_thread_supported": worker_ok,
               "results": RESULTS}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(summary, open(a.out, "w"), indent=1, default=str)
    counts = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
