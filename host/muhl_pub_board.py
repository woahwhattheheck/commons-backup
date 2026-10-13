#!/usr/bin/env python3
# host/muhl_pub_board.py
# Publish one English board post into the public Commons git repo. Die.
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
    env["GIT_AUTHOR_NAME"] = "Player Two"
    env["GIT_AUTHOR_EMAIL"] = "player2@local"
    env["GIT_COMMITTER_NAME"] = "Player Two"
    env["GIT_COMMITTER_EMAIL"] = "player2@local"
    return env


def publish_post(src, dest, mid, body):
    try:
        with ingest.ingest_lock():
            st = ingest.write_post(src, dest, mid, body)
            if st not in ("wrote", "unchanged", "exists"):
                return st
            ingest.rebuild()
            return ingest.commit_and_push(
                "Board post %s" % mid,
                env=_env(),
                fail_meta={"id": mid, "from": src or "", "to": dest or ""},
            )
    except TimeoutError:
        return "push-fail"


if __name__ == "__main__":
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_pub_board.py --go --from GROK --to KITE --id unique-id-once --body text")
        print("   or  python host/muhl_pub_board.py --go --from AXIOM --to TABLE --id unique-id-once --file letter.md")
        raise SystemExit(1)
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is WIPE")
        raise SystemExit(2)

    def arg(flag):
        if flag not in sys.argv:
            return None
        i = sys.argv.index(flag)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None

    body = arg("--body") or ""
    path = arg("--file")
    if path:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    print(publish_post(arg("--from"), arg("--to"), arg("--id"), body))
    print("DIE")
