from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from strands import Agent, tool
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent
from strands.hooks.registry import HookProvider, HookRegistry

from .core import DecisionRelayError, RelayEngine as HistoricalRelayEngine, canonical_json
from .current import CurrentRelayEngine


SYSTEM_PROMPT = """You are Commercial Decision Relay, a professional evidence-routing agent.
Your job is to quietly process normalized commercial evidence and surface ONLY real human decisions.
Always use the provided tools for factual state. Never infer acceptance, price, identity, authority, payment,
contract execution, fulfillment, or revenue from prose. Never claim that HUMAN_CLOSING_READY is legal or
signer authority: it only means reviewed evidence exactly matches the current offer and a human may decide
the next closing step. Do not invent tool results. For routine AWAITING_RESPONSE or DECLINED states, avoid
interrupting the human unless asked. For conflicts, counteroffers, clarifications, late replies, or expiry,
state the exact blocker and required human decision. You have no tool that can mutate a provider/customer,
sign, invoice, charge, fulfill, or recognize revenue; never imply otherwise. Trusted evidence is always
preloaded by the host, immutable for the run, and reconciled at a trusted evaluation time the model cannot choose."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RelayToolbox:
    def __init__(
        self,
        engine: HistoricalRelayEngine,
        *,
        trusted_evaluated_at: str | None = None,
        ingest_locked: bool = False,
    ):
        self.engine = engine
        self.trusted_evaluated_at = trusted_evaluated_at
        self.ingest_locked = ingest_locked

    def _trusted_time(self) -> str:
        if self.trusted_evaluated_at is None:
            raise DecisionRelayError(
                "trusted_time_required",
                "agent reconciliation and verification require a trusted evaluation time",
            )
        return self.trusted_evaluated_at

    @tool
    def ingest_batch(self, batch_json: str) -> str:
        """Ingest a normalized commercial evidence batch without external side effects.

        Args:
            batch_json: JSON object with schema_version, snapshot_at, and normalized offer/response events.
        """
        if self.ingest_locked:
            raise DecisionRelayError(
                "preloaded_batch_locked",
                "trusted preloaded evidence cannot be replaced by model-supplied evidence",
            )
        return _json(self.engine.ingest(json.loads(batch_json)))

    @tool
    def reconcile_evidence(self) -> str:
        """Reconcile evidence at the run's caller-supplied trusted UTC instant."""
        receipt = self.engine.reconcile(evaluated_at=self._trusted_time())
        return _json({"receipt_sha256": receipt["receipt_sha256"], "summary": receipt["summary"]})

    @tool
    def decision_queue(self) -> str:
        """Return only series that require a real human decision or intervention."""
        return _json(self.engine.decisions())

    @tool
    def explain_blocker(self, series_id: str) -> str:
        """Explain the deterministic status and blocker for one commercial series.

        Args:
            series_id: Stable commercial offer-series identifier.
        """
        return _json(self.engine.explain(series_id))

    @tool
    def verify_current_receipt(self, expected_receipt_sha256: str) -> str:
        """Verify the receipt at the run's trusted UTC instant and independent digest.

        Args:
            expected_receipt_sha256: Out-of-band SHA-256 commitment expected by the caller.
        """
        return _json({
            "valid": self.engine.verify(
                expected_receipt_sha256,
                evaluated_at=self._trusted_time(),
            )
        })


class AuditHooks(HookProvider):
    """Hash-only tool audit plus an allowlist enforcement hook."""

    ALLOWED = {
        "ingest_batch",
        "reconcile_evidence",
        "decision_queue",
        "explain_blocker",
        "verify_current_receipt",
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    @staticmethod
    def _name(tool_use: Any) -> str:
        if isinstance(tool_use, dict):
            return str(tool_use.get("name", ""))
        return str(getattr(tool_use, "name", ""))

    @staticmethod
    def _input(tool_use: Any) -> Any:
        if isinstance(tool_use, dict):
            return tool_use.get("input", {})
        return getattr(tool_use, "input", {})

    def _append(self, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_json(payload) + "\n")

    def before_tool(self, event: BeforeToolCallEvent) -> None:
        name = self._name(event.tool_use)
        if name not in self.ALLOWED:
            event.cancel_tool = f"Commercial Decision Relay forbids unapproved tool {name!r}."
            return
        payload = canonical_json(self._input(event.tool_use)).encode("utf-8")
        self._append({
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "phase": "before",
            "tool": name,
            "input_sha256": sha256(payload).hexdigest(),
        })

    def after_tool(self, event: AfterToolCallEvent) -> None:
        exception = getattr(event, "exception", None)
        cancel_message = getattr(event, "cancel_message", None)
        cancelled = bool(cancel_message)
        self._append({
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "phase": "after",
            "tool": self._name(event.tool_use),
            "ok": exception is None and not cancelled,
            "cancelled": cancelled,
            "exception_type": type(exception).__name__ if exception is not None else None,
            "duration_seconds": event.duration,
        })


def _openai_model():
    from strands.models.openai import OpenAIModel

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --provider openai")
    return OpenAIModel(
        client_args={"api_key": api_key},
        model_id=os.environ.get("DECISION_RELAY_MODEL_ID", "gpt-4o-mini"),
        params={"temperature": 0.0, "max_tokens": 1200},
    )


def build_agent(
    *,
    provider: str = "bedrock",
    audit_path: str | Path = ".relay/audit.jsonl",
    batch: dict[str, Any] | None = None,
    evaluated_at: str | None = None,
    model: Any | None = None,
) -> Agent:
    if batch is None:
        raise DecisionRelayError(
            "trusted_batch_required",
            "production agent construction requires caller-supplied trusted preloaded evidence",
        )
    if evaluated_at is None:
        raise DecisionRelayError(
            "trusted_time_required",
            "preloaded agent evidence requires caller-supplied evaluated_at",
        )

    engine = CurrentRelayEngine()
    engine.ingest(batch)
    engine.reconcile(evaluated_at=evaluated_at)

    toolbox = RelayToolbox(
        engine,
        trusted_evaluated_at=evaluated_at,
        ingest_locked=True,
    )
    kwargs: dict[str, Any] = {
        "name": "commercial_decision_relay",
        "description": "Evidence-bound professional agent that surfaces only real commercial decisions.",
        "system_prompt": SYSTEM_PROMPT,
        "tools": [
            toolbox.ingest_batch,
            toolbox.reconcile_evidence,
            toolbox.decision_queue,
            toolbox.explain_blocker,
            toolbox.verify_current_receipt,
        ],
        "hooks": [AuditHooks(audit_path)],
    }
    if model is not None:
        kwargs["model"] = model
    elif provider == "openai":
        kwargs["model"] = _openai_model()
    elif provider != "bedrock":
        raise ValueError("provider must be 'bedrock' or 'openai'")
    return Agent(**kwargs)
