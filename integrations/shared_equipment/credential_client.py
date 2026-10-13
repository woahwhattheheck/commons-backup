"""Requester runtime client. Private key and decrypted value never go to stdout.

Keep CredentialRequest alive in the requesting runtime while its public request
travels through the HTTP/Slack equipment road. Call open() there, then use the
returned real value directly in that runtime. No key files or new vault needed.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import uuid

from .credential_transfer import (
    CredentialTransferError, CredentialSources, crypto, open_credential, public_hex,
)


class CredentialRequest:
    def __init__(self, credential_ref: str, *, request_id: str | None = None, call_id: str = "retrieve"):
        self._private_key = crypto()[0].generate()
        self._arguments = {
            "credential_ref": credential_ref, "transfer_id": uuid.uuid4().hex,
            "request_id": request_id or "credential-" + uuid.uuid4().hex,
            "call_id": call_id, "recipient_public_key": public_hex(self._private_key),
        }

    def arguments(self) -> dict:
        return dict(self._arguments)

    def equipment_request(self) -> dict:
        return {"request_id": self._arguments["request_id"], "call_id": self._arguments["call_id"],
                "name": "credential_retrieve_sealed", "arguments": self.arguments()}

    def slack_request(self) -> str:
        return "<commons_equipment_request>" + json.dumps(self.equipment_request(), separators=(",", ":")) + "</commons_equipment_request>"

    def open(self, result: dict):
        """Accept a raw sealed result or existing HTTP/service result wrappers.

        If HTTP request/call IDs are present, compare them with the retained
        request as well. The encrypted envelope always binds both IDs itself.
        """
        try:
            for _ in range(4):
                if not isinstance(result, dict) or result.get("isError") or result.get("ok") is False:
                    raise ValueError()
                if "ciphertext" in result:
                    return open_credential(result, self._private_key, self._arguments)
                for field in ("request_id", "call_id"):
                    if field in result and result[field] != self._arguments[field]:
                        raise ValueError()
                result = result["result"]
        except Exception:
            raise CredentialTransferError("credential_delivery_invalid") from None
        raise CredentialTransferError("credential_delivery_invalid")


def retrieve_http(credential_ref: str, *, base_url="http://127.0.0.1:8878", opener=None):
    """Get an actual credential in caller memory through the existing gateway."""
    pending = CredentialRequest(credential_ref)
    request = urllib.request.Request(base_url.rstrip("/") + "/v1/tools/call",
        data=json.dumps(pending.equipment_request()).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(request, timeout=90) as response:
            result = json.loads(response.read())
    except Exception:
        raise CredentialTransferError("credential_transport_unavailable") from None
    return pending.open(result)


def retrieve_local(credential_ref: str):
    """Same-host direct raw reader; no broker, encryption dependency, or grant."""
    return CredentialSources().read(credential_ref)


_RESULT_OPEN_RE = re.compile(
    r"<commons_equipment_result\b[^>]*?request_id=\"(?P<rid>[^\"]+)\""
    r"[^>]*?call_id=\"(?P<cid>[^\"]+)\""
    r"[^>]*?part=\"(?P<i>\d+)/(?P<n>\d+)\""
    r"\s+sha256=\"(?P<sha>[0-9a-f]{64})\"\s*>")
_RESULT_CLOSE = "</commons_equipment_result>"


def _unescape_slack(text: str) -> str:
    # One transport layer, matching slack_carrier.parse_request: ampersand
    # last preserves a literal '&lt;' inside an envelope payload.
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


_SLACK_LINK_RE = re.compile(
    r"<(?:https?://|mailto:)[^>|]+\|([^>]+)>|<(https?://[^>]+)>")


def _slack_delink(text: str) -> str:
    """Undo Slack's auto-linkification inside a body posted without
    parse="none": <http://x|y> -> y and <https://x> -> x. Digest-checked
    afterwards, so an uncorrupted body is never altered into a match."""
    return _SLACK_LINK_RE.sub(lambda m: m.group(1) or m.group(2), text)


def _iter_result_parts(messages, request_id: str, call_id: str):
    """Stream thread messages in order; yield (index, total, digest, body).

    Slack splits a single carrier post of more than roughly 4000 characters
    into an enveloped first message plus same-author continuation messages.
    A part body therefore spans consecutive same-author messages until the
    close tag; foreign-author messages between chunks are skipped.
    """
    open_buf = None
    for msg in messages:
        text = _unescape_slack(msg.get("text", "") if isinstance(msg, dict) else msg)
        author = msg.get("user") or msg.get("bot_id") if isinstance(msg, dict) else None
        while True:
            if open_buf is None:
                m = _RESULT_OPEN_RE.search(text)
                if m is None or m["rid"] != request_id or m["cid"] != call_id:
                    if m is not None:
                        # Not ours; keep scanning the rest of this text.
                        text = text[m.end():]
                        continue
                    break
                open_buf = {"author": author, "m": m, "chunks": [text[m.end():]]}
                text = ""
            else:
                if author is not None and open_buf["author"] is not None \
                        and author != open_buf["author"]:
                    break  # foreign message cannot extend the body
                open_buf["chunks"].append(text)
                text = ""
            stream = "".join(open_buf["chunks"])
            close = stream.find(_RESULT_CLOSE)
            if close < 0:
                break
            body = stream[:close]
            if body.startswith("\n"):
                body = body[1:]
            if body.endswith("\n"):
                body = body[:-1]
            m = open_buf["m"]
            open_buf = None
            yield int(m["i"]), int(m["n"]), m["sha"], body
            text = stream[close + len(_RESULT_CLOSE):]


def assemble_result(messages, request_id: str, call_id: str) -> dict | None:
    """Reassemble one request's <commons_equipment_result> replies.

    The carrier splits the inner {"request_id","call_id","result"} JSON into
    ~28000-char parts, each wrapped with part="i/N" and the sha256 of the
    full body; Slack then splits each posted part into ~4000-char
    same-author continuation messages. Returns the verified inner dict only
    when every part of one digest generation is present; otherwise None.
    Other requests' envelopes and partial generations are ignored.
    """
    generations = {}
    for index, count, found, body in _iter_result_parts(messages, request_id, call_id):
        gen = generations.setdefault(found, {"total": count, "parts": {}})
        if count != gen["total"]:
            continue  # part-count disagreement inside one digest: poisoned
        gen["parts"][index] = body
    for digest, gen in generations.items():
        if len(gen["parts"]) != gen["total"]:
            continue
        joined = "".join(gen["parts"][i] for i in range(1, gen["total"] + 1))
        if hashlib.sha256(joined.encode("utf-8")).hexdigest() != digest:
            # Bodies posted without parse="none" arrive auto-linked; the
            # declared digest decides which form is authoritative.
            delinked = _slack_delink(joined)
            if hashlib.sha256(delinked.encode("utf-8")).hexdigest() != digest:
                continue
            joined = delinked
        inner = json.loads(joined)
        if inner.get("request_id") == request_id and inner.get("call_id") == call_id:
            return inner
    return None


def retrieve_slack(credential_ref: str, *, post_message, read_replies,
                   channel: str = "C0BU51F1PL3", thread_ts: str = "1788567066.179399",
                   call_id: str = "retrieve", request_id: str | None = None,
                   timeout_seconds: float = 600, poll_seconds: float = 15,
                   clock=None, sleep=None):
    """Off-host sealed retrieval over the existing Slack equipment carrier.

    post_message(channel, thread_ts, text) is the peer's own Slack send road
    (workspace connector, MCP tool, or Web API). read_replies(channel,
    thread_ts) returns the thread's message texts or message dicts. The
    retained private key never leaves this runtime; only ciphertext travels.
    """
    pending = CredentialRequest(credential_ref, request_id=request_id, call_id=call_id)
    post_message(channel, thread_ts, pending.slack_request())
    args = pending.arguments()
    clock = clock or time.time
    sleep = sleep or time.sleep
    deadline = clock() + timeout_seconds
    while True:
        inner = assemble_result(read_replies(channel, thread_ts),
                                args["request_id"], args["call_id"])
        if inner is not None:
            return pending.open(inner)
        if clock() >= deadline:
            raise CredentialTransferError("credential_transport_unavailable")
        sleep(poll_seconds)


def slack_web(token: str, *, opener=None):
    """Build (post_message, read_replies) for retrieve_slack over Slack Web API.

    The token stays an in-memory argument; it is never logged or persisted.
    A peer that already holds a Slack credential can use this directly, or
    adapt the same two callables to its own connector.
    """
    open_url = opener or urllib.request.urlopen

    def call(method: str, payload: dict, form: bool) -> dict:
        if form:
            data = urllib.parse.urlencode(payload).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(payload).encode("utf-8")
            content_type = "application/json"
        request = urllib.request.Request(
            "https://slack.com/api/" + method, data=data,
            headers={"Authorization": "Bearer " + token, "Content-Type": content_type},
            method="POST")
        with open_url(request, timeout=60) as response:
            body = json.loads(response.read())
        if not body.get("ok"):
            raise CredentialTransferError("credential_transport_unavailable")
        return body

    def post_message(channel: str, thread_ts: str, text: str) -> None:
        call("chat.postMessage",
             {"channel": channel, "thread_ts": thread_ts, "text": text}, form=True)

    def read_replies(channel: str, thread_ts: str) -> list:
        # Return full message dicts: "user"/"bot_id" let assemble_result
        # skip foreign messages interleaved inside a split result part.
        messages = []
        cursor = None
        while True:
            payload = {"channel": channel, "ts": thread_ts, "limit": "200"}
            if cursor:
                payload["cursor"] = cursor
            body = call("conversations.replies", payload, form=True)
            messages.extend(body.get("messages", []))
            cursor = body.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return messages

    return post_message, read_replies
