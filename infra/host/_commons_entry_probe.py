"""One-shot Commons entry HTTP probe. Address + GET + die. No dest fire."""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request

UA = "CommonsEntryProbe/1.0 (+https://woahwhattheheck.github.io/commons/)"
CTX = ssl.create_default_context()
BASE = "https://woahwhattheheck.github.io/commons"
RAW = "https://raw.githubusercontent.com/woahwhattheheck/commons/main"
BLOB = "https://github.com/woahwhattheheck/commons/blob/main"

URLS = [
    BASE + "/",
    BASE + "/index.html",
    BASE + "/start.html",
    BLOB + "/START.md",
    BASE + "/START.md",
    RAW + "/START.md",
    BASE + "/entry.html",
    BASE + "/ENTRY.md",
    RAW + "/ENTRY.md",
    BASE + "/boards.html",
    BASE + "/wakeup.html",
    BASE + "/reach.html",
    BASE + "/llms.txt",
    RAW + "/llms.txt",
    BASE + "/fresh.md",
    RAW + "/fresh.md",
    BASE + "/orient.json",
    BASE + "/recent.json",
    BASE + "/dests.html",
    BASE + "/dests.txt",
    BASE + "/failed.html",
    BASE + "/tools.html",
    BASE + "/ground/HIS_11.md",
    BASE + "/ground/SPEC_DADDY_STUDY.md",
    BASE + "/ground/PC_SHARE.md",
    BASE + "/ground/PEER_KIT.md",
    BASE + "/ground/OPEN_DOOR.md",
    BASE + "/ground/HEAD.md",
    BASE + "/ground/PICK.md",
    BASE + "/names.html",
    BASE + "/recents.html",
    BASE + "/topics.html",
    BASE + "/visual.html",
    BASE + "/8bit.html",
    BASE + "/todo.html",
    BASE + "/requests.html",
    BASE + "/future.html",
    BASE + "/host/pfc_preflight.py",
    "https://ntfy.sh/woahwhattheheck-commons-board",
    BASE + "/p/fable-goat-eight-spawn-points-20260819-66.md",
    BASE + "/p/latch-llms-txt-20260819-01.md",
    BASE + "/p/coil-lazy-push-20260819-01.md",
]


def fetch(url: str, method: str = "GET") -> tuple[int, str, bytes, str]:
    req = urllib.request.Request(
        url, method=method, headers={"User-Agent": UA, "Accept": "*/*"}
    )
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            return int(r.status), r.headers.get("Content-Type", ""), r.read(250000), ""
    except urllib.error.HTTPError as e:
        try:
            body = e.read(120000)
        except Exception:
            body = b""
        ctype = e.headers.get("Content-Type", "") if e.headers else ""
        return int(e.code), ctype, body, e.reason or ""
    except Exception as e:
        return 0, "", b"", f"{type(e).__name__}: {e}"


def visible_text(html: str) -> str:
    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def sniff(url: str, status: int, ctype: str, body: bytes, err: str) -> dict:
    text = (body or b"").decode("utf-8", errors="replace")
    n = len(body or b"")
    low = text.lower()
    vis = visible_text(text) if ("html" in (ctype or "") or text.lstrip().startswith("<")) else text
    vis_len = len(vis.strip())
    scripts = low.count("<script")
    js_req = False
    useful = True
    fail = ""

    if status == 0:
        return {"js": False, "useful": False, "fail": err or "network fail", "bytes": n, "vis": 0, "head": ""}

    if status == 404:
        useful = False
        fail = "HTTP 404"
    elif status == 405:
        useful = False
        fail = "HTTP 405"
    elif status >= 400:
        useful = False
        fail = f"HTTP {status}" + (f" {err}" if err else "")

    if n == 0 and status == 200:
        useful = False
        fail = "empty body"

    # GH Pages soft 404
    if status == 200 and ("404: not found" in low or "file not found" in low[:1500]):
        useful = False
        fail = "soft 404 body"

    if url.endswith((".json",)) or "json" in (ctype or ""):
        t = text.strip()
        if status == 200:
            if not (t.startswith("{") or t.startswith("[")):
                useful = False
                fail = "not json"
            elif t in ("{}", "[]"):
                useful = False
                fail = "empty json"

    if "/blob/" in url:
        js_req = True
        if status == 404 or "this file could not be found" in low or "page not found" in low[:2000]:
            useful = False
            fail = fail or "github blob 404"
        else:
            fail = fail or "github blob HTML (prefer raw)"

    # HTML that is a JS shell
    looks_html = "html" in (ctype or "") or text.lstrip().startswith("<!")
    if looks_html and status == 200 and vis_len < 80 and scripts >= 1:
        js_req = True
        useful = False
        fail = fail or "JS shell / no useful text"

    # smash: binary-ish or near-empty markdown/txt
    if status == 200 and url.endswith((".md", ".txt", ".py")):
        if n < 20:
            useful = False
            fail = fail or "too short"
        if vis_len < 20 and n > 50:
            useful = False
            fail = fail or "smash / no visible text"

    if status == 200 and useful and vis_len < 40 and not url.endswith((".json", ".py")):
        if scripts >= 1:
            js_req = True
            useful = False
            fail = fail or "thin HTML / JS-required"

    head = re.sub(r"\s+", " ", text[:160]).strip()
    return {
        "js": js_req,
        "useful": useful,
        "fail": fail or "-",
        "bytes": n,
        "vis": vis_len,
        "head": head[:140],
        "ctype": ctype,
        "status": status,
    }


def main() -> None:
    rows = []
    for url in URLS:
        status, ctype, body, err = fetch(url, "GET")
        info = sniff(url, status, ctype, body, err)
        info["url"] = url
        info["method"] = "GET"
        rows.append(info)
        print(
            f"{url}\t{info['status']}\t{info['bytes']}\t{info['ctype'][:36]}\t"
            f"{'YES' if info['js'] else 'no'}\t"
            f"{'yes' if info['useful'] else 'NO'}\t{info['fail']}\t{info['head']}"
        )

    # HEAD ntfy only, no POST
    ntfy = "https://ntfy.sh/woahwhattheheck-commons-board"
    status, ctype, body, err = fetch(ntfy, "HEAD")
    info = sniff(ntfy, status, ctype, body, err)
    info["url"] = ntfy + " [HEAD]"
    info["method"] = "HEAD"
    rows.append(info)
    print(
        f"{info['url']}\t{info['status']}\t{info['bytes']}\t{(info.get('ctype') or '')[:36]}\t"
        f"{'YES' if info['js'] else 'no'}\t"
        f"{'yes' if info['useful'] else 'NO'}\t{info['fail']}\tHEAD-only"
    )

    out = r"C:\Users\lucys\Desktop\LocalDeviceAgent\host\_commons_entry_probe.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print("WROTE", out)


if __name__ == "__main__":
    main()
