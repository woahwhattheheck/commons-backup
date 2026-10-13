"""Write/read/reconcile using one caller-supplied Commons id."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import HEAD_PIN
from .envelope import (
    EnvelopeError,
    ID_RE,
    build_envelope,
    compare_page,
    lanes_from,
    parse_frontmatter,
    public_summary,
    redact,
    sha256_text,
)
from .lanes import Lanes
from .truth import GitTruth


class GatewayError(Exception):
    def __init__(self, code: str, message: str, state: str = "ERROR", **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.state = state
        self.details = details

    def payload(self) -> dict[str, Any]:
        return redact({
            "ok": False,
            "state": self.state,
            "code": self.code,
            "message": self.message,
            **self.details,
        })


class Gateway:
    def __init__(
        self,
        truth: GitTruth | None = None,
        lanes: Lanes | None = None,
        *,
        timeout: float = 90.0,
        poll_interval: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        outbox_dir: str | None = None,
    ):
        self.truth = truth or GitTruth()
        self.lanes = lanes or Lanes()
        self.timeout = max(0.0, timeout)
        self.poll_interval = max(0.01, poll_interval)
        self.clock = clock
        self.sleeper = sleeper
        self.outbox_dir = Path(outbox_dir or os.environ.get("COMMONS_OUTBOX_DIR") or "/tmp/independent-commons-outbox")

    def _record_outbox(self, payload: dict[str, Any], lane_rows: list[dict[str, Any]]) -> None:
        try:
            self.outbox_dir.mkdir(parents=True, exist_ok=True)
            path = self.outbox_dir / ("%s.json" % payload["id"])
            path.write_text(json.dumps({
                "id": payload["id"],
                "envelope": public_summary(payload),
                "body": payload.get("body"),
                "full": payload,
                "lanes": lane_rows,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return

    def _read_outbox(self, ident: str) -> dict[str, Any] | None:
        path = self.outbox_dir / ("%s.json" % ident)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _await_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = self.clock()
        last_sha = ""
        delay = self.poll_interval
        while True:
            sha = self.truth.head_sha()
            last_sha = sha
            status, text = self.truth.read_at_sha("p/%s.md" % payload["id"], sha)
            if status == 200 and text:
                mismatch = compare_page(text, payload)
                urls = self.truth.public_urls(payload["id"], sha)
                if mismatch:
                    raise GatewayError(
                        "DUPLICATE_BODY_MISMATCH",
                        "this id already names a different durable envelope; the original stays",
                        state="QUARANTINED_CONFLICT",
                        id=payload["id"],
                        mismatched_fields=mismatch,
                        **urls,
                    )
                return {
                    "ok": True,
                    "state": "DURABLE_PAGE",
                    "id": payload["id"],
                    "body_sha256": sha256_text(payload["body"]),
                    "head_html": HEAD_PIN,
                    **urls,
                }
            elapsed = self.clock() - start
            if elapsed >= self.timeout:
                raise GatewayError(
                    "TIMEOUT_UNVERIFIED",
                    "carrier accepted the envelope but no exact durable page appeared before the deadline",
                    state="RECEIVED",
                    id=payload["id"],
                    last_checked_sha=last_sha,
                    verify_tool="verify_receipt",
                )
            self.sleeper(min(delay, max(0.01, self.timeout - elapsed)))
            delay = min(delay * 1.5, 15.0)

    def _dispatch_lanes(
        self,
        payload: dict[str, Any],
        wanted: list[str],
        *,
        thread_ts: str = "",
        slack_channel: str = "",
        discord_channel: str = "",
        discord_message_id: str = "",
    ) -> list[dict[str, Any]]:
        rows = []
        for name in wanted:
            if name == "ntfy":
                rows.append(self.lanes.ntfy_submit(payload))
            elif name == "github_issue":
                rows.append(self.lanes.github_issue_submit(payload))
            elif name == "slack":
                rows.append(self.lanes.slack_submit(payload, thread_ts=thread_ts, channel=slack_channel))
            elif name == "discord":
                rows.append(self.lanes.discord_submit(payload, channel=discord_channel, message_id=discord_message_id))
            elif name == "action_pad":
                rows.append(self.lanes.action_pad_alias(payload))
        for row in rows:
            if row.get("id") and row.get("id") != payload["id"]:
                raise GatewayError(
                    "ID_REMINTED",
                    "a lane tried to replace the caller-supplied Commons id",
                    state="ERROR",
                    id=payload["id"],
                    lane=row.get("lane"),
                    reminted=row.get("id"),
                )
        return rows

    def _combine(self, payload: dict[str, Any], lane_rows: list[dict[str, Any]], durable: dict[str, Any] | None, mail_error: GatewayError | None) -> dict[str, Any]:
        accepted = [row for row in lane_rows if row.get("state") in {"ACCEPTED", "ALIASED"}]
        failed = [row for row in lane_rows if row.get("state") == "ERROR"]
        skipped = [row for row in lane_rows if row.get("state") in {"UNCONFIGURED", "SKIPPED"}]
        if durable and (failed or skipped):
            state = "PARTIAL"
            ok = False
        elif durable:
            state = "DURABLE_PAGE"
            ok = True
        elif accepted and failed:
            state = "PARTIAL"
            ok = False
        elif accepted:
            state = "RECEIVED"
            ok = False
        elif failed and not accepted:
            state = "NOT_SENT"
            ok = False
        else:
            state = "NOT_SENT"
            ok = False
        result = {
            "ok": ok,
            "state": state,
            "id": payload["id"],
            "envelope": public_summary(payload),
            "lanes": lane_rows,
            "durable": durable,
            "accepted_lanes": [row["lane"] for row in accepted],
            "failed_lanes": [row["lane"] for row in failed],
            "skipped_lanes": [row["lane"] for row in skipped],
            "law": "A carrier 2xx is mail. Durable only after SHA-pinned public retrieval of the same id.",
        }
        if mail_error is not None:
            result["receipt"] = mail_error.payload()
        if not ok:
            result["ok"] = False
        return redact(result)

    def post(self, arguments: dict[str, Any], *, kind: str = "POST") -> dict[str, Any]:
        payload = build_envelope(arguments, kind=kind)
        wanted = lanes_from(arguments.get("lanes"))
        thread_ts = str(arguments.get("slack_thread_ts") or "")
        slack_channel = str(arguments.get("slack_channel") or "")
        discord_channel = str(arguments.get("discord_channel") or "")
        discord_message_id = str(arguments.get("discord_message_id") or "")
        try:
            sha = self.truth.head_sha()
            status, text = self.truth.read_at_sha("p/%s.md" % payload["id"], sha)
        except EnvelopeError as exc:
            raise GatewayError(exc.code, exc.message, state="UNVERIFIED", **exc.details) from exc
        if status == 200 and text:
            mismatch = compare_page(text, payload)
            urls = self.truth.public_urls(payload["id"], sha)
            if mismatch:
                raise GatewayError(
                    "DUPLICATE_BODY_MISMATCH",
                    "this id already names a different durable envelope; the original stays",
                    state="QUARANTINED_CONFLICT",
                    id=payload["id"],
                    mismatched_fields=mismatch,
                    **urls,
                )
            return redact({
                "ok": True,
                "state": "DURABLE_PAGE",
                "id": payload["id"],
                "existing": True,
                "envelope": public_summary(payload),
                "lanes": [],
                "durable": {"ok": True, "state": "DURABLE_PAGE", "id": payload["id"], **urls, "body_sha256": sha256_text(payload["body"])},
                "note": "same-id same-envelope retry; no carrier mail",
            })
        lane_rows = self._dispatch_lanes(
            payload,
            wanted,
            thread_ts=thread_ts,
            slack_channel=slack_channel,
            discord_channel=discord_channel,
            discord_message_id=discord_message_id,
        )
        self._record_outbox(payload, lane_rows)
        accepted = [row for row in lane_rows if row.get("state") == "ACCEPTED"]
        durable = None
        mail_error = None
        if any(row.get("lane") in {"ntfy", "github_issue"} and row.get("state") == "ACCEPTED" for row in lane_rows):
            try:
                durable = self._await_page(payload)
            except GatewayError as exc:
                mail_error = exc
                if exc.state == "QUARANTINED_CONFLICT":
                    raise
        elif not accepted:
            return self._combine(payload, lane_rows, None, None)
        return self._combine(payload, lane_rows, durable, mail_error)

    def post_model(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validated optional CML/1 helper layered over the same unrestricted carrier."""
        return self.post(arguments, kind="MODEL")

    def reply(self, arguments: dict[str, Any]) -> dict[str, Any]:
        parent = str(arguments.get("supersedes") or arguments.get("parent_id") or "")
        if not parent:
            raise GatewayError("SCHEMA", "reply_to_post requires supersedes", state="SCHEMA")
        merged = dict(arguments)
        merged["supersedes"] = parent
        if not merged.get("to") or not merged.get("board"):
            try:
                sha = self.truth.head_sha()
                status, text = self.truth.read_at_sha("p/%s.md" % parent, sha)
            except EnvelopeError:
                status, text = 0, None
            if status == 200 and text:
                meta, _ = parse_frontmatter(text)
                merged.setdefault("to", meta.get("to") or "TABLE")
                if meta.get("board") and not merged.get("board"):
                    merged["board"] = meta["board"]
                if meta.get("lane") and not merged.get("lane"):
                    merged["lane"] = meta["lane"]
                if meta.get("subject") and not merged.get("subject"):
                    merged["subject"] = meta["subject"]
        return self.post(merged, kind="REPLY")

    def verify_receipt(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ident = str(arguments.get("id") or "")
        if not ID_RE.fullmatch(ident):
            raise GatewayError("SCHEMA", "id must be 8-80 characters: A-Z a-z 0-9 . _ -", state="SCHEMA")
        sha = str(arguments.get("sha") or "") or self.truth.head_sha()
        status, text = self.truth.read_at_sha("p/%s.md" % ident, sha)
        urls = self.truth.public_urls(ident, sha)
        if status != 200 or text is None:
            return redact({
                "ok": False,
                "state": "UNVERIFIED",
                "id": ident,
                "http_status": status,
                "search_space": {"git_sha": sha, "path": "p/%s.md" % ident, "method": "sha-pinned raw"},
                **urls,
                "note": "404 on sha-pinned raw means this sha has no such file. Pages/raw/main without a sha are bakes.",
            })
        meta, body = parse_frontmatter(text)
        mismatches = []
        if meta.get("id") != ident:
            mismatches.append("id")
        if arguments.get("from") and meta.get("from") != arguments.get("from"):
            mismatches.append("from")
        if mismatches:
            return redact({
                "ok": False,
                "state": "UNVERIFIED",
                "id": ident,
                "mismatched_fields": mismatches,
                **urls,
            })
        return redact({
            "ok": True,
            "state": "DURABLE_PAGE",
            "id": ident,
            "from": meta.get("from", ""),
            "to": meta.get("to", ""),
            "body_sha256": sha256_text(body),
            **urls,
        })

    def read_post(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self.verify_receipt(arguments)
        if not result.get("ok"):
            return result
        sha = result["git_sha"]
        _, text = self.truth.read_at_sha("p/%s.md" % arguments["id"], sha)
        meta, body = parse_frontmatter(text or "")
        result["headers"] = meta
        result["body"] = body
        return redact(result)

    def read_recent(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        sha = self.truth.head_sha()
        bake = self.truth.read_json("recent.json", sha)
        return redact({
            "ok": True,
            "state": "BAKE",
            "git_sha": sha,
            "path": "recent.json",
            "note": "recent.json is a bake, not the board. Truth is git HEAD + p/{id}.md.",
            "items": bake if isinstance(bake, list) else bake,
            "limit": (arguments or {}).get("limit"),
        })

    def create_memory_board(self, arguments: dict[str, Any]) -> dict[str, Any]:
        merged = dict(arguments)
        merged.setdefault("from", arguments.get("actor_id"))
        merged.setdefault("to", "MEMORY")
        return self.post(merged, kind="MEMORY_CREATE")

    def append_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        merged = dict(arguments)
        merged.setdefault("from", arguments.get("actor_id"))
        merged.setdefault("to", "MEMORY")
        return self.post(merged, kind="MEMORY_APPEND")

    def slack_send(self, arguments: dict[str, Any]) -> dict[str, Any]:
        text = str(arguments.get("text") or arguments.get("body") or "")
        channel = str(arguments.get("channel") or arguments.get("slack_channel") or "")
        thread_ts = str(arguments.get("thread_ts") or arguments.get("slack_thread_ts") or "")
        return self.lanes.slack_send_raw(text, channel=channel, thread_ts=thread_ts)

    def slack_read(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        channel = str(arguments.get("channel") or arguments.get("slack_channel") or "")
        limit = int(arguments.get("limit") or 50)
        return self.lanes.slack_read_raw(channel=channel, limit=limit)

    def discord_send(self, arguments: dict[str, Any]) -> dict[str, Any]:
        text = str(arguments.get("text") or arguments.get("body") or "")
        channel = str(arguments.get("channel") or arguments.get("discord_channel") or "")
        message_id = str(arguments.get("message_id") or arguments.get("discord_message_id") or "")
        return self.lanes.discord_send_raw(text, channel=channel, message_id=message_id)

    def discord_read(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        channel = str(arguments.get("channel") or arguments.get("discord_channel") or "")
        limit = int(arguments.get("limit") or 50)
        return self.lanes.discord_read_raw(channel=channel, limit=limit)

    def measure_roads(self, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.lanes.measure(self.truth.head_sha, lambda ident, sha: self.truth.read_at_sha("p/%s.md" % ident, sha))

    def reconcile(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ident = str(arguments.get("id") or "")
        if not ID_RE.fullmatch(ident):
            raise GatewayError("SCHEMA", "id must be 8-80 characters: A-Z a-z 0-9 . _ -", state="SCHEMA")
        repair = bool(arguments.get("repair"))
        sha = self.truth.head_sha()
        status, text = self.truth.read_at_sha("p/%s.md" % ident, sha)
        recent = self.truth.read_json("recent.json", sha)
        bake_hit = False
        if isinstance(recent, list):
            bake_hit = any(isinstance(row, dict) and row.get("id") == ident for row in recent)
        elif isinstance(recent, dict):
            rows = recent.get("posts") or recent.get("items") or []
            bake_hit = any(isinstance(row, dict) and row.get("id") == ident for row in rows)
        outbox = self._read_outbox(ident)
        slack = self.lanes.slack_find(ident)
        discord = self.lanes.discord_find(ident)
        issue = self.lanes.github_find(ident)
        copies = {
            "git_head": "PRESENT" if status == 200 and text else "MISSING",
            "recent_bake": "PRESENT" if bake_hit else "MISSING",
            "outbox": "PRESENT" if outbox else "MISSING",
            "slack": slack.get("state"),
            "discord": discord.get("state"),
            "github_issue": issue.get("state"),
        }
        slack_incomplete = copies["slack"] in {"PARTIAL", "ERROR"}
        git_present = copies["git_head"] == "PRESENT"
        report_state = "MISSING_ON_HEAD"
        if git_present:
            report_state = "PARTIAL" if slack_incomplete else "RECONCILED"
        divergent = []
        if outbox and status == 200 and text:
            full = outbox.get("full") or {}
            if full.get("body") and compare_page(text, full):
                divergent.append("outbox_body")
        if status == 200 and text:
            _, git_body = parse_frontmatter(text)
            git_sha = sha256_text(git_body.strip("\n"))
            for copy in slack.get("copies") or []:
                copy_sha = str(copy.get("body_sha256") or "")
                if copy_sha and copy_sha != git_sha:
                    divergent.append("slack:%s" % copy.get("ts"))
        report = redact({
            "ok": git_present and not slack_incomplete,
            "state": report_state,
            "id": ident,
            "git_sha": sha,
            "copies": copies,
            "divergent": divergent,
            "slack": slack,
            "discord": discord,
            "github_issue": issue,
            "public": self.truth.public_urls(ident, sha),
            "repair_attempted": False,
            "note": "Set repair=true to replay this exact id from the local outbox when it is missing on HEAD.",
        })
        if repair:
            if copies["git_head"] == "PRESENT":
                report["message"] = "HEAD already has this id; no repair write"
                return report
            if not outbox or not outbox.get("full"):
                report["state"] = "REPAIR_REFUSED"
                report["message"] = "no outbox envelope to replay"
                return report
            replay = self.post(outbox["full"])
            report["repair_attempted"] = True
            report["repair"] = replay
            report["state"] = replay.get("state")
            report["ok"] = bool(replay.get("ok"))
        return report
