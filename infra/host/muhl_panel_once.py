#!/usr/bin/env python3
# host/muhl_panel_once.py
# Run ONE Commons PANEL ticket, write COMMANDS/RECEIPTS/<id>.txt on this
# git tree, die. Not a poller. Not a whole-board rebuild.
# Git copies of .mno do not run. Live computers stay on the hard drive.
# kind=surface|dump|analyzer. purpose=USE|BUILD. VERIFY/PROOF refused.
#   python host/muhl_panel_once.py --go
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(os.path.dirname(HERE)) == "infra":
    COMMONS_GIT = os.path.abspath(os.path.join(HERE, "..", ".."))
else:
    COMMONS_GIT = os.path.abspath(os.path.join(HERE, ".."))
if COMMONS_GIT not in sys.path:
    sys.path.insert(0, COMMONS_GIT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import panel as panel_mod
import muhl_github_drive as drive

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_panel_once.py --go")
        print("ONE ticket. then die. not a poller. not a bake.")
        return 1
    jobs = panel_mod.open_tickets(COMMONS_GIT)
    print("PANEL_ONCE open=%s" % len(jobs))
    if not jobs:
        print("NONE — no open COMMANDS ticket")
        print("DIE")
        return 0
    cmd = jobs[0]
    mid = cmd.get("id") or ""
    kind = (cmd.get("kind") or "surface").strip().lower()
    purpose = (cmd.get("purpose") or "USE").strip().upper()
    organ = (cmd.get("organ") or "").strip().upper()
    print("JOB", mid, "kind", kind, "purpose", purpose, "organ", organ)
    extra = {
        "kind": kind,
        "purpose": purpose,
        "organ": organ,
        "approved": cmd.get("approved") or "YES",
        "path": cmd.get("path") or "",
    }
    reason = panel_mod.refuse_reason(extra, cmd.get("body") or "", "PANEL")
    if reason:
        rec = panel_mod.receipt_refuse_text(mid, reason)
        panel_mod._write(
            os.path.join(COMMONS_GIT, "COMMANDS", "RECEIPTS", mid + ".txt"), rec
        )
        print("REFUSE", mid)
        print("DIE")
        return 0
    if kind == "surface":
        status, rec = drive.act_surface(mid, cmd)
    elif kind == "dump":
        status, rec = drive.act_dump(mid, cmd)
    elif kind == "analyzer":
        status, rec = drive.act_analyzer(mid, cmd)
    else:
        rec = panel_mod.receipt_refuse_text(mid, "NEED kind=surface|dump|analyzer")
        status = "refuse"
    dest = os.path.join(COMMONS_GIT, "COMMANDS", "RECEIPTS", mid + ".txt")
    panel_mod._write(dest, rec)
    print("RECEIPT", dest, status)
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
