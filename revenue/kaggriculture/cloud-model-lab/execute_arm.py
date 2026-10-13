"""Run any peer's callable arm against a control, on this VM, with real receipts.

This is the complementary-executor road. It takes whole callables by PATH -- no
peer file is copied, edited or re-implemented -- and gives back what actually
decides a rating plus what diagnoses it:

  * W/T/L first, per game, against the rival in that game
  * own AND rival cash, so a gain that is really the rival losing is visible
  * the end-of-day RNG path per arm, so a candidate/control pair that differs can
    be shown to be playing the SAME market world rather than a different town
  * worst single action wall time, first action included (initialization separate)
  * executor_timing: initialization, first action, and later-action timings
  * every failure preserved; a raising arm is reported, never silently dropped

Opponents resolve through this lab's single resolver: intact Arlene, Apex, and
the exact public bank from PR9942 (`lonespear`, `cok`) read-only from its owner's
path. lonespear and COK are two frozen public source revisions from ONE bank, not
two independent opponent families, and the summary says so.

A callable is `agent(observation, configuration)` or `agent(observation)`; an
`--arm-factory` module may instead expose `make_agent()` returning a fresh
per-match callable, which is what a stateful arm needs.

  python -B execute_arm.py \
     --candidate /path/to/arm.py --control /path/to/parent.py \
     --seeds 9890101 9890119 --seats 0 1 --opponents arlene apex lonespear cok
"""

import argparse
import contextlib
import hashlib
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import time
import traceback

import cards as cards_mod

# Reuse the sibling observer without adding a policy import root or a second
# callable loader. Its module load is outside all measured policy timings.
_timing_spec = importlib.util.spec_from_file_location(
    "_titan_execution_timing", os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "..", "cloud-combination-analysis", "execution_timing.py"))
_timing_module = importlib.util.module_from_spec(_timing_spec)
sys.modules[_timing_spec.name] = _timing_module
_timing_spec.loader.exec_module(_timing_module)
TimedFactory = _timing_module.TimedFactory


def load_callable(path, extra_sys_path=()):
    """Bind entrypoint bytes once; construct a fresh module and actor per match.

    The returned SHA describes the bytes compiled by every factory attempt, not
    a later filesystem read or cached bytecode. Imported dependencies retain
    normal Python import behavior and need a separately pinned source closure.
    """
    rp = os.path.realpath(path)
    for p in extra_sys_path:
        if p and p not in sys.path:
            sys.path.insert(0, p)
    with open(rp, "rb") as handle:
        source = handle.read()
    sha = hashlib.sha256(source).hexdigest()

    def factory():
        spec = importlib.util.spec_from_file_location(
            f"arm_{os.path.basename(rp).replace('.', '_')}_{time.time_ns()}", rp)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        exec(compile(source, rp, "exec", dont_inherit=True), mod.__dict__)
        if hasattr(mod, "make_agent"):
            fn = mod.make_agent()
        else:
            fn = mod.agent
        # Choose the supported call shape without executing a policy. Catching
        # TypeError around fn(...) would retry errors from inside a stateful arm.
        signature = inspect.signature(fn)
        try:
            signature.bind(None, None)
        except TypeError:
            signature.bind(None)
            with_config = False
        else:
            with_config = True

        def call(obs, cfg):
            if with_config:
                return fn(obs, cfg)
            return fn(obs)
        return call

    return factory, {"path": rp, "sha256": sha,
                     "label": f"{os.path.basename(rp)}@{sha[:12]}"}


def normalise(obs, seat):
    """The engine omits `step` from a seat-1 observation. Three published
    consumers index it directly, so a seat-1 game raises before any policy runs.
    Supplied here in the HARNESS exactly as Arlene does internally; no arm under
    test is modified."""
    o = dict(obs)
    if o.get("step") is None:
        o["step"] = int(o["day"]) * 24 + int(o["hour"])
    o.setdefault("player", seat)
    return o


def game(seed, seat, opponent, factory, label, record_path=True):
    # Ordinary failures outside the policy loop still have a named attempted
    # cell. Keep the original exception; main can checkpoint these known facts
    # before stopping. Cancellation is deliberately not converted into a row.
    row = {"seed": seed, "seat": seat, "opponent": opponent, "arm": label}
    stage = "setup"
    try:
        import arlene_arm
        import route_cards
        A, arl_id = route_cards.load_arlene()
        # Restore engine hooks even when cancellation or result diagnostics raise.
        with contextlib.ExitStack() as stack:
            rec = None
            if record_path:
                import market_path
                rec = stack.enter_context(market_path.PathRecorder())
            observer = TimedFactory(factory)
            try:
                env = cards_mod.make_env(seed)
                env.reset(2)
                opp, opp_id = arlene_arm.make_opponent(opponent, A)
                me = observer()
                t0, worst, n = time.time(), 0.0, 0
                while not env.done:
                    acts = [None, None]
                    for i in range(2):
                        obs = env.state[i].observation
                        if i == seat:
                            t = time.perf_counter()
                            acts[i] = me(normalise(obs, i), env.configuration)
                            worst = max(worst, time.perf_counter() - t)
                        else:
                            acts[i] = opp(obs, env.configuration)
                    env.step(acts)
                    n += 1
                farms = env.state[0].observation.farms
                own, rival = float(farms[seat]["money"]), float(farms[1 - seat]["money"])
                row.update(own_cash=own, rival_cash=rival, margin=own - rival, rounds=n,
                           wall_s=round(time.time() - t0, 1),
                           worst_action_s=round(worst, 4), opponent_id=opp_id,
                           arlene=arl_id, error=None)
            except Exception as exc:                     # preserved, never swallowed
                row.update(own_cash=None, rival_cash=None, margin=None, error=
                           f"{type(exc).__name__}: {exc}",
                           traceback=traceback.format_exc()[-2000:])
            finally:
                stage = "timing"
                row["executor_timing"] = observer.timings()
            if rec is not None:
                stage = "path"
                row["path"] = rec.path()
            stage = "cleanup"
            return row
    except Exception as exc:
        # A cleanup failure can mask an active cancellation. Preserve that
        # existing propagation without manufacturing an attempted-result row.
        if isinstance(exc.__context__, BaseException) and not isinstance(exc.__context__, Exception):
            raise
        failure = {"stage": stage, "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()[-2000:]}
        if "error" not in row:
            row.update(own_cash=None, rival_cash=None, margin=None,
                       error=failure["error"], traceback=failure["traceback"],
                       executor_timing=None)
        row.setdefault("executor_timing", None)
        row["executor_error"] = failure
        # Exception subclasses may reject custom attributes. Such a refusal
        # must not replace the original failure or imply a saved result.
        try:
            exc._titan_executor_row = row
        except Exception:
            pass
        raise


def wtl(m):
    return "?" if m is None else ("W" if m > 0 else ("L" if m < 0 else "T"))


def write_checkpoint(path, candidate, control, rows, expected_rows, complete=False):
    """Atomically retain returned game rows; complete describes the batch, not wins.

    Same-directory replacement leaves the previous JSON readable on a failed
    write. This does not resume games or promise recovery of an in-flight game.
    """
    directory = os.path.dirname(os.fspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    payload = {"candidate": candidate, "control": control, "rows": rows,
               "checkpoint": {"complete": complete,
                              "recorded_rows": len(rows),
                              "expected_rows": expected_rows,
                              "failed_rows": sum(bool(r.get("error")) for r in rows)}}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".execute-arm-", suffix=".json.tmp",
                                         delete=False) as handle:
            temporary = handle.name
            json.dump(payload, handle, indent=1, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--control", required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--sys-path", nargs="*", default=[],
                    help="extra import roots the arms need (their vendor dirs)")
    ap.add_argument("--no-path", action="store_true")
    ap.add_argument("--out", default="results/execute-arm.json")
    a = ap.parse_args()
    cf, cid = load_callable(a.candidate, a.sys_path)
    bf, bid = load_callable(a.control, a.sys_path)
    print(f"candidate {cid['label']}\ncontrol   {bid['label']}", flush=True)
    rows = []
    expected_rows = 2 * len(a.seeds) * len(a.seats) * len(a.opponents)

    def run_one(seed, seat, opponent, factory, label):
        try:
            result = game(seed, seat, opponent, factory, label, not a.no_path)
        except Exception as exc:
            try:
                result = getattr(exc, "_titan_executor_row", None)
            except Exception:
                result = None
            if isinstance(result, dict) and all(result.get(k) == v for k, v in
                    (("seed", seed), ("seat", seat), ("opponent", opponent),
                     ("arm", label))):
                rows.append(result)
                write_checkpoint(a.out, cid, bid, rows, expected_rows)
            raise
        rows.append(result)
        write_checkpoint(a.out, cid, bid, rows, expected_rows)
        return result

    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                b = run_one(seed, seat, opp, bf, "control")
                c = run_one(seed, seat, opp, cf, "candidate")
                div = None
                if not a.no_path and b.get("path") and c.get("path"):
                    import market_path
                    div = len(market_path.diff({"path": b["path"]},
                                               {"path": c["path"]}))
                    c["path_divergent_days"] = div
                    write_checkpoint(a.out, cid, bid, rows, expected_rows)
                d_own = (None if c["own_cash"] is None or b["own_cash"] is None
                         else c["own_cash"] - b["own_cash"])
                print(f"seed {seed} seat {seat} vs {opp:9s} control "
                      f"{wtl(b['margin'])} own {b['own_cash']} rival {b['rival_cash']}"
                      f" | candidate {wtl(c['margin'])} own {c['own_cash']} "
                      f"rival {c['rival_cash']} d_own {d_own}"
                      + (f" pathdiv {div}d" if div is not None else "")
                      + (f"  ERROR {c['error']}" if c["error"] else ""), flush=True)
    write_checkpoint(a.out, cid, bid, rows, expected_rows, complete=True)
    for label in ("control", "candidate"):
        rs = [r for r in rows if r["arm"] == label]
        v = [wtl(r["margin"]) for r in rs]
        fail = sum(1 for r in rs if r["error"])
        print(f"  {label:10s} {v.count('W')}/{v.count('T')}/{v.count('L')}  "
              f"failures {fail}  worst action "
              f"{max((r.get('worst_action_s') or 0) for r in rs) * 1000:.1f}ms")
    lineage = {"arlene": "arlene", "apex": "apex",
               "lonespear": "public bank PR9942", "cok": "public bank PR9942"}
    opps = sorted({r["opponent"] for r in rows})
    print(f"  independent seeds {len({r['seed'] for r in rows})}; opponent entries "
          f"{len(opps)}; independent opponent lineages "
          f"{len({lineage.get(o, o) for o in opps})}")


if __name__ == "__main__":
    main()
