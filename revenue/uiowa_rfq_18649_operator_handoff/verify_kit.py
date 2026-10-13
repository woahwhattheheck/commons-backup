#!/usr/bin/env python3
"""verify_kit.py -- earn a WORKING/DRAFT/MISSING status for every kit component.

Why this exists
---------------
An operator handoff that lists components as "working" because their README says
so is worthless: the README is the author's claim, not evidence. This tool
refuses to read status out of prose. A component is only called WORKING if this
process executed its own automated check and saw it pass, in this run, on this
machine.

Isolation rule
--------------
Other seats own their lane directories. This tool never executes anything inside
them. Each lane is copied to a temporary directory first and the check runs on
the copy, so a test that writes output files cannot mutate another seat's work.
The copy is deleted afterwards.

Status vocabulary (the only three the handoff uses)
---------------------------------------------------
  WORKING  an automated check inside the component was executed here and passed,
           and it actually ran at least one assertion-bearing test.
  DRAFT    the component exists but did not earn WORKING: no automated check, a
           check that failed, a check that timed out, or a check that needs a
           dependency this offline environment does not have.
  MISSING  the manifest says a phase needs this component and no directory for it
           exists yet.
  UNMAPPED is reported alongside the three above for lanes found on disk that the
           manifest does not place in a phase. It is a bookkeeping signal for the
           operator, not a quality judgement -- new lanes land continuously.

Absent evidence is never upgraded. A component with no check does not become a
pass, a zero, or a score. There is no maturity rating here and no ranking of one
seat's lane against another's.

Usage
-----
  python3 verify_kit.py --root /home/user/commons/revenue
  python3 verify_kit.py --root ./fixtures/minikit --manifest fixtures/minikit_manifest.json \
                        --out-json out.json --out-csv out.csv --out-md out.md
  python3 verify_kit.py --root ... --no-exec      # inventory only, run nothing
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from verification_artifacts import capture_output, canonical_digest, semantic_report, tree_digest, write_json

WORKING = "WORKING"
DRAFT = "DRAFT"
MISSING = "MISSING"
UNMAPPED = "UNMAPPED"

# Modules a lane may import that this offline, stdlib-only environment does not
# provide. Presence of one of these is reported as a real gap, not hidden.
STDLIB_HINT_SKIP = {"", "."}

RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
MODULE_ERR_RE = re.compile(r"No module named '([^']+)'")

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

# Directories that hold test INPUTS rather than a component's own checks. A fixture
# may legitimately contain a deliberately-broken sample -- this lane's own minikit does
# -- and collecting it as the parent component's test would make every kit that ships a
# negative fixture look broken. Inventory still counts these files; only check discovery
# skips them.
FIXTURE_DIRS = {"fixtures", "fixture", "samples"}


def _ignore(_dir, names):
    return [n for n in names if n in SKIP_DIRS or n.endswith((".pyc", ".pyo"))]


def find_checks(lane_dir):
    """Return test files inside a lane, relative to the lane root, sorted."""
    found = []
    for dirpath, dirnames, filenames in os.walk(lane_dir):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and d.lower() not in FIXTURE_DIRS]
        for fn in filenames:
            if (fn.startswith("test_") or fn.endswith("_test.py")) and fn.endswith(".py"):
                found.append(os.path.relpath(os.path.join(dirpath, fn), lane_dir))
    return sorted(found)


def inventory(lane_dir):
    """Count what is physically in a lane. No judgement, just facts."""
    files = 0
    py = 0
    docs = 0
    data = 0
    reqs = []
    for dirpath, dirnames, filenames in os.walk(lane_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if fn.endswith((".pyc", ".pyo")):
                continue
            files += 1
            if fn.endswith(".py"):
                py += 1
            elif fn.endswith((".md", ".txt", ".rst")):
                docs += 1
            elif fn.endswith((".json", ".csv", ".tsv", ".yaml", ".yml")):
                data += 1
            if fn == "requirements.txt":
                try:
                    with open(os.path.join(dirpath, fn), encoding="utf-8") as fh:
                        reqs = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
                except OSError:
                    reqs = ["<unreadable>"]
    return {"files": files, "py_files": py, "doc_files": docs, "data_files": data,
            "declared_requirements": reqs}


def run_one_check(workdir, rel_test, timeout, root=None, repo_root=None):
    """Execute one test file in an isolated copy. Returns a result record.

    Primary form is `python3 -m unittest <module>` from the test file's own
    directory: it reports "Ran N tests" whether or not the file carries a
    __main__ guard, so a file that defines no tests cannot masquerade as a pass.
    If that form cannot import the module, fall back to running the file from
    the lane root, which is how some lanes resolve their fixture paths.
    """
    test_path = os.path.join(workdir, rel_test)
    test_dir = os.path.dirname(test_path) or workdir
    module = os.path.splitext(os.path.basename(rel_test))[0]
    python = [sys.executable] + (["-" + "O" * sys.flags.optimize] if sys.flags.optimize else [])
    label = "python3" + (" -" + "O" * sys.flags.optimize if sys.flags.optimize else "")
    attempts = [
        {"cmd": python + ["-m", "unittest", module], "cwd": test_dir,
         "form": "%s -m unittest %s  (cwd=%s)" % (label, module, os.path.dirname(rel_test) or ".")},
        {"cmd": python + [os.path.basename(rel_test)], "cwd": test_dir,
         "form": "%s %s  (cwd=%s)" % (label, os.path.basename(rel_test), os.path.dirname(rel_test) or ".")},
    ]
    last = None
    for att in attempts:
        started = time.monotonic()
        try:
            proc = subprocess.run(att["cmd"], cwd=att["cwd"], timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = proc.stdout.decode("utf-8", "replace")
            rc = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            out = (exc.output or b"").decode("utf-8", "replace")
            rc = None
            timed_out = True
        dur = round(time.monotonic() - started, 2)
        m = RAN_RE.search(out)
        ran = int(m.group(1)) if m else 0
        missing_mod = MODULE_ERR_RE.search(out)
        rec = {
            "test_file": rel_test,
            "command": att["form"],
            "argv": att["cmd"], "cwd": att["cwd"],
            "exit_code": rc,
            "timed_out": timed_out,
            "duration_s": dur,
            "tests_ran": ran,
            "missing_module": missing_mod.group(1) if missing_mod else None,
            "output_tail": out.strip()[-1200:],
        }
        rec["python_optimization"] = sys.flags.optimize
        rec.update(capture_output(out, rec["command"],
                                  [("WORK", workdir), ("ROOT", root), ("REPO", repo_root)]))
        last = rec
        if rc == 0 and ran > 0:
            return rec
        # Only retry the second form when the first failed to import anything at all.
        if not (ran == 0 and rc not in (0,) and not timed_out):
            return rec
    return last


def run_runner(workdir, runner, root, timeout, repo_root=None):
    """Execute a component's documented command-line entry point in the copy.

    Some components are real, usable tools that simply ship no unittest file.
    Reading their README would tell us nothing. Running their documented command
    and seeing it exit 0 with output is direct evidence, so it is allowed to earn
    WORKING -- but the reason string always says the status came from the runner,
    not from a test suite, so nobody mistakes one for the other.
    """
    outdir = tempfile.mkdtemp(prefix="verify_kit_out_")
    try:
        repo_root = repo_root or os.path.dirname(os.path.abspath(root))
        cmd = [t.replace("{ROOT}", os.path.abspath(root))
                .replace("{REPO}", repo_root)
                .replace("{OUT}", outdir)
               for t in runner["cmd"]]
        cmd = [sys.executable if t == "python3" else t for t in cmd]
        if cmd and cmd[0] == sys.executable and sys.flags.optimize:
            cmd.insert(1, "-" + "O" * sys.flags.optimize)
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=workdir, timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = proc.stdout.decode("utf-8", "replace")
            rc, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired as exc:
            out = (exc.output or b"").decode("utf-8", "replace")
            rc, timed_out = None, True
        missing_mod = MODULE_ERR_RE.search(out)
        rec = {
            "test_file": "(documented runner)",
            "command": " ".join(["python3" if t == sys.executable else t for t in cmd]),
            "argv": cmd, "cwd": workdir,
            "exit_code": rc,
            "timed_out": timed_out,
            "duration_s": round(time.monotonic() - started, 2),
            "tests_ran": 0,
            "is_runner": True,
            "produced_output": bool(out.strip()),
            "missing_module": missing_mod.group(1) if missing_mod else None,
            "output_tail": out.strip()[-1200:],
        }
        rec["python_optimization"] = sys.flags.optimize if cmd[0] == sys.executable else None
        rec.update(capture_output(out, rec["command"], [("WORK", workdir), ("OUT", outdir),
                                                       ("ROOT", root), ("REPO", repo_root)]))
        return rec
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def classify(present, checks, results, inv, runner_result=None):
    """Turn observed facts into one of the three statuses, with a stated reason."""
    if not present:
        return MISSING, "no directory for this component exists under the survey root", "unbuilt"
    if not checks:
        if runner_result is not None:
            if runner_result["exit_code"] == 0 and runner_result["produced_output"]:
                return WORKING, ("no unittest suite; documented runner `%s` was executed here "
                                 "and exited 0 with output" % runner_result["command"]), "runner"
            return DRAFT, ("documented runner `%s` did not succeed here (exit=%s, timed_out=%s)"
                           % (runner_result["command"], runner_result["exit_code"],
                              runner_result["timed_out"])), "runner"
        if inv["py_files"] > 0:
            return DRAFT, ("executable code present (%d .py files) but the component ships no "
                           "automated check, so nothing here can be executed to prove it works"
                           % inv["py_files"]), "code-no-check"
        return DRAFT, ("document component: %d document/data files and no executable code; "
                       "completeness of prose is not machine-checkable and needs a human read"
                       % (inv["doc_files"] + inv["data_files"])), "document"
    failed = [r for r in results if not (r["exit_code"] == 0 and r["tests_ran"] > 0)]
    total_ran = sum(r["tests_ran"] for r in results)
    if not failed and total_ran > 0:
        return WORKING, ("executed %d test file(s) here, %d tests ran, all passed"
                         % (len(results), total_ran)), "executable"
    dep = next((r["missing_module"] for r in failed if r["missing_module"]), None)
    if dep:
        return DRAFT, ("check could not run offline: missing dependency %r (declared: %s)"
                       % (dep, ", ".join(inv["declared_requirements"]) or "none")), "executable"
    if any(r["timed_out"] for r in failed):
        return DRAFT, "check exceeded the timeout and was killed; treated as unproven", "executable"
    if total_ran == 0:
        return DRAFT, "check file present but no tests were collected from it", "executable"
    return DRAFT, ("check executed and did not pass: %d of %d test file(s) failed"
                   % (len(failed), len(results))), "executable"


def survey(root, manifest, timeout=120, execute=True, repo_root=None):
    prefix = manifest.get("lane_prefix", "")
    on_disk = sorted(
        d for d in os.listdir(root)
        if d.startswith(prefix) and os.path.isdir(os.path.join(root, d))
    ) if os.path.isdir(root) else []
    mapped = set()
    rows = []

    def assess(lane, phase_id, phase_title, role, runner=None):
        lane_dir = os.path.join(root, lane)
        present = os.path.isdir(lane_dir)
        inv = inventory(lane_dir) if present else {"files": 0, "py_files": 0, "doc_files": 0,
                                                   "data_files": 0, "declared_requirements": []}
        checks = find_checks(lane_dir) if present else []
        results = []
        source_sha256 = tree_digest(lane_dir) if present else None
        if present and checks and execute:
            tmp = tempfile.mkdtemp(prefix="verify_kit_")
            try:
                work = os.path.join(tmp, lane)
                shutil.copytree(lane_dir, work, ignore=_ignore)
                source_sha256 = tree_digest(work)
                for rel in checks:
                    results.append(run_one_check(work, rel, timeout, root, repo_root))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        runner_result = None
        if present and not checks and runner and execute:
            tmp = tempfile.mkdtemp(prefix="verify_kit_")
            try:
                work = os.path.join(tmp, lane)
                shutil.copytree(lane_dir, work, ignore=_ignore)
                source_sha256 = tree_digest(work)
                runner_result = run_runner(work, runner, root, timeout, repo_root)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            results.append(runner_result)
        status, reason, kind = classify(present, checks if execute else [], results, inv,
                                        runner_result)
        if present and checks and not execute:
            status, reason, kind = DRAFT, "not executed (--no-exec): status not earned", "executable"
        return {
            "phase": phase_id, "phase_title": phase_title, "component": lane, "role": role,
            "present": present, "status": status, "reason": reason, "kind": kind,
            "check_files": checks, "tests_ran": sum(r["tests_ran"] for r in results),
            "inventory": inv, "runs": results, "source_sha256": source_sha256,
        }

    for phase in sorted(manifest["phases"], key=lambda p: p["order"]):
        for comp in phase["components"]:
            lane = comp["lane"]
            mapped.add(lane)
            rows.append(assess(lane, phase["id"], phase["title"], comp.get("role", ""),
                               comp.get("runner")))

    for lane in on_disk:
        if lane in mapped:
            continue
        rec = assess(lane, "unassigned", "Unassigned (discovered on disk)",
                     "discovered after this manifest was written; assign it to a phase")
        rec["status"] = UNMAPPED if rec["status"] != MISSING else MISSING
        rec["reason"] = ("lane found on disk but not placed in any phase by the manifest; "
                         "underlying observation: " + rec["reason"])
        rows.append(rec)

    return {
        "survey_root": os.path.abspath(root),
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "executed_checks": bool(execute),
        "timeout_s": timeout,
        "manifest_version": manifest.get("manifest_version"),
        "manifest_sha256": canonical_digest(manifest),
        "counts": {s: sum(1 for r in rows if r["status"] == s)
                   for s in (WORKING, DRAFT, MISSING, UNMAPPED)},
        "components": rows,
    }


def write_csv(report, path):
    report = semantic_report(report)
    cols = ["phase", "component", "status", "kind", "tests_ran", "check_files", "reason"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in report["components"]:
            w.writerow([r["phase"], r["component"], r["status"], r["kind"], r["tests_ran"],
                        ";".join(r["check_files"]) or "-", r["reason"]])


def write_md(report, path):
    report = semantic_report(report)
    L = []
    L.append("# Component verification log")
    L.append("")
    L.append("WORKING requires observed execution; missing or unexecuted components remain "
             "unproven. Checks run on temporary copies. This is the normalized observation "
             "view, not a verbatim execution transcript; retain --out-run-json for raw evidence.")
    L.append("")
    L.append("- survey root: `%s`" % report["survey_root"])
    L.append("- artifact format: `%s`" % report["artifact_format"])
    L.append("- manifest SHA-256: `%s`" % report["manifest_sha256"])
    L.append("- python: %s · per-check timeout: %ss · checks executed: %s"
             % (report["python"], report["timeout_s"], report["executed_checks"]))
    c = report["counts"]
    L.append("- counts: WORKING %d · DRAFT %d · MISSING %d · UNMAPPED %d"
             % (c[WORKING], c[DRAFT], c[MISSING], c[UNMAPPED]))
    L.append("")
    for r in report["components"]:
        L.append("## %s — %s" % (r["component"], r["status"]))
        L.append("")
        L.append("- phase: %s" % r["phase"])
        L.append("- reason: %s" % r["reason"])
        L.append("- source SHA-256: `%s`" % r["source_sha256"])
        if r["present"]:
            i = r["inventory"]
            L.append("- files: %d (%d py, %d doc, %d data)"
                     % (i["files"], i["py_files"], i["doc_files"], i["data_files"]))
            if i["declared_requirements"]:
                L.append("- declared requirements: %s" % ", ".join(i["declared_requirements"]))
        for run in r["runs"]:
            L.append("")
            L.append("```")
            L.append("$ %s" % run["command"])
            L.append("exit=%s timed_out=%s tests_ran=%s optimization=%s"
                     % (run["exit_code"], run["timed_out"], run["tests_ran"], run["python_optimization"]))
            L.append("normalized-output-sha256=%s" % run["output_sha256"])
            L.append(run["output_tail"] or "(no output)")
            L.append("```")
        L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L).rstrip() + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Earn a status for every kit component by running it.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="directory containing the uiowa_rfq_18649_* lane directories")
    ap.add_argument("--manifest", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "kit_manifest.json"))
    ap.add_argument("--timeout", type=int, default=120, help="seconds per check file")
    ap.add_argument("--no-exec", action="store_true", help="inventory only; execute nothing")
    ap.add_argument("--out-json", default=None, help="stable semantic JSON")
    ap.add_argument("--out-run-json", default=None, help="raw execution provenance including full output")
    ap.add_argument("--out-csv", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--repo-root", default=None,
                    help="repository root for a component runner's {REPO} placeholder; "
                         "defaults to the parent of --root")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    destinations = [os.path.realpath(p) for p in
                    (args.out_json, args.out_run_json, args.out_csv, args.out_md) if p]
    if len(destinations) != len(set(destinations)):
        ap.error("output destinations must be distinct; raw metadata must not overwrite observations")

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    report = survey(args.root, manifest, timeout=args.timeout,
                    execute=not args.no_exec, repo_root=args.repo_root)

    if args.out_json:
        write_json(report, args.out_json)
    if args.out_run_json:
        write_json(report, args.out_run_json, raw=True)
    if args.out_csv:
        write_csv(report, args.out_csv)
    if args.out_md:
        write_md(report, args.out_md)

    if not args.quiet:
        c = report["counts"]
        print("survey root : %s" % report["survey_root"])
        print("generated   : %s (python %s)" % (report["generated_at_utc"], report["python"]))
        print("counts      : WORKING %d | DRAFT %d | MISSING %d | UNMAPPED %d"
              % (c[WORKING], c[DRAFT], c[MISSING], c[UNMAPPED]))
        print("")
        print("%-12s %-46s %-9s %s" % ("PHASE", "COMPONENT", "STATUS", "EVIDENCE"))
        for r in report["components"]:
            if r["status"] == WORKING:
                ev = ("%d tests passed" % r["tests_ran"]) if r["tests_ran"] else "documented runner exited 0"
            else:
                ev = r["reason"][:56]
            print("%-12s %-46s %-9s %s" % (r["phase"][:12], r["component"][:46], r["status"], ev))
    return 0


if __name__ == "__main__":
    sys.exit(main())
