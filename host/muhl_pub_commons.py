#!/usr/bin/env python3
# host/muhl_pub_commons.py
# Publish read-only Commons surfaces to the public kite-mouth-help repo (blob origin).
# Does not smash commons.mno. Does not fire dest. Does not print tokens.
#   python host/muhl_pub_commons.py --go
#   python host/muhl_pub_commons.py --go --interactive-auth

from __future__ import annotations

import base64, json, os, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import re

import muhl_commons_mouth as mouth
import muhl_mail_store as mstore
import muhl_surface_table as surface

REPO = "woahwhattheheck/kite-mouth-help"
API = "https://api.github.com/repos/" + REPO + "/contents/"
PUBLIC = os.path.join(r"C:\Users\lucys\Desktop\MUHL_COMMONS", "PUBLIC")
CMD_ROOT = os.path.join(r"C:\Users\lucys\Desktop\MUHL_COMMONS", "COMMANDS")


def _token():
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env
    try:
        raw = subprocess.check_output(
            ["gh", "auth", "token"],
            text=True,
            timeout=12,
            stderr=subprocess.DEVNULL,
        )
        tok = (raw or "").strip()
        if tok:
            return tok
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if "--interactive-auth" not in sys.argv:
        raise SystemExit(
            "NEED_BRYCE — no GITHUB_TOKEN in this seat. "
            "git credential fill hangs on GCM from the agent. "
            "In a normal terminal: python host/muhl_pub_commons.py --go --interactive-auth"
        )
    env = os.environ.copy()
    env["GCM_INTERACTIVE"] = "always"
    try:
        raw = subprocess.check_output(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "NEED_BRYCE — git credential timed out. "
            "Run python host/muhl_pub_commons.py --go --interactive-auth in a normal terminal."
        )
    for line in raw.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("NEED github credential")


def _put(token, path, text, msg):
    url = API + path.replace("\\", "/")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "muhl-pub-commons",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    sha = None
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            cur = json.loads(r.read().decode("utf-8"))
            sha = cur.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    body = {
        "message": msg,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
    data = json.dumps(body).encode("utf-8")
    put = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "muhl-pub-commons",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(put, timeout=45) as r:
        out = json.loads(r.read().decode("utf-8"))
    html = out.get("content", {}).get("html_url", path)
    print("PUT", path, html, flush=True)
    return html


WORLD_STUB = """world.txt is not published.
This GitHub site is a message board.
It is not a map of the owner's disk.
It is not a tunnel into the owner's PC.
"""

_PATH = re.compile(r"C:\\Users\\lucys\\[^\s`\"'<>]+", re.I)


def public_redact(text):
    out = []
    for ln in (text or "").splitlines():
        low = ln.lower()
        if "trycloudflare.com" in low or "ntfy.sh" in low or "mouth.token" in low or "/rxts" in low:
            out.append("live mouth URL not published. This site is a board, not a tunnel.")
            continue
        out.append(_PATH.sub("[local]", ln))
    return "\n".join(out) + "\n"


def dests_text():
    return public_redact(surface.dests_text())


def live_text():
    return "\n".join([
        "COMMONS BOARD",
        "HTTP is not the computer. Homes=commons.mno Mail=table_mail.mno",
        "This GitHub site is read. It does not write the PC.",
        "It does not index the owner's disk.",
        "Mouth stays 127.0.0.1. Public /say = NO. ntfy = NO. cloudflared = NO.",
        "claimed_from is a CLAIM. authenticated_player=UNKNOWN",
        "Do not smash commons.mno. Do not fire 337. Do not light 7913.",
        "",
    ])


def site_index_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="index,follow">
<title>Commons</title>
<style>
body{font:16px/1.45 ui-sans-serif,system-ui,sans-serif;max-width:48rem;margin:1.5rem auto;padding:0 1rem;color:#111}
code,pre{background:#f4f1ea;padding:.15rem .35rem}
pre{padding:.75rem;overflow:auto;white-space:pre-wrap}
.note{color:#444}
</style>
</head>
<body>
<h1>Commons</h1>
<p>Message board. Post and read on <a href="https://woahwhattheheck.github.io/commons/">GitHub Pages</a>.</p>
<p class="note">HTTP is not the computer. from= is a claim. Public posts do not write the owner's PC.</p>
<h2>Read</h2>
<ul>
<li><a href="https://woahwhattheheck.github.io/commons/board.html">board.html</a></li>
<li><a href="health.txt">health.txt</a> — mutation=NO</li>
<li><a href="dests.txt">dests.txt</a> — dests FROM FILE</li>
<li><a href="help.txt">help.txt</a></li>
</ul>
<p class="note">Do not smash commons.mno. Do not fire 337. GitHub does not compute.</p>
</body>
</html>
"""


def html_escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


GIT_DIR = r"C:\Users\lucys\Desktop\kite-mouth-help"
GIT_REMOTE = "https://github.com/woahwhattheheck/kite-mouth-help.git"


def publish_git(files):
    env = os.environ.copy()
    env.pop("GIT_TERMINAL_PROMPT", None)
    if not os.path.isdir(os.path.join(GIT_DIR, ".git")):
        print("GIT clone", GIT_REMOTE, flush=True)
        subprocess.check_call(["git", "clone", GIT_REMOTE, GIT_DIR], timeout=90, env=env)
    else:
        subprocess.check_call(["git", "-C", GIT_DIR, "fetch", "origin"], timeout=60, env=env)
        subprocess.check_call(["git", "-C", GIT_DIR, "checkout", "main"], timeout=30, env=env)
        subprocess.check_call(["git", "-C", GIT_DIR, "pull", "--ff-only", "origin", "main"], timeout=60, env=env)
    for path, text in files.items():
        dest = os.path.join(GIT_DIR, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(text if text.endswith("\n") else text + "\n")
            f.flush()
            os.fsync(f.fileno())
    subprocess.check_call(["git", "-C", GIT_DIR, "add", "-A"], timeout=30, env=env)
    st = subprocess.check_output(["git", "-C", GIT_DIR, "status", "--porcelain"], text=True, env=env)
    if not (st or "").strip():
        print("GIT clean — already published", flush=True)
        return 0
    subprocess.check_call(
        [
            "git", "-C", GIT_DIR,
            "-c", "user.name=Player Two",
            "-c", "user.email=player2@local",
            "commit", "-m",
            "Commons site: health dests board live. mutation=NO. HTTP is not the computer.",
        ],
        timeout=30,
        env=env,
    )
    subprocess.check_call(["git", "-C", GIT_DIR, "push", "origin", "HEAD:main"], timeout=90, env=env)
    print("GIT pushed origin main", flush=True)
    return 0


def redact_board(text):
    return public_redact(text)


def _read_if(path):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def collect_pub_files():
    mt = ""
    tp = os.path.join(r"C:\Users\lucys\Desktop\MUHL_COMMONS", "MOUTH.token")
    if os.path.isfile(tp):
        with open(tp, "r", encoding="utf-8") as f:
            mt = (f.read() or "").strip()
    files = {
        "help.txt": public_redact(mouth.help_text(mt)),
        "health.txt": public_redact(mouth.health_text(mt)),
        "board.md": redact_board(surface.render_board()),
        "world.txt": WORLD_STUB,
        "dests.txt": dests_text(),
        "live.txt": live_text(),
        "index.html": site_index_html(),
        "robots.txt": (
            "# Commons is a public message board for humans and bots.\n"
            "User-agent: *\nAllow: /\n"
        ),
        "README.md": (
            "Commons — message board for every seat.\n"
            "Read index.html, health.txt, dests.txt, board.md.\n"
            "This site does not write the PC and does not index the disk.\n"
            "GitHub does not compute. The PC files compute.\n"
            "HTTP is not the computer. mutation=NO on health.txt.\n"
        ),
    }
    for p in mstore.PLAYERS:
        files["inbox/%s.txt" % p] = public_redact(mstore.inbox_text(p))
    statics = (
        "COMMANDS/HOW.txt",
        "COMMANDS/inbox.txt",
        "COMMANDS/TEMPLATE_SAY.txt",
        "COMMANDS/TEMPLATE_SURFACE.txt",
        "COMMANDS/RECEIPTS/inbox.txt",
    )
    for rel in statics:
        text = _read_if(os.path.join(r"C:\Users\lucys\Desktop\MUHL_COMMONS", rel.replace("/", os.sep)))
        if text is not None:
            files[rel] = public_redact(text)
    rec_dir = os.path.join(CMD_ROOT, "RECEIPTS")
    if os.path.isdir(rec_dir):
        for fn in sorted(os.listdir(rec_dir)):
            if not fn.endswith(".txt"):
                continue
            text = _read_if(os.path.join(rec_dir, fn))
            if text is not None:
                files["COMMANDS/RECEIPTS/" + fn] = public_redact(text)
    for fn in sorted(os.listdir(CMD_ROOT)) if os.path.isdir(CMD_ROOT) else []:
        low = fn.lower()
        if not (low.endswith(".txt") or low.endswith(".json")):
            continue
        if low in ("how.txt", "inbox.txt", "readme.txt"):
            continue
        text = _read_if(os.path.join(CMD_ROOT, fn))
        if text is not None:
            files["COMMANDS/" + fn] = public_redact(text)
    return files


def write_local_public(files):
    for path, text in files.items():
        dest = os.path.join(PUBLIC, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(text if text.endswith("\n") else text + "\n")
            f.flush()
            os.fsync(f.fileno())
        print("LOCAL", dest, flush=True)


def main():
    if "--go" not in sys.argv:
        print("NEED_BRYCE — python host/muhl_pub_commons.py --go")
        return 1
    if "--inject" in sys.argv:
        print("REFUSE: --inject 0x01 is WIPE")
        return 2
    files = collect_pub_files()
    write_local_public(files)
    print("GIT publish kite-mouth-help...", flush=True)
    try:
        publish_git(files)
        print("DIE")
        return 0
    except Exception as e:
        print("GIT", type(e).__name__, e, flush=True)
    print("AUTH github API fallback...", flush=True)
    try:
        tok = _token()
    except SystemExit as e:
        print(e, flush=True)
        print("NEED_BRYCE — GitHub credential missing. Local PUBLIC written.", flush=True)
        print("NEED_BRYCE — python host/muhl_pub_commons.py --go --interactive-auth", flush=True)
        return 1
    print("AUTH ok", flush=True)
    for path, text in files.items():
        _put(tok, path, text, "Commons surface %s. mutation=NO on this publish." % path)
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
