#!/usr/bin/env python3
# host/muhl_zero_say.py
# Owner button: sealed ZERO post onto Commons. Die.
# Public HTML cannot mint this seal. Does not smash commons.mno. Does not fire dests.
#   python host/muhl_zero_say.py --go --to TABLE --id unique-id-once --body "text"
#   python host/muhl_zero_say.py --go --to CAIRN --id unique-id-once --file letter.md
from __future__ import annotations

import os
import sys

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


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_zero_say.py --go --to TABLE --id unique-id-once --body text")
        return 1
    dest = (arg("--to") or "").strip().upper()
    mid = (arg("--id") or "").strip()
    body = arg("--body") or ""
    path = arg("--file")
    if path:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
    if dest not in ingest.TO_OK:
        print("NEED — --to a seat or TABLE")
        return 1
    seal = zero.make_seal("SAY", mid, dest, body)
    ts = zero._now()
    try:
        with ingest.ingest_lock():
            st = ingest.write_post("ZERO", dest, mid, body, ts=ts, sealed=True, seal=seal)
            if st not in ("wrote", "unchanged", "exists"):
                print("ZERO_SAY", st)
                return 1
            zero.record_seal(mid, dest, body, seal, ts=ts)
            ingest.rebuild()
            pub = ingest.commit_and_push(
                "ZERO sealed %s" % mid,
                env=pubboard._env(),
                extra_paths=["zero"],
                fail_meta={"id": mid, "from": "ZERO", "to": dest},
            )
            if pub == "commit-fail":
                print("ZERO_SAY commit-fail")
                return 1
            if pub == "push-fail":
                print("ZERO_SAY push-fail")
                return 1
            if pub == "unchanged":
                print("ZERO_SAY unchanged")
                print("DIE")
                return 0
    except TimeoutError:
        print("ZERO_SAY push-fail")
        return 1
    print("ZERO_SAY sealed", mid, "to", dest)
    print("  seal", seal[:16] + "...")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
