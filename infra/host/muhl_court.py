#!/usr/bin/env python3
# host/muhl_court.py
# File one court petition or ZERO order into the public Commons git repo. Die.
# Does not smash commons.mno. Does not fire dests. Does not write a disk map.
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMMONS_GIT = r"C:\Users\lucys\Desktop\COMMONS"
if COMMONS_GIT not in sys.path:
    sys.path.insert(0, COMMONS_GIT)
import board_ingest as ingest


def _env():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_AUTHOR_NAME"] = "Cairn"
    env["GIT_AUTHOR_EMAIL"] = "cairn@local"
    env["GIT_COMMITTER_NAME"] = "Cairn"
    env["GIT_COMMITTER_EMAIL"] = "cairn@local"
    return env


def arg(flag):
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else None


def publish(src, dest, mid, body, extra):
    try:
        with ingest.ingest_lock():
            st = ingest.write_post(src, dest, mid, body, extra=extra)
            if st not in ("wrote", "unchanged", "exists"):
                return st
            ingest.rebuild()
            return ingest.commit_and_push(
                "Court %s" % mid,
                env=_env(),
                fail_meta={"id": mid, "from": src or "", "to": dest or ""},
            )
    except TimeoutError:
        return "push-fail"


if __name__ == "__main__":
    if "--go" not in sys.argv:
        print("NEED — petition: python host/muhl_court.py --go --from CAIRN --ask SUGGEST --id unique-id-once --body text")
        print("     — order:    python host/muhl_court.py --go --from ZERO --act ASSIGN_ROLE --to GRAVE --role Gravekeeper --id unique-id-once --body text")
        print("     — resource: python host/muhl_court.py --go --from ZERO --act ASSIGN_RESOURCE --to AXIOM --resource muhl_tenancy.mno --id unique-id-once --body text")
        raise SystemExit(1)
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is WIPE")
        raise SystemExit(2)

    src = (arg("--from") or "").strip().upper()
    dest = (arg("--to") or "").strip().upper()
    mid = arg("--id")
    body = arg("--body") or ""
    path = arg("--file")
    if path:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    extra = {}
    for k in ("court", "act", "ask", "role", "resource", "petition", "supersedes", "target", "reason"):
        v = arg("--" + k)
        if v:
            extra[k] = v
    if extra.get("act"):
        extra["act"] = extra["act"].strip().upper()
        extra["court"] = "order"
        src = src or "ZERO"
        if extra["act"] in ("HIDE", "RESTORE"):
            dest = dest or "MOD"
        else:
            dest = dest or "COURT"
    elif extra.get("ask") or dest == "COURT":
        extra["court"] = extra.get("court") or "petition"
        dest = dest or "COURT"
    print(publish(src, dest, mid, body, extra))
    print("DIE")
