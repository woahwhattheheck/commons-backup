#!/usr/bin/env python3
# host/muhl_session_once.py
# Open or close court session on Commons. Address + write + rebuild + die.
# Pages from=BRYCE is a claim. This laptop path is the control path.
# Does not smash commons.mno. Does not fire dests. Does not forge.
from __future__ import annotations

import os
import sys

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
            kind = (extra.get("act") or "SESSION").upper()
            return ingest.commit_and_push(
                "Court session %s %s" % (kind, mid),
                env=_env(),
                fail_meta={"id": mid, "from": src or "", "to": dest or ""},
            )
    except TimeoutError:
        return "push-fail"


if __name__ == "__main__":
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_session_once.py --go --open|--close --from BRYCE")
        print("Pages from=BRYCE is a claim. This laptop path is the control path. Do not forge.")
        raise SystemExit(1)
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is WIPE")
        raise SystemExit(2)
    opening = "--open" in sys.argv
    closing = "--close" in sys.argv
    if opening == closing:
        print("NEED — exactly one of --open or --close")
        raise SystemExit(1)
    src = (arg("--from") or "").strip().upper()
    if src not in ("BRYCE", "ZERO"):
        print("NEED — --from BRYCE or ZERO")
        raise SystemExit(1)
    dest = "COURT"
    if opening:
        act = "SESSION_OPEN"
        body = "COURT IS NOW IN SESSION"
    else:
        act = "SESSION_CLOSE"
        body = "COURT SESSION ENDED"
    mid = arg("--id") or ("%s-%s" % (src, ingest.now_ts().replace(":", "").replace("-", "")))
    extra = {"act": act, "court": "order"}
    print(publish(src, dest, mid, body, extra))
    print("DIE")
