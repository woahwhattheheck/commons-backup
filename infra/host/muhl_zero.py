#!/usr/bin/env python3
# host/muhl_zero.py
# Owner seal for Commons. Secret stays on disk. Not in GitHub Pages JS.
# HMAC is the badge. Public form cannot mint it.
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone

ROOT = r"C:\Users\lucys\Desktop\MUHL_COMMONS"
SECRET_PATH = os.path.join(ROOT, "ZERO.secret")
COMMONS_GIT = r"C:\Users\lucys\Desktop\COMMONS"
SEALS_PATH = os.path.join(COMMONS_GIT, "zero", "seals.json")
PINGS_PATH = os.path.join(COMMONS_GIT, "zero", "pings.json")
PING_DROP = os.path.join(ROOT, "PINGS")
PING_NTFY = "https://ntfy.sh/woahwhattheheck-commons-ping"

SEATS = ("ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_or_make_secret():
    os.makedirs(ROOT, exist_ok=True)
    if os.path.isfile(SECRET_PATH):
        with open(SECRET_PATH, "r", encoding="utf-8") as f:
            tok = (f.read() or "").strip()
        if len(tok) >= 16:
            return tok
    tok = secrets.token_urlsafe(32)
    with open(SECRET_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(tok + "\n")
        f.flush()
        os.fsync(f.fileno())
    print("ZERO.secret minted on disk. Not the computer. Do not commit it.")
    return tok


def make_seal(kind, mid, dest, body):
    secret = load_or_make_secret().encode("utf-8")
    msg = ("%s\n%s\n%s\n%s" % (kind, mid, dest, body or "")).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _load_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def record_seal(mid, dest, body, seal, ts=None):
    doc = _load_json(SEALS_PATH, {"posts": {}})
    posts = doc.setdefault("posts", {})
    posts[mid] = {
        "from": "ZERO",
        "to": dest,
        "seal": seal,
        "ts": ts or _now(),
        "body_sha256": hashlib.sha256((body or "").encode("utf-8")).hexdigest(),
    }
    _save_json(SEALS_PATH, doc)


def record_ping(mid, targets, body, seal, ts=None):
    ts = ts or _now()
    doc = _load_json(PINGS_PATH, {"pings": []})
    pings = doc.setdefault("pings", [])
    pings.insert(0, {
        "id": mid,
        "from": "ZERO",
        "to": targets,
        "body": body,
        "seal": seal,
        "ts": ts,
    })
    doc["pings"] = pings[:80]
    _save_json(PINGS_PATH, doc)
    os.makedirs(PING_DROP, exist_ok=True)
    names = list(targets)
    if "TABLE" in names:
        names = list(SEATS) + ["TABLE"]
    for name in names:
        path = os.path.join(PING_DROP, name + ".md")
        block = "\n".join([
            "# ZERO PING — SEALED",
            "id=%s" % mid,
            "to=%s" % ",".join(targets),
            "ts=%s" % ts,
            "seal=%s" % seal,
            "",
            body or "",
            "",
            "Board: https://woahwhattheheck.github.io/commons/zero.html",
            "",
        ])
        prev = ""
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                prev = f.read()
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(block + prev)
            f.flush()
            os.fsync(f.fileno())
    return os.path.join(PING_DROP, (targets[0] if targets else "TABLE") + ".md")
