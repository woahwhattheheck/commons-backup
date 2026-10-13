from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Iterable

MAX_TEXT = 8_192
MAX_EVIDENCE_ITEMS = 16
MAX_EVENTS = 10_000
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ValidationError(ValueError):
    """Raised when caller-supplied state is not admissible."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, field: str, *, required: bool = True, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{field} must not be empty")
    if len(value.encode("utf-8")) > limit:
        raise ValidationError(f"{field} is too large")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise ValidationError(f"{field} contains a control character")
    return value


def _integer(value: Any, field: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{field} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{field} must be <= {maximum}")
    return value


def _exact_keys(mapping: Any, field: str, allowed: set[str], required: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValidationError(f"{field} must be an object")
    unknown = set(mapping) - allowed
    if unknown:
        raise ValidationError(f"{field} has unknown keys: {', '.join(sorted(unknown))}")
    missing = (required or set()) - set(mapping)
    if missing:
        raise ValidationError(f"{field} is missing keys: {', '.join(sorted(missing))}")
    return mapping


def _evidence(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_ITEMS:
        raise ValidationError(f"evidence must be a list of at most {MAX_EVIDENCE_ITEMS} strings")
    return [_text(item, f"evidence[{idx}]", limit=2_048) for idx, item in enumerate(value)]


class HomeOpsLedger:
    """Append-only household-operations ledger with deterministic receipts.

    Nothing in this class contacts a vendor, schedules a visit, purchases an
    item, or mutates a real household system. Action tools create reviewable
    proposals only. The event chain is designed so a demo or judge can replay
    and verify exactly what the MCP server did.
    """

    SEVERITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
    ACTION_TYPES = {"CONTACT_PROVIDER", "SCHEDULE_VISIT", "PURCHASE_PART", "CLAIM_WARRANTY"}

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.issues: dict[str, dict[str, Any]] = {}
        self.quotes: dict[str, dict[str, Any]] = {}
        self.actions: dict[str, dict[str, Any]] = {}

    @property
    def receipt(self) -> str:
        return self.events[-1]["hash"] if self.events else hashlib.sha256(b"homeops-relay/empty").hexdigest()

    def _next_id(self, prefix: str, body: dict[str, Any]) -> str:
        seq = len(self.events) + 1
        token = _digest({"seq": seq, "body": body})[:10]
        return f"{prefix}-{seq:04d}-{token}"

    def _append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if len(self.events) >= MAX_EVENTS:
            raise ValidationError("event limit reached")
        core = {
            "seq": len(self.events) + 1,
            "kind": kind,
            "payload": deepcopy(payload),
            "prev_hash": self.receipt,
        }
        event = {**core, "hash": _digest(core)}
        self._apply(event)
        self.events.append(event)
        return deepcopy(event)

    def _issue(self, issue_id: Any) -> dict[str, Any]:
        issue_id = _text(issue_id, "issue_id", limit=128)
        if issue_id not in self.issues:
            raise ValidationError("unknown issue_id")
        return self.issues[issue_id]

    def intake_issue(
        self,
        *,
        title: Any,
        area: Any,
        severity: Any,
        details: Any,
        evidence: Any = None,
    ) -> dict[str, Any]:
        title = _text(title, "title", limit=256)
        area = _text(area, "area", limit=128)
        severity = _text(severity, "severity", limit=16).upper()
        if severity not in self.SEVERITIES:
            raise ValidationError(f"severity must be one of {sorted(self.SEVERITIES)}")
        details = _text(details, "details")
        evidence_items = _evidence(evidence)
        body = {
            "title": title,
            "area": area,
            "severity": severity,
            "details": details,
            "evidence": evidence_items,
        }
        issue_id = self._next_id("ISS", body)
        event = self._append("ISSUE_INTAKE", {"issue_id": issue_id, **body})
        return {"issue_id": issue_id, "state": "OPEN", "receipt": event["hash"]}

    def record_quote(
        self,
        *,
        issue_id: Any,
        provider: Any,
        amount_minor: Any,
        currency: Any = "USD",
        scope: Any,
        source: Any = "caller_supplied",
    ) -> dict[str, Any]:
        issue = self._issue(issue_id)
        provider = _text(provider, "provider", limit=256)
        amount_minor = _integer(amount_minor, "amount_minor", minimum=0, maximum=10**12)
        currency = _text(currency, "currency", limit=3).upper()
        if not CURRENCY_RE.fullmatch(currency):
            raise ValidationError("currency must be a three-letter uppercase code")
        scope = _text(scope, "scope")
        source = _text(source, "source", limit=512)
        body = {
            "issue_id": issue["issue_id"],
            "provider": provider,
            "amount_minor": amount_minor,
            "currency": currency,
            "scope": scope,
            "source": source,
        }
        quote_id = self._next_id("QTE", body)
        event = self._append("QUOTE_RECORDED", {"quote_id": quote_id, **body})
        return {"quote_id": quote_id, "state": "RECORDED_UNVERIFIED", "receipt": event["hash"]}

    def propose_plan(self, *, issue_id: Any) -> dict[str, Any]:
        issue = deepcopy(self._issue(issue_id))
        details = f"{issue['title']} {issue['details']}".casefold()
        steps: list[str] = []
        if issue["severity"] == "URGENT":
            steps.append("Make the area safe and stop ongoing damage only when it is safe to do so.")
        if any(word in details for word in ("water", "leak", "pipe", "flood")):
            steps.append("Inspect visible water sources and isolate the affected fixture or supply only if safe.")
            steps.append("Document moisture location and progression before cleanup or repair.")
        elif any(word in details for word in ("electric", "outlet", "spark", "breaker")):
            steps.append("Avoid touching energized equipment; isolate the affected circuit only if safe and understood.")
            steps.append("Record the device, circuit, and observable symptoms for a qualified electrician.")
        elif any(word in details for word in ("heat", "hvac", "furnace", "air conditioner", "ac ")):
            steps.append("Capture thermostat state, filter condition, and observable equipment symptoms without bypassing safety interlocks.")
        else:
            steps.append("Capture reproducible symptoms, photos or measurements, and what changed immediately before the issue appeared.")
        steps.append("Compare repair options by scope, evidence, warranty implications, price, and scheduling constraints.")
        steps.append("Present any vendor contact, scheduling, purchase, or warranty action for owner approval before external execution.")

        quotes = [deepcopy(q) for q in self.quotes.values() if q["issue_id"] == issue["issue_id"]]
        quotes.sort(key=lambda q: (q["currency"], q["amount_minor"], q["provider"].casefold(), q["quote_id"]))
        quote_summary = [
            {
                "quote_id": q["quote_id"],
                "provider": q["provider"],
                "amount_minor": q["amount_minor"],
                "currency": q["currency"],
                "scope": q["scope"],
                "verification": "CALLER_SUPPLIED_UNVERIFIED",
            }
            for q in quotes
        ]
        plan_core = {
            "issue_id": issue["issue_id"],
            "severity": issue["severity"],
            "steps": steps,
            "quotes": quote_summary,
            "authority": {
                "mode": "OWNER_REVIEW_REQUIRED",
                "external_effect": False,
                "purchase": False,
                "contact_provider": False,
                "schedule_visit": False,
            },
            "source_receipt": self.receipt,
        }
        return {**plan_core, "plan_digest": _digest(plan_core)}

    def request_action(
        self,
        *,
        issue_id: Any,
        action_type: Any,
        target: Any,
        note: Any = "",
        max_amount_minor: Any = None,
        currency: Any = "USD",
    ) -> dict[str, Any]:
        issue = self._issue(issue_id)
        action_type = _text(action_type, "action_type", limit=64).upper()
        if action_type not in self.ACTION_TYPES:
            raise ValidationError(f"action_type must be one of {sorted(self.ACTION_TYPES)}")
        target = _text(target, "target", limit=512)
        note = _text(note, "note", required=False)
        if max_amount_minor is not None:
            max_amount_minor = _integer(max_amount_minor, "max_amount_minor", minimum=0, maximum=10**12)
        currency = _text(currency, "currency", limit=3).upper()
        if not CURRENCY_RE.fullmatch(currency):
            raise ValidationError("currency must be a three-letter uppercase code")
        body = {
            "issue_id": issue["issue_id"],
            "action_type": action_type,
            "target": target,
            "note": note,
            "max_amount_minor": max_amount_minor,
            "currency": currency,
        }
        action_id = self._next_id("ACT", body)
        event = self._append("ACTION_REQUESTED", {"action_id": action_id, **body})
        return {
            "action_id": action_id,
            "state": "PENDING_OWNER_REVIEW",
            "external_effect": False,
            "receipt": event["hash"],
        }

    def record_owner_decision(self, *, action_id: Any, decision: Any, evidence_note: Any) -> dict[str, Any]:
        action_id = _text(action_id, "action_id", limit=128)
        if action_id not in self.actions:
            raise ValidationError("unknown action_id")
        action = self.actions[action_id]
        if action["state"] != "PENDING_OWNER_REVIEW":
            raise ValidationError("action is not pending owner review")
        decision = _text(decision, "decision", limit=16).upper()
        if decision not in {"APPROVE", "REJECT"}:
            raise ValidationError("decision must be APPROVE or REJECT")
        evidence_note = _text(evidence_note, "evidence_note", limit=1_024)
        state = "APPROVED_NOT_EXECUTED" if decision == "APPROVE" else "REJECTED"
        event = self._append(
            "ACTION_REVIEWED",
            {
                "action_id": action_id,
                "decision": decision,
                "evidence_note": evidence_note,
                "state": state,
                "external_effect": False,
            },
        )
        return {"action_id": action_id, "state": state, "external_effect": False, "receipt": event["hash"]}

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "schema": "homeops-relay-snapshot/v1",
            "issues": [deepcopy(self.issues[k]) for k in sorted(self.issues)],
            "quotes": [deepcopy(self.quotes[k]) for k in sorted(self.quotes)],
            "actions": [deepcopy(self.actions[k]) for k in sorted(self.actions)],
            "event_count": len(self.events),
            "event_receipt": self.receipt,
            "authority": {
                "external_effect": False,
                "provider_contact": False,
                "scheduling": False,
                "purchase": False,
                "payment": False,
            },
        }
        return {**snapshot, "snapshot_digest": _digest(snapshot)}

    def export_events(self) -> list[dict[str, Any]]:
        return deepcopy(self.events)

    @classmethod
    def replay(cls, events: Iterable[dict[str, Any]]) -> "HomeOpsLedger":
        ledger = cls()
        for raw in events:
            event = deepcopy(raw)
            _exact_keys(event, "event", {"seq", "kind", "payload", "prev_hash", "hash"}, {"seq", "kind", "payload", "prev_hash", "hash"})
            seq = _integer(event["seq"], "event.seq", minimum=1)
            if seq != len(ledger.events) + 1:
                raise ValidationError("event sequence is not contiguous")
            kind = _text(event["kind"], "event.kind", limit=64)
            payload = event["payload"]
            if not isinstance(payload, dict):
                raise ValidationError("event.payload must be an object")
            prev_hash = _text(event["prev_hash"], "event.prev_hash", limit=64)
            event_hash = _text(event["hash"], "event.hash", limit=64)
            if prev_hash != ledger.receipt:
                raise ValidationError("event chain predecessor mismatch")
            core = {"seq": seq, "kind": kind, "payload": payload, "prev_hash": prev_hash}
            if _digest(core) != event_hash:
                raise ValidationError("event hash mismatch")
            ledger._apply(event)
            ledger.events.append(event)
        return ledger

    @classmethod
    def verify_events(cls, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
        ledger = cls.replay(events)
        return {
            "verified": True,
            "event_count": len(ledger.events),
            "receipt": ledger.receipt,
            "snapshot_digest": ledger.snapshot()["snapshot_digest"],
        }

    def _apply(self, event: dict[str, Any]) -> None:
        kind = event["kind"]
        p = event["payload"]
        if kind == "ISSUE_INTAKE":
            _exact_keys(p, "ISSUE_INTAKE", {"issue_id", "title", "area", "severity", "details", "evidence"}, {"issue_id", "title", "area", "severity", "details", "evidence"})
            issue_id = _text(p["issue_id"], "issue_id", limit=128)
            if issue_id in self.issues:
                raise ValidationError("duplicate issue_id")
            severity = _text(p["severity"], "severity", limit=16).upper()
            if severity not in self.SEVERITIES:
                raise ValidationError("invalid severity")
            issue = {
                "issue_id": issue_id,
                "title": _text(p["title"], "title", limit=256),
                "area": _text(p["area"], "area", limit=128),
                "severity": severity,
                "details": _text(p["details"], "details"),
                "evidence": _evidence(p["evidence"]),
                "state": "OPEN",
            }
            self.issues[issue_id] = issue
            return
        if kind == "QUOTE_RECORDED":
            _exact_keys(p, "QUOTE_RECORDED", {"quote_id", "issue_id", "provider", "amount_minor", "currency", "scope", "source"}, {"quote_id", "issue_id", "provider", "amount_minor", "currency", "scope", "source"})
            issue = self._issue(p["issue_id"])
            quote_id = _text(p["quote_id"], "quote_id", limit=128)
            if quote_id in self.quotes:
                raise ValidationError("duplicate quote_id")
            currency = _text(p["currency"], "currency", limit=3).upper()
            if not CURRENCY_RE.fullmatch(currency):
                raise ValidationError("invalid currency")
            self.quotes[quote_id] = {
                "quote_id": quote_id,
                "issue_id": issue["issue_id"],
                "provider": _text(p["provider"], "provider", limit=256),
                "amount_minor": _integer(p["amount_minor"], "amount_minor", minimum=0, maximum=10**12),
                "currency": currency,
                "scope": _text(p["scope"], "scope"),
                "source": _text(p["source"], "source", limit=512),
                "verification": "CALLER_SUPPLIED_UNVERIFIED",
            }
            return
        if kind == "ACTION_REQUESTED":
            _exact_keys(p, "ACTION_REQUESTED", {"action_id", "issue_id", "action_type", "target", "note", "max_amount_minor", "currency"}, {"action_id", "issue_id", "action_type", "target", "note", "max_amount_minor", "currency"})
            issue = self._issue(p["issue_id"])
            action_id = _text(p["action_id"], "action_id", limit=128)
            if action_id in self.actions:
                raise ValidationError("duplicate action_id")
            action_type = _text(p["action_type"], "action_type", limit=64).upper()
            if action_type not in self.ACTION_TYPES:
                raise ValidationError("invalid action_type")
            amount = p["max_amount_minor"]
            if amount is not None:
                amount = _integer(amount, "max_amount_minor", minimum=0, maximum=10**12)
            currency = _text(p["currency"], "currency", limit=3).upper()
            if not CURRENCY_RE.fullmatch(currency):
                raise ValidationError("invalid currency")
            self.actions[action_id] = {
                "action_id": action_id,
                "issue_id": issue["issue_id"],
                "action_type": action_type,
                "target": _text(p["target"], "target", limit=512),
                "note": _text(p["note"], "note", required=False),
                "max_amount_minor": amount,
                "currency": currency,
                "state": "PENDING_OWNER_REVIEW",
                "external_effect": False,
            }
            return
        if kind == "ACTION_REVIEWED":
            _exact_keys(p, "ACTION_REVIEWED", {"action_id", "decision", "evidence_note", "state", "external_effect"}, {"action_id", "decision", "evidence_note", "state", "external_effect"})
            action_id = _text(p["action_id"], "action_id", limit=128)
            if action_id not in self.actions:
                raise ValidationError("unknown action_id")
            if self.actions[action_id]["state"] != "PENDING_OWNER_REVIEW":
                raise ValidationError("action already reviewed")
            decision = _text(p["decision"], "decision", limit=16).upper()
            expected = "APPROVED_NOT_EXECUTED" if decision == "APPROVE" else "REJECTED" if decision == "REJECT" else None
            if expected is None or p["state"] != expected or p["external_effect"] is not False:
                raise ValidationError("invalid action review state")
            _text(p["evidence_note"], "evidence_note", limit=1_024)
            self.actions[action_id]["state"] = expected
            self.actions[action_id]["external_effect"] = False
            return
        raise ValidationError(f"unknown event kind: {kind}")

    @classmethod
    def tool_definitions(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "homeops.intake_issue",
                "description": "Record a household maintenance issue and evidence without causing external effects.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "area", "severity", "details"],
                    "properties": {
                        "title": {"type": "string", "maxLength": 256},
                        "area": {"type": "string", "maxLength": 128},
                        "severity": {"type": "string", "enum": sorted(cls.SEVERITIES)},
                        "details": {"type": "string"},
                        "evidence": {"type": "array", "maxItems": MAX_EVIDENCE_ITEMS, "items": {"type": "string"}},
                    },
                },
            },
            {
                "name": "homeops.record_quote",
                "description": "Record a caller-supplied repair quote in integer minor units; the quote remains unverified.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["issue_id", "provider", "amount_minor", "scope"],
                    "properties": {
                        "issue_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "amount_minor": {"type": "integer", "minimum": 0},
                        "currency": {"type": "string", "default": "USD"},
                        "scope": {"type": "string"},
                        "source": {"type": "string", "default": "caller_supplied"},
                    },
                },
            },
            {
                "name": "homeops.propose_plan",
                "description": "Create a deterministic evidence-linked diagnostic and comparison plan; all external actions remain owner-gated.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["issue_id"],
                    "properties": {"issue_id": {"type": "string"}},
                },
            },
            {
                "name": "homeops.request_action",
                "description": "Create a reviewable vendor/scheduling/purchase/warranty action proposal. This never executes the action.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["issue_id", "action_type", "target"],
                    "properties": {
                        "issue_id": {"type": "string"},
                        "action_type": {"type": "string", "enum": sorted(cls.ACTION_TYPES)},
                        "target": {"type": "string"},
                        "note": {"type": "string", "default": ""},
                        "max_amount_minor": {"type": ["integer", "null"], "minimum": 0},
                        "currency": {"type": "string", "default": "USD"},
                    },
                },
            },
            {
                "name": "homeops.record_owner_decision",
                "description": "Record an owner decision on an action proposal. Even APPROVE means approved-not-executed.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["action_id", "decision", "evidence_note"],
                    "properties": {
                        "action_id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["APPROVE", "REJECT"]},
                        "evidence_note": {"type": "string"},
                    },
                },
            },
            {
                "name": "homeops.snapshot",
                "description": "Return the deterministic current state and tamper-evident receipt.",
                "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
            },
        ]

    def call_tool(self, name: Any, arguments: Any) -> dict[str, Any]:
        name = _text(name, "tool.name", limit=128)
        if not isinstance(arguments, dict):
            raise ValidationError("tool arguments must be an object")
        if name == "homeops.intake_issue":
            _exact_keys(arguments, "arguments", {"title", "area", "severity", "details", "evidence"}, {"title", "area", "severity", "details"})
            return self.intake_issue(**arguments)
        if name == "homeops.record_quote":
            _exact_keys(arguments, "arguments", {"issue_id", "provider", "amount_minor", "currency", "scope", "source"}, {"issue_id", "provider", "amount_minor", "scope"})
            return self.record_quote(**arguments)
        if name == "homeops.propose_plan":
            _exact_keys(arguments, "arguments", {"issue_id"}, {"issue_id"})
            return self.propose_plan(**arguments)
        if name == "homeops.request_action":
            _exact_keys(arguments, "arguments", {"issue_id", "action_type", "target", "note", "max_amount_minor", "currency"}, {"issue_id", "action_type", "target"})
            return self.request_action(**arguments)
        if name == "homeops.record_owner_decision":
            _exact_keys(arguments, "arguments", {"action_id", "decision", "evidence_note"}, {"action_id", "decision", "evidence_note"})
            return self.record_owner_decision(**arguments)
        if name == "homeops.snapshot":
            _exact_keys(arguments, "arguments", set())
            return self.snapshot()
        raise ValidationError("unknown tool")
