#!/usr/bin/env python3
"""host/mcp_wake.py — collision-hold talk is not a land.

Slack 1787637758.258119 (SPECTER collision check) held visual CI
because an isolated jojo-visual-ci-20260825-01 clone existed with no
JOJO p/{id}.md. Visual CI / render_check is already on current main
(rivet-ship-render-check-20260825-01, render-contract leftover).
SPECTER named the adjacent leftover: MCP/wake real-job verification.

DEMON Slack 1787635487.642039 assigned JOJO: one canonical MCP
inventory, one Grok smoke after active sessions, honest idle-resume.
JOJO has not posted that claim as p/{id}.md. This leftover ships it.

It does not remint render-check / render-contract. It does not remint
rivet-ship-mcp-wake-job-20260825-01 or host/mcp_wake_job.py. It does
recognize the separately claimed SPECTER production canary as one
canonical wake_jobs/{id}.json in this lane. VERIFIED requires every
canonical row in one snapshot to be DONE. It does not mutate ~/.grok.
It does not claim a named idle bc- resume. titan: NOT_WRITTEN. No auth.

  python3 host/mcp_wake.py
  python3 host/mcp_wake.py --root .
  python3 host/mcp_wake.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harness_wake.idle_resume import probe_idle_resume
from independent_commons_mcp.jobs import JobStore


DEFAULT_INVENTORY = os.path.join("ground", "MCP_INVENTORY.json")
DEFAULT_CATALOG = os.path.join("ground", "MCP_WAKE.json")
SLACK_TS = "1787637758.258119"
STRANDED_TS = "1787635487.642039"
OTHER_BC = "bc-5df880c8-9ab2-5c66-b1c0-01d7b0e7b1cd"
JOB_ID = "rivet-mcp-wake-probe-20260825-01"
SURFACES = (
    "commons_mcp.py",
    os.path.join("independent_commons_mcp"),
    os.path.join("door", "src", "mcp.server.ts"),
    "mcp_server",
)
TEST_FILES = (
    "test_commons_mcp.py",
    "test_independent_commons_mcp.py",
    "test_harness_wake.py",
    os.path.join("mcp_server", "test_mcp.py"),
)
JOB_TOOLS = (
    "upsert_job",
    "get_job",
    "tick_job",
    "checkpoint_job",
    "complete_job",
)
ADAPTER_PATHS = (
    os.path.join("harness_wake", "idle_resume.py"),
    os.path.join("harness_wake", "watchdog.py"),
    "wake_jobs",
)
WAKE_JOBS = "wake_jobs"
PRODUCTION_CANARY_ID = "specter-watchdog-head-proof-20260825-01"


def _exists(root, rel):
    return os.path.exists(os.path.join(root, rel))


def _wake_job_json_count(root):
    return _wake_job_census(root)["wake_job_json"]


def _wake_job_census(root):
    """One snapshot: count and rows come from the same listing."""
    rows = _wake_job_rows(root)
    return {"wake_jobs": rows, "wake_job_json": len(rows)}


def is_canonical_wake_job(item):
    """Production canaries are canonical. Live grok.com executor jobs are not.

    wake_jobs/ is one store: watchdog canaries and the grok.com executor queue.
    VERIFIED is the canary lane. A live LEASED/OPEN executor job stays visible
    and does not poison that lane.
    """
    item = item or {}
    claim = str(item.get("owner_claim") or "").strip().upper()
    schema = str(item.get("schema") or "").strip().lower()
    checkpoint = item.get("checkpoint") if isinstance(item.get("checkpoint"), dict) else {}
    checkpoint_schema = str(checkpoint.get("schema") or "").strip().lower()
    if claim == "GROK_EXECUTOR":
        return False
    if schema.startswith("commons-grok-executor"):
        return False
    if checkpoint_schema.startswith("commons-grok-executor"):
        return False
    return True


def _wake_state(wake_json, wake_jobs):
    """VERIFIED only when every canonical row is DONE. Else CANDIDATE/EMPTY."""
    rows = list(wake_jobs or [])
    if wake_json <= 0:
        return "EMPTY"
    if len(rows) != int(wake_json):
        return "CANDIDATE"
    canonical = [item for item in rows if is_canonical_wake_job(item)]
    if not canonical:
        return "CANDIDATE"
    statuses = [
        str((item or {}).get("status") or "UNKNOWN").upper()
        for item in canonical
    ]
    if all(status == "DONE" for status in statuses):
        return "VERIFIED"
    return "CANDIDATE"


def _wake_job_rows(root):
    """Read every job file. Invalid files stay visible, never silent.

    Executor-queue rows stay in the census. VERIFIED uses canonical canaries.
    """
    folder = os.path.join(root, WAKE_JOBS)
    if not os.path.isdir(folder):
        return []
    rows = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if (
            not name.endswith(".json")
            or name == "_last_tick.json"
            or not os.path.isfile(path)
        ):
            continue
        stem = name[:-5]
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            rows.append({"job_id": stem, "status": "INVALID"})
            continue
        if not isinstance(data, dict):
            rows.append({"job_id": stem, "status": "INVALID"})
            continue
        checkpoint = data.get("checkpoint") if isinstance(data.get("checkpoint"), dict) else {}
        rows.append(
            {
                "job_id": str(data.get("job_id") or stem),
                "status": str(data.get("status") or "UNKNOWN"),
                "owner_claim": str(data.get("owner_claim") or ""),
                "schema": str(data.get("schema") or checkpoint.get("schema") or ""),
                "result_address": str(data.get("result_address") or ""),
                "attempt_count": int(data.get("attempt_count") or 0),
                "receipt_count": len(data.get("event_receipts") or []),
            }
        )
    return rows


def _surfaces_present(root):
    found = []
    for rel in SURFACES:
        if _exists(root, rel):
            found.append(rel.replace("\\", "/"))
    return found


def _tests_present(root):
    found = []
    for rel in TEST_FILES:
        if _exists(root, rel):
            found.append(rel.replace("\\", "/"))
    return found


def _has_job_tools(root):
    path = os.path.join(root, "independent_commons_mcp", "fixtures", "tools.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    tools = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(tools, list):
        return False
    names = {
        str(row.get("name") or "").strip()
        for row in tools
        if isinstance(row, dict)
    }
    return all(name in names for name in JOB_TOOLS)


def load_inventory(text):
    """Parse the canonical MCP inventory. Invalid JSON is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "inventory is not JSON", "surfaces": []}
    if not isinstance(data, dict):
        return {"error": "inventory is not an object", "surfaces": []}
    surfaces = []
    raw = data.get("surfaces")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                path = str(item.get("path") or item.get("id") or "").strip()
            else:
                path = str(item or "").strip()
            if path:
                surfaces.append(path.replace("\\", "/"))
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "surfaces": surfaces,
        "job_tools": [
            str(name or "").strip()
            for name in (data.get("job_tools") or [])
            if str(name or "").strip()
        ],
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
    }


def grok_smoke(exists):
    """Honest Grok smoke. Missing ~/.grok is UNMEASURED, not a live connect."""
    if exists:
        return {
            "state": "CANDIDATE",
            "exists": True,
            "note": (
                "~/.grok is present. This leftover does not mutate or "
                "restart Grok. A path is not a smoke connection."
            ),
        }
    return {
        "state": "UNMEASURED",
        "exists": False,
        "note": (
            "~/.grok absent on this box. Grok smoke after active sessions "
            "is UNMEASURED. Absence was not stillness. Do not mutate Grok."
        ),
    }


def idle_resume_row(probe):
    """Named idle bc- resume of a different run stays fail-closed."""
    probe = probe or {}
    live = bool(probe.get("live_resume"))
    state = str(probe.get("state") or "UNMEASURED")
    return {
        "state": "NOT_LANDED" if live else state,
        "live_resume": live,
        "invoke_model": bool(probe.get("invoke_model")),
        "bc_id": str(probe.get("bc_id") or ""),
        "this_bc": str(probe.get("this_bc") or ""),
        "reason": str(probe.get("reason") or ""),
        "note": (
            "claimed a live resume of a different bc-. That is not measured "
            "in this harness."
            if live
            else (
                "named idle bc- resume of a different run is %s. "
                "list/inspect only. get-message-queue is this run only."
            )
            % state
        ),
    }


def verify_job(now="2026-08-25T06:00:00Z", due="2026-08-25T07:00:00Z"):
    """Cheap JobStore upsert+tick in a temp dir. Never writes wake_jobs/."""
    with tempfile.TemporaryDirectory(prefix="mcp-wake-") as folder:
        store = JobStore(folder)
        store.upsert(
            {
                "job_id": JOB_ID,
                "owner_claim": "RIVET",
                "harness": "cursor-slack",
                "objective": "MCP/wake real-job verification; cheap tick only",
                "checkpoint": {"step": 0},
                "next_wake_at": due,
                "deadline": "2026-08-25T18:00:00Z",
                "max_attempts": 2,
                "budget_tokens": 10,
                "completion_predicate": {"type": "status_done"},
                "result_address": "rivet-ship-mcp-wake-20260825-01",
            }
        )
        tick = store.tick(JOB_ID, now=now, worker_id="mcp-wake-probe")
        wrote_repo = os.path.isfile(os.path.join(ROOT, "wake_jobs", JOB_ID + ".json"))
        return {
            "ok": bool(tick.get("ok")),
            "state": str(tick.get("state") or ""),
            "action": str(tick.get("action") or ""),
            "reason": str(tick.get("reason") or ""),
            "invoke_model": bool(tick.get("invoke_model")),
            "job_id": JOB_ID,
            "wrote_wake_jobs": wrote_repo,
            "note": (
                "temp JobStore upsert+tick %s/%s invoke_model=%s. "
                "wake_jobs/ was not written."
            )
            % (
                tick.get("action") or "?",
                tick.get("reason") or tick.get("state") or "?",
                bool(tick.get("invoke_model")),
            ),
        }


def measure_from_rows(facts):
    """Pure census so tests do not need a live Grok or wake_jobs write."""
    facts = facts or {}
    surfaces = list(facts.get("surfaces") or [])
    inventory_surfaces = list(facts.get("inventory_surfaces") or [])
    tests = list(facts.get("tests") or [])
    wake_jobs = list(facts.get("wake_jobs") or [])
    if "wake_job_json" in facts:
        wake_json = int(facts.get("wake_job_json") or 0)
    else:
        wake_json = len(wake_jobs)
    inventory = bool(facts.get("inventory"))
    job_tools = bool(facts.get("job_tools"))
    job = dict(facts.get("job") or {})
    grok = grok_smoke(bool(facts.get("grok_exists")))
    idle = idle_resume_row(facts.get("idle") or {})
    if surfaces and inventory:
        mcp = "INTEGRATED"
    elif surfaces:
        mcp = "FRAGMENTED"
    else:
        mcp = "NOT_LANDED"
    wake = _wake_state(wake_json, wake_jobs)
    return {
        "measured": True,
        "mcp": mcp,
        "surfaces": surfaces,
        "surface_count": len(surfaces),
        "inventory": inventory,
        "inventory_surfaces": inventory_surfaces,
        "job_tools": job_tools,
        "tests": tests,
        "wake": wake,
        "wake_job_json": wake_json,
        "wake_jobs": wake_jobs,
        "job": job,
        "grok": grok,
        "idle": idle,
        "secrets": False,
        "titan": "NOT_WRITTEN",
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
    }


def classify(row):
    """Turn a measured MCP/wake census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "MCP/wake census not read. Absence was not stillness. "
                "A Slack collision hold is not the inventory."
            ),
        }
    if row.get("secrets"):
        return {
            "state": "NOT_LANDED",
            "note": "census tried to record secrets. Drop them. Status only.",
        }
    job = row.get("job") or {}
    idle = row.get("idle") or {}
    if job.get("wrote_wake_jobs"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "probe wrote wake_jobs/{id}.json. Real-job verification "
                "uses a temp store. Do not invent a live wake job."
            ),
        }
    if idle.get("live_resume") or idle.get("invoke_model"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "idle-resume leftover claimed a live different-bc resume "
                "or invoked a model. This harness fail-closes."
            ),
        }
    if (
        int(row.get("surface_count") or 0) >= 4
        and row.get("inventory")
        and row.get("job_tools")
        and job.get("ok")
        and job.get("invoke_model") is False
        and str(idle.get("state") or "") == "UNMEASURED"
    ):
        return {
            "state": "INTEGRATED",
            "note": (
                "canonical MCP inventory is on this tree. Four surfaces "
                "named. Cheap JobStore tick invoke_model=false. Named idle "
                "bc- resume stays UNMEASURED. Grok smoke %s. wake_jobs state "
                "is %s. A Slack collision hold is still not the file."
            )
            % (
                (row.get("grok") or {}).get("state") or "UNMEASURED",
                row.get("wake") or "UNMEASURED",
            ),
        }
    missing = []
    if int(row.get("surface_count") or 0) < 4:
        missing.append("four MCP surfaces")
    if not row.get("inventory"):
        missing.append("ground/MCP_INVENTORY.json")
    if not row.get("job_tools"):
        missing.append("job contract tools")
    if not job.get("ok") or job.get("invoke_model") is not False:
        missing.append("cheap real-job tick")
    if str(idle.get("state") or "") != "UNMEASURED":
        missing.append("honest idle-resume UNMEASURED")
    return {
        "state": "NOT_LANDED",
        "note": (
            "MCP/wake leftover is incomplete. Missing: %s. "
            "Collision-hold / JOJO-visual-CI / holding-implementation talk "
            "is CLAIMED until this leftover ships."
        )
        % (", ".join(missing) if missing else "census"),
    }


def measure_root(root):
    """Read current-main MCP/wake facts. Never write wake_jobs or ~/.grok."""
    inventory_path = os.path.join(os.path.abspath(root), DEFAULT_INVENTORY)
    inventory_text = ""
    if os.path.isfile(inventory_path):
        with open(inventory_path, encoding="utf-8") as handle:
            inventory_text = handle.read()
    inventory = load_inventory(inventory_text) if inventory_text else {"surfaces": []}
    grok_home = os.path.expanduser("~/.grok")
    census = _wake_job_census(root)
    facts = {
        "surfaces": _surfaces_present(root),
        "inventory": bool(inventory_text) and not inventory.get("error"),
        "inventory_surfaces": inventory.get("surfaces") or [],
        "tests": _tests_present(root),
        "job_tools": _has_job_tools(root),
        "wake_job_json": census["wake_job_json"],
        "wake_jobs": census["wake_jobs"],
        "job": verify_job(),
        "grok_exists": os.path.exists(grok_home),
        "idle": probe_idle_resume(OTHER_BC),
        "slack_ts": SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["root"] = os.path.abspath(root)
    row["stranded_ts"] = STRANDED_TS
    return row


def catalog_from_row(row):
    """Status receipt. Names and counts only. No secrets."""
    row = row or {}
    grok = row.get("grok") or {}
    idle = row.get("idle") or {}
    job = row.get("job") or {}
    return {
        "source_id": "rivet-ship-mcp-wake-20260825-01",
        "slack_ts": SLACK_TS,
        "stranded_ts": STRANDED_TS,
        "kind": "MCP_WAKE",
        "subject": "MCP/wake real-job verification — collision hold is not a land",
        "surfaces": list(row.get("surfaces") or []),
        "inventory": bool(row.get("inventory")),
        "job_tools": bool(row.get("job_tools")),
        "wake": row.get("wake"),
        "wake_job_json": int(row.get("wake_job_json") or 0),
        "wake_jobs": list(row.get("wake_jobs") or []),
        "production_canaries": [
            {
                "job_id": str(item.get("job_id") or ""),
                "source_state": str(item.get("status") or ""),
                "result_address": str(item.get("result_address") or ""),
            }
            for item in (row.get("wake_jobs") or [])
            if str(item.get("job_id") or "")
        ],
        "job": {
            "ok": bool(job.get("ok")),
            "state": job.get("state"),
            "action": job.get("action"),
            "reason": job.get("reason"),
            "invoke_model": bool(job.get("invoke_model")),
            "wrote_wake_jobs": bool(job.get("wrote_wake_jobs")),
        },
        "idle": {
            "state": idle.get("state"),
            "live_resume": bool(idle.get("live_resume")),
            "invoke_model": bool(idle.get("invoke_model")),
            "bc_id": idle.get("bc_id"),
        },
        "grok": {
            "state": grok.get("state"),
            "exists": bool(grok.get("exists")),
        },
        "hands_off": [
            "render-check / render-contract leftovers",
            "rivet-ship-mcp-wake-job-20260825-01 / host/mcp_wake_job.py",
            "jojo-visual-ci-20260825-01 remint",
            "named idle bc- resume of a different run",
            "~/.grok mutate/restart",
            "unscoped wake_jobs/{id}.json beyond the named SPECTER canary",
            "titan.gguf write",
            "DIO Android / White Box / Bazaar commercial",
            "DEMON flight recorder",
        ],
        "titan": "NOT_WRITTEN",
        "note": (
            "Do not remint render-check. Do not remint a JOJO taking with "
            "no p/{id}.md. Collision hold is CLAIMED. No secrets."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure canonical MCP inventory + honest wake/job leftover"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["catalog"] = catalog_from_row(row)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    secrets = classify({"measured": True, "secrets": True})
    assert secrets["state"] == "NOT_LANDED"
    wrote = classify(
        {
            "measured": True,
            "surface_count": 4,
            "inventory": True,
            "job_tools": True,
            "job": {"ok": True, "invoke_model": False, "wrote_wake_jobs": True},
            "idle": {"state": "UNMEASURED"},
        }
    )
    assert wrote["state"] == "NOT_LANDED"
    live = classify(
        {
            "measured": True,
            "surface_count": 4,
            "inventory": True,
            "job_tools": True,
            "job": {"ok": True, "invoke_model": False},
            "idle": {"state": "UNMEASURED", "live_resume": True},
        }
    )
    assert live["state"] == "NOT_LANDED"
    fixtures = measure_from_rows(
        {
            "surfaces": list(SURFACES),
            "inventory": True,
            "inventory_surfaces": list(SURFACES),
            "tests": list(TEST_FILES),
            "job_tools": True,
            "wake_job_json": 0,
                "job": {
                    "ok": True,
                    "state": "TICKED",
                    "action": "STOP",
                    "reason": "NOT_DUE",
                    "invoke_model": False,
                    "wrote_wake_jobs": False,
                },
            "grok_exists": False,
            "idle": probe_idle_resume(OTHER_BC),
        }
    )
    assert fixtures["mcp"] == "INTEGRATED"
    assert fixtures["wake"] == "EMPTY"
    assert fixtures["grok"]["state"] == "UNMEASURED"
    assert fixtures["idle"]["state"] == "UNMEASURED"
    assert fixtures["idle"]["live_resume"] is False
    assert classify(fixtures)["state"] == "INTEGRATED"
    fragmented = measure_from_rows(
        {"surfaces": list(SURFACES), "inventory": False, "wake_job_json": 0}
    )
    assert fragmented["mcp"] == "FRAGMENTED"
    assert classify(fragmented)["state"] == "NOT_LANDED"
    job = verify_job()
    assert job["ok"] is True
    assert job["invoke_model"] is False
    assert job["wrote_wake_jobs"] is False
    assert job["action"] == "STOP"
    assert job["reason"] == "NOT_DUE"
    same = idle_resume_row(probe_idle_resume("bc-6778d25b-caae-51cb-a4a6-0254fedcf6cd"))
    assert same["state"] in {"NOT_OTHER_RUN", "UNMEASURED"}
    return True


if __name__ == "__main__":
    sys.exit(main())
