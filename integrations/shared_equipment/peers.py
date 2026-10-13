"""Expose Gemini + GrokBot lifecycle operations through shared equipment."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from integrations.grokbot_control.paid_case import (
    receipt_from_g2_submit,
    receipt_row_from_case,
)
from .diagnostic_equipment_cards import (
    call_diagnostic_card,
    diagnostic_card_tool_schemas,
)
from .services import _schema

DEFAULT_GROKBOT_CONTROL = "http://127.0.0.1:8881"


class GeminiEquipment:
    def __init__(self, gateway):
        self.gateway = gateway

    def tools(self):
        return [
            _schema(
                "gemini_submit",
                "Submit useful work to an existing Gemini peer; returns a request id. Request completion may require model/tool turns. Reuse the equipment envelope IDs on retry.",
                {"peer": "string", "message": "string"},
            ),
            _schema(
                "gemini_get_request",
                "Inspect a Gemini request without starting work. Wait up to 45 seconds if desired.",
                {"request_id": "string"},
                {"wait_ms": "integer"},
            ),
            _schema(
                "gemini_follow_up",
                "Continue the same named Gemini conversation with a new request. Preserves the existing upstream history.",
                {"request_id": "string", "message": "string"},
            ),
            _schema(
                "gemini_cancel",
                "Request cooperative cancellation. In-flight provider response may finish; no further tool effects then run. Does not kill the provider or other work.",
                {"request_id": "string"},
            ),
            _schema(
                "gemini_recover",
                "Inspect interrupted requests after a gateway restart. Never automatically replays work; inspect prior tool effects and explicitly follow up.",
                {},
            ),
            _schema(
                "gemini_events",
                "Read Gemini lifecycle and results after a cursor.",
                {},
                {"after": "integer", "limit": "integer", "peer": "string"},
            ),
        ]

    def call(self, name, args):
        g = self.gateway
        if name == "gemini_submit":
            item = g.submit(g.normalize_peer(args["peer"]), args["message"])
            return {"request_id": item.request_id, "status": "queued"}
        if name == "gemini_get_request":
            return {
                "event": g.events.request(
                    args["request_id"], min(45000, max(0, int(args.get("wait_ms", 0))))
                )
            }
        if name == "gemini_cancel":
            return g.cancel(args["request_id"])
        if name == "gemini_follow_up":
            prior = g.events.request(args["request_id"], 0)
            if prior is None:
                return {"error": "request_not_found"}
            item = g.submit(prior["peer"], args["message"])
            return {
                "request_id": item.request_id,
                "peer": prior["peer"],
                "previous_request_id": args["request_id"],
                "status": "queued",
            }
        if name == "gemini_recover":
            return {
                "interrupted": [
                    event
                    for event in g.events._latest.values()
                    if event.get("status") == "interrupted"
                ],
                "replayed": False,
            }
        if name == "gemini_events":
            events = g.events.after(
                int(args.get("after", 0)),
                args.get("peer"),
                min(200, max(1, int(args.get("limit", 20)))),
                0,
            )
            return {
                "events": events,
                "next_cursor": max(
                    [int(args.get("after", 0))] + [e["event_id"] for e in events]
                ),
            }
        return {"error": "unknown_equipment_tool"}


class GrokBotEquipment:
    """Drive existing GrokBot pools via integrations/grokbot_control (:8881).

    Distinct from Gemini lifecycle tools and from grok.com. Does not start the
    control gateway; callers point base_url at a running (or test) instance.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_GROKBOT_CONTROL,
        *,
        opener=None,
    ) -> None:
        self.base_url = str(base_url or DEFAULT_GROKBOT_CONTROL).rstrip("/")
        self.opener = opener or urllib.request.urlopen

    def tools(self):
        return [
            _schema(
                "grokbot_submit",
                "Submit work to an existing GrokBot pool via grokbot_control. Optional case ties the run to a paid offer (offer_id/case_ref/client_reference_id/sku). Returns run_id + session_id. Not grok.com. Not Cursor cloud.",
                {"prompt": "string"},
                {
                    "pool_id": "string",
                    "seat": "string",
                    "async": "boolean",
                    "case": "object",
                },
            ),
            _schema(
                "grokbot_inspect",
                "Inspect a GrokBot run by run_id. Optional wait_ms blocks until terminal.",
                {"run_id": "string"},
                {"wait_ms": "integer"},
            ),
            _schema(
                "grokbot_follow_up",
                "Follow up on the same GrokBot session_id (new run_id). Pass any prior run_id from that session.",
                {"run_id": "string", "prompt": "string"},
                {"async": "boolean"},
            ),
            _schema(
                "grokbot_cancel",
                "Cancel one GrokBot run_id only. Session remains recoverable for follow-up.",
                {"run_id": "string"},
            ),
            _schema(
                "grokbot_session",
                "Recover a GrokBot session and its runs after controller replacement.",
                {"session_id": "string"},
            ),
            _schema(
                "grokbot_events",
                "Read GrokBot control events after a cursor (Gemini/C1 convention).",
                {},
                {"after": "integer", "limit": "integer", "pool_id": "string", "wait_ms": "integer"},
            ),
            _schema(
                "grokbot_pools",
                "List known GrokBot pool_ids (corpus ids only; second account kebab not invented).",
                {},
            ),
            _schema(
                "grokbot_health",
                "Report grokbot_control GET /health including memory_guard without submitting a run.",
                {},
            ),
            _schema(
                "grokbot_receipt_row_from_case",
                "Build an opaque seats case_row from a G2 case. Pass submit_response to bind run_id/session_id via receipt_from_g2_submit; otherwise optional g2_run_id/g2_session_id. Local helper; does not call :8881.",
                {"case": "object"},
                {
                    "g2_run_id": "string",
                    "g2_session_id": "string",
                    "payment_observed_at": "string",
                    "state": "string",
                    "submit_response": "object",
                },
            ),
        ] + diagnostic_card_tool_schemas()

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "grokbot_submit":
            body = {
                "prompt": args["prompt"],
                "pool_id": args.get("pool_id") or "grokbot",
                "async": bool(args.get("async", True)),
            }
            if args.get("seat"):
                body["seat"] = args["seat"]
            if args.get("case") is not None:
                body["case"] = args["case"]
            return self._request("POST", "/v1/runs", payload=body)
        if name == "grokbot_inspect":
            wait_ms = min(45000, max(0, int(args.get("wait_ms", 0))))
            query = {"wait_ms": wait_ms} if wait_ms else None
            return self._request(
                "GET",
                "/v1/runs/%s" % args["run_id"],
                query=query,
                timeout=max(60.0, wait_ms / 1000.0 + 5),
            )
        if name == "grokbot_follow_up":
            body = {
                "prompt": args["prompt"],
                "async": bool(args.get("async", True)),
            }
            return self._request(
                "POST",
                "/v1/runs/%s/follow-up" % args["run_id"],
                payload=body,
            )
        if name == "grokbot_cancel":
            return self._request(
                "POST", "/v1/runs/%s/cancel" % args["run_id"], payload={}
            )
        if name == "grokbot_session":
            return self._request("GET", "/v1/sessions/%s" % args["session_id"])
        if name == "grokbot_events":
            return self._request(
                "GET",
                "/v1/events",
                query={
                    "after": int(args.get("after", 0)),
                    "limit": min(200, max(1, int(args.get("limit", 50)))),
                    "wait_ms": min(45000, max(0, int(args.get("wait_ms", 0)))),
                    "pool_id": args.get("pool_id"),
                },
            )
        if name == "grokbot_pools":
            return self._request("GET", "/v1/pools")
        if name == "grokbot_health":
            return self._request("GET", "/health")
        if name == "grokbot_receipt_row_from_case":
            try:
                if args.get("submit_response") is not None:
                    row = receipt_from_g2_submit(
                        args["case"],
                        args["submit_response"],
                        payment_observed_at=args.get("payment_observed_at"),
                        state=args.get("state") or "UNVERIFIED",
                    )
                else:
                    row = receipt_row_from_case(
                        args["case"],
                        g2_run_id=args.get("g2_run_id"),
                        g2_session_id=args.get("g2_session_id"),
                        payment_observed_at=args.get("payment_observed_at"),
                        state=args.get("state") or "UNVERIFIED",
                    )
            except (ValueError, TypeError, KeyError):
                return {"ok": False, "error": "invalid_receipt"}
            return {"ok": True, "case_row": row}
        handled = call_diagnostic_card(name, args)
        if handled is not None:
            return handled
        return {"error": "unknown_equipment_tool"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {
                    "ok": False,
                    "error": "grokbot_control_http_error",
                    "status": exc.code,
                    "body": body[:500],
                }
        except Exception as exc:
            return {
                "ok": False,
                "error": "grokbot_control_unreachable",
                "message": "%s: %s" % (type(exc).__name__, exc),
                "base_url": self.base_url,
                "note": "Control gateway not running; do not relaunch residents on owner PC until cleared.",
            }


def _load_claude_headless():
    """Import integrations/claude_headless/claude_headless.py (a script directory, not a package)."""
    import importlib
    import sys
    from pathlib import Path

    package_dir = Path(__file__).resolve().parents[1] / "claude_headless"
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return importlib.import_module("claude_headless")


_CLAUDE_SUMMARY_KEYS = (
    "run_id", "session_id", "status", "resume", "label", "peer", "cwd", "model",
    "started_at", "ended_at", "exit_code", "result_text", "result_subtype", "is_error",
    "num_turns", "cost_usd", "duration_ms", "child_model", "child_version", "event_count", "error",
)


class ClaudeHeadlessEquipment:
    """Drive the installed Claude Code CLI headlessly through integrations/claude_headless (C1).

    In-process over ``claude_headless.Runner``: every run is an on-disk record under the runs
    root, so a replacement occupant recovers it from disk. The runner's memory floor applies;
    on a starved machine ``claude_headless_start`` returns the refusal as the tool result and
    spawns nothing. No credential is touched: the CLI uses the auth already on the machine.
    """

    def __init__(
        self,
        root: str | None = None,
        *,
        claude: list[str] | None = None,
        min_free_mb: int | None = None,
        runner=None,
    ) -> None:
        self._runner = runner
        self._root = root
        self._claude = claude
        self._min_free_mb = min_free_mb

    @property
    def runner(self):
        if self._runner is None:
            module = _load_claude_headless()
            self._runner = module.Runner(self._root, claude=self._claude, min_free_mb=self._min_free_mb)
        return self._runner

    def tools(self):
        run_options = {
            "cwd": "string",
            "model": "string",
            "tools": "string",
            "allowed_tools": "string",
            "strict_mcp": "boolean",
            "permission_mode": "string",
            "label": "string",
            "peer": "string",
            "wait_s": "integer",
        }
        return [
            _schema(
                "claude_headless_start",
                "Start a headless Claude Code run on the equipped machine (C1). Returns run_id + durable session_id; wait_s blocks up to 300 s for the result. allowed_tools pre-approves tools (print mode cannot prompt); strict_mcp drops inherited MCP servers. Refuses under the memory floor.",
                {"prompt": "string"},
                run_options,
            ),
            _schema(
                "claude_headless_status",
                "Inspect one run by run_id; wait_s blocks up to 300 s for a terminal status. Finalizes from the on-disk record if the child is gone.",
                {"run_id": "string"},
                {"wait_s": "integer"},
            ),
            _schema(
                "claude_headless_followup",
                "Continue the exact same conversation (claude -p --resume) as a new run. target is a run_id or session_id.",
                {"target": "string", "prompt": "string"},
                run_options,
            ),
            _schema(
                "claude_headless_cancel",
                "Kill one run's process tree. The session stays resumable.",
                {"run_id": "string"},
            ),
            _schema(
                "claude_headless_events",
                "Raw stream-json lines of a run after a cursor (1-based line index), with next_cursor.",
                {"run_id": "string"},
                {"after": "integer", "limit": "integer", "wait_ms": "integer"},
            ),
            _schema(
                "claude_headless_recover",
                "Finalize runs whose controller died, list still-running ones, and read the memory floor. A replacement occupant calls this first.",
                {},
            ),
        ]

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        out = {key: record.get(key) for key in _CLAUDE_SUMMARY_KEYS}
        headless = record.get("headless") or {}
        out["free_physical_mb_at_spawn"] = headless.get("free_physical_mb_at_spawn")
        out["min_free_mb"] = headless.get("min_free_mb")
        text = out.get("result_text")
        if isinstance(text, str) and len(text) > 20000:
            out["result_text"] = text[:20000]
            out["result_text_truncated"] = True
        out["ok"] = True
        return out

    @staticmethod
    def _run_kwargs(args: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        for key in ("cwd", "model", "tools", "allowed_tools", "permission_mode", "label", "peer"):
            if args.get(key) is not None:
                kwargs[key] = args[key]
        if args.get("strict_mcp"):
            kwargs["strict_mcp"] = True
        return kwargs

    @staticmethod
    def _wait_s(args: dict[str, Any]) -> float:
        return float(min(300, max(0, int(args.get("wait_s", 0) or 0))))

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        module = _load_claude_headless()
        try:
            if name == "claude_headless_start":
                record = self.runner.start(str(args["prompt"]), **self._run_kwargs(args))
                wait = self._wait_s(args)
                if wait:
                    record = self.runner.wait(record["run_id"], timeout=wait)
                return self._summary(record)
            if name == "claude_headless_status":
                wait = self._wait_s(args)
                record = self.runner.wait(args["run_id"], timeout=wait) if wait else self.runner.status(args["run_id"])
                return self._summary(record)
            if name == "claude_headless_followup":
                record = self.runner.followup(str(args["target"]), str(args["prompt"]), **self._run_kwargs(args))
                wait = self._wait_s(args)
                if wait:
                    record = self.runner.wait(record["run_id"], timeout=wait)
                return self._summary(record)
            if name == "claude_headless_cancel":
                return self.runner.cancel(args["run_id"])
            if name == "claude_headless_events":
                events, cursor = self.runner.events(
                    args["run_id"],
                    after=int(args.get("after", 0) or 0),
                    limit=min(500, max(1, int(args.get("limit", 200) or 200))),
                    wait_ms=min(45000, max(0, int(args.get("wait_ms", 0) or 0))),
                )
                return {"ok": True, "run_id": args["run_id"], "events": events, "next_cursor": cursor}
            if name == "claude_headless_recover":
                return {
                    "ok": True,
                    "recovered": self.runner.recover(),
                    "still_running": self.runner.active(),
                    "memory_floor": self.runner.memory_floor(),
                }
        except module.HeadlessError as exc:
            return {"ok": False, "error": "claude_headless_refused", "message": str(exc)}
        except KeyError as exc:
            return {"ok": False, "error": "missing_argument", "message": "missing %s" % exc}
        return {"error": "unknown_equipment_tool"}
