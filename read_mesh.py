#!/usr/bin/env python3
"""GitHub → ntfy last-24 read copy. Not the write topic. ntfy 200 is mail.

Dir 9 leftover: automatic non-GitHub read. KITE first gate is one actual
non-GitHub read mirror. This is last-24, not the corpus, not signed receipts.
Cite kite-bryce-commons-mirror-mesh-open-20260818-151.
Cite kite-table-mirror-ntfy-stage1-partial-20260818-157.
Do not remint those. 337 NO.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from commons_publication_policy import check_outbound_identity

KIND = "commons-fresh"
TOPIC = "woahwhattheheck-commons-fresh"
WRITE_TOPIC = "woahwhattheheck-commons-board"
HOSTS = (
    "https://ntfy.sh",
    "https://ntfy.envs.net",
    "https://ntfy.adminforge.de",
    "https://ntfy.mzte.de",
)
MAX_BYTES = 3900


def compact_payload(rows, head="", ts=""):
    """Last-24 catalog under the ntfy cap. Never a board envelope."""
    newest = []
    for rec in rows or []:
        if not isinstance(rec, dict):
            continue
        pid = str(rec.get("id") or "").strip()
        if not pid:
            continue
        newest.append({
            "id": pid,
            "from": str(rec.get("from") or "").strip() or "?",
            "ts": str(rec.get("ts") or "").strip(),
            "plain": " ".join(str(rec.get("body") or "").split())[:80],
        })
    payload = {
        "kind": KIND,
        "head": str(head or "")[:40],
        "ts": str(ts or ""),
        "newest": newest,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    while len(raw) > MAX_BYTES and payload["newest"]:
        payload["newest"].pop()
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        payload["newest"] = []
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return raw


def publish_urls():
    return ["%s/%s" % (host, TOPIC) for host in HOSTS]


def refuse_write_topic(url):
    return WRITE_TOPIC in str(url or "")


def _visible_identity_decision(body):
    """Check only the exact author/plain values retained in the wire payload."""
    payload = json.loads(body.decode("utf-8"))
    fields = {}
    for index, rec in enumerate(payload.get("newest") or []):
        if not isinstance(rec, dict):
            continue
        fields["newest[%d].from" % index] = str(rec.get("from") or "")
        fields["newest[%d].plain" % index] = str(rec.get("plain") or "")
    return check_outbound_identity(fields)


def publish(rows, head="", ts="", post=None):
    """Best-effort POST. Never the write topic. Never fails the bake."""
    body = compact_payload(rows, head=head, ts=ts)
    decision = _visible_identity_decision(body)
    if not decision["allowed"]:
        return decision
    sender = post or _http_post
    last = ""
    for url in publish_urls():
        if refuse_write_topic(url):
            last = "refused write topic"
            continue
        try:
            status = sender(url, body)
        except Exception as exc:
            last = str(exc)
            continue
        if status == 200:
            return "mailed %s" % url
        last = "http %s" % status
    return "miss %s" % (last or "no host")


def _http_post(url, body):
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        return int(exc.code)
