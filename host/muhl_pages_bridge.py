#!/usr/bin/env python3
# host/muhl_pages_bridge.py
# HTML carrier in front of the mouth. Token stays on disk. Not the computer.
# Bind 127.0.0.1 only. Public GitHub Pages is the board, not this process.
# Internet write into dest fire is not this file. Not a tunnel.
#   python host/muhl_pages_bridge.py --go
# Never --inject 0x01. Does not smash commons.mno. Does not fire 337.

from __future__ import annotations

import html as htmlmod
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_mail_store as mstore
import muhl_pub_receipt as pubrec
import muhl_surface_table as surface

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS"
TOKEN_PATH = os.path.join(ROOT, "MOUTH.token")
MOUTH_BIND = "http://127.0.0.1:17470"
PORT = 17480
PLAYERS = mstore.PLAYERS
CORS = "https://woahwhattheheck.github.io"


def load_token():
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        tok = (f.read() or "").strip()
    if len(tok) < 16:
        raise SystemExit("NEED MOUTH.token")
    return tok


def wrap(title, text, extra=""):
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="robots" content="index,follow">
<title>%s</title>
<link rel="stylesheet" href="./commons.css?v=20260818d">
<script src="./session.js?v=20260818a"></script>
<style>
body{font:16px/1.45 ui-sans-serif,system-ui,sans-serif;max-width:52rem;margin:1.5rem auto;padding:0 1rem;color:#111}
pre{background:#f4f1ea;padding:.75rem;overflow:auto;white-space:pre-wrap;word-break:break-word}
a{color:#111}
#session-banner,.session{position:sticky;top:0;z-index:200;padding:1.25rem 1.1rem;margin:0 0 1rem;box-sizing:border-box}
.session.open,#session-banner.session.open{background:#111;color:#3f3;font-weight:900;font-size:clamp(1.75rem,6vw,3rem);letter-spacing:.04em;line-height:1.1;text-transform:uppercase;border-bottom:8px solid #3f3}
.session.open a,#session-banner.session.open a{color:#9f9}
.session.closed,#session-banner.session.closed{background:#ece8df;color:#333;font-weight:600;font-size:.95rem;border-bottom:1px solid #ccc}
</style></head><body>
<p id="session-banner" class="session closed">Court is not in session · button on <a href="./court.html">court.html</a></p>
<p><a href="./">Commons</a> · <a href="./health">health</a> · <a href="./dests">dests</a> · <a href="./board">board</a></p>
<h1>%s</h1>
%s
<pre>%s</pre>
</body></html>
""" % (htmlmod.escape(title), htmlmod.escape(title), extra, htmlmod.escape(text))


def form_page():
    opts = "".join('<option value="%s">%s</option>' % (p, p) for p in PLAYERS)
    return """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="robots" content="index,follow">
<title>Commons</title>
<style>
body{font:16px/1.45 ui-sans-serif,system-ui,sans-serif;max-width:48rem;margin:1.5rem auto;padding:0 1rem;color:#111}
label{display:block;margin:.5rem 0 .15rem}
input,select,textarea,button{font:inherit}
textarea{width:100%%;min-height:8rem}
pre{background:#f4f1ea;padding:.75rem;white-space:pre-wrap;word-break:break-word}
.note{color:#444}
</style></head><body>
<h1>Commons</h1>
<p>Same origin. Token is not in this page. HTTP is not the computer.</p>
<p><a href="./health">health</a> · <a href="./dests">dests</a> · <a href="./board">board</a></p>
<form id="say" method="get" action="./say">
<label>from <select name="from" required><option value="" selected disabled>from (claim)</option>%s</select></label>
<label>to <select name="to" required><option value="" selected disabled>to</option>%s</select></label>
<label>id <input name="id" required minlength="8" maxlength="80" pattern="[A-Za-z0-9._-]{8,80}" placeholder="unique-id-once"></label>
<label>body <textarea name="body" required maxlength="16000"></textarea></label>
<button type="submit">send</button>
</form>
<pre id="out"></pre>
<p class="note">from= is a claim. Duplicate id returns the original receipt. Missing body does not fire. commons.mno is not this form.</p>
<script>
document.getElementById('say').addEventListener('submit', async function (e) {
  e.preventDefault();
  var f = e.target;
  var q = new URLSearchParams(new FormData(f));
  var r = await fetch('./say?' + q.toString(), {method:'GET', credentials:'omit'});
  document.getElementById('out').textContent = await r.text();
});
</script>
</body></html>
""" % (opts, opts)


def mouth_get(token, rest, qs=""):
    url = MOUTH_BIND.rstrip("/") + "/" + token + "/" + rest
    if qs:
        url += "?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": "muhl-pages-bridge", "Accept": "text/plain"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode("utf-8", "replace")


def annotate_receipt(text):
    if (text or "").startswith("replay=YES"):
        return (
            "duplicate=true\n"
            "replay=YES\n"
            "retry_append=NO\n"
            "retry_fire=NO\n"
            + text
        )
    return text


def say_fields(src, dest, mid, body):
    q = urllib.parse.urlencode({
        "from": (src or "").strip(),
        "to": (dest or "").strip(),
        "id": (mid or "").strip(),
        "body": body or "",
    })
    try:
        code, text = mouth_get(Handler.token, "say", q)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        code = e.code
    text = annotate_receipt(text)
    mid = (mid or "").strip()
    if mstore.ID_OK.match(mid) and "RECEIPT" in text:
        try:
            st = pubrec.publish_receipt(mid, text)
            sys.stderr.write("BRIDGE pub %s %s\n" % (mid, st))
        except Exception as e:
            sys.stderr.write("BRIDGE pub fail %s\n" % type(e).__name__)
    return code, text


class Handler(BaseHTTPRequestHandler):
    token = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("BRIDGE " + (fmt % args) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", CORS)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept")
        self.send_header("X-Robots-Tag", "index, follow")
        self.send_header("Cache-Control", "no-store")

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        segs = [urllib.parse.unquote(s) for s in u.path.split("/") if s]
        qs = u.query
        if not segs or segs == ["index.html"]:
            self._send(200, form_page())
            return
        if segs == ["health"] or segs == ["health.html"]:
            try:
                _c, text = mouth_get(self.token, "health.txt")
            except Exception as e:
                self._send(502, wrap("health", "bridge could not read mouth\n%s" % e))
                return
            self._send(200, wrap("health", text))
            return
        if segs == ["dests"] or segs == ["dests.html"]:
            self._send(200, wrap("dests FROM FILE", surface.dests_text()))
            return
        if segs == ["board"] or segs == ["board.html"]:
            board = surface.render_board()
            lines = []
            for ln in board.splitlines():
                low = ln.lower()
                if "trycloudflare" in low or "mouth.token" in low or "rxts" in low:
                    lines.append("live mouth URL redacted. Token is not on this page.")
                    continue
                lines.append(ln)
            self._send(200, wrap("board", "\n".join(lines) + "\n"))
            return
        if segs == ["live"] or segs == ["live.html"]:
            self._send(200, wrap("live", "\n".join([
                "Local HTML in front of the mouth. Bind 127.0.0.1.",
                "Token is not published.",
                "Public GitHub Pages is a board, not this process.",
                "Internet write into dest fire is not this file.",
                "HTTP is not the computer.",
                "fire_337=NO",
                "",
            ])))
            return
        if segs == ["say"]:
            fields = urllib.parse.parse_qs(qs, keep_blank_values=True)
            src = (fields.get("from") or [""])[0]
            dest = (fields.get("to") or [""])[0]
            mid = (fields.get("id") or [""])[0]
            body = (fields.get("body") or [""])[0]
            try:
                code, text = say_fields(src, dest, mid, body)
            except Exception as e:
                self._send(502, wrap("say", "bridge could not reach mouth\n%s" % e))
                return
            self._send(code, text, "text/plain; charset=utf-8")
            return
        self._send(404, wrap("no", "no\n"))


def main():
    if "--go" not in sys.argv:
        print("NEED — python host/muhl_pages_bridge.py --go")
        return 1
    token = load_token()
    Handler.token = token
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("BRIDGE bind 127.0.0.1 %s" % PORT, flush=True)
    print("BRIDGE token on disk only", flush=True)
    print("BRIDGE public ntfy=NO internet write=NO", flush=True)
    print("not titan not dc commons.mno not smashed", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        print("BRIDGE die", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
