"""One-shot public demo messages through the existing Slack account.

This concrete route is michael-external-demo, not the generic internal sender.
The existing private journal suppresses duplicate effects and keeps uncertain
sends for readback. No service, credential store or background worker is added.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from commons_publication_policy import PublicationPolicyViolation, check_outbound_identity
from host.customer_link_boundary import require_customer_link_safe
from .provider_io import EquipmentError, GitHubSlackEquipment, redacted
from .workhandoff import WorkHandoff, TEAM_ID, _OPERATION_ID


DEMO_CHANNEL_ID = "C0C7S2D5QRE"
DEMO_CHANNEL_NAME = "michael-external-demo"
_TIMESTAMP = re.compile(r"[0-9]{10}\.[0-9]{6}")
_PROBE_KEYS = ("ok", "error", "needed", "provided", "status", "retry_after")
# Owner-installed bots in workspace T0BRETUB5TK that may post here. The sender
# is not fixed to one of them: it is read from auth.test for the token in use,
# and the readback must match that identity.
ALLOWED_SENDER_BOT_IDS = frozenset({
    "B0BTD42EMFY",  # Commons Grok (bot user U0BTGV2G589)
    "B0C26JX3G3S",  # commons_swarm
})


class _DemoTransport(GitHubSlackEquipment):
    """Keep the existing provider field mapping and fixed account transport."""

    def _slack_write_route_verified(self, channel_id=None):
        return (channel_id == DEMO_CHANNEL_ID and self.demo.sender_verified()
                and self.demo._destination_verified(channel_id))

    def slack(self, method, payload):
        if method == "chat.postMessage":
            # The dedicated tool never changes username, icon, or account.
            if payload.get("channel") != DEMO_CHANNEL_ID:
                raise EquipmentError("external demo destination differs from the configured channel",
                                     code="external_demo_destination_mismatch", delivered=False)
            decision = check_outbound_identity({"text": payload.get("text", "")})
            if not decision["allowed"]:
                raise PublicationPolicyViolation(decision)
            require_customer_link_safe(payload.get("text", ""))
        elif method not in {"auth.test", "conversations.history",
                            "conversations.replies", "chat.getPermalink"}:
            raise EquipmentError("external demo route maps only a text message",
                                 code="outbound_field_mapping_missing", delivered=False)
        return super().slack(method, payload)


class ExternalDemoMessages(WorkHandoff):
    """Reuse account/read/journal helpers for a fixed public demo destination."""

    def __init__(self, equipment=None, *, journal_path=None):
        transport = _DemoTransport(**({
            "gh": equipment.gh, "slack_token_loader": equipment.slack_token_loader,
            "gh_runner": equipment.gh_runner, "opener": equipment.opener,
        } if equipment is not None else {}))
        super().__init__(transport, journal_path=journal_path or (
            Path.home() / ".commons" / "shared_equipment" / "external_demo.sqlite3"))
        transport.demo = self
        self._destination_probe = {}
        self._sender = None

    def _resolve_sender(self):
        # auth.test needs no scope. Its answer for the token in use is kept for
        # the life of this route instance; a binding change reloads the
        # gateway, which builds a new instance. A failed or unreachable
        # auth.test is not kept, so the next call asks again.
        if self._sender is not None:
            return self._sender
        try:
            auth = self._slack_read("auth.test", {})
        except Exception as exc:
            return {"allowed": False, "reason": "SENDER_UNRESOLVED",
                    "error": getattr(exc, "code", type(exc).__name__)}
        if not isinstance(auth, dict) or auth.get("ok") is not True:
            return {"allowed": False, "reason": "SENDER_UNRESOLVED",
                    "error": auth.get("error") if isinstance(auth, dict) else "auth_test_invalid"}
        sender = {key: auth.get(key) for key in ("user_id", "bot_id", "team_id", "team")}
        # A user token (no bot_id), another app's bot, or another workspace
        # is outside the owner-installed pair and never sends here.
        allowed = (isinstance(sender["user_id"], str) and bool(sender["user_id"])
                   and sender["bot_id"] in ALLOWED_SENDER_BOT_IDS and sender["team_id"] == TEAM_ID)
        sender.update(allowed=allowed, reason=None if allowed else "SENDER_NOT_ALLOWED")
        self._sender = sender
        return sender

    def sender_verified(self):
        return self._resolve_sender().get("allowed") is True

    def _destination_verified(self, channel_id):
        # Only the fixed Connect channel ID is accepted. conversations.info is
        # not called: it needs channels:read/groups:read, which the installed
        # bot does not hold (missing_scope), and the owner may switch the
        # channel between public and private. A bot token's history read
        # answers ok only for a channel the bot is a member of, under
        # channels:history while public or groups:history while private. The
        # bot holds both, so either setting passes; not_in_channel,
        # channel_not_found or a missing scope fails closed.
        if channel_id != DEMO_CHANNEL_ID:
            return False
        member = self._slack_read("conversations.history", {"channel": DEMO_CHANNEL_ID, "limit": 1})
        self._destination_probe = {"method": "conversations.history", "channel_id": DEMO_CHANNEL_ID,
                                   **{key: member[key] for key in _PROBE_KEYS if key in member}}
        return member.get("ok") is True

    def inspect(self):
        resolved = self._resolve_sender()
        sender = resolved.get("allowed") is True
        destination = self._destination_verified(DEMO_CHANNEL_ID)
        result = {"ok": sender and destination, "state": "READY" if sender and destination else "ROUTE_UNAVAILABLE",
                  "channel_id": DEMO_CHANNEL_ID, "channel_name": DEMO_CHANNEL_NAME,
                  "sender": resolved, "allowed_sender_bot_ids": sorted(ALLOWED_SENDER_BOT_IDS),
                  "sender_verified": sender, "destination_verified": destination,
                  "destination_probe": self._destination_probe, "writes": 0}
        if not result["ok"]:
            result["reason"] = resolved.get("reason") or "DESTINATION_UNVERIFIED"
        return result

    @staticmethod
    def normalize(args):
        if not isinstance(args, dict) or set(args) - {"operation_id", "text", "thread_ts"}:
            raise ValueError("demo message contains unknown fields")
        operation = args.get("operation_id")
        if not isinstance(operation, str) or not _OPERATION_ID.fullmatch(operation):
            raise ValueError("operation_id must be a stable 8-128 character ID")
        text = args.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("text must contain 1-4000 characters of public demo copy")
        if redacted(text) != text:
            raise ValueError("demo text contains credential material")
        decision = check_outbound_identity({"text": text})
        if not decision["allowed"]:
            raise PublicationPolicyViolation(decision)
        require_customer_link_safe(text)
        item = {"operation_id": operation, "channel_id": DEMO_CHANNEL_ID, "text": text}
        if args.get("thread_ts") is not None:
            if not isinstance(args["thread_ts"], str) or not _TIMESTAMP.fullmatch(args["thread_ts"]):
                raise ValueError("thread_ts must be a Slack message timestamp")
            item["thread_ts"] = args["thread_ts"]
        return item

    @staticmethod
    def _provider_failure(failure, *, operation_id=None, phase=None):
        result = WorkHandoff._provider_failure(failure, operation_id=operation_id, phase=phase)
        read = failure.get if isinstance(failure, dict) else (
            lambda key, default=None: getattr(failure, key, default))
        if read("error") == "missing_scope":
            # Slack names the scopes it wanted and the scopes the token holds.
            # Keep both so the fleet sees exactly which bot scope is missing.
            result.update(code="missing_scope", provider_error="missing_scope",
                          **{key: read(key) for key in ("needed", "provided") if isinstance(read(key), str)})
        return result

    def _verify_message(self, item, digest):
        message_ts = item.get("message_ts")
        if not isinstance(message_ts, str) or not _TIMESTAMP.fullmatch(message_ts):
            return None
        # GET query arguments: send Slack's documented "true" rather than
        # Python True, which urlencode renders as "True".
        args = {"channel": DEMO_CHANNEL_ID, "limit": 100, "inclusive": "true"}
        if item.get("thread_ts"):
            method = "conversations.replies"
            args.update(ts=item["thread_ts"], oldest=message_ts, latest=message_ts)
        else:
            method = "conversations.history"
            args.update(latest=message_ts, limit=1)
        page = self._slack_read(method, args)
        if page.get("ok") is not True:
            return {**self._provider_failure(page, operation_id=item["operation_id"], phase="readback"),
                    "channel_id": DEMO_CHANNEL_ID, "message_ts": message_ts, "delivered": True}
        message = next((value for value in page.get("messages", [])
                        if isinstance(value, dict) and value.get("ts") == message_ts), None)
        if not message:
            return None
        body = message.get("text")
        # The message must come from the identity auth.test resolved for the
        # token in use, not merely from any allowed bot.
        expected = self._resolve_sender()
        sender = (expected.get("allowed") is True and message.get("user") == expected.get("user_id")
                  and message.get("bot_id") == expected.get("bot_id"))
        body_ok = body == item["text"]
        # A provider-appended footer or rich field must never become a passed
        # outward result merely because the original text was a prefix.
        visible = {"text": body} if isinstance(body, str) else {}
        decision = check_outbound_identity(visible)
        confirmed = sender and body_ok and decision["allowed"]
        receipt = {"operation_id": item["operation_id"], "payload_sha256": digest,
                   "channel_id": DEMO_CHANNEL_ID, "message_ts": message_ts,
                   "sender_user_id": message.get("user"), "sender_bot_id": message.get("bot_id"),
                   "sender_verified": sender,
                   "body_verified": body_ok, "provider_footer_present": not body_ok,
                   "readback_state": "confirmed" if confirmed else "mismatch", "message_permalink": None}
        try:
            link = self._slack_read("chat.getPermalink", {"channel": DEMO_CHANNEL_ID, "message_ts": message_ts})
            receipt["message_permalink"] = link.get("permalink") if link.get("ok") is True else None
        except Exception:
            pass
        return receipt

    def status(self, args):
        operation = args.get("operation_id") if isinstance(args, dict) else None
        if (not isinstance(args, dict) or set(args) - {"operation_id", "message_ts"}
                or not isinstance(operation, str) or not _OPERATION_ID.fullmatch(operation)):
            return {"ok": False, "state": "INVALID_ARGUMENTS", "delivered": False}
        prior = self._journal(operation)
        if not prior:
            return {"ok": True, "state": "NOT_FOUND", "operation_id": operation}
        if prior["state"] == "rejected":
            return {**((prior.get("metadata") or {}).get("provider_failure") or {}),
                    "ok": False, "state": "REJECTED", "operation_id": operation,
                    "delivered": False, "uncertain": False}
        item = {"operation_id": operation, **(prior.get("metadata") or {})}
        if args.get("message_ts") is not None:
            if not isinstance(args["message_ts"], str) or not _TIMESTAMP.fullmatch(args["message_ts"]):
                return {"ok": False, "state": "INVALID_ARGUMENTS", "code": "invalid_message_ts"}
            item["message_ts"] = args["message_ts"]
        resolved = self._resolve_sender()
        sender = resolved.get("allowed") is True
        if not sender or not self._destination_verified(DEMO_CHANNEL_ID):
            return {"ok": False, "state": "ROUTE_UNAVAILABLE", "operation_id": operation,
                    "reason": resolved.get("reason") or "DESTINATION_UNVERIFIED",
                    "uncertain": prior["state"] != "delivered", "sender": resolved, "sender_verified": sender,
                    "destination_probe": self._destination_probe if sender else {}}
        receipt = self._verify_message(item, prior["payload_sha256"])
        if receipt and receipt.get("readback_state") == "confirmed":
            self._save(operation, prior["payload_sha256"], "delivered", receipt, item)
            return {"ok": True, "state": "DELIVERED", "delivered": True, "receipt": receipt, "reconciled": True}
        return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": operation,
                "delivered": True if item.get("message_ts") else None,
                "uncertain": not bool(item.get("message_ts")), "receipt": receipt,
                "message_ts": item.get("message_ts"), "retry": "read status; never resend an uncertain operation"}

    def post(self, args):
        item = self.normalize(args)
        digest = self.payload_hash(item)
        prior = self._journal(item["operation_id"])
        if prior:
            if prior["payload_sha256"] != digest:
                return {"ok": False, "state": "IDEMPOTENCY_CONFLICT", "operation_id": item["operation_id"], "delivered": False}
            if prior["state"] == "delivered" and prior.get("receipt"):
                return {"ok": True, "state": "DELIVERED", "delivered": True, "receipt": prior["receipt"], "replayed": True}
            return self.status({"operation_id": item["operation_id"]})
        readiness = self.inspect()
        if not readiness["ok"]:
            return {**readiness, "delivered": False, "operation_id": item["operation_id"]}
        concurrent = self._claim(item["operation_id"], digest, item)
        if concurrent:
            if concurrent["payload_sha256"] != digest:
                return {"ok": False, "state": "IDEMPOTENCY_CONFLICT", "delivered": False}
            return self.status({"operation_id": item["operation_id"]})
        payload = {"channel": DEMO_CHANNEL_ID, "text": item["text"], "unfurl_links": False,
                   "unfurl_media": False, "parse": "none"}
        if item.get("thread_ts"):
            payload["thread_ts"] = item["thread_ts"]
        self.equipment._slack_route_preverified = DEMO_CHANNEL_ID
        try:
            sent = self.equipment.slack("chat.postMessage", payload)
        except Exception as exc:
            failure = self._provider_failure(exc, operation_id=item["operation_id"], phase="send")
            uncertain = bool(getattr(exc, "uncertain", True))
            failure.update(uncertain=uncertain, delivered=None if uncertain else False,
                           code=getattr(exc, "code", type(exc).__name__))
            self._save(item["operation_id"], digest, "reconcile_required" if uncertain else "rejected",
                       metadata={**item, "provider_failure": failure})
            return failure
        if sent.get("ok") is not True:
            failure = self._provider_failure(sent, operation_id=item["operation_id"], phase="send")
            uncertain = sent.get("uncertain") is True
            failure.update(delivered=None if uncertain else False, uncertain=uncertain,
                           provider_error=sent.get("error"))
            self._save(item["operation_id"], digest, "reconcile_required" if uncertain else "rejected",
                       metadata={**item, "provider_failure": failure})
            return failure
        item["message_ts"] = sent.get("ts")
        self._save(item["operation_id"], digest, "reconcile_required", metadata=item)
        return self.status({"operation_id": item["operation_id"]})


    # Compatibility for the unchanged shared-equipment service; the concrete
    # external action remains `post`, which is the route's actual behavior.
    submit = post


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "post", "status"))
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args(argv)
    route = ExternalDemoMessages(journal_path=args.journal)
    try:
        result = route.inspect() if args.action == "inspect" else (
            route.post(json.load(sys.stdin)) if args.action == "post" else route.status(json.load(sys.stdin)))
    except Exception as exc:
        result = {"ok": False, "state": "FAILED", "code": getattr(exc, "code", type(exc).__name__),
                  "message": redacted(str(exc)), "uncertain": bool(getattr(exc, "uncertain", False))}
    finally:
        route.close()
    print(json.dumps(redacted(result), ensure_ascii=False))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
