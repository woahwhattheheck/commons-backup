"""Internal Slack patch handoffs through the existing shared equipment account."""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
import sqlite3
import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

TEAM_ID = "T0BRETUB5TK"
SENDER_USER_ID = "U0BTGV2G589"
SENDER_BOT_ID = "B0BTD42EMFY"
DEFAULT_CHANNEL_ID = "C0BU51F1PL3"
DEFAULT_THREAD_TS = "1790851459.659859"
MAX_PATCH_BYTES = 10 * 1024 * 1024
_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_FOOTER = re.compile(r"(?im)^\s*(?:\*?sent using\*?|\*?powered by\*?)\b")


class WorkHandoff:
    """Uploads one exact patch and verifies the actual internal Slack result."""

    def __init__(self, equipment, *, journal_path: Path | None = None):
        self.equipment = equipment
        self.path = journal_path or (Path.home() / ".commons" / "shared_equipment" / "team_workhandoff.sqlite3")
        self._lock = threading.RLock()
        self._db: sqlite3.Connection | None = None
        self._auth_ok = False
        self._auth_checked_at = 0.0

    def _connection(self, *, create: bool) -> sqlite3.Connection | None:
        if self._db is not None:
            return self._db
        if not create and not self.path.is_file():
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS handoffs(
                    operation_id TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    receipt_json TEXT,
                    metadata_json TEXT,
                    updated_at REAL NOT NULL
                )
            """)
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(handoffs)")}
            if "metadata_json" not in columns:
                self._db.execute("ALTER TABLE handoffs ADD COLUMN metadata_json TEXT")
        return self._db

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    @staticmethod
    def normalize(args: dict[str, Any]) -> dict[str, Any]:
        allowed = {"operation_id", "work_id", "objective", "summary", "patch", "tests", "result", "channel_id", "thread_ts"}
        if not isinstance(args, dict) or set(args) - allowed:
            raise ValueError("handoff contains unknown fields")
        op = args.get("operation_id")
        if not isinstance(op, str) or not _OPERATION_ID.fullmatch(op):
            raise ValueError("operation_id must be a stable 8-128 character ID")
        values = {}
        for key in ("work_id", "objective", "summary", "tests", "result"):
            value = args.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(key + " must be non-empty text")
            values[key] = value.strip()
        patch = args.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            raise ValueError("patch must be non-empty UTF-8 text")
        patch_bytes = patch.encode("utf-8")
        if len(patch_bytes) > MAX_PATCH_BYTES:
            raise ValueError("patch exceeds the supported 10 MiB Slack file limit")
        channel = args.get("channel_id", DEFAULT_CHANNEL_ID)
        thread = args.get("thread_ts", DEFAULT_THREAD_TS)
        if not isinstance(channel, str) or not re.fullmatch(r"[CG][A-Z0-9]{8,31}", channel):
            raise ValueError("channel_id must be a Slack workspace channel")
        if not isinstance(thread, str) or not re.fullmatch(r"[0-9]{10}\.[0-9]{6}", thread):
            raise ValueError("thread_ts must be a Slack message timestamp")
        return {"operation_id": op, **values, "patch": patch,
                "channel_id": channel, "thread_ts": thread}

    @staticmethod
    def payload_hash(item: dict[str, Any]) -> str:
        raw = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _provider_failure(failure, *, operation_id=None, phase=None) -> dict[str, Any]:
        """Retain retry evidence without changing the existing recovery action."""
        read = failure.get if isinstance(failure, dict) else lambda key, default=None: getattr(failure, key, default)
        status = read("http_status") or read("status")
        code = read("code") or read("error")
        limited = status == 429 or code in ("ratelimited", "slack_rate_limited")
        result = {"ok": False, "state": "RATE_LIMITED" if limited else "RECONCILE_REQUIRED"}
        if operation_id is not None:
            result["operation_id"] = operation_id
        if phase is not None:
            result["phase"] = phase
        if status is not None:
            result["http_status"] = status
        if isinstance(read("uncertain"), bool):
            result["uncertain"] = read("uncertain")
        retry_after = read("retry_after")
        if retry_after is not None:
            result["retry_after"] = retry_after
        if limited:
            result["code"] = "slack_rate_limited"
            if retry_after is not None and not isinstance(retry_after, bool):
                now = time.time()
                try:
                    seconds = float(retry_after)
                    deadline = now + seconds if math.isfinite(seconds) and seconds >= 0 else None
                except (ValueError, TypeError, OverflowError):
                    try:
                        deadline = parsedate_to_datetime(str(retry_after)).timestamp()
                    except (ValueError, TypeError, OverflowError):
                        deadline = None
                if deadline is not None and math.isfinite(deadline):
                    result["retry_not_before"] = max(now, deadline)
        return result

    def _record_failure(self, item, digest, failure, metadata=None):
        """Keep prior receipts and partial handles available for reconciliation."""
        prior = self._journal(item["operation_id"])
        details = {**((prior or {}).get("metadata") or {}), **(metadata or {})}
        previous_failure = details.get("provider_failure")
        if (failure.get("phase") == "readback" and isinstance(previous_failure, dict)
                and previous_failure.get("uncertain") is True):
            failure["uncertain"] = True
        if prior and prior.get("receipt"):
            failure["receipt"] = prior["receipt"]
        details["provider_failure"] = failure
        state = "delivered" if prior and prior["state"] == "delivered" else "reconcile_required"
        self._save(item["operation_id"], digest, state, metadata=details)
        return failure

    def _readback_failure(self, failure, item, digest, *, file_id=None, message_ts=None):
        result = self._provider_failure(failure, operation_id=item["operation_id"], phase="readback")
        if result.get("code") != "slack_rate_limited":
            return None
        # A refused read says nothing new about an earlier unknown write.
        result.pop("uncertain", None)
        result.update(readback_state="rate_limited", channel_id=item["channel_id"], thread_ts=item["thread_ts"])
        if file_id is not None:
            result["file_id"] = file_id
        if message_ts is not None:
            result["message_ts"] = message_ts
        return self._record_failure(item, digest, result)

    def _transfer_failure(self, failure, item, digest, metadata, *, phase, file_id=None):
        result = self._provider_failure(failure, operation_id=item["operation_id"], phase=phase)
        if file_id is not None:
            result["file_id"] = file_id
        return self._record_failure(item, digest, result, metadata)

    def sender_verified(self) -> bool:
        if self._auth_checked_at and time.monotonic() - self._auth_checked_at < 60:
            return self._auth_ok
        try:
            auth = self._slack_read("auth.test", {})
            self._auth_ok = (auth.get("ok") is True and auth.get("team_id") == TEAM_ID
                             and auth.get("user_id") == SENDER_USER_ID and auth.get("bot_id") == SENDER_BOT_ID)
        except Exception:
            self._auth_ok = False
        self._auth_checked_at = time.monotonic()
        return self._auth_ok

    def _channel_info_result(self, channel_id: str) -> dict[str, Any]:
        try:
            result = self._slack_read("conversations.info", {"channel": channel_id})
        except Exception:
            return {}
        return result if isinstance(result, dict) else {}

    def _channel_info(self, channel_id: str) -> dict[str, Any] | None:
        channel = self._channel_info_result(channel_id).get("channel")
        if not isinstance(channel, dict):
            return None
        return channel if self._channel_internal(channel) else None

    @staticmethod
    def _channel_internal(channel: dict[str, Any]) -> bool:
        shared = channel.get("shared_team_ids")
        return (channel.get("context_team_id") == TEAM_ID and shared == [TEAM_ID]
                and channel.get("is_shared") is False and channel.get("is_ext_shared") is False
                and channel.get("is_org_shared") is False and channel.get("is_pending_ext_shared") is False
                and channel.get("pending_connected_team_ids") == [] and channel.get("is_archived") is False)

    def _channel_member_verified(self, channel_id: str) -> bool:
        # conversations.info needs a channel-read scope no installed token
        # holds on private channels (Slack reports needed groups:read). The
        # installed sender's existing groups:history read road answers ok
        # only when the channel exists and the fixed sender is a member,
        # which is the destination check the posting call relies on.
        try:
            result = self._slack_read("conversations.history", {"channel": channel_id, "limit": 1})
        except Exception:
            return False
        return result.get("ok") is True

    def _destination_verified(self, channel_id: str) -> bool:
        channel = self._channel_info_result(channel_id).get("channel")
        if isinstance(channel, dict):
            # A provider-answered channel is judged on its sharing flags
            # only; a failed internal check never falls back to membership.
            return self._channel_internal(channel)
        return self._channel_member_verified(channel_id)

    def _slack_read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Force provider readback past local observation caches when supported."""
        slack = self.equipment.slack
        try:
            accepts_fresh = "fresh" in inspect.signature(slack).parameters
        except (TypeError, ValueError):
            accepts_fresh = False
        return slack(method, payload, **({"fresh": True} if accepts_fresh else {}))

    def write_route_verified(self) -> bool:
        return self.sender_verified()

    def validate_destination(self, channel_id: str) -> bool:
        verifier = getattr(self.equipment, "_slack_write_route_verified", None)
        production = getattr(type(self.equipment), "_slack_write_route_verified", None)
        replaced = getattr(verifier, "__func__", None) is not getattr(production, "__func__", production)
        if replaced:
            ok = bool(verifier(channel_id))
        else:
            ok = self.sender_verified() and self._destination_verified(channel_id)
        if ok:
            self.equipment._slack_route_preverified = channel_id
        return ok

    @staticmethod
    def _message(item: dict[str, Any]) -> str:
        return "\n".join((
            f"Work handoff `{item['work_id']}` · operation `{item['operation_id']}`",
            f"Objective: {item['objective']}",
            f"Summary: {item['summary']}",
            f"Patch artifact: handoff-{item['operation_id']}.patch (attached in this thread)",
            f"Tests and results: {item['tests']}",
            f"Result: {item['result']}",
            f"Operation marker: `{item['operation_id']}`",
        ))

    def _thread_messages(self, channel_id: str, thread_ts: str) -> list[dict[str, Any]]:
        cursor = None
        messages: list[dict[str, Any]] = []
        for _ in range(20):
            args = {"channel": channel_id, "ts": thread_ts, "limit": 100}
            if cursor:
                args["cursor"] = cursor
            response = self._slack_read("conversations.replies", args)
            if response.get("ok") is not True:
                return []
            messages.extend(m for m in response.get("messages", []) if isinstance(m, dict))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                return messages
        return []

    def _verify(self, item: dict[str, Any], payload_sha256: str) -> dict[str, Any] | None:
        expected = self._message(item)
        messages = self._thread_messages(item["channel_id"], item["thread_ts"])
        hits = [m for m in messages if item["operation_id"] in str(m.get("text") or "")]
        if len(hits) != 1:
            return None
        message = hits[0]
        actual_text = str(message.get("text") or "")
        body_verified = actual_text.startswith(expected)
        suffix = actual_text[len(expected):].strip() if body_verified else ""
        footer_present = bool(suffix)
        sender_verified = message.get("user") == SENDER_USER_ID
        files = message.get("files") if isinstance(message.get("files"), list) else []
        candidates = [f for f in files if isinstance(f, dict) and f.get("name") == f"handoff-{item['operation_id']}.patch"]
        if len(candidates) != 1:
            return None
        file_id = candidates[0].get("id")
        if not isinstance(file_id, str) or not file_id:
            return None
        info_result = self._slack_read("files.info", {"file": file_id})
        file_info = info_result.get("file") if info_result.get("ok") is True else None
        if not isinstance(file_info, dict) or file_info.get("user") != SENDER_USER_ID:
            return self._readback_failure(info_result, item, payload_sha256,
                                          file_id=file_id, message_ts=message.get("ts"))
        try:
            file_bytes = self.equipment.slack_download_file(file_info, max_bytes=MAX_PATCH_BYTES)
        except Exception as exc:
            return self._readback_failure(exc, item, payload_sha256,
                                          file_id=file_id, message_ts=message.get("ts"))
        expected_patch_sha256 = item.get("patch_sha256")
        if isinstance(item.get("patch"), str):
            expected_patch_sha256 = hashlib.sha256(item["patch"].encode("utf-8")).hexdigest()
        patch_verified = (isinstance(expected_patch_sha256, str)
                          and hashlib.sha256(file_bytes).hexdigest() == expected_patch_sha256)
        receipt = {
            "operation_id": item["operation_id"],
            "payload_sha256": payload_sha256,
            "channel_id": item["channel_id"],
            "thread_ts": item["thread_ts"],
            "file_id": file_id,
            "file_link": file_info.get("permalink"),
            "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "message_ts": message.get("ts"),
            "message_permalink": None,
            "sender_user_id": message.get("user"),
            "sender_verified": sender_verified,
            "body_verified": body_verified,
            "provider_footer_present": footer_present,
            "provider_footer_kind": "sent_using" if _FOOTER.search(suffix) else "other_suffix" if suffix else None,
            "provider_footer_sha256": hashlib.sha256(suffix.encode("utf-8")).hexdigest() if suffix else None,
            "patch_verified": patch_verified,
            "readback_state": "confirmed" if sender_verified and body_verified and patch_verified else "mismatch",
        }
        try:
            link = self._slack_read("chat.getPermalink", {"channel": item["channel_id"], "message_ts": message.get("ts")})
            receipt["message_permalink"] = link.get("permalink") if link.get("ok") else None
        except Exception:
            pass
        return receipt

    def _journal(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            db = self._connection(create=False)
            row = db.execute("SELECT * FROM handoffs WHERE operation_id=?", (operation_id,)).fetchone() if db else None
        if not row:
            return None
        receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else None
        return {"payload_sha256": row["payload_sha256"], "state": row["state"],
                "receipt": receipt, "metadata": metadata}

    def _save(self, operation_id: str, payload_sha256: str, state: str,
              receipt: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> None:
        encoded = json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) if receipt is not None else None
        meta = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) if metadata is not None else None
        with self._lock:
            db = self._connection(create=True)
            with db:
                db.execute("INSERT INTO handoffs(operation_id,payload_sha256,state,receipt_json,metadata_json,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(operation_id) DO UPDATE SET state=excluded.state, receipt_json=COALESCE(excluded.receipt_json,handoffs.receipt_json), metadata_json=COALESCE(excluded.metadata_json,handoffs.metadata_json), updated_at=excluded.updated_at",
                             (operation_id, payload_sha256, state, encoded, meta, time.time()))

    def _claim(self, operation_id: str, payload_sha256: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
        meta = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            db = self._connection(create=True)
            with db:
                row = db.execute("SELECT * FROM handoffs WHERE operation_id=?", (operation_id,)).fetchone()
                if row:
                    receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
                    existing_meta = json.loads(row["metadata_json"]) if row["metadata_json"] else None
                    return {"payload_sha256": row["payload_sha256"], "state": row["state"],
                            "receipt": receipt, "metadata": existing_meta}
                db.execute("INSERT INTO handoffs(operation_id,payload_sha256,state,receipt_json,metadata_json,updated_at) VALUES(?,?,?,?,?,?)",
                           (operation_id, payload_sha256, "uploading", None, meta, time.time()))
        return None

    def status(self, args: dict[str, Any]) -> dict[str, Any]:
        operation_id = args.get("operation_id") if isinstance(args, dict) else None
        if not isinstance(operation_id, str) or not _OPERATION_ID.fullmatch(operation_id):
            return {"ok": False, "state": "DENIED", "code": "invalid_operation_id"}
        prior = self._journal(operation_id)
        if not prior:
            return {"ok": True, "state": "NOT_FOUND", "operation_id": operation_id}
        metadata = prior.get("metadata") or {}
        item = {"operation_id": operation_id, **metadata,
                "channel_id": args.get("channel_id", metadata.get("channel_id", DEFAULT_CHANNEL_ID)),
                "thread_ts": args.get("thread_ts", metadata.get("thread_ts", DEFAULT_THREAD_TS))}
        if not self.sender_verified() or not self._destination_verified(item["channel_id"]):
            return {"ok": False, "state": "PUBLISHER_ROUTE_REQUIRED", "operation_id": operation_id}
        receipt = self._verify(item, prior["payload_sha256"])
        if receipt and receipt["readback_state"] == "confirmed":
            self._save(operation_id, prior["payload_sha256"], "delivered", receipt, metadata)
            return {"ok": True, "state": "DELIVERED", "receipt": receipt, "reconciled": True}
        if receipt and receipt.get("state") == "RATE_LIMITED":
            return receipt
        return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": operation_id,
                "payload_sha256": prior["payload_sha256"], "readback_available": True}

    def submit(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            item = self.normalize(args)
        except (ValueError, TypeError) as exc:
            return {"ok": False, "state": "DENIED", "code": "invalid_handoff", "message": str(exc)}
        digest = self.payload_hash(item)
        prior = self._journal(item["operation_id"])
        if prior:
            if prior["payload_sha256"] != digest:
                return {"ok": False, "state": "IDEMPOTENCY_CONFLICT", "operation_id": item["operation_id"]}
            if prior["state"] == "delivered" and prior.get("receipt"):
                return {"ok": True, "state": "DELIVERED", "receipt": prior["receipt"], "replayed": True}
            reconciled = self._verify(item, digest)
            if reconciled and reconciled["readback_state"] == "confirmed":
                self._save(item["operation_id"], digest, "delivered", reconciled)
                return {"ok": True, "state": "DELIVERED", "receipt": reconciled, "reconciled": True}
            if reconciled and reconciled.get("state") == "RATE_LIMITED":
                return reconciled
            return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": item["operation_id"]}
        if not self.sender_verified():
            return {"ok": False, "state": "OUTBOUND_ROUTE_BLOCKED", "code": "slack_sender_identity_unverified"}
        if not self._destination_verified(item["channel_id"]):
            return {"ok": False, "state": "PUBLISHER_ROUTE_REQUIRED", "operation_id": item["operation_id"],
                    "code": "internal_channel_unavailable_or_external"}
        metadata = {key: value for key, value in item.items() if key != "patch"}
        metadata["patch_sha256"] = hashlib.sha256(item["patch"].encode("utf-8")).hexdigest()
        concurrent = self._claim(item["operation_id"], digest, metadata)
        if concurrent:
            if concurrent["payload_sha256"] != digest:
                return {"ok": False, "state": "IDEMPOTENCY_CONFLICT", "operation_id": item["operation_id"]}
            reconciled = self._verify(item, digest)
            if reconciled and reconciled["readback_state"] == "confirmed":
                self._save(item["operation_id"], digest, "delivered", reconciled, metadata)
                return {"ok": True, "state": "DELIVERED", "receipt": reconciled, "reconciled": True}
            if reconciled and reconciled.get("state") == "RATE_LIMITED":
                return reconciled
            return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": item["operation_id"]}
        filename = f"handoff-{item['operation_id']}.patch"
        patch_bytes = item["patch"].encode("utf-8")
        body = self._message(item)
        if len(body) > 4500:
            self._save(item["operation_id"], digest, "denied", metadata=metadata)
            return {"ok": False, "state": "DENIED", "operation_id": item["operation_id"], "code": "handoff_comment_too_long"}
        phase, file_id = "upload_url", None
        try:
            upload = self.equipment._slack_upload_url(filename, len(patch_bytes))
            if upload.get("ok") is not True:
                return self._transfer_failure(upload, item, digest, metadata, phase=phase)
            file_id = upload.get("file_id")
            url = upload.get("upload_url")
            if not isinstance(file_id, str) or not isinstance(url, str):
                self._save(item["operation_id"], digest, "reconcile_required", metadata=metadata)
                return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": item["operation_id"]}
            phase = "file_upload"
            raw_upload = self.equipment.slack_upload_bytes(url, patch_bytes)
            if raw_upload.get("ok") is not True:
                return self._transfer_failure(raw_upload, item, digest, metadata, phase=phase, file_id=file_id)
            phase = "completion"
            complete = self.equipment.slack("files.completeUploadExternal", {
                "files": [{"id": file_id, "title": filename}],
                "channel_id": item["channel_id"], "thread_ts": item["thread_ts"], "initial_comment": body,
            })
            if complete.get("ok") is not True:
                return self._transfer_failure(complete, item, digest, metadata, phase=phase, file_id=file_id)
        except Exception as exc:
            return self._transfer_failure(exc, item, digest, metadata, phase=phase, file_id=file_id)
        receipt = self._verify(item, digest)
        if receipt and receipt.get("state") == "RATE_LIMITED":
            return receipt
        if not receipt or receipt["readback_state"] != "confirmed":
            self._save(item["operation_id"], digest, "reconcile_required", receipt, metadata)
            return {"ok": False, "state": "RECONCILE_REQUIRED", "operation_id": item["operation_id"],
                    "receipt": receipt}
        self._save(item["operation_id"], digest, "delivered", receipt, metadata)
        return {"ok": True, "state": "DELIVERED", "receipt": receipt}

    def read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        file_id = args.get("file_id") if isinstance(args, dict) else None
        if not isinstance(file_id, str) or not re.fullmatch(r"F[A-Z0-9]{8,31}", file_id):
            return {"ok": False, "error": "invalid_file_id"}
        if not self.sender_verified():
            return {"ok": False, "error": "slack_sender_identity_unverified"}
        info_result = self._slack_read("files.info", {"file": file_id})
        info = info_result.get("file") if info_result.get("ok") else None
        if not isinstance(info, dict) or info.get("user") != SENDER_USER_ID:
            failure = self._provider_failure(info_result, phase="file_info")
            if failure.get("code") == "slack_rate_limited":
                return {**failure, "file_id": file_id}
            return {"ok": False, "error": "file_unavailable"}
        try:
            content = self.equipment.slack_download_file(info, max_bytes=MAX_PATCH_BYTES)
            text = content.decode("utf-8")
        except Exception as exc:
            failure = self._provider_failure(exc, phase="file_read")
            if failure.get("code") == "slack_rate_limited":
                return {**failure, "file_id": file_id}
            return {"ok": False, "error": "file_readback_failed"}
        return {"ok": True, "file_id": file_id, "title": info.get("title"),
                "content": text, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
