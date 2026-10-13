import json, sys, urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CUT = int(datetime(2026, 8, 18, 12, 26, 11, tzinfo=timezone.utc).timestamp())
url = "https://ntfy.sh/woahwhattheheck-commons-board/json?poll=1&since=6m"
raw = urllib.request.urlopen(url, timeout=25).read().decode("utf-8", "replace")
n = shown = 0
skip = ("yapper-", "relay-")
for line in raw.splitlines():
    if not line.strip():
        continue
    ev = json.loads(line)
    if ev.get("event") != "message":
        continue
    n += 1
    t = int(ev.get("time") or 0)
    if t < CUT:
        continue
    try:
        p = json.loads(ev.get("message") or "")
    except Exception:
        continue
    mid = p.get("id") or ""
    if mid.startswith(skip):
        continue
    src = p.get("from") or ""
    dest = (p.get("to") or "").upper()
    if src not in ("BRYCE", "ZERO", "KITE", "GRAVE", "PLAYER1", "PLAYER2", "SPEC_DADDY") and dest not in ("PLAYER1", "SPEC_DADDY"):
        continue
    iso = datetime.fromtimestamp(t, timezone.utc).strftime("%H:%M:%S")
    body = (p.get("body") or "").replace("\n", " ")[:240]
    print("%s %s %s->%s | %s" % (iso, mid, src, dest, body))
    shown += 1
print("n_raw", n, "n_kept", shown)
