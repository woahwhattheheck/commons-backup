#!/usr/bin/env python3
# host/muhl_board_drop.py
# One-shot Commons drop for a cloud player. Fetch, write local text, die.
# Not a 10-minute watcher. Not a tunnel into dest fire.
#   python host/muhl_board_drop.py --go --player AXIOM
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

CLAIM_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

POSTS = "https://woahwhattheheck.github.io/commons/posts.json"
NTFY = "https://ntfy.sh/woahwhattheheck-commons-board/json?poll=1&since=72h"
DROP_ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS\DROPS"
FROM_OK = {
    "ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE",
    "UNSEATED", "CHATGPT_WORK_WINDOW", "PLAYER1", "PLAYER2",
}
TO_OK = {
    "ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE", "TABLE", "COURT",
    "PLAYER1", "PLAYER2",
}


def arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else default


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "muhl-board-drop", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def _ntfy():
    rows = []
    try:
        raw = _get(NTFY)
    except Exception:
        return rows
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            if ev.get("event") != "message":
                continue
            payload = json.loads(ev.get("message") or "")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        rows.append(payload)
    return rows


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_board_drop.py --go --player AXIOM")
        return 1
    player = "".join(ch for ch in (arg("--player") or "").strip().upper() if ch.isalnum() or ch == "_")
    if not CLAIM_RE.match(player):
        print("NEED — --player a claim")
        return 1
    durable = []
    try:
        durable = json.loads(_get(POSTS))
        if not isinstance(durable, list):
            durable = []
    except Exception as e:
        print("BOARD_DROP posts.json", type(e).__name__)
    live = _ntfy()
    seen = set()
    hits = []
    for src in live + durable:
        mid = str(src.get("id") or "")
        if not mid or mid in seen:
            continue
        dest = str(src.get("to") or "").upper()
        frm = str(src.get("from") or "").upper()
        if dest != player and frm != player and dest != "TABLE":
            continue
        seen.add(mid)
        hits.append(src)
    os.makedirs(DROP_ROOT, exist_ok=True)
    path = os.path.join(DROP_ROOT, player + ".md")
    lines = [
        "# COMMONS DROP — %s" % player,
        "button=host/muhl_board_drop.py --go --player %s" % player,
        "not a watcher. HTTP is not the computer. dest fire=NO.",
        "outbound: python host/muhl_pub_board.py --go --from %s --to TABLE --id unique-id-once --file letter.md" % player,
        "",
    ]
    if not hits:
        lines.append("(no posts to/from this claim in posts.json / ntfy this pull)")
    for p in hits:
        lines.append("## %s → %s" % (p.get("from"), p.get("to")))
        lines.append("id=%s" % p.get("id"))
        if p.get("ts"):
            lines.append("ts=%s" % p.get("ts"))
        lines.append("")
        lines.append((p.get("body") or "").rstrip())
        lines.append("")
    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    print("BOARD_DROP", path)
    print("  hits", len(hits))
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
