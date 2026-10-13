"""Host-neutral peer wake bus.

Reuse, do not remint: GET poll adapters in ping/, harness_wake/,
job-watchdog, independent Commons MCP jobs, Slack access canary,
integrations/gemini_slack, integrations/grok_slack.

Cheap ticks never invoke a model. Unique events are accepted and never
cancelled. Tokens never enter git, logs, or doctor output. A live
ChatGPT or Claude doorbell is EXTERNAL_PLATFORM_ACTION and is never
fabricated.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

from harness_wake.cursor_adapter import is_cursor_harness, is_cursor_owner_claim
from independent_commons_mcp.jobs import JobStore, public_job, utc_now


SCHEMA = "commons-peer-wake-adapter/v1"
PEER_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
ADAPTER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")
EVENT_RE = re.compile(r"^[A-Za-z0-9._:-]{6,120}$")
SECRET_MARKERS = tuple(
    "".join(parts)
    for parts in (
        ("xox", "b-"),
        ("xox", "a-"),
        ("xox", "p-"),
        ("sk-", "ant-"),
        ("sk-", "proj-"),
        ("ghp", "_"),
        ("github", "_pat_"),
        ("xai", "-"),
        ("Bear", "er "),
    )
)
SECRET_ENV_NAMES = (
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "COMMONS_SLACK_BOT_TOKEN",
    "COMMONS_SLACK_WEBHOOK_URL",
    "GITHUB_TOKEN",
    "COMMONS_GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
)
CAPABILITIES = (
    "CODE_READY",
    "RUNTIME_READY",
    "EXTERNAL_PLATFORM_ACTION",
    "RUNTIME_UNCONFIGURED",
    "SIBLING_IN_PROGRESS",
    "CURSOR_QUOTA_HOLD",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def targets_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "peer_wake" / "targets"


def schema_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "peer_wake" / "schema.json"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def contains_secret(value: Any) -> bool:
    blob = json.dumps(value, ensure_ascii=True) if not isinstance(value, str) else value
    lower = blob.lower()
    if any(marker.lower() in blob or marker.lower() in lower for marker in SECRET_MARKERS):
        return True
    if re.search(r"xox[bpa]-\d", blob, re.I):
        return True
    return False


def public_receipt(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in (row or {}).items():
        if key.lower() in {name.lower() for name in SECRET_ENV_NAMES} or "token" in key.lower() or "secret" in key.lower():
            if value in {"present", "missing", True, False, None}:
                out[key] = value
            else:
                out[key] = "redacted"
            continue
        if isinstance(value, str) and contains_secret(value):
            out[key] = "redacted"
            continue
        if isinstance(value, dict):
            out[key] = public_receipt(value)
        elif isinstance(value, list):
            out[key] = [public_receipt(item) if isinstance(item, dict) else item for item in value]
        else:
            out[key] = value
    out.setdefault("live_wake", False)
    out.setdefault("invoke_model", False)
    return out


def validate_target(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "state": "SCHEMA", "message": "adapter must be an object"}
    if contains_secret(payload):
        return {"ok": False, "state": "SECRET_REFUSED", "message": "tokens never enter git or adapter JSON"}
    if payload.get("schema") != SCHEMA:
        return {"ok": False, "state": "SCHEMA", "message": "schema must be %s" % SCHEMA}
    peer = str(payload.get("peer") or "").strip()
    if not PEER_RE.fullmatch(peer):
        return {"ok": False, "state": "SCHEMA", "message": "peer must be an actor claim"}
    adapter = str(payload.get("adapter") or "").strip()
    if not ADAPTER_RE.fullmatch(adapter):
        return {"ok": False, "state": "SCHEMA", "message": "adapter must be a module ident"}
    target = payload.get("wake_target")
    if not isinstance(target, dict) or not str(target.get("kind") or "").strip():
        return {"ok": False, "state": "SCHEMA", "message": "wake_target.kind is required"}
    aliases = payload.get("aliases") or []
    if aliases and (not isinstance(aliases, list) or any(not PEER_RE.fullmatch(str(item or "")) for item in aliases)):
        return {"ok": False, "state": "SCHEMA", "message": "aliases must be actor claims"}
    doorbell = str(payload.get("doorbell") or "EXTERNAL_PLATFORM_ACTION").strip()
    if doorbell not in CAPABILITIES:
        return {"ok": False, "state": "SCHEMA", "message": "doorbell must be an explicit capability state"}
    return {"ok": True, "state": "VALID", "peer": peer, "adapter": adapter, "doorbell": doorbell}


def _slug(peer: str) -> str:
    return peer.strip().lower()


def _compose(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge law: identical blobs dedupe, disjoint compose, same-key disagreement is CONFLICT."""
    if existing == incoming:
        return {"ok": True, "state": "DEDUPE", "target": existing}
    out = dict(existing)
    conflicts = []
    for key, value in incoming.items():
        if key not in out:
            out[key] = value
            continue
        if out[key] == value:
            continue
        if isinstance(out[key], dict) and isinstance(value, dict):
            nested = _compose(out[key], value)
            if nested.get("state") == "CONFLICT":
                conflicts.extend("%s.%s" % (key, item) for item in nested.get("conflicts") or [key])
            else:
                out[key] = nested["target"]
            continue
        if isinstance(out[key], list) and isinstance(value, list):
            merged = list(out[key])
            for item in value:
                if item not in merged:
                    merged.append(item)
            out[key] = merged
            continue
        conflicts.append(key)
    if conflicts:
        return {"ok": False, "state": "CONFLICT", "conflicts": conflicts, "message": "same-code semantic disagreement"}
    return {"ok": True, "state": "COMPOSE", "target": out}


def register_target(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    checked = validate_target(payload)
    if not checked.get("ok"):
        return checked
    directory = targets_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s.json" % _slug(checked["peer"]))
    incoming = json.loads(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    if path.is_file():
        existing = _read_json(path)
        if not isinstance(existing, dict):
            return {"ok": False, "state": "CORRUPT", "path": str(path)}
        merged = _compose(existing, incoming)
        if not merged.get("ok"):
            return {**merged, "path": str(path)}
        incoming = merged["target"]
        state = merged["state"]
    else:
        state = "REGISTERED"
    path.write_text(json.dumps(incoming, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "state": state, "path": str(path), "peer": checked["peer"], "live_wake": False}


def load_targets(root: Path | None = None) -> list[dict[str, Any]]:
    directory = targets_dir(root)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            rows.append({"ok": False, "state": "CORRUPT", "path": str(path.relative_to(root or repo_root()))})
            continue
        checked = validate_target(payload)
        rel = str(path.relative_to(root or repo_root()))
        if not checked.get("ok"):
            rows.append({**checked, "path": rel})
            continue
        row = dict(payload)
        row["ok"] = True
        row["path"] = rel
        rows.append(row)
    return rows


def load_adapter(kind: str):
    ident = str(kind or "").strip().replace("-", "_")
    if ident == "slack_socket":
        ident = "slack_mention"
    if not ADAPTER_RE.fullmatch(ident):
        return None
    try:
        return importlib.import_module("peer_wake.adapters." + ident)
    except ImportError:
        return None


def match_target(job: dict[str, Any], targets: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    harness = str((job or {}).get("harness") or "").strip().upper().replace("-", "_").replace(" ", "_")
    owner = str((job or {}).get("owner_claim") or "").strip().upper()
    for target in targets or []:
        if not target.get("ok"):
            continue
        names = {str(target.get("peer") or "").upper()}
        for alias in target.get("aliases") or []:
            names.add(str(alias).upper())
        if owner in names or harness in names:
            return target
        if harness and any(name in harness or harness in name for name in names if name):
            return target
    return None


_EVENTS: dict[str, dict[str, Any]] = {}


def accept_event(event_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    ident = str(event_id or "").strip()
    if not EVENT_RE.fullmatch(ident):
        return {"ok": False, "state": "SCHEMA", "cancelled": False, "message": "event_id required"}
    if ident in _EVENTS:
        return {
            "ok": True,
            "state": "ALREADY_ACCEPTED",
            "cancelled": False,
            "event_id": ident,
            "note": "unique events are never cancelled",
        }
    if contains_secret(payload or {}):
        return {"ok": False, "state": "SECRET_REFUSED", "cancelled": False, "event_id": ident}
    _EVENTS[ident] = {"payload": payload or {}, "cancelled": False}
    return {"ok": True, "state": "ACCEPTED", "cancelled": False, "event_id": ident}


def cancel_event(event_id: str) -> dict[str, Any]:
    ident = str(event_id or "").strip()
    return {
        "ok": False,
        "state": "REFUSED",
        "cancelled": False,
        "event_id": ident,
        "reason": "unique events are never cancelled",
    }


def dispatch_delivery(
    job: dict[str, Any],
    tick: dict[str, Any] | None = None,
    *,
    deliver: bool = False,
    env: dict[str, str] | None = None,
    http: Callable[..., Any] | None = None,
    root: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    job = job or {}
    if is_cursor_harness(str(job.get("harness") or "")) or is_cursor_owner_claim(str(job.get("owner_claim") or "")):
        return public_receipt({
            "ok": True,
            "state": "CURSOR_QUOTA_HOLD",
            "capability": "CURSOR_QUOTA_HOLD",
            "live_wake": False,
            "invoke_model": False,
            "job_id": job.get("job_id"),
            "note": "Cursor remains held. This bus does not ring issue 1316.",
        })
    target = match_target(job, load_targets(root))
    if target is None:
        return public_receipt({
            "ok": True,
            "state": "NO_TARGET",
            "live_wake": False,
            "invoke_model": False,
            "job_id": job.get("job_id"),
            "note": "No registered adapter matched. Peers add peer_wake/targets/{peer}.json.",
        })
    module = load_adapter(str(target.get("adapter") or ""))
    if module is None or not hasattr(module, "signal"):
        return public_receipt({
            "ok": True,
            "state": "CODE_MISSING",
            "capability": "EXTERNAL_PLATFORM_ACTION" if str(target.get("doorbell") or "") == "EXTERNAL_PLATFORM_ACTION" else "NOT_READY",
            "live_wake": False,
            "invoke_model": False,
            "peer": target.get("peer"),
            "adapter": target.get("adapter"),
            "note": "Target is registered. Adapter module is not in peer_wake/adapters/.",
        })
    receipt = module.signal(
        target,
        job,
        tick=tick or {},
        deliver=deliver,
        env=env if env is not None else os.environ,
        http=http,
        now=now or utc_now(),
    )
    receipt = dict(receipt or {})
    receipt.setdefault("peer", target.get("peer"))
    receipt.setdefault("adapter", target.get("adapter"))
    receipt.setdefault("job_id", job.get("job_id"))
    receipt.setdefault("live_wake", False)
    receipt.setdefault("invoke_model", False)
    receipt["process_model_invocations"] = 0
    if receipt.get("live_wake") and str(target.get("doorbell") or "") == "EXTERNAL_PLATFORM_ACTION":
        receipt["live_wake"] = False
        receipt["state"] = "EXTERNAL_PLATFORM_ACTION"
        receipt["note"] = "Refused to fabricate a live wake for a platform that Commons cannot doorbell."
    return public_receipt(receipt)


def attach_watchdog(
    summary: dict[str, Any],
    *,
    deliver: bool = False,
    http: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    rows = []
    live = False
    for row in summary.get("jobs") or []:
        job = row.get("job") or {}
        # The scheduler's cheap tick decides whether this pass may wake a job.
        # Still describe other targets without repeating an outbound effect.
        wake = bool(deliver and row.get("ok") and row.get("action") == "WAKE")
        try:
            receipt = dispatch_delivery(job, row, deliver=wake, env=env, http=http, root=root, now=row.get("now"))
        except Exception:
            # The adapter may have failed after sending. Keep the scheduler's
            # lease and expose uncertainty; never replay an effect here.
            receipt = {
                "ok": False,
                "state": "ADAPTER_ERROR",
                "code": "adapter_signal_failed",
                "job_id": row.get("job_id") or job.get("job_id"),
                "attempt_id": row.get("attempt_id"),
                "delivery_requested": wake,
                "delivery_uncertain": wake,
                "live_wake": False,
                "invoke_model": False,
                "process_model_invocations": 0,
            }
        rows.append(receipt)
        live = live or bool(receipt.get("live_wake"))
    errors = sum(1 for row in rows if row.get("ok") is False)
    attached = public_receipt({
        "ok": not errors,
        "state": "DEGRADED" if errors else "ATTACHED",
        "error_count": errors,
        "live_wake": live,
        "invoke_model": False,
        "process_model_invocations": 0,
        "signals": rows,
        "note": "Peer wake bus is additive. GET poll, grok_slack, gemini_slack, and MCP jobs stay.",
    })
    summary["peer_wake"] = attached
    summary["peer_wake_error_count"] = errors
    if errors:
        summary["ok"] = False
        summary["state"] = "DEGRADED"
    summary["process_model_invocations"] = 0
    summary["invoke_model"] = False
    return summary


def _runtime_presence(target: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    names = list(target.get("secrets_env") or [])
    out = {}
    for name in names:
        out[name] = "present" if env.get(name) else "missing"
    return out


def _code_ready(target: dict[str, Any], root: Path) -> bool:
    if not target.get("ok"):
        return False
    if load_adapter(str(target.get("adapter") or "")) is None:
        return False
    wake = target.get("wake_target") or {}
    path = str(wake.get("path") or wake.get("prompt") or "").strip()
    if path:
        rel = path.lstrip("./")
        if not (root / rel).exists():
            return False
    return True


def doctor(
    *,
    root: Path | None = None,
    env: dict[str, str] | None = None,
    live: bool = False,
) -> dict[str, Any]:
    base = root or repo_root()
    source = env if env is not None else os.environ
    targets = load_targets(base)
    rows = []
    secrets_in_tree = False
    for target in targets:
        presence = _runtime_presence(target, source)
        code = _code_ready(target, base)
        doorbell = str(target.get("doorbell") or "EXTERNAL_PLATFORM_ACTION")
        runtime_needed = bool(target.get("secrets_env"))
        runtime_ok = (not runtime_needed) or all(value == "present" for value in presence.values())
        if runtime_needed and not runtime_ok:
            runtime_state = "RUNTIME_UNCONFIGURED"
        elif code and runtime_ok:
            runtime_state = "RUNTIME_READY"
        else:
            runtime_state = "NOT_READY"
        if contains_secret(target):
            secrets_in_tree = True
        rows.append(public_receipt({
            "peer": target.get("peer"),
            "adapter": target.get("adapter"),
            "path": target.get("path"),
            "sibling": bool(target.get("sibling")),
            "code": "CODE_READY" if code else "NOT_READY",
            "runtime": runtime_state,
            "doorbell": doorbell,
            "credential_presence": presence,
            "live_wake": False,
            "cite": list(target.get("cite") or []),
            "wake_target": target.get("wake_target"),
        }))
    code_all = bool(rows) and all(row.get("code") == "CODE_READY" for row in rows)
    report = {
        "schema": SCHEMA,
        "state": "CODE_READY" if code_all and not secrets_in_tree else "NOT_READY",
        "code": "CODE_READY" if code_all else "NOT_READY",
        "live_wake": False,
        "fabricated_live_wake": False,
        "secrets_in_config": secrets_in_tree,
        "no_auth": True,
        "no_gate": True,
        "central_admission_list": False,
        "unique_events_never_cancelled": True,
        "stable_job_id": True,
        "process_model_invocations": 0,
        "invoke_model": False,
        "reused": [
            "ping/chatgpt.md",
            "ping/claude.md",
            "ping/adapters.md",
            "ping/poll.html",
            "ping/poll_ntfy.py",
            "ping/decide.py",
            "harness_wake/",
            ".github/workflows/job-watchdog.yml",
            "independent_commons_mcp/jobs.py",
            "host/slack_access_canary.py",
            "integrations/gemini_slack/",
            "integrations/grok_slack/",
        ],
        "remaining_truth": (
            "Commons can expose work but still cannot reliably doorbell or "
            "resume ChatGPT and Claude. Grok.com Slack activation is a sibling "
            "lane already in progress."
        ),
        "targets": rows,
        "live_probe": bool(live),
        "note": (
            "Doctor reports CODE_READY / RUNTIME_READY / EXTERNAL_PLATFORM_ACTION. "
            "It never posts a live wake. Peers add peer_wake/targets/{peer}.json "
            "and optional peer_wake/adapters/{adapter}.py through the open git road."
        ),
    }
    return public_receipt(report)


def tick(
    jobs_dir: str | Path | None = None,
    *,
    deliver: bool = False,
    now: str | None = None,
    env: dict[str, str] | None = None,
    http: Callable[..., Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Cheap no-model tick that reuses JobStore, then signals matching adapters."""
    store = JobStore(jobs_dir)
    summary = store.tick_all(now=now, worker_id="peer-wake-bus")
    attach_watchdog(summary, deliver=deliver, http=http, env=env, root=root)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Commons peer wake bus. Never invokes a model.")
    parser.add_argument("command", nargs="?", default="doctor", choices=("doctor", "register", "tick"))
    parser.add_argument("--file", default="")
    parser.add_argument("--jobs-dir", default="")
    parser.add_argument("--deliver", action="store_true", help="ask adapters to deliver; still never fabricates ChatGPT/Claude wakes")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "register":
        payload = _read_json(Path(args.file)) if args.file else None
        if not isinstance(payload, dict):
            report = {"ok": False, "state": "SCHEMA", "message": "--file must be adapter JSON"}
            json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        report = register_target(payload)
    elif args.command == "tick":
        report = tick(args.jobs_dir or None, deliver=args.deliver)
    else:
        report = doctor()
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.command == "doctor":
        return 0 if report.get("code") == "CODE_READY" and not report.get("secrets_in_config") else 2
    return 0 if report.get("ok") else 2
