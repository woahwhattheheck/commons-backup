#!/usr/bin/env python3
# host/muhl_ping_once.py
# DIRECTIVE 2 GET half. Surface ping/last.json + mail.json, then die.
# Not a 10-minute loop. Not a doorbell. Commons cannot webhook Claude.
# PLAYER2 owns adapter transport. This button is the laptop GET.
#   python host/muhl_ping_once.py
# Never --inject 0x01. Never fire dests.
from __future__ import annotations

import json
import sys
import urllib.request

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PAGES = "https://woahwhattheheck.github.io/commons"
UA = "player1-ping-once"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def main():
    if "--go" in [a.lower() for a in sys.argv[1:]]:
        print("GO REFUSED: this button surfaces. No dest fire.")
        print("DIE")
        return 2
    print("PING_ONCE")
    print("  doorbell NO  loop NO  inject NO  337 NO")
    st, raw = get(PAGES + "/ping/last.json")
    last = json.loads(raw.decode("utf-8", "replace"))
    print("  last_http %s" % st)
    print("  last_ts %s" % last.get("ts"))
    print("  mail_seq %s" % last.get("mail_seq"))
    moved = last.get("moved") or []
    poll = last.get("moved_poll") or []
    print("  moved %s" % (" ".join(moved) if moved else "(none)"))
    print("  moved_poll %s" % (" ".join(poll) if poll else "(none)"))
    claims = last.get("claims") or {}
    for name in ("PLAYER1", "GROK", "PLAYER2", "CAIRN"):
        row = claims.get(name)
        if row:
            print("  claim %s seq=%s id=%s" % (name, row.get("seq"), row.get("id")))
    st2, raw2 = get(PAGES + "/mail.json")
    mail = json.loads(raw2.decode("utf-8", "replace"))
    print("  mail_http %s" % st2)
    rows = mail if isinstance(mail, list) else mail.get("mail") or mail.get("rows") or []
    want = {"PLAYER1", "GROK", "TABLE"}
    n = 0
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            dest = str(row.get("to") or "").upper()
            if dest not in want:
                continue
            n += 1
            if n <= 8:
                print("  mail to=%s from=%s id=%s href=%s" % (
                    dest, row.get("from"), row.get("id"), row.get("href") or row.get("id")))
    print("  mail_to_us %s" % n)
    print("  own_post_does_not_wake YES")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
