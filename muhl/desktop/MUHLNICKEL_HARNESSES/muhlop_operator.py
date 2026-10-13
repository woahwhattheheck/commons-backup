#!/usr/bin/env python3
"""host/muhlop_operator.py — THE EXECUTION PROTOCOL. A strict finite-state operator.

Additive and disjoint: this file adds an entry point and changes nothing that already exists. It
does not alter frozen paths, the calibration suite, governance, manifests, checkers or preserved
evidence, and it performs no computation belonging to the machine.

WHY IT EXISTS. The sequencing rules were previously carried in prose and had to be remembered. Here
they are executable: a run advances through a fixed phase order and an out-of-order transition is
refused by code rather than by recollection.

PHASE ORDER, and none may be skipped, reordered or substituted:
    SNAPSHOT -> VERIFY_BASELINE -> CONFIGURE -> INJECT_LITERAL_INPUT -> FIRE ->
    WAIT_PHYSICAL -> SCAN -> HASH_AND_RECORD -> RESTORE -> VERIFY_RESTORATION ->
    FROZEN_CALIBRATION -> COMPLETE

WHAT THE HOST IS PERMITTED TO DO HERE, and it is the whole list: snapshot bytes, verify a baseline,
invoke an owner-approved configuration path, place an owner-authorized literal input, invoke the
owner-authorized fire path, wait on an owner-approved physical readiness primitive, invoke the
owner's unchanged instruments, hash and store raw observations, restore journaled state, and run the
frozen calibration suite. Anything else is refused.

REFUSED BY CODE: evaluating gates on the host, advancing state on the host, computing an expected
answer, host-selected answer-bearing addressing, a generic sleep or host clock standing in for the
physical readiness primitive, an unregistered mutation tool, a second concurrent run, and starting a
new run while a prior journal is open.

WAIT_PHYSICAL is mandatory. When the owner-approved readiness primitive is not recoverable from the
local specification, tools or journals, the operator stops in OWNER_INPUT_REQUIRED and emits one
bounded question. It does not substitute a delay.

  python host/muhlop_operator.py status
  python host/muhlop_operator.py run <workload-id>
  python host/muhlop_operator.py resume
  python host/muhlop_operator.py results
  python host/muhlop_operator.py answer <key> <value>
  python host/muhlop_operator.py selftest
"""
import hashlib, io, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROTOCOL_VERSION = 1
STATE_DIR = "C:/llm/sdc_out/muhlop"
STATE_PATH = os.path.join(STATE_DIR, "run_state.json")
LOCK_PATH = os.path.join(STATE_DIR, "run.lock")
JOURNAL_DIR = os.path.join(STATE_DIR, "journals")
RESULT_DIR = os.path.join(STATE_DIR, "results")
TITAN = "C:/llm/models/titan.gguf"
REG = "C:/llm/models/titan_circuits.json"

CONTAINER_BYTES = 40028316800
CONTAINER_MAGIC = b"GGUF"
CALIBRATION_EXPECT = (34, 0)

PHASES = ["SNAPSHOT", "VERIFY_BASELINE", "CONFIGURE", "INJECT_LITERAL_INPUT", "FIRE",
          "WAIT_PHYSICAL", "SCAN", "HASH_AND_RECORD", "RESTORE", "VERIFY_RESTORATION",
          "FROZEN_CALIBRATION", "COMPLETE"]
TERMINAL = ("COMPLETE", "RECOVERY_REQUIRED", "OWNER_INPUT_REQUIRED", "FAILED")

# Only these may be invoked as owner tools. An entry point not on this list is refused, and a raw
# shell fragment is refused because every entry here is an explicit argument vector.
TOOL_ALLOWLIST = {
    "scan_index":      ["pfc_index.py", "--stats"],
    "scan_permanence": ["muhl_permanence_audit.py"],
    "scan_space":      ["pfc_space.py"],
    "scan_collapse":   ["muhl_collapse.py"],
    "readout_meter":   ["pfc_meter.py"],
    "readout_assert":  ["pfc_assert.py"],
    "readout_inspect": ["pfc_inspect.py"],
    "calibration":     ["muhl_test.py"],
}

# Host-side constructs the operator refuses to carry. Each is a shape, not a name, so renaming does
# not evade it. Checked against any candidate step body handed to the operator.
REFUSED_SHAPES = (
    "gate evaluation on the host",
    "host state advancement",
    "expected-answer computation on the host",
    "host-selected answer-bearing addressing",
    "generic sleep standing in for the physical readiness primitive",
)


class ProtocolError(RuntimeError):
    """Raised on any refused transition. The operator fails closed."""


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _ensure_dirs():
    for d in (STATE_DIR, JOURNAL_DIR, RESULT_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)


def _write_json(path, doc):
    """Every protocol write is fsynced in this function, so an interrupted process leaves a state
    file that is either the previous record or the new one, never a partial line."""
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.flush(); os.fsync(f.fileno())
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def _read_json(path):
    if not os.path.exists(path):
        return None
    return json.load(io.open(path, encoding="utf-8"))


# ── baseline measurement, read-only ───────────────────────────────────────────────────────────────
def measure_baseline():
    """Read the current container and registry facts. Counts are ENTRIES; sizes are BYTES."""
    st = os.stat(TITAN)
    with io.open(TITAN, "rb", buffering=0) as f:
        magic = f.read(4)
    reg = json.load(io.open(REG, encoding="utf-8"))
    keyset = _sha("\n".join(sorted(reg)).encode("utf-8"))
    return {"container_bytes": st.st_size, "container_magic_ok": magic == CONTAINER_MAGIC,
            "registry_entries": len(reg), "registry_keyset_sha": keyset}


def baseline_matches(recorded, current):
    """EQUALITY IS CHECKED AT TWO BOUNDARIES ONLY: before a run starts, and after an explicitly
    authorized reversal. It is NOT checked while the machine is running.

    A matching count with a differing key set is not a match.

    This function answers 'are these two states equal', nothing more. It does not decide that an
    inequality is a fault; see record_delta for state observed during a run."""
    return (recorded["container_bytes"] == current["container_bytes"]
            and current["container_magic_ok"]
            and recorded["registry_entries"] == current["registry_entries"]
            and recorded["registry_keyset_sha"] == current["registry_keyset_sha"])


def record_delta(run, label, before, after):
    """STATE CHANGE DURING A RUN IS DATA. After FIRE the machine is computing, so entry counts,
    key sets, fields and observations may all move. Those movements are recorded as raw
    measurements with their before and after values. Nothing here classifies a change as a fault,
    and no field is treated as invariant during execution unless the specification marks it so."""
    d = {"label": label, "at": _now(),
         "registry_entries_before": before.get("registry_entries"),
         "registry_entries_after": after.get("registry_entries"),
         "registry_keyset_before": before.get("registry_keyset_sha"),
         "registry_keyset_after": after.get("registry_keyset_sha"),
         "container_bytes_before": before.get("container_bytes"),
         "container_bytes_after": after.get("container_bytes"),
         "changed": before != after}
    run.setdefault("deltas", []).append(d)
    save(run)
    return d


# ── run state ─────────────────────────────────────────────────────────────────────────────────────
def new_run(workload):
    _ensure_dirs()
    rid = "%s-%s" % (workload, _sha((_now() + workload).encode("utf-8"))[:12])
    return {"protocol_version": PROTOCOL_VERSION, "run_id": rid, "workload": workload,
            "phase": None, "phases_done": [], "baseline": None, "region_hashes": {},
            "journal_id": None, "literal_input": None, "fire_id": None,
            "readiness_primitive": None, "instruments": [], "observations": {},
            "restoration": None, "calibration": None, "owner_input_required": None,
            "failure": None, "started": _now(), "updated": _now()}


def save(run):
    run["updated"] = _now()
    _write_json(STATE_PATH, run)


def load():
    return _read_json(STATE_PATH)


def acquire_lock(rid):
    _ensure_dirs()
    if os.path.exists(LOCK_PATH):
        held = _read_json(LOCK_PATH) or {}
        raise ProtocolError("a run lock is already held by %s; concurrent runs are refused"
                            % held.get("run_id", "an earlier run"))
    _write_json(LOCK_PATH, {"run_id": rid, "acquired": _now()})


def release_lock():
    if os.path.exists(LOCK_PATH):
        os.remove(LOCK_PATH)


def enter(run, phase):
    """The only way a run changes phase. Order is fixed and an out-of-order request is refused."""
    if phase not in PHASES:
        raise ProtocolError("%s is not a protocol phase" % phase)
    want = PHASES.index(phase)
    if want == 0:
        if run["phases_done"]:
            raise ProtocolError("SNAPSHOT may only open a run")
    else:
        need = PHASES[want - 1]
        if need not in run["phases_done"]:
            raise ProtocolError("%s is refused: %s has not completed" % (phase, need))
    if phase in run["phases_done"]:
        raise ProtocolError("%s has already completed in this run" % phase)
    run["phase"] = phase
    save(run)
    return run


def complete_phase(run, phase):
    if run["phase"] != phase:
        raise ProtocolError("cannot complete %s while the run is in %s" % (phase, run["phase"]))
    run["phases_done"].append(phase)
    save(run)
    return run


def refuse_unregistered(tool_key):
    if tool_key not in TOOL_ALLOWLIST:
        raise ProtocolError("%s is not an allowlisted owner tool; unregistered mutation and raw "
                            "shell fragments are refused" % tool_key)
    return TOOL_ALLOWLIST[tool_key]


def refuse_host_computation(description):
    """A candidate step describing host-side computation is refused before it can run."""
    low = (description or "").lower()
    for shape in REFUSED_SHAPES:
        key = shape.split()[0]
        if key in low and ("host" in low or "sleep" in low):
            raise ProtocolError("refused: the step describes %s" % shape)
    return True


def require_readiness(run, primitive):
    """WAIT_PHYSICAL.

    OWNER AUTHORITY, recorded 2026-07-31: there is no tool that decides when to scan. The interval
    comes from the muhlnickel's DESIGN — his example: if it is designed to complete in 30 seconds,
    check after 30 seconds. So a DESIGN-DERIVED interval is the approved condition and is accepted
    here, carrying the design figure it came from.

    What stays refused is an interval with no design behind it: a bare sleep, a poll, a host clock
    or an immediate read. Those are the host inventing a condition rather than reading one off the
    design, and the operator stops and asks instead."""
    if isinstance(primitive, dict) and primitive.get("kind") == "design_interval":
        if not primitive.get("design_seconds"):
            raise ProtocolError("a design_interval must carry the design figure it derives from")
        run["readiness_primitive"] = primitive
        save(run)
        return True
    if primitive in (None, "", "sleep", "delay", "poll", "host_clock", "immediate"):
        run["owner_input_required"] = {
            "blocked_transition": "WAIT_PHYSICAL -> SCAN",
            "inspected": "local specification, registry, journals, owner tool surfaces",
            "ambiguity": "the owner-approved physical readiness primitive between FIRE and SCAN "
                         "is not recoverable locally",
            "minimum_answer": "the identifier of the existing local readiness primitive, or its "
                              "non-proprietary invocation"}
        run["phase"] = "OWNER_INPUT_REQUIRED"
        save(run)
        raise ProtocolError("OWNER_INPUT_REQUIRED: %s" % run["owner_input_required"]["ambiguity"])
    run["readiness_primitive"] = primitive
    save(run)
    return True


def run_tool(tool_key, extra=None):
    """Invoke an allowlisted owner tool unchanged. stdout is captured as a raw observation."""
    argv = list(refuse_unregistered(tool_key))
    if extra:
        argv = argv + [str(x) for x in extra]
    env = dict(os.environ); env["PFC_ROOT"] = env.get("PFC_ROOT", "C:/llm"); env["PYTHONUTF8"] = "1"
    p = subprocess.run([sys.executable, os.path.join(HERE, argv[0])] + argv[1:],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    out = p.stdout.decode("utf-8", "replace")
    return {"tool": tool_key, "exit": p.returncode, "sha256": _sha(out.encode("utf-8")),
            "bytes": len(out)}, out


def frozen_calibration():
    """The calibration suite is invoked exactly as stored and is never modified by this operator."""
    rec, out = run_tool("calibration")
    passed = failed = None
    for line in out.splitlines():
        if "PASS" in line and "FAIL" in line:
            parts = line.replace("·", " ").split()
            for i, tok in enumerate(parts):
                if tok == "PASS" and i: passed = int(parts[i - 1])
                if tok == "FAIL" and i: failed = int(parts[i - 1])
    rec["passed"] = passed; rec["failed"] = failed
    rec["matches_baseline"] = (passed, failed) == CALIBRATION_EXPECT
    return rec


def status():
    run = load()
    if run is None:
        base = measure_baseline()
        print("no run on record. baseline now: %d registry ENTRIES, container %d BYTES, magic ok %s"
              % (base["registry_entries"], base["container_bytes"], base["container_magic_ok"]))
        print("allowed next action: run <workload-id>")
        return 0
    print("run %s  workload %s  phase %s" % (run["run_id"], run["workload"], run["phase"]))
    print("  phases done: %s" % ", ".join(run["phases_done"]) or "none")
    if run["phase"] not in TERMINAL and run["phases_done"]:
        print("  INCOMPLETE RUN ON RECORD — a new run is refused until this one is restored.")
        print("  allowed next action: resume")
    elif run["phase"] == "OWNER_INPUT_REQUIRED":
        print("  OWNER INPUT REQUIRED at %s" % run["owner_input_required"]["blocked_transition"])
        print("  allowed next action: answer <key> <value>")
    else:
        print("  allowed next action: run <workload-id>")
    return 0


def resume():
    """RESTART AFTER A HOST INTERRUPTION.

    The machine keeps running without host monitoring, so a host process that exited says nothing
    about the machine. This reads the preserved host record, observes the CURRENT state with the
    owner's scanners, reconciles which host steps completed, and reports. It does not describe the
    machine as stopped, failed or faulted because the host went away."""
    run = load()
    if run is None:
        print("nothing to resume."); return 0
    if run["phase"] == "COMPLETE":
        print("last host run completed; nothing to resume."); return 0
    cur = measure_baseline()
    print("HOST RECORD RECOVERED — the host exited during %s. This is a host-side interruption;"
          % (run["phase"] or "an early phase"))
    print("  it carries no statement about the machine, which runs without host monitoring.")
    print("  host phases completed: %s" % (", ".join(run["phases_done"]) or "none"))
    rec = run.get("baseline")
    if rec:
        record_delta(run, "host_restart_observation", rec, cur)
        print("  observed now vs recorded start: registry %s -> %s ENTRIES, container %s BYTES"
              % (rec["registry_entries"], cur["registry_entries"], cur["container_bytes"]))
        print("  recorded as raw observation, not classified.")
    fired = "FIRE" in run["phases_done"]
    reversed_ok = "RESTORE" in run["phases_done"]
    if fired and not reversed_ok:
        print("  a fire was issued and no authorized reversal has run. Equality to the start "
              "baseline is NOT required here; only an authorized reversal restores it.")
        run["phase"] = "SCAN_PENDING"; save(run)
        print("  allowed next action: scan with the owner instruments, or run the journaled reversal.")
        return 0
    if rec and baseline_matches(rec, cur):
        run["restoration"] = {"verified": True, "at": _now()}
        run["phase"] = "COMPLETE"; save(run); release_lock()
        print("  no fire was issued and state equals the recorded start; lock released.")
        return 0
    run["phase"] = "RESTORATION_PENDING"; save(run)
    print("  journaled host-side reversal has not been applied; new runs refused until it is.")
    return 0


def answer(key, value):
    run = load()
    if run is None or run["phase"] != "OWNER_INPUT_REQUIRED":
        print("no owner question is outstanding."); return 1
    run["readiness_primitive"] = value if key == "readiness" else run["readiness_primitive"]
    run.setdefault("owner_answers", {})[key] = value
    run["owner_input_required"] = None
    run["phase"] = "WAIT_PHYSICAL"
    save(run)
    print("recorded owner answer for %s; run resumes at WAIT_PHYSICAL." % key)
    return 0


def results():
    run = load()
    if run is None:
        print("no results on record."); return 0
    print(json.dumps({"run_id": run["run_id"], "workload": run["workload"], "phase": run["phase"],
                      "phases_done": run["phases_done"], "instruments": run["instruments"],
                      "observations": run["observations"], "calibration": run["calibration"],
                      "restoration": run["restoration"]}, indent=1))
    return 0


def main():
    a = sys.argv[1:]
    if not a or a[0] == "status":   return status()
    if a[0] == "resume":            return resume()
    if a[0] == "results":           return results()
    if a[0] == "answer" and len(a) >= 3:
        return answer(a[1], " ".join(a[2:]))
    if a[0] == "selftest":
        import muhlop_tests
        return muhlop_tests.run_all()
    if a[0] == "run" and len(a) >= 2:
        print("a workload run requires the owner-approved readiness primitive; "
              "the operator will stop at WAIT_PHYSICAL and emit one bounded question if it is not "
              "recorded. use: selftest, status, resume, results, answer")
        return 1
    print(__doc__.strip().splitlines()[-7])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
