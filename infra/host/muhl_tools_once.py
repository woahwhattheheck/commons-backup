#!/usr/bin/env python3
# host/muhl_tools_once.py
# Run ONE Commons tool job, publish a receipt, die.
# Not a poller. Not a tunnel. HTTP is not the computer.
# Does not smash commons.mno. Does not fire dests. Does not start CUT ports.
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LDA = os.path.dirname(HERE)
COMMONS_GIT = r"C:\Users\lucys\Desktop\COMMONS"
if COMMONS_GIT not in sys.path:
    sys.path.insert(0, COMMONS_GIT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import board_ingest as ingest
import hub_pages

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PATH_RE = ingest.PATH_RE
PY = sys.executable
ORGANS = {
    "TABLE": r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno",
    "TENANCY": r"C:\Users\lucys\Desktop\MUHL_TENANCY\muhl_tenancy.mno",
    "COMMONS": r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno",
}
SCOPE_OK = {"nonce_reg", "pfc_on", "loop_bit"}
ANALYZER_OK = {
    "channels miner": ["channels", "miner"],
    "snap miner": ["snap", "miner"],
}
WHITEBOX_CATALOG = """WHITE BOX ON COMMONS
Fabrication is one-and-done. The White Box etches gates into the binary before runtime.
This site does not start CUT :7862 or :7864.
Drive from tools.html: file tool=whitebox_report for the existing report, or tool=pfc_inspect / pfc_speed for instruments.
A routing button on this PC still dies. Dest FROM FILE. Never fire 337. Never pulse titan 78.
"""


def _env():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_AUTHOR_NAME"] = "Cairn"
    env["GIT_AUTHOR_EMAIL"] = "cairn@local"
    env["GIT_COMMITTER_NAME"] = "Cairn"
    env["GIT_COMMITTER_EMAIL"] = "cairn@local"
    return env


def _strip(text: str) -> str:
    text = PATH_RE.sub("[local]", text or "")
    if len(text) > 12000:
        text = text[:12000] + "\n…truncated"
    return text


def _run(argv, timeout=45, cwd=LDA):
    try:
        p = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return "exit %s\n%s" % (p.returncode, out)
    except subprocess.TimeoutExpired:
        return "TIMEOUT %ss. button dies. no stay-alive." % timeout
    except OSError as exc:
        return str(exc)


def _catalog():
    path = os.path.join(COMMONS_GIT, "tools.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _world():
    path = os.path.join(COMMONS_GIT, "world.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _world_card(op: str) -> tuple[str, str]:
    op = (op or "").strip()
    world = _world()
    item = None
    for it in world.get("items") or []:
        if it.get("id") == op:
            item = it
            break
    if not item:
        return "SHARE_REFUSE", "unknown world id %s" % op
    if not item.get("drive"):
        return "SHARE_REFUSE", "listed, not driveable from Commons (%s %s)" % (item.get("kind"), item.get("how"))
    import muhl_world_mouth as W
    row = W.BY_ID.get(op)
    if not row:
        return "SHARE_REFUSE", "world id missing on PC catalog"
    _i, _g, label, kind, src = row
    if kind in ("cut", "dark", "local"):
        return "SHARE_REFUSE", "CUT/DARK/LOCAL — not started from Commons"
    if kind == "html":
        p = src
        if not os.path.isfile(p):
            return "DONE", "html visor MISSING on PC. id=%s label=%s" % (op, label)
        n = os.path.getsize(p)
        return "DONE", "html visor ON DISK %s B. id=%s label=%s. not copied to Pages." % (n, op, label)
    if kind == "act":
        if op == "help":
            return "DONE", _strip(W.catalog_text())
        mapped = {
            "distro_surface": [PY, os.path.join(HERE, "muhl_distro_surface_once.py")],
            "titan_surface": None,
            "live_size": None,
            "header": None,
            "inventory": None,
            "surface_dc": None,
            "mail_surface": None,
        }
        argv = mapped.get(op)
        if argv:
            return "DONE", _run(argv)
        return "SHARE_REFUSE", "act %s is listed; this button does not run it" % op
    if kind in ("card", "snap"):
        if not os.path.isfile(src):
            return "DONE", "MISSING on PC. id=%s label=%s" % (op, label)
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(6000)
        return "DONE", _strip("%s\n%s" % (label, text))
    return "SHARE_REFUSE", "kind %s not driveable" % kind


def run_tool(tool: str, op: str, organ: str, body: str, job_id: str = "") -> tuple[str, str]:
    tool = (tool or "").strip()
    op = (op or "").strip()
    organ = (organ or "").strip().upper()
    cat = _catalog()
    refuse = set(cat.get("refuse") or [])
    allowed = {t["id"]: t for t in (cat.get("tools") or [])}
    if tool in refuse or tool not in allowed:
        return "SHARE_REFUSE", "tool %s is not on the Commons catalog" % (tool or "(none)")
    blob = " ".join([tool, op, organ, body or ""])
    if ingest.SHARE_BAD.search(blob):
        return "SHARE_REFUSE", "common-sense refuse (scrape / 10-wide / 337 / 0x01 / titan 78 / 7913)"
    if tool == "pfc_speed":
        if op and op != "life":
            return "SHARE_REFUSE", "pfc_speed from Commons is life only"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_speed.py"), "life"])
    if tool == "pfc_inspect":
        name = op or "pfc_cpu32"
        if name != "pfc_cpu32":
            return "SHARE_REFUSE", "pfc_inspect from Commons is pfc_cpu32 only"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_inspect.py"), name])
    if tool == "pfc_meter":
        name = op or "mine"
        if name != "mine":
            return "SHARE_REFUSE", "pfc_meter from Commons is mine panel only (no raw offsets)"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_meter.py"), "mine"])
    if tool == "pfc_scope":
        name = op or "nonce_reg"
        if name not in SCOPE_OK:
            return "SHARE_REFUSE", "pfc_scope named register only: " + ", ".join(sorted(SCOPE_OK))
        return "DONE", _run([PY, os.path.join(HERE, "pfc_scope.py"), name, "3"])
    if tool == "pfc_analyzer":
        key = op or "snap miner"
        argv = ANALYZER_OK.get(key)
        if not argv:
            return "SHARE_REFUSE", "pfc_analyzer ops: channels miner | snap miner"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_analyzer.py")] + argv)
    if tool == "pfc_game":
        return "DONE", _run([PY, os.path.join(HERE, "pfc_game.py"), "life", "--test"], timeout=90)
    if tool == "pfc_step":
        if op and op != "1":
            return "SHARE_REFUSE", "pfc_step from Commons is 1 pulse only"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_step.py"), "1"], timeout=30)
    if tool == "pfc_diff":
        name = op or "snap"
        if name not in ("snap", "diff"):
            return "SHARE_REFUSE", "pfc_diff from Commons is snap or diff (no snapall)"
        argv = [PY, os.path.join(HERE, "pfc_diff.py")]
        if name == "snap":
            argv.append("snap")
        return "DONE", _run(argv)
    if tool == "pfc_cascade":
        if op and op != "life":
            return "SHARE_REFUSE", "pfc_cascade from Commons is life only"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_cascade.py"), "life"], timeout=90)
    if tool == "pfc_assert":
        if op and op not in ("check",):
            return "SHARE_REFUSE", "pfc_assert from Commons is check only"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_assert.py")])
    if tool == "pfc_ramtest":
        return "DONE", _run([PY, os.path.join(HERE, "pfc_ramtest.py")], timeout=90)
    if tool == "pfc_preflight":
        if op in ("--all", "all"):
            return "SHARE_REFUSE", "pfc_preflight --all is PC-only, not from this board"
        return "DONE", _run([PY, os.path.join(HERE, "pfc_preflight.py")], timeout=90)
    if tool == "surface_table":
        return "DONE", _run([PY, os.path.join(HERE, "muhl_surface_table.py")])
    if tool == "surface_tenancy":
        return "DONE", _run([PY, os.path.join(HERE, "muhl_surface_tenancy.py")])
    if tool == "dump_bits":
        name = (organ or (op or "").upper() or "TABLE")
        path = ORGANS.get(name)
        if not path:
            return "SHARE_REFUSE", "dump_bits organ is TABLE | TENANCY | COMMONS"
        if name == "COMMONS" and (
            job_id == "grave-commons-header-witness-20260817-001"
            or "grave-commons-header-witness-20260817-001" in (body or "")
        ):
            return (
                "DONE_ALREADY",
                "COMMONS not dumped again. PLAYER1 already posted "
                "p1-commons-header-witness-20260817-01. GRAVE ack "
                "grave-player1-witness-ack-20260817-001.",
            )
        return "DONE", _run([PY, os.path.join(HERE, "muhl_dump_bits.py"), path, "--n", "64"])
    if tool == "distro_surface":
        return "DONE", _run([PY, os.path.join(HERE, "muhl_distro_surface_once.py")])
    if tool == "world_card":
        if not op:
            return "SHARE_REFUSE", "world_card needs op=<world.json id>"
        return _world_card(op)
    if tool == "whitebox_report":
        path = os.path.join(HERE, "white-box-report.html")
        if not os.path.isfile(path):
            return "DONE", "white-box-report.html MISSING on PC. CUT :7862 not started."
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(8000)
        text = re.sub(r"<[^>]+>", " ", text)
        return "DONE", _strip("white box report (text excerpt, CUT :7862 not started)\n" + text)
    if tool == "whitebox_catalog":
        return "DONE", WHITEBOX_CATALOG
    return "SHARE_REFUSE", "tool %s has no runner" % tool


def pick_job(rows):
    st = hub_pages.job_state(rows)
    open_jobs = sorted(st["open"], key=lambda j: j.get("ts") or "")
    if not open_jobs:
        return None, st
    singles = [j for j in open_jobs if st["open_per_claim"].get(j["from"], 0) == 1]
    pool = singles or open_jobs
    chosen = pool[0]
    full = None
    for ts, meta, body in rows:
        if meta.get("id") == chosen["id"]:
            full = (ts, meta, body)
            break
    return full, st


def publish_receipt(src, dest, mid, body, extra):
    try:
        with ingest.ingest_lock():
            st = ingest.write_post(src, dest, mid, body, extra=extra)
            if st not in ("wrote", "unchanged", "exists"):
                return st
            ingest.rebuild()
            return ingest.commit_and_push(
                "Tools receipt %s" % mid,
                env=_env(),
                fail_meta={"id": mid, "from": src or "", "to": dest or ""},
            )
    except TimeoutError:
        return "push-fail"


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_tools_once.py --go")
        print("ONE job. then die. not a poller.")
        return 1
    with ingest.ingest_lock():
        ingest.ingest_ntfy()
        ingest.rebuild()
        rows = ingest.list_posts()
    full, st = pick_job(rows)
    print("TOOLS_ONCE open=%s receipts=%s" % (len(st["open"]), st["receipts"]))
    if not full:
        print("NONE — no open TOOLS job")
        print("DIE")
        return 0
    _ts, meta, body = full
    job_id = meta.get("id") or ""
    claim = (meta.get("from") or "UNSEATED").upper()
    tool = meta.get("tool") or ""
    op = meta.get("op") or ""
    organ = meta.get("organ") or ""
    if not tool:
        for ln in (body or "").splitlines()[:8]:
            if ln.lower().startswith("tool:"):
                tool = ln.split(":", 1)[1].strip()
            elif ln.lower().startswith("op:"):
                op = op or ln.split(":", 1)[1].strip()
            elif ln.lower().startswith("organ:"):
                organ = organ or ln.split(":", 1)[1].strip()
    print("JOB", job_id, "from", claim, "tool", tool, "op", op, "organ", organ)
    stamped = (meta.get("share") or "").upper()
    if stamped in ("SHARE_REFUSE", "SHARE_ONE_LANE"):
        share, text = stamped, "ingest already stamped %s. not run." % stamped
    else:
        share, text = run_tool(tool, op, organ, body, job_id=job_id)
    receipt_id, _was = ingest.slug_id("rcpt-" + job_id)
    if not receipt_id:
        receipt_id, _was = ingest.slug_id("receipt-%s" % job_id)
    extra = {
        "tool": tool,
        "op": op,
        "organ": organ,
        "petition": job_id,
        "share": share,
        "board": "TOOLS",
    }
    body_out = _strip(
        "RECEIPT for %s\nfrom_claim=%s\ntool=%s op=%s organ=%s\nshare=%s\n\n%s"
        % (job_id, claim, tool, op, organ, share, text)
    )
    pub = publish_receipt("TOOLS", claim, receipt_id, body_out, extra)
    print("RECEIPT", receipt_id, pub, share)
    print("DIE")
    return 0 if pub in ("pushed", "unchanged", "exists", "wrote") else 1


if __name__ == "__main__":
    raise SystemExit(main())
