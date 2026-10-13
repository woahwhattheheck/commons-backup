"""Private Slack request/return carrier attached to the existing tool gateway.

Any equipped workspace harness can use the same catalog. No public MCP route
is added, and Slack credentials remain in the existing local service adapter.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path

from .outcomes import effect_uncertain, tool_failed
from .provider_io import EquipmentError, redacted

OPEN = "<commons_equipment_request>"
CLOSE = "</commons_equipment_request>"
RECEIPT_OPEN = "<commons_equipment_receipt>"
RECEIPT_CLOSE = "</commons_equipment_receipt>"
_EXTERNAL_DEMO_POST = "slack_post_external_demo_message"
_EXTERNAL_DEMO_STATUS = "slack_external_demo_message_status"


def slack_timestamp(value) -> str:
    """Slack accepts microsecond precision; extra digits silently miss replies.

    Preserve received timestamps exactly and truncate any higher precision
    startup clock value instead of floating-point rounding a stored cursor up.
    """
    whole, _, fraction = str(value).partition(".")
    return whole + "." + fraction[:6].ljust(6, "0")


def parse_request(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("&lt;commons_equipment_request&gt;"):
        # Slack's Claude connector escapes its text fallback while rendering
        # literal brackets in rich_text. Decode exactly one transport layer;
        # ampersand last preserves an original literal '&lt;' in an argument.
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    if not text.startswith(OPEN):
        return None
    # A closing tag inside a JSON string is payload, not the envelope end.
    # Decode the value first so source-code and template handoffs stay intact.
    body = text[len(OPEN):].lstrip()
    value, end = json.JSONDecoder().raw_decode(body)
    if not body[end:].lstrip().startswith(CLOSE):
        raise ValueError("equipment request envelope is incomplete")
    if not isinstance(value, dict):
        raise ValueError("equipment request must be an object")
    for key in ("request_id", "call_id", "name"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(key + " must be a nonempty string")
    if not isinstance(value.get("arguments", {}), dict):
        raise ValueError("arguments must be an object")
    return value


def encode_request(request: dict) -> str:
    """Preserve JSON string values through Slack's Markdown text conversion.

    Standard JSON escapes protect source, prose, whitespace, and Unicode.
    The existing parser restores every value before dispatch and publication.
    """
    serialized = json.dumps(request, ensure_ascii=True, allow_nan=False)
    parse_request(OPEN + serialized + CLOSE)

    def quote_string(match):
        value = json.loads(match.group(0))
        escaped = []
        for character in value:
            codepoint = ord(character)
            if character.isascii() and character.isalnum():
                escaped.append(character)
            elif codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                # Let the standard encoder retain the UTF-16 surrogate pair.
                escaped.append(json.dumps(character, ensure_ascii=True)[1:-1])
        return '"' + "".join(escaped) + '"'

    encoded = re.sub(r'"(?:\\.|[^"\\])*"', quote_string, serialized)
    return f"{OPEN}\n{encoded}\n{CLOSE}"


def terminal_delivery_rejection(delivery: dict) -> bool:
    """Recognize only a recorded, definitive pre-transport policy rejection."""
    return (
        isinstance(delivery, dict)
        and delivery.get("isError") is True
        and delivery.get("uncertain") is False
        and not effect_uncertain(delivery)
        and delivery.get("error") == "PublicationPolicyViolation"
        and delivery.get("code") in {
            "commons_publication_terms",
            "outbound_identity_attribution",
        }
    )


def _catalog_json(value) -> str:
    """Lossless JSON that legacy per-part ``strip()`` consumers cannot corrupt.

    Catalog replies are split into bounded Slack messages. Older consumers strip
    each part before joining it, so a literal whitespace character on a chunk
    boundary would be deleted. Compact JSON plus ASCII escaping leaves no
    literal whitespace in the transport while ``json.loads`` restores the exact
    schema text, including spaces, Unicode, embedded fences, and tags.
    """
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":"))
            .replace(" ", "\\u0020").replace("`", "\\u0060").replace("<", "\\u003c"))


def _external_demo_operation_id(request: dict) -> str | None:
    if request.get("name") not in {_EXTERNAL_DEMO_POST, _EXTERNAL_DEMO_STATUS}:
        return None
    arguments = request.get("arguments")
    operation_id = arguments.get("operation_id") if isinstance(arguments, dict) else None
    return operation_id if isinstance(operation_id, str) and operation_id.strip() else None


def _result_payload(result: dict) -> dict:
    if not isinstance(result, dict):
        return {}
    nested = result.get("result")
    return nested if isinstance(nested, dict) else result


def _equipment_receipt(request: dict, state: str, result: dict | None = None) -> dict | None:
    """Return a payload-free internal receipt for the external-demo road."""
    operation_id = _external_demo_operation_id(request)
    if operation_id is None:
        return None
    receipt = {
        "request_id": request["request_id"],
        "operation_id": operation_id,
        "state": state,
    }
    if state == "ACCEPTED":
        return receipt

    payload = _result_payload(result or {})
    provider_receipt = payload.get("receipt") if isinstance(payload.get("receipt"), dict) else {}
    if state == "DELIVERED":
        channel_id = provider_receipt.get("channel_id") or payload.get("channel_id")
        message_ts = provider_receipt.get("message_ts") or payload.get("message_ts")
        if channel_id is not None:
            receipt["channel_id"] = channel_id
        if message_ts is not None:
            receipt["message_ts"] = message_ts
        return receipt

    if state == "DUPLICATE":
        safe_keys = (
            "operation_id", "payload_sha256", "channel_id", "message_ts",
            "sender_user_id", "sender_verified", "body_verified",
            "provider_footer_present", "readback_state", "message_permalink",
        )
        receipt["original_receipt"] = {
            key: provider_receipt[key] for key in safe_keys if provider_receipt.get(key) is not None
        }
        return receipt

    code = payload.get("code") or payload.get("state")
    if not code and isinstance(result, dict):
        code = result.get("code") or result.get("error")
    receipt["code"] = str(code or "operation_failed")
    if effect_uncertain(result or {}):
        receipt["uncertain"] = True
    return receipt


def _terminal_equipment_receipt(request: dict, result: dict) -> dict | None:
    if _external_demo_operation_id(request) is None:
        return None
    payload = _result_payload(result)
    if (not tool_failed(result) and not effect_uncertain(result)
            and payload.get("state") == "DELIVERED"):
        state = "DUPLICATE" if (
            request.get("name") == _EXTERNAL_DEMO_POST and payload.get("replayed") is True
        ) else "DELIVERED"
    else:
        state = "FAILED"
    return _equipment_receipt(request, state, result)


class SlackEquipmentCarrier:
    def __init__(self, catalog, calls, route: dict, cursor_path: Path):
        self.catalog = catalog
        self.calls = calls
        self.channel = route["channel_id"]
        self.thread_ts = route.get("thread_ts")
        self.interval = max(5, float(route.get("poll_seconds", 15)))
        self.path = cursor_path
        self.cursor = slack_timestamp(time.time())
        if self.path.is_file():
            self.cursor = json.loads(self.path.read_text(encoding="utf-8")).get("cursor", self.cursor)
        self.cursor = slack_timestamp(self.cursor)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.run, daemon=True, name="shared-equipment-slack-carrier")
        self.status = {"ok": True, "phase": "configured", "channel_id": self.channel,
            "thread_ts": self.thread_ts, "cursor": self.cursor}
        if not self.path.is_file():
            self._save(self.cursor)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=35)

    def _save(self, cursor):
        cursor = slack_timestamp(cursor)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"cursor": cursor, "channel_id": self.channel, "thread_ts": self.thread_ts}), encoding="utf-8")
        temp.replace(self.path)
        self.cursor = cursor

    def _post_receipt(self, request: dict, message: dict, receipt: dict | None, phase: str):
        if receipt is None:
            return None
        text = RECEIPT_OPEN + json.dumps(redacted(receipt), ensure_ascii=False, separators=(",", ":")) + RECEIPT_CLOSE
        return self.calls.execute_journaled(
            "equipment-receipt:" + request["request_id"] + ":" + receipt["operation_id"],
            request["call_id"] + ":" + phase,
            "slack_post_message",
            {
                "channel_id": self.channel,
                "thread_ts": message.get("thread_ts") or message["ts"],
                "text": text,
            },
            self.catalog.services.call,
        )

    def process(self, message):
        try:
            request = parse_request(message.get("text", ""))
        except (ValueError, TypeError) as exc:
            # Malformed transport input must not strand later valid requests.
            self.catalog.services.call("slack_post_message", {"channel_id": self.channel,
                "thread_ts": message.get("thread_ts") or message["ts"],
                "text": "Equipment request parse error: " + str(exc)})
            return
        if request is None:
            return
        rid, cid = request["request_id"], request["call_id"]
        if request["name"] == _EXTERNAL_DEMO_POST:
            # Receipt delivery is journaled independently from the outward
            # effect. A failed/uncertain ACK never causes an external replay.
            self._post_receipt(request, message, _equipment_receipt(request, "ACCEPTED"), "accepted")
        if request["name"] == "equipment_catalog":
            runner = lambda _name, _args: {"tools": self.catalog.tools()}
        else:
            # Capability manifests are ordinary catalog operations here.
            # Avoid importing the high-level services module into the carrier:
            # that widened this transport's runtime closure unnecessarily.
            runner = self.catalog.call
        result = self.calls.execute_journaled("equipment:" + rid, cid,
            request["name"], request.get("arguments", {}), runner)
        terminal_receipt = _terminal_equipment_receipt(request, result)
        if terminal_receipt is not None:
            self._post_receipt(request, message, terminal_receipt, "terminal")
        metadata_reply = (
            not tool_failed(result) and not effect_uncertain(result)
            and isinstance(result, dict)
            and ((request["name"] == "equipment_catalog" and isinstance(result.get("tools"), list))
                 or (request["name"] == "equipment_capability_manifest"
                     and result.get("schema") == "commons.shared_equipment.capability_manifest.v1"
                     and isinstance(result.get("operations"), list)))
        )
        encode = _catalog_json if metadata_reply else lambda value: json.dumps(value, ensure_ascii=False)
        response = encode(redacted({"request_id": rid, "call_id": cid, "result": result}))
        # Slack text has a finite message size. Multiple parts preserve the full
        # JSON; consumers join content between the per-part wrappers in order.
        parts = [response[i:i + 28000] for i in range(0, len(response), 28000)]
        digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
        for index, part in enumerate(parts, start=1):
            text = (f"<commons_equipment_result request_id={encode(rid)} call_id={encode(cid)} "
                f"part=\"{index}/{len(parts)}\" sha256=\"{digest}\">\n{part}\n</commons_equipment_result>")
            if metadata_reply:
                # Catalogs are source schemas, not assertions about an operation.
                # The code fence is OUTSIDE the unchanged result envelope, so
                # existing consumers still join JSON between the original tags.
                # Ordinary results and catalog errors keep their original path.
                text = "```\n" + text + "\n```"
            delivery = self.calls.execute_journaled("equipment-return:" + rid,
                cid + ":" + message["ts"] + ":" + str(index), "slack_post_message",
                {"channel_id": self.channel, "thread_ts": message.get("thread_ts") or message["ts"], "text": text},
                self.catalog.services.call)
            if tool_failed(delivery) or effect_uncertain(delivery):
                if terminal_delivery_rejection(delivery):
                    # Retain the journaled rejection and omit remaining parts.
                    # This is a terminal delivery outcome, never a sent receipt.
                    return {"request_id": rid, "call_id": cid,
                        "code": delivery["code"], "part": index,
                        "parts": len(parts), "delivered_parts": index - 1}
                raise RuntimeError("equipment result delivery failed; inspect journal before retry")

    def once(self):
        args = {"channel": self.channel, "oldest": slack_timestamp(self.cursor), "limit": 100}
        method = "conversations.history"
        if self.thread_ts:
            method = "conversations.replies"
            args["ts"] = self.thread_ts
        messages = []
        while True:
            page = self.catalog.services.slack(method, args)
            if not page.get("ok"):
                raise EquipmentError("Slack carrier read failed: " + str(page.get("error", "unknown")),
                    code=page.get("error", "unknown"), http_status=page.get("status"),
                    retry_after=page.get("retry_after"))
            messages.extend(m for m in page.get("messages", []) if float(m["ts"]) > float(self.cursor))
            cursor = page.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
            args["cursor"] = cursor
        terminal_failures = 0
        last_terminal_failure = None
        for message in sorted(messages, key=lambda m: float(m["ts"])):
            terminal_failure = self.process(message)
            if terminal_failure is not None:
                terminal_failures += 1
                last_terminal_failure = terminal_failure
            # The cursor records a handled request, not successful delivery.
            # Definitive rejected replies remain in the existing tool journal.
            self._save(message["ts"])
        return {"terminal_delivery_failures": terminal_failures,
            "last_terminal_delivery_failure": last_terminal_failure}

    def run(self):
        while not self._stop.is_set():
            delay = self.interval
            try:
                delivery_status = self.once()
                self.status = {"ok": True, "phase": "polling", "channel_id": self.channel,
                    "thread_ts": self.thread_ts, "cursor": self.cursor, "time": time.time(),
                    **delivery_status}
            except Exception as exc:
                self.status = {"ok": False, "phase": "error", "error": type(exc).__name__,
                    "message": redacted(str(exc)), "cursor": self.cursor, "time": time.time()}
                if isinstance(exc, EquipmentError):
                    self.status.update(http_status=exc.http_status, retry_after=redacted(exc.retry_after))
                    if exc.http_status == 429:
                        try:
                            retry_after = float(exc.retry_after)
                        except (TypeError, ValueError):
                            retry_after = 0
                        if math.isfinite(retry_after):
                            delay = max(delay, retry_after)
                        self.status["poll_delay_seconds"] = delay
            # One redacted diagnostic snapshot; no source message/secret log.
            diagnostic = self.path.with_name("equipment_slack_status.json")
            diagnostic.write_text(json.dumps(self.status), encoding="utf-8")
            # Preserve the provider delay while keeping shutdown interruptible.
            deadline = time.monotonic() + delay
            while not self._stop.wait(min(delay, threading.TIMEOUT_MAX)):
                delay = deadline - time.monotonic()
                if delay <= 0:
                    break
