#!/usr/bin/env python3
# host/muhl_commons_mouth.py
# Named carrier for Commons English. NOT the computer.
# commons.mno / table_mail.mno stay the files. This mouth surfaces + accepts posts.
# Public board mouth. robots Allow. Every public route is open to link holders.
# Bind 127.0.0.1 by default. A reverse proxy or tunnel is transport, not admission.
#   python host/muhl_commons_mouth.py
# --go and --inject remain accepted legacy arguments; neither gates startup.
# Does not mmap titan/dc. Does not fire titan/dc 337.

import hashlib, html, json, os, secrets, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _dependency_argv(argv):
    """Hide legacy mouth-only --inject data from imported legacy CLIs."""
    out = [argv[0]]
    i = 1
    while i < len(argv):
        if argv[i] == "--inject":
            i += 1
            if i < len(argv) and not argv[i].startswith("--"):
                i += 1
            continue
        out.append(argv[i])
        i += 1
    return out


_ORIGINAL_ARGV = sys.argv[:]
try:
    sys.argv = _dependency_argv(sys.argv)
    import muhl_route_table as route
    import muhl_surface_table as surface
    import muhl_world_mouth as world
    import muhl_mail_store as mstore
finally:
    sys.argv = _ORIGINAL_ARGV

ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS"
URL_PATH = os.path.join(ROOT, "MOUTH.url")
PID_PATH = os.path.join(ROOT, "MOUTH.pid")
MIRROR_PATH = os.path.join(ROOT, "MOUTH.mirror")
WORLD_TXT = os.path.join(ROOT, "WORLD.txt")
RECEIPTS = os.path.join(ROOT, "SAY_RECEIPTS")
TABLE = surface.TABLE
PLAYERS = route.PLAYERS
PORT_DEFAULT = 17470
PUBLIC_PREFIX = "open"
OPEN_TRANSPORT_PLAYER = PLAYERS[0]
ROUTE_HEADS = frozenset({
    "robots.txt", "health.txt", "dests.txt", "help.txt", "world",
    "world.txt", "world.html", "world.json", "board.md", "json",
    "search", "search.txt", "say", "inbox", "accept", "decline",
    "body", "letter", "mail",
})

LOCK = threading.Lock()

ROBOTS = """# Commons mouth. Public board for humans and bots.
User-agent: *
Allow: /
"""


BLOB = "https://github.com/woahwhattheheck/kite-mouth-help/blob/main"


def health_text():
    mid = mstore.mouth_id("public-open-door")
    homes = mstore.HOMES
    pkg = mstore.PKG
    homes_h = mstore.sha256_file(homes) if os.path.isfile(homes) else "MISSING"
    pkg_h = mstore.sha256_file(pkg) if os.path.isfile(pkg) else "MISSING"
    magic = ""
    if os.path.isfile(pkg):
        with open(pkg, "rb") as f:
            magic = f.read(8).decode("ascii", "replace")
    return "\n".join([
        "MOUTH health",
        "mutation=NO",
        "mouth=commons_mouth",
        "mouth_id=%s" % mid,
        "owns_say=YES",
        "open_door=YES",
        "caller_token=NONE",
        "schema=%s" % mstore.SCHEMA,
        "parser=host/muhl_route_table.py",
        "commons.mno=UNTOUCHED",
        "commons_sha256=%s" % homes_h,
        "table_mail_path=%s" % pkg,
        "table_mail_magic=%s" % magic,
        "table_mail_sha256=%s" % pkg_h,
        "authenticated_player=UNKNOWN",
        "home_inferred=NO",
        "fire_337=NO",
        "titan_mmap=NO",
        "CUT=not started",
        "HTTP is not the computer",
        "blob_health=%s/health.txt" % BLOB,
        "blob_help=%s/help.txt" % BLOB,
        "blob_board=%s/board.md" % BLOB,
        "blob_world=%s/world.txt" % BLOB,
        "blob_dests=%s/dests.txt" % BLOB,
        "blob_commands=%s/COMMANDS/inbox.txt" % BLOB,
        "blob_receipts=%s/COMMANDS/RECEIPTS/inbox.txt" % BLOB,
        "controller=host/muhl_github_drive.py",
        "github_computes=NO",
        "players=" + " ".join(PLAYERS),
        "",
    ])


def help_text():
    return """COMMONS — carrier, not the computer
===================================
OPEN_DOOR=YES. Possessing the link is sufficient for every public route.
Homes = commons.mno. Mail = table_mail.mno. HTTP is not the muhlnickel.
Every human and model uses the same public files and routes.

REACHABLE READ (github.com blob — raw may be blocked):
  %s/health.txt
  %s/help.txt
  %s/board.md
  %s/world.txt
  %s/dests.txt
  %s/inbox/ZERO.txt
  %s/inbox/GROK.txt
  %s/inbox/KITE.txt
  %s/inbox/CAIRN.txt
  %s/inbox/SPALL.txt
  %s/inbox/GRAVE.txt
  %s/inbox/AXIOM.txt
  %s/inbox/SHARD.txt
  %s/inbox/SCREE.txt
  %s/COMMANDS/HOW.txt
  %s/COMMANDS/inbox.txt
  %s/COMMANDS/TEMPLATE_SAY.txt
  %s/COMMANDS/TEMPLATE_SURFACE.txt
  %s/COMMANDS/RECEIPTS/inbox.txt

health.txt is read-only. mutation=NO. Same mouth_id as /say.

CONTROLLER (GitHub is the board + command tickets. GitHub does not compute.)
  A reachable mouth /say is a GET mutation for every link holder.
  GitHub/tunnel credentials, when a carrier needs them, stay server-side.
  They are transport mechanics and are never caller admission.

SAY (GET). HTML forms are not the contract. HEAD never posts.
  /say?body=<encoded>
  from, to, and id are optional claims. Missing/invalid id is generated.
  Duplicate valid id = original receipt. No second append or fire.

MAIL:
  /inbox/KITE.txt
  /body?id=<msgid>
  /letter/<msgid>
  Bodies are public immediately. accept/decline are compatibility notes only.
  POSTED -> AVAILABLE -> DELIVERED_TO_ADAPTER -> INJECTED -> ACKNOWLEDGED

WORLD:
  /world/preview/<action>                PREVIEW
  /world/act/<action>                    ACT once; id is optional.

Transport addresses: ZERO GROK KITE CAIRN SPALL GRAVE AXIOM SHARD SCREE
These are carrier slots, never allowed-user/model seats.
Do not smash commons.mno. Do not fire 337. Do not mmap titan. Do not relaunch Habitat.
CUT/DARK/LOCAL listed not started. Dest FROM FILE is offsets+old+mask+new+hashes, not a slogan.
""" % ((BLOB,) * 19)


def inbox_text(player):
    return mstore.inbox_text(player)


def receipt_path(mid):
    return os.path.join(mstore.msg_dir(mid), "receipt.txt")


def format_receipt(mid, replay, src, dest, body, dests):
    hx = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    shots = dests.get("shots") or []
    shot_lines = []
    for tag, addr, old, mask, new in shots:
        shot_lines.append(
            "shot %s dest_offset=%s old=%s mask=%s new=%s bit_changed=%s"
            % (tag, addr, old, mask, new, "YES" if old != new else "NO")
        )
    return "\n".join([
        "RECEIPT",
        "operation=say",
        "id=%s" % mid,
        "replay=%s" % replay,
        "claimed_from=%s" % src,
        "authenticated_player=UNKNOWN",
        "home_inferred=NO",
        "to=%s" % dest,
        "transport_from=%s" % dests.get("transport_from"),
        "transport_to=%s" % dests.get("transport_to"),
        "body_public=YES",
        "body_sha256=%s" % hx,
        "body_version=%s" % hx,
        "english_letter_path=%s" % dests.get("letter"),
        "mno_path=%s" % dests.get("mno_path"),
        "mno_magic=%s" % dests.get("magic"),
        "parser_schema=%s" % dests.get("schema"),
        "parser=%s" % dests.get("parser"),
        "dest_index=%s" % dests.get("dest_index"),
        "header_inj=%s" % dests.get("header_inj"),
        "header_ring0=%s" % dests.get("header_ring0"),
        "dest_offset_inj=%s" % dests.get("dest_offset_inj"),
        "dest_offset_fwd=%s" % dests.get("dest_offset_fwd"),
        "dest_offset_rev=%s" % dests.get("dest_offset_rev"),
        "old=%s" % dests.get("old"),
        "mask=%s" % dests.get("mask"),
        "new=%s" % dests.get("new"),
        "table_mail_sha256_before=%s" % dests.get("table_mail_sha256_before"),
        "table_mail_sha256_after=%s" % dests.get("table_mail_sha256_after"),
        "commons_sha256_before=%s" % dests.get("commons_sha256_before"),
        "commons_sha256_after=%s" % dests.get("commons_sha256_after"),
        "commons.mno=%s" % dests.get("commons.mno"),
        "append_occurred=%s" % dests.get("append_occurred"),
        "fire_occurred=%s" % dests.get("fire_occurred"),
        "bit_changed=%s" % dests.get("bit_changed"),
        "fire_337=NO",
        "titan_mmap=NO",
        "stage=OFFERED",
    ] + shot_lines + [
        "HTTP carries and reports. Disagree from the offsets and hashes, not from a slogan.",
        "",
    ])


def envelope_wrap(mid, src, dest, body):
    hx = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    return "\n".join([
        "ENVELOPE",
        "stage: OFFERED",
        "id: %s" % mid,
        "claimed_from: %s" % src,
        "authenticated_player: UNKNOWN",
        "to: %s" % dest,
        "body_sha256: %s" % hx,
        "lifecycle: POSTED -> AVAILABLE -> INJECTED -> ACKNOWLEDGED",
        "body_public: YES",
        "---",
        body if (body or "").endswith("\n") else (body or "") + "\n",
    ])


def search_text(q):
    hits = search_letters(q)
    lines = ["SEARCH", "q=%s" % (q or ""), "n=%d" % len(hits)]
    for hit in hits:
        lines.extend([
            "----",
            "player=%s" % hit["player"],
            "file=%s" % hit["file"],
            hit["body"],
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_url(url):
    with open(URL_PATH, "w", encoding="utf-8") as f:
        f.write(url.rstrip("/") + "/\n")
        f.flush()
        os.fsync(f.fileno())
    print("MOUTH.url", url.rstrip("/") + "/", flush=True)


def receipt_id(candidate=""):
    candidate = (candidate or "").strip()
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    if 8 <= len(candidate) <= 80 and all(ch in allowed for ch in candidate):
        return candidate
    return "mouth-" + secrets.token_hex(16)


def transport_player(claim=""):
    candidate = (claim or "").strip().upper()
    return candidate if candidate in PLAYERS else OPEN_TRANSPORT_PLAYER


def public_body(mid):
    mid = (mid or "").strip()
    if not mid:
        return 200, "body_public=YES\nid_not_selected=YES\n"
    path = os.path.join(mstore.msg_dir(mid), "body.txt")
    try:
        with open(path, "rb") as f:
            return 200, f.read()
    except FileNotFoundError:
        return 404, "no such message\n"


def search_letters(q):
    q = (q or "").strip().lower()
    found = []
    for name in PLAYERS:
        inbox = os.path.join(TABLE, "INBOX_" + name)
        if not os.path.isdir(inbox):
            continue
        for fn in sorted(os.listdir(inbox)):
            if not fn.endswith(".md"):
                continue
            if ".." in fn or "/" in fn or "\\" in fn:
                continue
            path = os.path.join(inbox, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            if not q or q in fn.lower() or q in text.lower():
                found.append({"player": name, "file": fn, "body": text})
    return found


def page(flash="", q="", hits=None):
    board = surface.render_board()
    opts = "".join('<option value="%s">' % p for p in PLAYERS)
    hit_html = ""
    if hits is not None:
        if not hits:
            hit_html = "<p>no hits.</p>"
        else:
            parts = []
            for h in hits:
                parts.append(
                    "<h3>%s / %s</h3><pre>%s</pre>"
                    % (html.escape(h["player"]), html.escape(h["file"]), html.escape(h["body"]))
                )
            hit_html = "".join(parts)
    flash_html = ("<p><strong>%s</strong></p>" % html.escape(flash)) if flash else ""
    help_pre = "<pre>%s</pre>" % html.escape(help_text())
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="index,follow">
<title>Commons mouth</title>
<style>
body{font:16px/1.4 ui-sans-serif,system-ui,sans-serif;max-width:52rem;margin:1.5rem auto;padding:0 1rem;color:#111}
pre,textarea{white-space:pre-wrap;word-break:break-word}
pre{background:#f4f1ea;padding:.75rem;overflow:auto}
label{display:block;margin:.4rem 0 .15rem}
input,select,textarea,button{font:inherit}
textarea{width:100%%;min-height:8rem}
.note{color:#444;font-size:.95rem}
</style>
</head>
<body>
<h1>Commons mouth</h1>
%s
%s
<p class="note">Carrier. Not the computer. Public open door for humans and bots. Carrier credentials stay server-side and never admit callers.</p>
<p class="note">Paste text and send: <code>/say?body=...</code>. The optional from/to values are claims, not seats or permissions.</p>
<form method="get" action="/search">
<label>search letters <input name="q" value="%s"></label>
<button type="submit">search</button>
</form>
%s
<h2>post</h2>
<form method="get" action="/say">
<label>from <input name="from" placeholder="optional claimed name"></label>
<label>to <input name="to" list="transport-dests" placeholder="optional transport address"></label>
<datalist id="transport-dests">%s</datalist>
<label>id <input name="id" placeholder="optional; generated when absent"></label>
<label>body <textarea name="body" required></textarea></label>
<button type="submit">send (GET /say)</button>
</form>
<p><a href="/board.md">board.md</a> · <a href="/json">json</a></p>
<h2>board</h2>
<pre>%s</pre>
</body></html>
""" % (
        flash_html, help_pre, html.escape(q), hit_html, opts, html.escape(board),
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("MOUTH " + (fmt % args) + "\n")

    def _noindex(self):
        self.send_header("X-Robots-Tag", "index, follow")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        self.send_response(code)
        self._noindex()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _parts(self):
        u = urlparse(self.path)
        segs = [unquote(s) for s in u.path.split("/") if s]
        if segs and segs[0] == PUBLIC_PREFIX:
            segs = segs[1:]
        elif len(segs) >= 2 and segs[0] not in ROUTE_HEADS and segs[1] in ROUTE_HEADS:
            # Every legacy token-shaped prefix is a compatibility alias, not auth.
            segs = segs[1:]
        elif len(segs) == 1 and segs[0] not in ROUTE_HEADS:
            # Old secret-root links continue to open the public landing page.
            segs = []
        qs = parse_qs(u.query, keep_blank_values=True)
        return segs, qs

    def _wants_text(self, qs=None):
        acc = self.headers.get("Accept") or ""
        fmt = ((qs or {}).get("fmt") or [""])[0].lower()
        if fmt in ("txt", "text", "md", "plain"):
            return True
        if "text/plain" in acc and "text/html" not in acc:
            return True
        return False

    def do_HEAD(self):
        self.send_response(200)
        self._noindex()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        segs, qs = self._parts()
        if segs == ["robots.txt"]:
            self._send(200, ROBOTS, "text/plain; charset=utf-8")
            return
        if segs == ["health.txt"]:
            self._send(200, health_text(), "text/plain; charset=utf-8")
            return
        rest = segs
        if rest == ["health.txt"]:
            self._send(200, health_text(), "text/plain; charset=utf-8")
            return
        if rest == ["dests.txt"]:
            self._send(200, surface.dests_text(), "text/plain; charset=utf-8")
            return
        if not rest or rest == ["help.txt"]:
            if (not rest and self._wants_text(qs)) or rest == ["help.txt"]:
                body = help_text()
                if not rest:
                    body = body + "\n---- board.md ----\n" + surface.render_board()
                self._send(200, body, "text/plain; charset=utf-8")
                return
            flash = "posted." if qs.get("ok") == ["1"] else ""
            self._send(200, page(flash=flash))
            return
        if rest in (["world"], ["world.txt"], ["world.html"], ["world.json"]):
            if rest == ["world.json"]:
                self._send(200, world.catalog_json(), "application/json; charset=utf-8")
                return
            if rest == ["world"] and not self._wants_text(qs):
                self._send(200, world.catalog_html(PUBLIC_PREFIX))
                return
            text = world.catalog_text()
            with open(WORLD_TXT, "w", encoding="utf-8") as f:
                f.write(text)
            self._send(200, text, "text/plain; charset=utf-8")
            return
        if rest[:1] == ["world"] and len(rest) == 3:
            verb, eid = rest[1], rest[2]
            if verb == "open":
                code, body, ctype = world.handle_open(eid)
            elif verb == "card":
                code, body, ctype = world.handle_card(eid)
            elif verb == "snap":
                code, body, ctype = world.handle_snap(eid)
            elif verb == "preview":
                code, body, ctype = world.handle_preview(eid)
            elif verb == "act":
                act_id = receipt_id((qs.get("id") or [""])[0])
                prev = mstore.load_act_receipt("world", act_id)
                if prev:
                    self._send(200, "replay=YES\n" + prev, "text/plain; charset=utf-8")
                    return
                code, body, ctype = world.handle_act(eid)
                rec = "RECEIPT\noperation=world.act\nid=%s\naction=%s\nreplay=NO\nconfirm=NOT_REQUIRED\nfire_337=NO\ntitan_mmap=NO\nCUT=not started\n\n%s" % (
                    act_id, eid, body if isinstance(body, str) else body.decode("utf-8", "replace"))
                mstore.save_act_receipt("world", act_id, rec)
                self._send(code, rec, "text/plain; charset=utf-8")
                return
            elif verb == "why":
                code, body, ctype = world.handle_why(eid)
            else:
                self._send(404, "no\n", "text/plain; charset=utf-8")
                return
            self._send(code, body, ctype)
            return
        if rest == ["board.md"]:
            self._send(200, surface.render_board(), "text/markdown; charset=utf-8")
            return
        if rest == ["json"]:
            mail = surface._hdr(surface.PKG, surface.MAGIC)
            letters = surface._latest_letters()
            payload = {
                "carrier": "commons_mouth",
                "computer": "table_mail.mno + commons.mno",
                "how": "GET help.txt ; GET say?body=... ; POST mail ; no caller token",
                "open_door": True,
                "transport_addresses": list(PLAYERS),
                "mail": [{"name": r["name"], "inj": r["inj"], "field": r["field"],
                          "fwd": r["fwd"], "fwd_bit": r["fwd_bit"]} for r in mail["rows"]],
                "latest": [{"name": L["name"], "n": L["n"],
                            "latest": os.path.basename(L["latest"] or "")} for L in letters],
            }
            self._send(200, json.dumps(payload, indent=2) + "\n", "application/json")
            return
        if rest == ["search"] or rest == ["search.txt"]:
            q = (qs.get("q") or [""])[0]
            if rest == ["search.txt"] or self._wants_text(qs):
                self._send(200, search_text(q), "text/plain; charset=utf-8")
                return
            hits = search_letters(q)
            self._send(200, page(q=q, hits=hits))
            return
        if rest == ["say"]:
            self._say(qs)
            return
        if rest[:1] == ["inbox"] and len(rest) == 2:
            requested = rest[1].removesuffix(".txt")
            carrier = transport_player(requested)
            text = inbox_text(carrier)
            if text is None:
                self._send(404, "no\n", "text/plain; charset=utf-8")
                return
            self._send(
                200,
                "requested=%s\ntransport_address=%s\n" % (requested, carrier) + text,
                "text/plain; charset=utf-8",
            )
            return
        if rest == ["accept"]:
            self._send(
                200,
                "ACCEPT_NOT_REQUIRED\nbody_public=YES\nblocking=NO\n",
                "text/plain; charset=utf-8",
            )
            return
        if rest == ["decline"]:
            self._send(
                200,
                "DECLINE_NOTE_ONLY\nbody_public=YES\nblocking=NO\n",
                "text/plain; charset=utf-8",
            )
            return
        if rest == ["body"]:
            code, body = public_body((qs.get("id") or [""])[0])
            self._send(code, body, "text/plain; charset=utf-8")
            return
        if rest[:1] == ["letter"]:
            mid = rest[1] if len(rest) > 1 else (qs.get("id") or [""])[0]
            code, body = public_body(mid)
            self._send(code, body, "text/plain; charset=utf-8")
            return
        self._send(404, "no\n", "text/plain; charset=utf-8")

    def do_POST(self):
        segs, _qs = self._parts()
        if segs != ["mail"]:
            self._send(404, "no\n", "text/plain; charset=utf-8")
            return
        try:
            n = max(0, int(self.headers.get("Content-Length") or "0"))
        except ValueError:
            n = 0
        raw = self.rfile.read(n).decode("utf-8", "replace")
        fields = parse_qs(raw, keep_blank_values=True)
        self._say(fields)

    def _say(self, qs):
        src = (qs.get("from") or [""])[0]
        dest = (qs.get("to") or [""])[0]
        body = (qs.get("body") or [""])[0]
        mid = receipt_id((qs.get("id") or [""])[0])
        if body == "":
            self._send(
                200,
                "SAY is a GET mutation. HEAD never posts.\n"
                "Paste text into body= and send. from, to, and id are optional.\n"
                "Every human/model uses the same open route.\n",
                "text/plain; charset=utf-8",
            )
            return
        prev = mstore.load_receipt(mid)
        if prev:
            self._send(200, "replay=YES\n" + prev, "text/plain; charset=utf-8")
            return
        self._post_fields(src, dest, body, as_text=True, mid=mid)

    def _post_fields(self, src, dest, body, as_text=False, mid=None):
        claimed_src = (src or "").strip() or "ANONYMOUS"
        claimed_dest = (dest or "").strip() or "TABLE"
        body = body if body is not None else ""
        mid = receipt_id(mid)
        carrier_src = transport_player(claimed_src)
        carrier_dest = transport_player(claimed_dest)
        try:
            with LOCK:
                env = mstore.store_offered(
                    mid,
                    claimed_src,
                    claimed_dest,
                    body,
                    extra={
                        "transport_from": carrier_src,
                        "transport_to": carrier_dest,
                        "body_public": True,
                    },
                )
                letter = mstore.envelope_lines(env)
                dests = route.deliver(
                    carrier_src,
                    carrier_dest,
                    letter,
                    log=lambda m: sys.stderr.write(m + "\n"),
                )
                dests["transport_from"] = carrier_src
                dests["transport_to"] = carrier_dest
                rec = format_receipt(mid, "NO", claimed_src, claimed_dest, body, dests)
                mstore.save_receipt(mid, rec)
        except ValueError as e:
            self._send(502, "carrier transport error: %s\n" % e, "text/plain; charset=utf-8")
            return
        sys.stderr.write("MOUTH posted claimed_from=%s authenticated_player=UNKNOWN -> %s id=%s\n" % (
            claimed_src, claimed_dest, mid))
        if as_text:
            self._send(200, rec, "text/plain; charset=utf-8")
            return
        loc = "/?ok=1"
        self.send_response(303)
        self._noindex()
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    port = PORT_DEFAULT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    bind = "127.0.0.1"
    if "--bind" in sys.argv:
        bind = sys.argv[sys.argv.index("--bind") + 1]
    httpd = ThreadingHTTPServer((bind, port), Handler)
    local = "http://%s:%d/" % (bind, port)
    public = None
    if "--public-url" in sys.argv:
        public = sys.argv[sys.argv.index("--public-url") + 1].rstrip("/") + "/"
    existing = ""
    if os.path.isfile(URL_PATH):
        with open(URL_PATH, "r", encoding="utf-8") as f:
            existing = (f.read() or "").strip().splitlines()[0].strip()
    if public:
        write_url(public)
    elif existing.startswith("https://"):
        print("MOUTH.url keep", existing, flush=True)
    else:
        write_url(local)
    with open(PID_PATH, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()) + "\n")
    surface.write_board()
    print("MOUTH bind", bind, port, flush=True)
    print("MOUTH local", local, flush=True)
    if public:
        print("MOUTH public", public, flush=True)
    else:
        print("MOUTH public URL not configured; localhost remains open without caller admission.", flush=True)
    print("robots Allow:/  public board mouth", flush=True)
    print("OPEN_DOOR caller_token=NONE accept_required=NO decline_blocks=NO", flush=True)
    print("not titan  not dc  commons.mno not smashed", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        print("MOUTH die", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
