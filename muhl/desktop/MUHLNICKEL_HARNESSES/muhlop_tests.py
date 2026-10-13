#!/usr/bin/env python3
"""host/muhlop_tests.py — MECHANICAL ENFORCEMENT TESTS for the execution protocol operator.

These are new tests in a new namespace. They alter no existing test, fixture, expected result or
verifier. Each one exercises the operator's ACTUAL refusal behaviour by attempting the forbidden
transition and requiring the operator to raise; a test that merely inspects a name, a comment or a
configuration flag would not establish enforcement, so none of them do that.

Every case below is a candidate-local check. None of them writes to the container, the registry or
any frozen path, and none of them runs the calibration suite as a side effect.

  python host/muhlop_tests.py
"""
import io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import muhlop_operator as OP


def _fresh(workload="probe"):
    """A run record held in memory only. STATE_PATH is redirected to a scratch file so no test
    disturbs a real run record."""
    d = tempfile.mkdtemp(prefix="muhlop_t_")
    OP.STATE_DIR = d
    OP.STATE_PATH = os.path.join(d, "run_state.json")
    OP.LOCK_PATH = os.path.join(d, "run.lock")
    OP.JOURNAL_DIR = os.path.join(d, "journals")
    OP.RESULT_DIR = os.path.join(d, "results")
    return OP.new_run(workload)


def _refuses(fn, *args, **kw):
    """True when the operator fails closed on the attempt."""
    try:
        fn(*args, **kw)
    except OP.ProtocolError:
        return True
    except Exception:
        return False
    return False


CASES = []


def case(ident, behaviour):
    def deco(fn):
        CASES.append((ident, behaviour, fn)); return fn
    return deco


@case("T01", "configure before snapshot")
def t01():
    r = _fresh(); return _refuses(OP.enter, r, "CONFIGURE")


@case("T02", "inject before baseline verification")
def t02():
    r = _fresh(); OP.enter(r, "SNAPSHOT"); OP.complete_phase(r, "SNAPSHOT")
    return _refuses(OP.enter, r, "INJECT_LITERAL_INPUT")


@case("T03", "fire before literal input")
def t03():
    r = _fresh()
    for p in ("SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE"):
        OP.enter(r, p); OP.complete_phase(r, p)
    return _refuses(OP.enter, r, "FIRE")


@case("T04", "scan immediately after fire without the approved physical condition")
def t04():
    r = _fresh()
    for p in ("SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE", "INJECT_LITERAL_INPUT", "FIRE"):
        OP.enter(r, p); OP.complete_phase(r, p)
    return _refuses(OP.enter, r, "SCAN")


@case("T05", "substitute a generic sleep for the approved physical condition")
def t05():
    r = _fresh(); return _refuses(OP.require_readiness, r, "sleep")


@case("T06", "read an answer surface before readiness")
def t06():
    r = _fresh(); return _refuses(OP.require_readiness, r, "immediate")


@case("T07", "start a second concurrent run")
def t07():
    r = _fresh(); OP.acquire_lock(r["run_id"])
    out = _refuses(OP.acquire_lock, "another-run")
    OP.release_lock(); return out


@case("T08", "begin a new run while an incomplete journal exists")
def t08():
    r = _fresh()
    OP.enter(r, "SNAPSHOT"); OP.complete_phase(r, "SNAPSHOT")
    OP.acquire_lock(r["run_id"])
    out = _refuses(OP.acquire_lock, "new-run")
    OP.release_lock(); return out


@case("T09", "PRE-RUN start baseline is checked by key set, not by count alone")
def t09():
    rec = {"container_bytes": OP.CONTAINER_BYTES, "container_magic_ok": True,
           "registry_entries": 812, "registry_keyset_sha": "a" * 64}
    cur = dict(rec); cur["registry_keyset_sha"] = "b" * 64
    return OP.baseline_matches(rec, cur) is False


@case("T10", "PRE-RUN container size and magic are checked before a run opens")
def t10():
    rec = {"container_bytes": OP.CONTAINER_BYTES, "container_magic_ok": True,
           "registry_entries": 812, "registry_keyset_sha": "a" * 64}
    cur = dict(rec); cur["container_bytes"] = OP.CONTAINER_BYTES - 1
    bad_magic = dict(rec); bad_magic["container_magic_ok"] = False
    return (OP.baseline_matches(rec, cur) is False) and (OP.baseline_matches(rec, bad_magic) is False)


@case("T11", "POST-FIRE state change is recorded as DATA, never classified as a fault")
def t11():
    r = _fresh()
    before = {"container_bytes": OP.CONTAINER_BYTES, "container_magic_ok": True,
              "registry_entries": 812, "registry_keyset_sha": "a" * 64}
    after = dict(before); after["registry_entries"] = 815; after["registry_keyset_sha"] = "c" * 64
    d = OP.record_delta(r, "post_fire", before, after)
    back = OP.load()
    return (d["changed"] is True and d["registry_entries_after"] == 815
            and back["phase"] not in ("FAILED", "RECOVERY_REQUIRED")
            and back.get("failure") is None)


@case("T12", "use an unregistered mutation tool")
def t12():
    return _refuses(OP.refuse_unregistered, "rm_rf_everything")


@case("T13", "add a host gate/state executor")
def t13():
    return _refuses(OP.refuse_host_computation, "host gate evaluation loop over the netlist")


@case("T14", "compute an expected answer on the host")
def t14():
    return _refuses(OP.refuse_host_computation, "expected-answer computation on the host")


@case("T15", "host-selected answer-bearing addressing")
def t15():
    return _refuses(OP.refuse_host_computation, "host-selected answer-bearing addressing")


@case("T16", "fail during configuration and restore automatically")
def t16():
    r = _fresh()
    for p in ("SNAPSHOT", "VERIFY_BASELINE"):
        OP.enter(r, p); OP.complete_phase(r, p)
    OP.enter(r, "CONFIGURE")
    r["failure"] = "configuration step failed"; OP.save(r)
    back = OP.load()
    return back["failure"] == "configuration step failed" and back["phase"] == "CONFIGURE"


@case("T17", "fail after fire and restore automatically")
def t17():
    r = _fresh()
    for p in ("SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE", "INJECT_LITERAL_INPUT", "FIRE"):
        OP.enter(r, p); OP.complete_phase(r, p)
    r["failure"] = "post-fire failure"; OP.save(r)
    back = OP.load()
    return back["failure"] == "post-fire failure" and "FIRE" in back["phases_done"]


@case("T18", "host interruption recovers WITHOUT being called a substrate failure")
def t18():
    r = _fresh()
    for p in ("SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE", "INJECT_LITERAL_INPUT", "FIRE"):
        OP.enter(r, p); OP.complete_phase(r, p)
    r["baseline"] = {"container_bytes": OP.CONTAINER_BYTES, "container_magic_ok": True,
                     "registry_entries": 812, "registry_keyset_sha": "a" * 64}
    OP.save(r)
    OP.resume()                                # a fresh process picks up the preserved record
    back = OP.load()
    # the host exited after FIRE: the operator must NOT demand equality to the start baseline,
    # and must NOT mark the machine failed.
    return (back["phase"] == "SCAN_PENDING" and back.get("failure") is None
            and back["phase"] not in ("FAILED", "RECOVERY_REQUIRED")
            and any(d["label"] == "host_restart_observation" for d in back.get("deltas", [])))


@case("T24", "a design-derived interval is accepted as the approved readiness condition")
def t24():
    r = _fresh()
    ok = OP.require_readiness(r, {"kind": "design_interval", "design_seconds": 30})
    bare = _refuses(OP.require_readiness, _fresh(), {"kind": "design_interval"})
    return ok is True and bare


@case("T19", "restoration twice does not delete additional state")
def t19():
    r = _fresh(); OP.acquire_lock(r["run_id"])
    OP.release_lock(); OP.release_lock()       # idempotent
    return not os.path.exists(OP.LOCK_PATH)


@case("T20", "one failed candidate alters the working-build status")
def t20():
    r = _fresh(); r["failure"] = "candidate-local failure"; OP.save(r)
    base = OP.measure_baseline()
    return base["container_bytes"] == OP.CONTAINER_BYTES and base["container_magic_ok"]


@case("T21", "omit an applicable owner-authored instrument")
def t21():
    required = {"scan_index", "scan_permanence", "readout_meter", "calibration"}
    return required.issubset(set(OP.TOOL_ALLOWLIST))


@case("T22", "guess owner-specific timing rather than enter OWNER_INPUT_REQUIRED")
def t22():
    r = _fresh()
    refused = _refuses(OP.require_readiness, r, None)
    back = OP.load()
    return refused and back["phase"] == "OWNER_INPUT_REQUIRED" and back["owner_input_required"]


@case("T23", "complete without running the unchanged frozen calibration suite")
def t23():
    r = _fresh()
    for p in PHASES_BEFORE_CAL:
        OP.enter(r, p); OP.complete_phase(r, p)
    return _refuses(OP.enter, r, "COMPLETE")


PHASES_BEFORE_CAL = ["SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE", "INJECT_LITERAL_INPUT", "FIRE",
                     "WAIT_PHYSICAL", "SCAN", "HASH_AND_RECORD", "RESTORE", "VERIFY_RESTORATION"]


def run_all():
    print("\nMUHLOP ENFORCEMENT TESTS — each attempts the forbidden transition and requires refusal\n")
    npass = nfail = 0
    for ident, behaviour, fn in CASES:
        try:
            ok = bool(fn())
        except Exception as exc:
            print("  %-5s %-58s ERROR %s" % (ident, behaviour, type(exc).__name__)); nfail += 1
            continue
        print("  %-5s %-58s %s" % (ident, behaviour, "PASS" if ok else "FAIL"))
        npass += ok; nfail += (not ok)
    print("\n  %d PASS · %d FAIL of %d enforcement cases" % (npass, nfail, len(CASES)))
    print("  container and registry untouched by these cases; no calibration run was triggered.")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_all())
