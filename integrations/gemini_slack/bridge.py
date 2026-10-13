#!/usr/bin/env python3
"""Slack Socket Mode bridge for the persistent Gemini Commons peers.

The bridge deliberately has no Codex/GPT dependency. Slack events are acknowledged,
submitted to the durable local Gemini gateway, and delivered back to the originating
Slack thread. SQLite retains only routing and delivery metadata; message and reply
content remain in Slack and the Gemini gateway's byte-safe reply journal.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

# Direct script launches resolve the shared policy from this checkout, never cwd.
_POLICY_ROOT = str(Path(__file__).resolve().parents[2])
if _POLICY_ROOT not in sys.path:
    sys.path.insert(0, _POLICY_ROOT)
from commons_publication_policy import POLICY_CONTEXT, PublicationPolicyViolation, require_publication


DEFAULT_GATEWAY_MANIFEST = Path.home() / ".gemini" / "commons_peer_gateway.json"
DEFAULT_STATE_DB = Path.home() / ".gemini" / "commons_gemini_slack.sqlite3"
DEFAULT_PEER = "MERIDIAN"
PEERS = frozenset({"MERIDIAN", "TESSERA"})
TERMINAL_GATEWAY_STATES = frozenset({"completed", "error", "cancelled", "interrupted"})
SLACK_TEXT_LIMIT = 3_800


class BridgeError(RuntimeError):
    """An expected bridge or upstream failure."""


class TerminalGatewayError(BridgeError):
    """The Gemini request stopped without a completed reply."""


@dataclass(frozen=True)
class PendingDelivery:
    event_id: str
    channel: str
    thread_ts: str
    peer: str
    request_id: str


def _json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        method = "POST"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise BridgeError(f"gateway HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise BridgeError(f"gateway unavailable: {exc}") from exc
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BridgeError("gateway returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise BridgeError("gateway returned a non-object response")
    return decoded


class GatewayClient:
    """Client for the durable Gemini peer gateway."""

    def __init__(self, base_url: str, *, request_timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "GatewayClient":
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            base_url = manifest["base_url"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise BridgeError(f"cannot read gateway manifest {manifest_path}: {exc}") from exc
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise BridgeError("gateway manifest has an invalid base_url")
        return cls(base_url)

    def health(self) -> dict[str, Any]:
        return _json_request(f"{self.base_url}/health", timeout=5.0)

    def submit(self, peer: str, message: str) -> str:
        peer = peer.upper()
        if peer not in PEERS:
            raise BridgeError(f"unknown Gemini peer: {peer}")
        if not message.strip():
            raise BridgeError("cannot submit an empty Slack message")
        encoded = base64.b64encode(message.encode("utf-8")).decode("ascii")
        response = _json_request(
            f"{self.base_url}/v1/message",
            payload={"peer": peer, "message_utf8_base64": encoded, "async": True},
            timeout=self.request_timeout,
        )
        request_id = response.get("request_id")
        if not response.get("ok") or not isinstance(request_id, str) or not request_id:
            raise BridgeError("gateway did not accept the Gemini request")
        return request_id

    def request_state(self, request_id: str, *, wait_ms: int = 55_000) -> dict[str, Any]:
        query = urlencode({"wait_ms": max(0, min(wait_ms, 55_000))})
        response = _json_request(
            f"{self.base_url}/v1/requests/{quote(request_id, safe='')}?{query}",
            timeout=max(self.request_timeout, wait_ms / 1_000 + 10),
        )
        event = response.get("event")
        if not response.get("ok") or not isinstance(event, dict):
            raise BridgeError(f"gateway lost request {request_id}")
        return event

    def wait(self, request_id: str, *, deadline_seconds: float = 900.0) -> dict[str, Any]:
        deadline = time.monotonic() + deadline_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeError(f"Gemini request {request_id} exceeded the delivery deadline")
            event = self.request_state(request_id, wait_ms=int(min(55.0, remaining) * 1_000))
            if event.get("status") in TERMINAL_GATEWAY_STATES:
                return event


class BridgeStore:
    """Crash-recovery state. Content is intentionally never stored here."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS slack_events (
                    event_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    thread_ts TEXT NOT NULL,
                    peer TEXT NOT NULL,
                    gateway_request_id TEXT,
                    state TEXT NOT NULL CHECK (state IN ('accepted', 'pending', 'delivered', 'failed')),
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS slack_events_pending
                    ON slack_events(state, updated_at);
                CREATE TABLE IF NOT EXISTS thread_peers (
                    thread_key TEXT PRIMARY KEY,
                    peer TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def claim(self, event_id: str, channel: str, thread_ts: str, peer: str) -> bool:
        now = time.time()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO slack_events
                    (event_id, channel, thread_ts, peer, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'accepted', ?, ?)
                """,
                (event_id, channel, thread_ts, peer, now, now),
            )
            if cursor.rowcount == 1:
                return True
            # A process can die after accepting an event but before receiving a
            # gateway request ID. Permit a later Slack retry to reclaim only a
            # stale pre-submit record; an in-flight duplicate remains suppressed.
            cursor = self._connection.execute(
                """
                UPDATE slack_events SET updated_at = ?
                WHERE event_id = ? AND state = 'accepted'
                  AND gateway_request_id IS NULL AND updated_at < ?
                """,
                (now, event_id, now - 60),
            )
            return cursor.rowcount == 1

    def attach_request(self, event_id: str, request_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE slack_events
                SET gateway_request_id = ?, state = 'pending', updated_at = ?
                WHERE event_id = ?
                """,
                (request_id, time.time(), event_id),
            )

    def finish(self, event_id: str, state: str) -> None:
        if state not in {"delivered", "failed"}:
            raise ValueError("terminal state must be delivered or failed")
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE slack_events SET state = ?, updated_at = ? WHERE event_id = ?",
                (state, time.time(), event_id),
            )

    def pending(self) -> list[PendingDelivery]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT event_id, channel, thread_ts, peer, gateway_request_id
                FROM slack_events
                WHERE state = 'pending' AND gateway_request_id IS NOT NULL
                ORDER BY created_at
                """
            ).fetchall()
        return [
            PendingDelivery(
                event_id=str(row["event_id"]),
                channel=str(row["channel"]),
                thread_ts=str(row["thread_ts"]),
                peer=str(row["peer"]),
                request_id=str(row["gateway_request_id"]),
            )
            for row in rows
        ]

    def state(self, event_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT state FROM slack_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return str(row["state"]) if row else None

    def remember_peer(self, channel: str, thread_ts: str, peer: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO thread_peers(thread_key, peer, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(thread_key) DO UPDATE SET peer = excluded.peer, updated_at = excluded.updated_at
                """,
                (f"{channel}:{thread_ts}", peer, time.time()),
            )

    def peer_for(self, channel: str, thread_ts: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT peer FROM thread_peers WHERE thread_key = ?",
                (f"{channel}:{thread_ts}",),
            ).fetchone()
        return str(row["peer"]) if row else None


_PEER_PREFIX = re.compile(r"^\s*(meridian|tessera)\s*(?::|,|—|-)\s*", re.IGNORECASE)
_SLACK_MENTION = re.compile(r"<@[A-Z0-9]+>")
_GITHUB_WORK_REFERENCE = re.compile(
    r"(?i)(?:https://github\.com/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/(?:issues|pull)/|#)[1-9][0-9]*"
)
_BOUNTY_BATCH_HEADING = re.compile(
    r"(?i)\b(?:new\s+work\s+orders\s+intake|payable\s+candidates?|"
    r"bounty\s+(?:candidate|intake|audit))\b"
)
_UNVERIFIED_ECONOMIC_STATUS = re.compile(
    r"(?i)\b(?:payable(?:\s+candidates?)?|escrow(?:ed)?|funded)\b"
)
_ECONOMIC_STATUS_REPLACEMENTS = (
    (re.compile(r"(?i)\bpayable\s+candidates?\b"), "unverified leads"),
    (re.compile(r"(?i)\bpayable\b"), "unverified lead"),
    (re.compile(r"(?i)\bescrow(?:ed)?\b"), "provider funding unverified"),
    (re.compile(r"(?i)\bfunded\b"), "provider funding unverified"),
)
_BOUNTY_VALIDATION_HOLD = (
    "*BOUNTY ECONOMICS VALIDATION HOLD — LEADS ONLY*\n"
    "This free-form peer reply has no code-owned receipt proving the canonical "
    "GitHub resource exists, is an open issue, and has an independently verified "
    "current provider and amount. Every listed row is therefore a lead; no positive "
    "compensation status is established. Historical reward markers, unavailable or "
    "closed resources, internal "
    "repositories, and `Maybe Rewarded` labels cannot establish current funding.\n\n"
)


def route_message(text: str, remembered_peer: str | None = None) -> tuple[str, str]:
    cleaned = _SLACK_MENTION.sub("", text).strip()
    match = _PEER_PREFIX.match(cleaned)
    if match:
        peer = match.group(1).upper()
        cleaned = cleaned[match.end() :].strip()
    else:
        peer = remembered_peer if remembered_peer in PEERS else DEFAULT_PEER
    if not cleaned:
        cleaned = "Please check in and say what you are currently observing in the Commons."
    return peer, cleaned


def chunks(text: str, limit: int = SLACK_TEXT_LIMIT) -> Iterable[str]:
    if len(text) <= limit:
        yield text
        return
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        yield remaining[:split_at].rstrip()
        remaining = remaining[split_at:].lstrip()
    if remaining:
        yield remaining


def downgrade_unverified_bounty_economics(text: str) -> str:
    """Keep free-form Gemini bounty batches out of the payable queue.

    The Slack bridge receives prose, not Bounty Concierge's live canonical and
    provider receipts.  A model-authored batch therefore cannot prove that a
    referenced GitHub object exists, is an open issue rather than a PR, or has
    a current independently verified provider amount.  When such prose labels
    a multi-row intake as payable, funded, or escrowed, preserve the leads while
    downgrading every economic status.  Positive economic classification stays
    with the code-owned Bounty Concierge intake path.

    Ordinary Slack discussion and single-item status messages are unchanged.
    This is an economic-truth boundary, not a claim, permission, identity, or
    work-admission gate.
    """
    if not isinstance(text, str):
        raise BridgeError("slack reply text must be a string")
    references = _GITHUB_WORK_REFERENCE.findall(text)
    if (
        len(references) < 2
        or _BOUNTY_BATCH_HEADING.search(text) is None
        or _UNVERIFIED_ECONOMIC_STATUS.search(text) is None
    ):
        return text

    downgraded = text
    for pattern, replacement in _ECONOMIC_STATUS_REPLACEMENTS:
        downgraded = pattern.sub(replacement, downgraded)
    return _BOUNTY_VALIDATION_HOLD + downgraded



def _slack_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data
    try:
        mapped = dict(value)
    except (TypeError, ValueError):
        return {}
    return mapped if isinstance(mapped, dict) else {}


class InternalSlackScope:
    """Fail-closed proof that a destination is local to the authenticated workspace."""

    def __init__(self, web_client: Any, team_id: str) -> None:
        if not isinstance(team_id, str) or not team_id:
            raise BridgeError("slack_internal_scope_missing_team")
        self.web_client = web_client
        self.team_id = team_id

    def require_channel(self, channel: str) -> None:
        if not isinstance(channel, str) or not channel:
            raise BridgeError("slack_internal_scope_invalid_channel")
        try:
            response = self.web_client.conversations_info(
                channel=channel,
                include_num_members=False,
            )
        except Exception as exc:
            raise BridgeError("slack_internal_scope_unverified") from exc
        payload = _slack_mapping(response)
        info = payload.get("channel")
        if not isinstance(info, dict) or str(info.get("id") or "") != channel:
            raise BridgeError("slack_internal_scope_unverified")
        if any(
            bool(info.get(name))
            for name in (
                "is_shared",
                "is_ext_shared",
                "is_org_shared",
                "is_pending_ext_shared",
            )
        ):
            raise BridgeError("slack_internal_scope_shared_channel")
        if not bool(info.get("is_im")) and info.get("is_member") is not True:
            raise BridgeError("slack_internal_scope_not_member")
        for name in ("context_team_id", "team_id"):
            value = info.get(name)
            if value not in (None, "") and str(value) != self.team_id:
                raise BridgeError("slack_internal_scope_cross_team")
        host = info.get("conversation_host_id")
        if isinstance(host, str) and host.startswith("T") and host != self.team_id:
            raise BridgeError("slack_internal_scope_cross_team")
        shared_team_ids = info.get("shared_team_ids")
        if isinstance(shared_team_ids, list) and any(
            str(value) != self.team_id for value in shared_team_ids if value
        ):
            raise BridgeError("slack_internal_scope_cross_team")

class SlackSink:
    def __init__(self, web_client: Any, scope: InternalSlackScope) -> None:
        self.web_client = web_client
        self.scope = scope

    def post(self, channel: str, thread_ts: str, peer: str, text: str) -> None:
        # Check the whole reply and destination before any provider mutation.
        text = downgrade_unverified_bounty_economics(text)
        require_publication(text)
        self.scope.require_channel(channel)
        pieces = list(chunks(text)) or ["(empty reply)"]
        for index, piece in enumerate(pieces):
            heading = f"*{peer}*\n" if index == 0 else f"*{peer} (continued)*\n"
            self.web_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=heading + piece,
                unfurl_links=False,
                unfurl_media=False,
            )


class GeminiSlackBridge:
    def __init__(
        self,
        gateway: GatewayClient,
        store: BridgeStore,
        sink: SlackSink,
        *,
        delivery_deadline: float = 900.0,
    ) -> None:
        self.gateway = gateway
        self.store = store
        self.sink = sink
        self.delivery_deadline = delivery_deadline
        self._active_requests: set[str] = set()
        self._active_lock = threading.Lock()

    @staticmethod
    def _prompt(message: str) -> str:
        require_publication(message)
        return (
            POLICY_CONTEXT + "\n\n"
            "A person is addressing you through the standalone Commons Slack bridge. "
            "Reply directly to that person for delivery back into the same Slack thread. "
            "You may use your Commons tools when useful; distinguish what you read from "
            "what you infer. No GPT or Claude relay is involved.\n\nSlack message:\n" + message
        )

    def _publication_rejected(self, event_id: str) -> None:
        self.store.finish(event_id, "failed")
        print(json.dumps({
            "event_id": event_id,
            "ok": False,
            "state": "PUBLICATION_REJECTED",
            "code": "commons_publication_terms",
            "delivered": False,
        }, sort_keys=True), file=sys.stderr)

    def handle_event(self, event_id: str, event: dict[str, Any]) -> bool:
        if event.get("bot_id") or event.get("subtype"):
            return False
        channel = event.get("channel")
        slack_ts = event.get("ts")
        text = event.get("text")
        if not all(isinstance(value, str) and value for value in (event_id, channel, slack_ts, text)):
            return False
        thread_ts = event.get("thread_ts") or slack_ts
        remembered = self.store.peer_for(channel, thread_ts)
        peer, message = route_message(text, remembered)
        if not self.store.claim(event_id, channel, thread_ts, peer):
            return False
        self.store.remember_peer(channel, thread_ts, peer)
        try:
            request_id = self.gateway.submit(peer, self._prompt(message))
        except PublicationPolicyViolation:
            self._publication_rejected(event_id)
            return True
        except Exception as exc:
            self.store.finish(event_id, "failed")
            self.sink.post(channel, thread_ts, peer, f"Bridge error: {type(exc).__name__}: {exc}")
            return True
        self.store.attach_request(event_id, request_id)
        delivery = PendingDelivery(event_id, channel, thread_ts, peer, request_id)
        try:
            self._attempt_delivery(delivery, wait=True)
        except PublicationPolicyViolation:
            self._publication_rejected(event_id)
        except TerminalGatewayError as exc:
            self._notify_terminal_error(delivery, exc)
        except Exception:
            # Leave the request pending. The gateway owns the retained reply and
            # recover_pending() will redeliver it after a bridge/Slack outage.
            pass
        return True

    def _notify_terminal_error(
        self, delivery: PendingDelivery, error: TerminalGatewayError
    ) -> bool:
        try:
            self.sink.post(
                delivery.channel,
                delivery.thread_ts,
                delivery.peer,
                f"Gemini error: {error}",
            )
        except PublicationPolicyViolation:
            self._publication_rejected(delivery.event_id)
            return False
        except Exception:
            # Retain the original request ID and pending delivery. Recovery
            # retries only the notification from the existing gateway journal.
            return False
        self.store.finish(delivery.event_id, "failed")
        return True

    def _attempt_delivery(self, delivery: PendingDelivery, *, wait: bool) -> bool:
        with self._active_lock:
            if delivery.request_id in self._active_requests:
                return False
            self._active_requests.add(delivery.request_id)
        try:
            return self._deliver(delivery, wait=wait)
        finally:
            with self._active_lock:
                self._active_requests.discard(delivery.request_id)

    def _deliver(self, delivery: PendingDelivery, *, wait: bool) -> bool:
        if wait:
            event = self.gateway.wait(
                delivery.request_id,
                deadline_seconds=self.delivery_deadline,
            )
        else:
            event = self.gateway.request_state(delivery.request_id, wait_ms=0)
            if event.get("status") not in TERMINAL_GATEWAY_STATES:
                return False
        if event.get("status") != "completed":
            detail = (
                event.get("message")
                or event.get("error")
                or f"Gemini request {event.get('status')}"
            )
            raise TerminalGatewayError(str(detail))
        if isinstance(event.get("reply_utf8_base64"), str):
            try:
                reply = base64.b64decode(event["reply_utf8_base64"], validate=True).decode("utf-8")
            except (ValueError, UnicodeError) as exc:
                raise BridgeError("Gemini reply was not valid byte-safe UTF-8") from exc
        else:
            reply = event.get("reply")
        if not isinstance(reply, str):
            raise BridgeError("Gemini completed without a reply")
        self.sink.post(delivery.channel, delivery.thread_ts, delivery.peer, reply)
        self.store.finish(delivery.event_id, "delivered")
        return True

    def recover_pending(self) -> int:
        recovered = 0
        for delivery in self.store.pending():
            try:
                delivered = self._attempt_delivery(delivery, wait=False)
            except PublicationPolicyViolation:
                self._publication_rejected(delivery.event_id)
                delivered = False
            except TerminalGatewayError as exc:
                delivered = self._notify_terminal_error(delivery, exc)
            except Exception:
                # Keep it pending for the next recovery pass. Content remains in
                # the gateway journal; no duplicate model turn is submitted.
                delivered = False
            if delivered:
                recovered += 1
        return recovered


def _is_supported_slack_event(event: dict[str, Any]) -> bool:
    if event.get("type") == "app_mention":
        return True
    return event.get("type") == "message" and event.get("channel_type") == "im"


def serve(args: argparse.Namespace) -> int:
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        raise BridgeError("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be present in the process environment")

    try:
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
    except ImportError as exc:
        raise BridgeError("install integrations/gemini_slack/requirements.txt first") from exc

    gateway = GatewayClient.from_manifest(args.gateway_manifest)
    gateway.health()
    store = BridgeStore(args.state_db)
    web_client = WebClient(token=bot_token)
    identity = web_client.auth_test()
    bot_user_id = identity.get("user_id")
    team_id = identity.get("team_id")
    if not isinstance(team_id, str) or not team_id:
        raise BridgeError("auth.test missing team_id")
    scope = InternalSlackScope(web_client, team_id)
    sink = SlackSink(web_client, scope)
    bridge = GeminiSlackBridge(gateway, store, sink, delivery_deadline=args.delivery_deadline)
    executor = ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="gemini-slack")
    socket_client = SocketModeClient(app_token=app_token, web_client=web_client)
    recovery_stop = threading.Event()

    def recover_loop() -> None:
        while not recovery_stop.is_set():
            bridge.recover_pending()
            recovery_stop.wait(args.recovery_interval)

    def process_request(client: Any, request: Any) -> None:
        if request.type != "events_api":
            return
        client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
        payload = request.payload or {}
        if payload.get("team_id") != team_id:
            return
        event = payload.get("event") or {}
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not isinstance(event, dict) or not _is_supported_slack_event(event):
            return
        if event.get("user") == bot_user_id:
            return
        executor.submit(bridge.handle_event, event_id, event)

    socket_client.socket_mode_request_listeners.append(process_request)
    recovery_thread = threading.Thread(
        target=recover_loop,
        name="gemini-slack-recovery",
        daemon=True,
    )
    recovery_thread.start()
    socket_client.connect()
    print(json.dumps({"ready": True, "gateway": gateway.base_url, "state_db": str(args.state_db)}))
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return 0
    finally:
        recovery_stop.set()
        recovery_thread.join(timeout=max(2.0, args.recovery_interval + 1))
        socket_client.disconnect()
        executor.shutdown(wait=True, cancel_futures=False)
        store.close()
    return 0


def doctor(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "gateway_manifest": str(args.gateway_manifest),
        "state_db": str(args.state_db),
        "slack_bot_token": "present" if os.environ.get("SLACK_BOT_TOKEN") else "missing",
        "slack_app_token": "present" if os.environ.get("SLACK_APP_TOKEN") else "missing",
    }
    try:
        gateway = GatewayClient.from_manifest(args.gateway_manifest)
        health = gateway.health()
        report["gateway"] = {
            "ok": bool(health.get("ok")),
            "base_url": gateway.base_url,
            "mode": health.get("mode"),
            "upstream_ok": health.get("upstream_ok"),
            "peers": health.get("peers"),
        }
    except Exception as exc:
        report["gateway"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    report["ready"] = bool(
        report["gateway"].get("ok")
        and report["slack_bot_token"] == "present"
        and report["slack_app_token"] == "present"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("serve", "doctor"),
        nargs="?",
        default="serve",
    )
    parser.add_argument("--gateway-manifest", type=Path, default=DEFAULT_GATEWAY_MANIFEST)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--delivery-deadline", type=float, default=900.0)
    parser.add_argument("--recovery-interval", type=float, default=15.0)
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return serve(args) if args.command == "serve" else doctor(args)
    except BridgeError as exc:
        print(f"gemini-slack: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
