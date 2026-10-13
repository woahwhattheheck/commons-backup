"""Execute capability routes through an existing runtime tool bridge.

Native ChatGPT tools use dispatch/resume; Python/MCP consumers supply an invoker
or a JSON subprocess bridge to run the same loop automatically. Provider limits
are stored in private runtime state, never in the public capability catalog.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from integrations.shared_equipment.outcomes import effect_uncertain, tool_failed
from integrations.shared_equipment.provider_io import EquipmentError, redacted
from integrations.shared_equipment.services import plan_capability_fallback


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _time(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise EquipmentError("runtime timestamps require a timezone")
    return parsed.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def load_routes(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value if isinstance(value, list) else value["tool_fleet"]["free_pool_routes"]


def _envelopes(value):
    """Read transport metadata only, not a job status buried in returned data."""
    if isinstance(value, dict):
        yield value
        for key in ("structuredContent", "result", "error"):
            child = value.get(key)
            if isinstance(child, dict):
                yield from _envelopes(child)


def response_evidence(value):
    if not isinstance(value, dict):
        raise EquipmentError("provider response must be a JSON object")
    failed = tool_failed(value)
    evidence = {"observed_at": _iso(_now()), "uncertain": effect_uncertain(value)}
    for envelope in _envelopes(value):
        for key in ("http_status", "retry_after", "retry_not_before", "quota_remaining",
                    "rate_limit_remaining", "rate_limit_reset", "rate_limit_buckets",
                    "rate_limit_kind", "rate_limit_resource",
                    "delivered", "effect", "code", "error_code"):
            if key in envelope and envelope[key] is not None:
                evidence.setdefault(key, envelope[key])
        status = envelope.get("status")
        if isinstance(status, int) and not isinstance(status, bool):
            evidence.setdefault("http_status", status)
        # Native MCP failures carry HTTP status in a typed error_data envelope.
        # Do not treat returned job data or arbitrary error codes as transport status.
        native_error = envelope.get("error_data")
        if failed and isinstance(native_error, dict) and native_error.get("type") == "http_error":
            if native_error.get("code") is not None:
                evidence.setdefault("http_status", native_error["code"])
        for header_field in ("headers", "rate_limit_headers"):
            headers = envelope.get(header_field)
            if not isinstance(headers, dict):
                continue
            for key, item in headers.items():
                key = str(key).lower()
                if key == "retry-after":
                    evidence.setdefault("retry_after", item)
                elif key == "x-ratelimit-remaining":
                    evidence.setdefault("rate_limit_remaining", item)
                elif key == "x-ratelimit-reset":
                    evidence.setdefault("rate_limit_reset", item)
                elif key == "x-ratelimit-limit":
                    window = re.search(r"(?:^|;)w=(\d+)", str(item))
                    if window:
                        evidence.setdefault("rate_limit_window_seconds", int(window.group(1)))
                else:
                    bucket = re.fullmatch(r"x-ratelimit-(remaining|reset)-(requests|tokens)", key)
                    if bucket:
                        field, name = bucket.groups()
                        evidence.setdefault("rate_limit_buckets", {}).setdefault(name, {}).setdefault(field, item)
    status = evidence.get("http_status")
    if status is not None and (isinstance(status, bool) or not isinstance(status, int)
                               or not 100 <= status <= 599):
        raise EquipmentError("provider http_status must be an HTTP status integer")
    evidence["failed"] = failed or bool(status and status >= 400)
    # A permission 403 is not quota exhaustion. Read rate-refusal prose only
    # from failed transport envelopes, never from returned jobs or page bodies.
    if evidence["failed"] and status in {403, 429}:
        messages = []
        for envelope in _envelopes(value):
            for key in ("message", "error"):
                if isinstance(envelope.get(key), str):
                    messages.append(envelope[key].lower())
            native_error = envelope.get("error_data")
            if isinstance(native_error, dict) and isinstance(native_error.get("message"), str):
                messages.append(native_error["message"].lower())
        secondary = any(term in message for message in messages
                        for term in ("secondary rate limit", "abuse detection mechanism"))
        primary = any("api rate limit exceeded" in message for message in messages)
        if secondary:
            evidence["rate_limit_kind"] = "secondary"
        elif primary:
            evidence["rate_limit_kind"] = "primary"
        code = str(evidence.get("code", evidence.get("error_code", ""))).lower()
        evidence["rate_limited"] = bool(status == 429 or secondary or primary
            or evidence.get("rate_limit_kind") in ("primary", "secondary")
            or code in {"github_rate_limited", "rate_limited", "rate_limit_exceeded"}
            or evidence.get("rate_limit_remaining") in (0, "0")
            or evidence.get("retry_after") is not None)
    return evidence


def project_rail_health(routes, state):
    """Project typed observations only; none establishes current recovery."""
    now = _now()

    def timestamp(value):
        if not isinstance(value, str):
            return None
        try:
            return _iso(_time(value))
        except (ValueError, TypeError, OverflowError, EquipmentError):
            return None

    def balance(value):
        return value if (type(value) in (int, float) and math.isfinite(value)
                         and value >= 0) else None

    domains = {}
    for route in routes:
        domain = route["quota_domain"]
        row = domains.setdefault(domain, {"quota_domain": domain, "route_ids": []})
        row["route_ids"].append(route["id"])
    pending_by_domain = dict.fromkeys(domains, 0)
    for operation in state.get("operations", {}).values():
        domain = (operation.get("pending") or {}).get("quota_domain")
        if isinstance(domain, str) and domain in pending_by_domain:
            pending_by_domain[domain] += 1
    for domain, row in domains.items():
        limits = state.get("quota_domains", {}).get(domain, {})
        raw = limits.get("last_response", {})
        raw = raw if isinstance(raw, dict) else {}
        last = {}
        observed = timestamp(raw.get("observed_at"))
        if observed:
            last["observed_at"] = observed
        for key in ("failed", "uncertain", "rate_limited"):
            if type(raw.get(key)) is bool:
                last[key] = raw[key]
        status = raw.get("http_status")
        if type(status) is int and 100 <= status <= 599:
            last["http_status"] = status
        if raw.get("rate_limit_kind") in ("primary", "secondary"):
            last["rate_limit_kind"] = raw["rate_limit_kind"]
        if raw.get("rate_limit_resource") in ("core", "search", "graphql", "integration_manifest", "code_search"):
            last["rate_limit_resource"] = raw["rate_limit_resource"]
        row["last_response"] = last
        row["last_response_known"] = bool(observed and "failed" in last and "uncertain" in last)
        row["current_provider_health"] = "unknown"
        for key in ("observed_at", "quota_observed_at", "reset_at",
                    "cooldown_until", "client_cooldown_until"):
            row[key] = timestamp(limits.get(key))
        row["quota_remaining"] = balance(limits.get("quota_remaining"))
        kind = limits.get("quota_remaining_kind")
        row["quota_remaining_kind"] = kind if kind in ("quota", "requests") else None
        row["client_backoff_attempts"] = (
            limits.get("client_backoff_attempts") if type(limits.get("client_backoff_attempts")) is int
            and limits["client_backoff_attempts"] >= 0 else None)
        row["request_budget_known"] = bool(kind == "requests"
            and row["quota_remaining"] is not None and row["quota_observed_at"])
        row["request_budget_remaining"] = row["quota_remaining"] if row["request_budget_known"] else None
        row["request_budget_observed_at"] = row["quota_observed_at"] if row["request_budget_known"] else None
        reset = _time(row["reset_at"])
        row["request_budget_window_expired"] = bool(reset and reset <= now) if reset else None
        row["rate_limit_buckets"] = {}
        for name, bucket in limits.get("rate_limit_buckets", {}).items():
            if name not in ("requests", "tokens") or not isinstance(bucket, dict):
                continue
            row["rate_limit_buckets"][name] = {
                "remaining": balance(bucket.get("remaining")),
                "reset_at": timestamp(bucket.get("reset_at")),
                "observed_at": timestamp(bucket.get("observed_at"))}
        deadlines = [_time(row[key]) for key in
                     ("cooldown_until", "client_cooldown_until")]
        row["cooldown_active"] = any(value and value > now for value in deadlines)
        row["cooldown_observation_known"] = bool(row["last_response_known"] or any(deadlines))
        row["pending_dispatches"] = pending_by_domain[domain]
    return {"decision": "RAIL_HEALTH", "observed_at": _iso(now),
            "provider_calls": 0, "rails": list(domains.values()),
            "identity_basis": "Configured quota-domain and route IDs only; no actor inference.",
            "scope": "This private runtime journal only; expired deadlines and past success do not establish recovery."}


class ConnectedToolRouter:
    """One operation journal and cooldown map shared by all bridge consumers."""

    def __init__(self, routes: list[dict], state_file: str | Path):
        self.routes = copy.deepcopy(routes)
        self.state_file = Path(state_file).expanduser().resolve()

    @contextmanager
    def _state(self, *, write=True):
        self.state_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.state_file.with_suffix(self.state_file.suffix + ".lock")
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.chmod(lock_path, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            state = json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else {
                "schema": "commons.connected_tool_runtime.v1", "quota_domains": {}, "operations": {}}
            if state.get("schema") != "commons.connected_tool_runtime.v1":
                raise EquipmentError("unsupported runtime state schema")
            yield state
            if not write:
                return
            serialized = json.dumps(state, ensure_ascii=False, allow_nan=False)
            temporary = None
            try:
                fd, temporary = tempfile.mkstemp(prefix=".router-", dir=self.state_file.parent)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    os.chmod(temporary, 0o600)
                    stream.write(serialized)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.state_file)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        finally:
            os.close(descriptor)

    def _routes_for(self, request, state, operation):
        rows = copy.deepcopy(self.routes)
        bindings = request.get("bindings", {})
        if not isinstance(bindings, dict):
            raise EquipmentError("bindings must map route IDs to tool/arguments objects")
        for row in rows:
            limits = state["quota_domains"].get(row["quota_domain"], {})
            reset_at = _time(limits.get("reset_at"))
            if reset_at and reset_at <= _now():
                limits = {key: value for key, value in limits.items()
                          if key not in {"quota_remaining", "reset_at"}}
            row.update({key: limits[key] for key in ("cooldown_until", "quota_remaining") if key in limits})
            client_deadline = _time(limits.get("client_cooldown_until"))
            if client_deadline:
                provider_deadline = _time(row.get("cooldown_until"))
                row["cooldown_until"] = _iso(max(provider_deadline, client_deadline)
                                              if provider_deadline else client_deadline)
                row["client_cooldown_policy"] = copy.deepcopy(limits.get("client_cooldown_policy"))
            for bucket in limits.get("rate_limit_buckets", {}).values():
                reset_at = _time(bucket.get("reset_at"))
                if reset_at and reset_at <= _now():
                    continue
                if bucket.get("remaining") == 0:
                    if reset_at:
                        existing = _time(row.get("cooldown_until"))
                        row["cooldown_until"] = _iso(max(existing, reset_at) if existing else reset_at)
                    else:
                        row["quota_remaining"] = 0
            binding = bindings.get(row["id"], {})
            if not isinstance(binding, dict):
                raise EquipmentError("each runtime binding must be an object")
            tool = binding.get("tool", row.get("native_tool"))
            arguments = binding.get("arguments", request.get("arguments_by_route", {}).get(row["id"]))
            if tool is not None and (not isinstance(tool, str) or not tool.strip()):
                raise EquipmentError("runtime tool names must be nonempty strings")
            if tool and isinstance(arguments, dict):
                # Free economics belong to the observed method, not the whole
                # provider. An arbitrary runtime binding cannot inherit them.
                observed_tools = row.get("native_tools", {})
                observed_methods = ({method for method in observed_tools.values() if isinstance(method, str)}
                                    if isinstance(observed_tools, dict) else set())
                if isinstance(row.get("native_tool"), str):
                    observed_methods.add(row["native_tool"])
                if tool not in observed_methods:
                    row["free_plan_verified"] = False
                    row["zero_net_spend_verified"] = False
                row["native_tool"] = tool
                row["binding_state"] = "callable"
            else:
                row["binding_state"] = "runtime_arguments_required"
            domain = request.get("task_domain")
            domains = binding.get("task_domains", row.get("task_domains", []))
            if not isinstance(domains, list) or any(not isinstance(item, str) or not item for item in domains):
                raise EquipmentError("task_domains must be an array of nonempty strings")
            if domain and domain not in domains and "*" not in domains:
                row["binding_state"] = "task_domain_mismatch"
            if row["id"] in operation["attempted_routes"]:
                row["binding_state"] = "attempted_this_operation"
        return rows

    def _next(self, request, state, operation):
        if operation.get("terminal"):
            return copy.deepcopy(operation["terminal"])
        if operation.get("pending"):
            return {"decision": "AWAITING_PROVIDER_RESPONSE", "operation_id": request["operation_id"],
                    "dispatch_id": operation["pending"]["dispatch_id"],
                    "route_id": operation["pending"]["route_id"], "provider_calls": 0}
        rows = self._routes_for(request, state, operation)
        selector = {"routes": rows, "capability": request["capability"],
                    "operation_id": request["operation_id"], "effect": request.get("effect", "read"),
                    "previous_effect": request.get("previous_effect", "none"),
                    "input_sensitivity": request.get("input_sensitivity", "public")}
        last = operation.get("last_failure")
        if last:
            selector.update(failed_route=last["route_id"], failure=last["evidence"])
        plan = plan_capability_fallback(selector)
        attempted_domains = {next(row["quota_domain"] for row in self.routes if row["id"] == route_id)
                             for route_id in operation["attempted_routes"]}
        choices = [row for row in plan["candidates"]
                   if not row["reasons"] and row["quota_domain"] not in attempted_domains]
        # Distinct quota domains are useful even when backend independence is
        # unknown. Preserve the distinction rather than inflating the pool count.
        if not choices or len(operation["attempted_routes"]) >= request.get("max_attempts", 8):
            result = {"decision": plan["decision"] if not choices else "ATTEMPT_LIMIT_REACHED",
                      "operation_id": request["operation_id"], "attempted_routes": operation["attempted_routes"],
                      "plan": plan, "provider_calls": 0}
            if result["decision"] == "USE_READY_ROUTE":
                result["decision"] = "NO_UNTRIED_QUOTA_DOMAIN"
            return result
        preferred = request.get("preferred_route")
        # Spread distinct operations over available domains before one provider
        # returns 429. These are actual local dispatch counts, not inferred
        # provider limits; nothing sleeps and direct tool use stays available.
        moment = _now()
        recent_since = moment - timedelta(seconds=60)
        pending_by_domain = dict.fromkeys((row["quota_domain"] for row in choices), 0)
        for item in state["operations"].values():
            domain = (item.get("pending") or {}).get("quota_domain")
            if isinstance(domain, str) and domain in pending_by_domain:
                pending_by_domain[domain] += 1
        pressure = {}
        for domain, pending in pending_by_domain.items():
            recent = state["quota_domains"].get(domain, {}).get("recent_dispatches", [])
            count = sum(1 for stamp in recent if _time(stamp) >= recent_since)
            pressure[domain] = (pending, count)
        choice = next((row for row in choices if row["id"] == preferred), None)
        if choice is None:
            choice = min(choices, key=lambda row: pressure[row["quota_domain"]])
        limits = state["quota_domains"].setdefault(choice["quota_domain"], {})
        recent = [stamp for stamp in limits.get("recent_dispatches", []) if _time(stamp) >= recent_since]
        limits["recent_dispatches"] = [*recent, _iso(moment)]
        binding = request.get("bindings", {}).get(choice["id"], {})
        arguments = binding.get("arguments", request.get("arguments_by_route", {}).get(choice["id"]))
        dispatch = {"decision": "DISPATCH", "operation_id": request["operation_id"],
                    "dispatch_id": uuid.uuid4().hex, "route_id": choice["id"],
                    "tool": choice["native_tool"], "arguments": arguments,
                    "quota_domain": choice["quota_domain"], "backend": choice["backend"],
                    "shared_backend_with_failed": choice["shared_backend_with_failed"],
                    "backend_independence_known": choice["backend_independence_known"],
                    "effect": request.get("effect", "read"), "created_at": _iso(_now()),
                    "selection": {"pending_in_domain": pressure[choice["quota_domain"]][0],
                                  "dispatches_in_last_minute": pressure[choice["quota_domain"]][1]},
                    "provider_calls": 0, "invocation_required": True}
        operation["pending"] = dispatch
        return copy.deepcopy(dispatch)

    def dispatch(self, request: dict):
        if not isinstance(request, dict):
            raise EquipmentError("dispatch request must be an object")
        for key in ("operation_id", "capability"):
            if not isinstance(request.get(key), str) or not request[key].strip():
                raise EquipmentError(key + " must be a nonempty string")
        attempts = request.get("max_attempts", 8)
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 32:
            raise EquipmentError("max_attempts must be an integer from 1 to 32")
        if not isinstance(request.get("arguments_by_route", {}), dict):
            raise EquipmentError("arguments_by_route must be an object")
        if "task_domain" in request and (not isinstance(request["task_domain"], str) or not request["task_domain"]):
            raise EquipmentError("task_domain must be a nonempty string")
        request = copy.deepcopy(request)
        # An explicit new write starts with no prior effect. A caller recovering
        # an existing write must supply its actual accepted/unknown state.
        request.setdefault("previous_effect", "none")
        fingerprint = _digest(request)
        with self._state() as state:
            operation = state["operations"].get(request["operation_id"])
            if operation and operation["request_digest"] != fingerprint:
                previous = operation["request"]
                routing_fields = {"bindings", "arguments_by_route", "max_attempts", "preferred_route", "previous_effect"}
                previous_intent = {key: value for key, value in previous.items() if key not in routing_fields}
                current_intent = {key: value for key, value in request.items() if key not in routing_fields}
                if previous_intent != current_intent:
                    raise EquipmentError("operation_id already names different inputs; preserve the existing operation")
                # New connections can extend the same unfinished operation.
                # Existing route arguments remain immutable and never remint a
                # provider call already dispatched for this logical operation.
                for field in ("bindings", "arguments_by_route"):
                    prior_map, current_map = previous.get(field, {}), request.get(field, {})
                    if not isinstance(current_map, dict):
                        raise EquipmentError(field + " must be an object")
                    if any(key in current_map and current_map[key] != value for key, value in prior_map.items()):
                        raise EquipmentError("existing route inputs changed under operation_id")
                    request[field] = {**prior_map, **current_map}
                if previous.get("previous_effect") in {"accepted", "unknown"}:
                    request["previous_effect"] = previous["previous_effect"]
                operation["request"] = request
                operation["request_digest"] = _digest(request)
            if operation is None:
                operation = {"request_digest": fingerprint, "request": request,
                             "attempted_routes": [], "responses": {}, "created_at": _iso(_now())}
                state["operations"][request["operation_id"]] = operation
            return self._next(request, state, operation)

    @staticmethod
    def _bucket_reset(value, observed):
        # Groq request/day and token/minute buckets return relative durations,
        # such as 2m59.56s and 7.66s. Keep their individual deadlines; a token
        # window is not an account credit balance or a request-day counter.
        raw = str(value).strip()
        pieces = list(re.finditer(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", raw))
        if pieces and "".join(piece.group(0) for piece in pieces) == raw:
            factors = {"ms": .001, "s": 1, "m": 60, "h": 3600, "d": 86400}
            seconds = sum(float(piece.group(1)) * factors[piece.group(2)] for piece in pieces)
            if not math.isfinite(seconds):
                raise EquipmentError("provider bucket reset duration must be finite")
            return observed + timedelta(seconds=seconds)
        try:
            return datetime.fromtimestamp(float(value), timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return _time(value)

    @staticmethod
    def _limits(evidence, current):
        limits = dict(current)
        observed = _time(evidence["observed_at"])
        limits["last_response"] = {key: evidence[key] for key in
            ("observed_at", "http_status", "failed", "uncertain", "rate_limited") if key in evidence}
        if evidence.get("rate_limit_kind") in {"primary", "secondary"}:
            limits["last_response"]["rate_limit_kind"] = evidence["rate_limit_kind"]
        if evidence.get("rate_limit_resource") in {"core", "search", "graphql", "integration_manifest", "code_search"}:
            limits["last_response"]["rate_limit_resource"] = evidence["rate_limit_resource"]
        deadline = _time(evidence.get("retry_not_before"))
        retry_after = evidence.get("retry_after")
        if retry_after is not None:
            try:
                seconds = float(retry_after)
            except (TypeError, ValueError):
                additional = parsedate_to_datetime(str(retry_after))
                if additional.tzinfo is None:
                    raise EquipmentError("Retry-After HTTP date requires a timezone")
                additional = additional.astimezone(timezone.utc)
            else:
                if not math.isfinite(seconds) or seconds < 0:
                    raise EquipmentError("Retry-After seconds must be finite and nonnegative")
                additional = observed + timedelta(seconds=seconds)
            deadline = max(deadline, additional) if deadline else additional
        existing = _time(limits.get("cooldown_until"))
        if deadline:
            limits["cooldown_until"] = _iso(max(existing, deadline) if existing else deadline)
        remaining = evidence.get("quota_remaining", evidence.get("rate_limit_remaining"))
        if remaining is not None:
            try:
                remaining = float(remaining)
            except (TypeError, ValueError):
                raise EquipmentError("provider remaining quota must be numeric") from None
            if not math.isfinite(remaining) or remaining < 0:
                raise EquipmentError("provider remaining quota must be finite and nonnegative")
            limits["quota_remaining"] = remaining
            limits["quota_observed_at"] = evidence["observed_at"]
            limits["quota_remaining_kind"] = "quota" if "quota_remaining" in evidence else "requests"
        reset = evidence.get("rate_limit_reset")
        if reset is not None:
            try:
                reset_at = datetime.fromtimestamp(float(reset), timezone.utc)
            except (TypeError, ValueError, OverflowError):
                reset_at = _time(reset)
            limits["reset_at"] = _iso(reset_at)
        elif "quota_remaining" not in evidence and "rate_limit_remaining" in evidence:
            # A provider's request-window count differs from a credit balance.
            # Expire it at the supplied deadline/window rather than leaving a
            # one-minute exhausted window permanently at zero.
            window = evidence.get("rate_limit_window_seconds")
            if deadline:
                limits["reset_at"] = _iso(deadline)
            elif isinstance(window, int) and 0 < window <= 86400:
                limits["reset_at"] = _iso(observed + timedelta(seconds=window))
        # With no provider retry deadline, a new operation must not immediately
        # hit the same observed limited domain again. This is optional bridge
        # client policy, not a claimed quota/reset or a mandatory fleet gate.
        # GitHub documents at least one minute for headerless secondary limits.
        exhausted_reset = remaining == 0 and reset is not None
        if evidence.get("rate_limited") and deadline is None and not exhausted_reset:
            previous_attempts = limits.get("client_backoff_attempts", 0)
            if type(previous_attempts) is not int or previous_attempts < 0:
                raise EquipmentError("runtime client_backoff_attempts must be a nonnegative integer")
            attempts = min(previous_attempts + 1, 32)
            seconds = min(60 * 2 ** min(attempts - 1, 4), 900)
            client_deadline = observed + timedelta(seconds=seconds)
            existing_client = _time(limits.get("client_cooldown_until"))
            limits["client_cooldown_until"] = _iso(max(existing_client, client_deadline)
                                                   if existing_client else client_deadline)
            limits["client_backoff_attempts"] = attempts
            limits["client_cooldown_policy"] = {
                "kind": "client_policy", "reason": "observed_rate_refusal_without_provider_deadline",
                "attempt": attempts, "seconds": seconds}
        elif not evidence.get("failed") and not evidence.get("uncertain"):
            # A successful response resets escalation, without declaring an
            # active cooldown or another pending request globally recovered.
            limits.pop("client_backoff_attempts", None)
        buckets = evidence.get("rate_limit_buckets", {})
        if not isinstance(buckets, dict):
            raise EquipmentError("provider rate_limit_buckets must be an object")
        if buckets:
            retained = copy.deepcopy(limits.get("rate_limit_buckets", {}))
            for name, values in buckets.items():
                if not isinstance(values, dict):
                    raise EquipmentError("provider quota bucket must be an object")
                bucket = retained.setdefault(name, {})
                if values.get("remaining") is not None:
                    try:
                        remaining = float(values["remaining"])
                    except (TypeError, ValueError):
                        raise EquipmentError("provider bucket remaining must be numeric") from None
                    if not math.isfinite(remaining) or remaining < 0:
                        raise EquipmentError("provider bucket remaining must be finite and nonnegative")
                    bucket["remaining"] = remaining
                if values.get("reset") is not None:
                    bucket["reset_at"] = _iso(ConnectedToolRouter._bucket_reset(values["reset"], observed))
                bucket["observed_at"] = evidence["observed_at"]
            limits["rate_limit_buckets"] = retained
        limits["observed_at"] = evidence["observed_at"]
        return limits

    def resume(self, operation_id: str, dispatch_id: str, response: dict):
        evidence = response_evidence(response)
        with self._state() as state:
            operation = state["operations"].get(operation_id)
            if not operation:
                raise EquipmentError("operation_id has no dispatch in this private runtime state")
            if dispatch_id in operation["responses"]:
                # The earlier result may have emitted another dispatch which
                # has already run. Return current state, never that old call.
                return self._next(operation["request"], state, operation)
            dispatch = operation.get("pending")
            if not dispatch or dispatch["dispatch_id"] != dispatch_id:
                raise EquipmentError("dispatch_id does not identify the outstanding provider call")
            domain = dispatch["quota_domain"]
            state["quota_domains"][domain] = self._limits(evidence, state["quota_domains"].get(domain, {}))
            operation["pending"] = None
            operation["attempted_routes"].append(dispatch["route_id"])
            result = {"operation_id": operation_id, "route_id": dispatch["route_id"],
                      "dispatch_id": dispatch_id, "evidence": evidence,
                      "provider_calls": 1, "attempted_routes": list(operation["attempted_routes"])}
            request = operation["request"]
            if not evidence["failed"] and not evidence["uncertain"]:
                result.update(decision="COMPLETED", result=response)
                operation["terminal"] = result
            else:
                is_write = dispatch["effect"] == "write"
                status = evidence.get("http_status")
                rejected = evidence.get("effect") == "rejected" or evidence.get("delivered") is False or bool(
                    status and 400 <= status < 500 and status not in {408, 409} and not evidence["uncertain"])
                if is_write and not rejected:
                    result.update(decision="RECONCILE_EXISTING_WRITE", result=response)
                    operation["terminal"] = result
                elif status in {400, 404, 405, 409, 413, 415, 422}:
                    result.update(decision="REQUEST_FAILED", result=response)
                    operation["terminal"] = result
                else:
                    operation["last_failure"] = {"route_id": dispatch["route_id"], "evidence": evidence}
                    request["previous_effect"] = "rejected" if is_write else "none"
                    result = self._next(request, state, operation)
                    result["previous_response"] = {"route_id": dispatch["route_id"], "evidence": evidence}
            operation["responses"][dispatch_id] = copy.deepcopy(result)
            return result

    def status(self, operation_id):
        with self._state(write=False) as state:
            operation = state["operations"].get(operation_id)
            if operation is None:
                return {"decision": "OPERATION_NOT_FOUND", "operation_id": operation_id}
            return {"operation_id": operation_id, "decision": operation.get("terminal", {}).get(
                "decision", "AWAITING_PROVIDER_RESPONSE" if operation.get("pending") else "ROUTING"),
                    "pending_dispatch_id": (operation.get("pending") or {}).get("dispatch_id"),
                    "attempted_routes": operation["attempted_routes"],
                    "quota_domains": copy.deepcopy(state["quota_domains"])}

    def rail_health(self):
        """Offline metadata only; configured identities are never inferred."""
        with self._state(write=False) as state:
            return project_rail_health(self.routes, state)

    def run(self, request: dict, invoker: Callable[[dict], dict]):
        """Run actual bridge calls, switching immediately on eligible failures."""
        result = self.dispatch(request)
        calls = 0
        while result["decision"] == "DISPATCH":
            dispatch = result
            try:
                response = invoker(copy.deepcopy(dispatch))
            except Exception as exc:
                # A bridge exception may occur after provider acceptance; writes
                # retain the pending ID for readback instead of being replayed.
                # Typed provider exceptions also carry actual rate feedback.
                # Retain that evidence instead of discarding Retry-After/status
                # and accidentally selecting the same limited pool next time.
                native = getattr(exc, "native_result", None)
                response = copy.deepcopy(native) if isinstance(native, dict) else {}
                response.update(isError=True)
                response.setdefault("code", getattr(exc, "code", type(exc).__name__))
                for attribute in ("http_status", "retry_after", "retry_not_before", "quota_remaining",
                                  "rate_limit_remaining", "rate_limit_reset", "rate_limit_resource",
                                  "rate_limit_kind", "delivered", "effect"):
                    value = getattr(exc, attribute, None)
                    if value is not None:
                        response.setdefault(attribute, value)
                failure = response_evidence(response)
                status = failure.get("http_status")
                rejected = failure.get("delivered") is False or failure.get("effect") == "rejected" or bool(
                    status and 400 <= status < 500 and status not in {408, 409} and not failure["uncertain"])
                response["uncertain"] = failure["uncertain"] or bool(getattr(exc, "uncertain", False)) or (
                    dispatch["effect"] == "write" and not rejected)
            calls += 1
            result = self.resume(dispatch["operation_id"], dispatch["dispatch_id"], response)
        result["provider_calls_this_run"] = calls
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("dispatch", "resume", "run", "status", "rail-health"))
    parser.add_argument("--routes-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True,
                        help="private runtime state outside the git checkout")
    parser.add_argument("--operation-id", help="existing ID for status")
    parser.add_argument("--provider-apis", action="store_true", help="invoke existing shared ProviderAPIs tools")
    parser.add_argument("--bridge-command", nargs=argparse.REMAINDER,
                        help="JSON stdin/stdout tool bridge; receives tool/arguments and stable operation/dispatch metadata")
    args = parser.parse_args()
    try:
        router = ConnectedToolRouter(load_routes(args.routes_file), args.state_file)
        if args.operation == "rail-health":
            result = router.rail_health()
        elif args.operation == "status":
            result = router.status(args.operation_id)
        else:
            request = json.load(sys.stdin)
            if args.operation == "dispatch":
                result = router.dispatch(request)
            elif args.operation == "resume":
                result = router.resume(request["operation_id"], request["dispatch_id"], request["response"])
            else:
                if args.provider_apis:
                    from integrations.shared_equipment.provider_apis import GroqExaEquipment
                    equipment = GroqExaEquipment()
                    from integrations.shared_equipment.free_model_apis import FreeModelEquipment
                    model_equipment = FreeModelEquipment()
                    model_tools = {item["name"] for item in model_equipment.tools()}
                    def invoker(dispatch):
                        target = model_equipment if dispatch["tool"] in model_tools else equipment
                        return target.call(dispatch["tool"], dispatch["arguments"])
                elif args.bridge_command:
                    def invoker(dispatch):
                        completed = subprocess.run(args.bridge_command, input=json.dumps(dispatch),
                                                   capture_output=True, text=True, timeout=90, check=False)
                        if completed.returncode:
                            raise EquipmentError("runtime bridge returned a nonzero exit code")
                        return json.loads(completed.stdout)
                else:
                    raise EquipmentError("run requires --provider-apis or --bridge-command")
                result = router.run(request, invoker)
        # Native arguments/results belong to the calling private runtime. Secret
        # credential fields are redacted; the state file is never published.
        print(json.dumps(redacted(result), ensure_ascii=False, allow_nan=False))
        return 0 if result["decision"] in {"DISPATCH", "COMPLETED", "AWAITING_PROVIDER_RESPONSE", "ROUTING", "RAIL_HEALTH"} else 3
    except (OSError, ValueError, KeyError, TypeError, EquipmentError) as exc:
        print(json.dumps({"isError": True, "code": "connected_router_failed", "message": redacted(str(exc))}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

