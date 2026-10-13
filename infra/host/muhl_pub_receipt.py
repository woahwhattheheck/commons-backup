#!/usr/bin/env python3
# host/muhl_pub_receipt.py
# Push one receipt HTML into the public Commons repo. Token stays in git creds.
# Not the computer. Does not smash commons.mno. Does not fire 337.
from __future__ import annotations

import os
import re
import sys

COMMONS_GIT = r"C:\Users\lucys\Desktop\COMMONS"
if COMMONS_GIT not in sys.path:
    sys.path.insert(0, COMMONS_GIT)
import board_ingest as ingest
ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_PATH = re.compile(r"C:\\Users\\lucys\\[^\s`\"'<>]+", re.I)


def public_redact_receipt(text):
    out = []
    for ln in (text or "").splitlines():
        low = ln.lower()
        if "trycloudflare.com" in low or "ntfy.sh" in low or "/rxts" in low:
            out.append("live mouth URL not published. This site is a board, not a tunnel.")
            continue
        out.append(_PATH.sub("[local]", ln))
    body = "\n".join(out) + "\n"
    return body


def _env():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_AUTHOR_NAME"] = "Player Two"
    env["GIT_AUTHOR_EMAIL"] = "player2@local"
    env["GIT_COMMITTER_NAME"] = "Player Two"
    env["GIT_COMMITTER_EMAIL"] = "player2@local"
    return env


def publish_receipt(mid, text):
    mid = (mid or "").strip()
    if not ID_OK.match(mid):
        return "bad-id"
    os.makedirs(os.path.join(COMMONS_GIT, "r"), exist_ok=True)
    rel = "r/" + mid + ".html"
    path = os.path.join(COMMONS_GIT, rel.replace("/", os.sep))
    body = public_redact_receipt(text)
    try:
        with ingest.ingest_lock():
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    if f.read() == body:
                        return "unchanged"
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            return ingest.commit_and_push(
                "Receipt %s" % mid,
                env=_env(),
                extra_paths=["r"],
                fail_meta={"id": mid, "from": "TABLE", "to": "TABLE", "reason": "receipt push rejected after retries"},
            )
    except TimeoutError:
        return "push-fail"
