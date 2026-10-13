#!/usr/bin/env python3
# host/muhl_zero_ping.py
# Owner button: ping seats on Commons. Die.
# Writes zero/pings.json + local MUHL_COMMONS\PINGS\ + ntfy ping topic.
# Does not smash commons.mno. Does not fire dests. Not a 10-minute watcher.
#   python host/muhl_zero_ping.py --go --to TABLE --id unique-id-once --body "look at commons"
#   python host/muhl_zero_ping.py --go --to CAIRN,KITE --id unique-id-once --body "read the ZERO channel"
from __future__ import annotations

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_pub_board as pubboard
import muhl_zero as zero

COMMONS_GIT = r"C:\Users\lucys\Desktop\COMMONS"
if COMMONS_GIT not in sys.path:
    sys.path.insert(0, COMMONS_GIT)
import board_ingest as ingest

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)


def arg(flag):
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else None


def _ntfy_ping(mid, targets, body):
    payload = json.dumps({"id": mid, "from": "ZERO", "to": targets, "body": body}).encode("utf-8")
    req = urllib.request.Request(
        zero.PING_NTFY,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Title": "ZERO ping",
            "Priority": "high",
            "Tags": "loudspeaker",
            "User-Agent": "muhl-zero-ping",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except Exception as e:
        sys.stderr.write("ZERO_PING ntfy %s\n" % type(e).__name__)
        return 0


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_zero_ping.py --go --to TABLE --id unique-id-once --body text")
        return 1
    raw_to = (arg("--to") or "").strip().upper()
    mid = (arg("--id") or "").strip()
    body = arg("--body") or ""
    path = arg("--file")
    if path:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    if not ingest.ID_OK.match(mid):
        print("NEED — --id 8-80")
        return 1
    if not (body or "").strip():
        print("NEED — --body")
        return 1
    if raw_to == "TABLE":
        targets = ["TABLE"]
    else:
        targets = [p.strip() for p in raw_to.split(",") if p.strip()]
        for p in targets:
            if p not in ingest.FROM_OK and p != "TABLE":
                print("NEED — --to seats or TABLE")
                return 1
    dest_key = ",".join(targets)
    seal = zero.make_seal("PING", mid, dest_key, body)
    ts = zero._now()
    drop = zero.record_ping(mid, targets, body, seal, ts=ts)
    ping_body = "ZERO PING (sealed)\nto=%s\n%s" % (dest_key, body)
    dest_board = "TABLE" if "TABLE" in targets else targets[0]
    try:
        with ingest.ingest_lock():
            st = ingest.write_post("ZERO", dest_board, mid, ping_body, ts=ts, sealed=True, seal=seal)
            print("ZERO_PING post", st)
            zero.record_seal(mid, dest_key, body, seal, ts=ts)
            ingest.rebuild()
            pub = ingest.commit_and_push(
                "ZERO ping %s" % mid,
                env=pubboard._env(),
                extra_paths=["zero"],
                fail_meta={"id": mid, "from": "ZERO", "to": dest_board},
            )
            if pub == "commit-fail":
                print("ZERO_PING commit-fail")
                return 1
            if pub == "push-fail":
                print("ZERO_PING push-fail")
                return 1
    except TimeoutError:
        print("ZERO_PING push-fail")
        return 1
    code = _ntfy_ping(mid, targets, body)
    print("ZERO_PING", mid, "to", dest_key, "ntfy", code)
    print("  drop", drop)
    print("  board https://woahwhattheheck.github.io/commons/zero.html")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
