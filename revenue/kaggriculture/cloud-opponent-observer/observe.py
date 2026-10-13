"""Offline activation telemetry for the unchanged, pinned COK V10 opponent.

Consumes the existing T07 source bank and cloud-pack official loader. There is
one original controller call per act; no monkey-patching or controller reset.
Only public routing inputs and detached controller state enter the report.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from typing import Any

SOURCE_SHA256 = "56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109"
SOURCE_COMMIT = "7ef67eac458cd9ecd13786063e2e581fbe7403ec"
SCHEMA = "cok-activation-v1"


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def load_official(pack: Path):
    path = Path(pack).resolve(strict=True) / "official.py"
    spec = importlib.util.spec_from_file_location("cok_observer_official", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the supplied cloud-pack/official.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CokObserver:
    """One instance per actor/match; act returns the original action unchanged.

    last_record is replaced after each call. Only the latest record is retained;
    a caller may stream records without an ever-growing runtime buffer. This is
    an evaluation instrument, not a new policy or a source of opponent secrets.
    """

    def __init__(self, source: str | Path, pack: str | Path):
        self.source = Path(source).resolve(strict=True)
        source_bytes = self.source.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
            raise ValueError("COK source differs from the declared T07 revision")
        self.official = load_official(Path(pack))
        self.contract = self.official.contract()
        self.call, _ = self.contract["build_agent"](str(self.source), {}, "kaggriculture")
        # Bind the declared identity to the text the existing lazy loader will
        # compile, not a separate earlier path read. No policy executes here.
        captured = inspect.getclosurevars(self.call).nonlocals.get("raw_agent")
        if captured != source_bytes.decode("utf-8"):
            raise ValueError("COK source changed while the official loader captured it")
        self.last_record: dict[str, Any] | None = None
        self.calls = 0
        self._last_route: dict[int, str | None] = {}

    def _globals(self):
        # build_agent's preserved lazy closure holds the actual selected callable.
        raw = inspect.getclosurevars(self.call).nonlocals.get("agent")
        return raw.__globals__ if raw is not None else None

    @staticmethod
    def _route(namespace, seat):
        selected = namespace.get("_ACTIONS")
        if selected is namespace["_V5_HIGH_ACTIONS"]:
            return "v5/high"
        if selected is namespace["_V5_LOW_ACTIONS"]:
            return "v5/low"
        for family in ("CURRENT", "LEGACY"):
            for label, actions in namespace[f"_V7_{family}_ROUTES"].items():
                if selected is actions:
                    return f"v7/{family.lower()}/{label}"
        return None

    def act(self, observation: Any, configuration: Any = None):
        obs = self.contract["structify"](copy.deepcopy(observation))
        cfg = self.contract["structify"](copy.deepcopy(configuration or {}))
        before = self._globals()
        previous = copy.deepcopy(before.get("_ROUTE_STATE", {})) if before else {}
        cached = False
        if before is not None:
            try:
                seat = before["_seat"](obs)
                step = max(0, int(before["_get"](obs, "step", 0) or 0))
                cache = before["_ACTION_CACHE"][seat]
                signature = before["_action_cache_signature"](obs)
                cached = bool(step > 0 and signature is not None
                              and int(cache.get("step", -1)) == step
                              and cache.get("signature") == signature
                              and cache.get("action") is not None)
            except (TypeError, ValueError, AttributeError, KeyError, OverflowError):
                pass
        # Exactly one call through the original official loading/slicing road.
        action = self.call(obs, cfg)
        self.calls += 1
        record: dict[str, Any] = {
            "schema": SCHEMA, "source_sha256": SOURCE_SHA256,
            "source_commit": SOURCE_COMMIT, "call_index": self.calls,
            "action_sha256": digest(action), "cached_retry": cached,
            "telemetry_error": None,
        }
        try:
            ns = self._globals()
            seat = ns["_seat"](obs)
            raw_step = ns["_get"](obs, "step", None)
            step = max(0, int(raw_step or 0))
            state = copy.deepcopy(ns["_ROUTE_STATE"][seat])
            old = previous.get(seat, {})
            reset = step == 0 or step < int(old.get("last_step", -1))
            previous_gate = None if reset else old.get("v5_gate")
            # Source helpers are pure reads of public data, not a second policy.
            farms = ns["_get"](obs, "farms", None)
            own = farms[seat] if isinstance(farms, (list, tuple)) and len(farms) > seat else {}
            rival = farms[1-seat] if isinstance(farms, (list, tuple)) and len(farms) > 1 else {}
            counts = ns["_v10_opening_tile_counts"](rival)
            features = {
                "shops": list(ns["_public_shops"](obs)),
                "own_money": ns["_v10_public_money"](own),
                "rival_money": ns["_v10_public_money"](rival),
                "rival_opening_tiles": None if counts is None else {
                    k: int(counts[k]) for k in ("COW", "SHEEP", "WHEAT", "MELON")},
            }
            route = self._route(ns, seat)
            # On a cached retry the source's global _ACTIONS can belong to a
            # different seat. Use this actor's previously observed route instead.
            if cached:
                route = self._last_route.get(seat)
            self._last_route[seat] = route
            record.update({
                "seat": seat, "observed_step": raw_step,
                "controller_step": step, "step_present": raw_step is not None,
                "reset_observed": reset,
                "public_features": features,
                "predicate_matches_now": bool(ns["_v10_should_use_v5"](obs)),
                "gate_evaluated_this_call": step == 72 and not cached,
                "gate_before": previous_gate, "gate_after": state.get("v5_gate"),
                "gate_changed": previous_gate != state.get("v5_gate"),
                "expert_before": None if reset else old.get("v5_expert"),
                "expert_after": state.get("v5_expert"),
                "route": route, "route_state": state,
            })
        except (TypeError, ValueError, AttributeError, KeyError, IndexError, OverflowError) as exc:
            # An instrumentation issue must not turn a valid source action into
            # a different policy action. Do not serialize raw input or error text.
            record["telemetry_error"] = type(exc).__name__
        self.last_record = record
        return action


def summarize(records):
    """Aggregate activation per input match/seat, never infer scores or strength."""
    groups = {}
    for row in records:
        if row.get("schema") != SCHEMA or row.get("source_sha256") != SOURCE_SHA256:
            raise ValueError("Unexpected telemetry schema or source identity")
        key = (str(row.get("match_id", "default")), row.get("seat"))
        item = groups.setdefault(key, {"match_id": key[0], "seat": key[1],
            "calls": 0, "telemetry_errors": 0, "expected_action_mismatches": 0,
            "gate_open_calls": 0, "gate_closed_calls": 0, "gate_unknown_calls": 0,
            "gate_evaluations": 0, "cached_retries": 0, "route_counts": {},
            "gate_transitions": [], "expert_transitions": [], "steps": set()})
        item["calls"] += 1
        if row.get("telemetry_error"):
            item["telemetry_errors"] += 1
        item["expected_action_mismatches"] += row.get("expected_action_matches") is False
        gate = row.get("gate_after")
        item["gate_open_calls" if gate is True else "gate_closed_calls" if gate is False
             else "gate_unknown_calls"] += 1
        item["gate_evaluations"] += row.get("gate_evaluated_this_call") is True
        item["cached_retries"] += row.get("cached_retry") is True
        route = row.get("route")
        if route is not None:
            item["route_counts"][route] = item["route_counts"].get(route, 0) + 1
        if row.get("gate_changed"):
            item["gate_transitions"].append({"step": row.get("controller_step"),
                "before": row.get("gate_before"), "after": gate})
        if row.get("expert_before") != row.get("expert_after"):
            item["expert_transitions"].append({"step": row.get("controller_step"),
                "before": row.get("expert_before"), "after": row.get("expert_after")})
        step = row.get("observed_step")
        if type(step) is int and step >= 0:
            item["steps"].add(step)
    result = []
    for item in groups.values():
        steps = sorted(item.pop("steps"))
        item.update(unique_observed_steps=len(steps), first_step=steps[0] if steps else None,
                    last_step=steps[-1] if steps else None,
                    has_every_step_0_through_718=steps == list(range(719)))
        result.append(item)
    return {"schema": SCHEMA, "source_sha256": SOURCE_SHA256,
            "interpretation": "Activation telemetry only; no game outcomes or strength inference.",
            "actors": result}


def run_jsonl(source, pack, input_path, output_path, summary_path):
    """Replay already-delivered observations. No engine/network or new games."""
    agents, rows = {}, []
    source_paths = {Path(input_path).resolve(), Path(source).resolve()}
    destinations = {Path(output_path).resolve(), Path(summary_path).resolve()}
    if len(destinations) != 2 or destinations & source_paths:
        raise ValueError("Use distinct input, telemetry, summary and source paths")
    with Path(input_path).open(encoding="utf-8") as incoming, Path(output_path).open("w", encoding="utf-8") as outgoing:
        for number, line in enumerate(incoming, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            obs = payload["observation"]
            # A match ID keeps independent histories separate; it is metadata,
            # never passed to the original policy or added to its observation.
            match = str(payload.get("match_id", "default"))
            seat = 1 if int(obs.get("player", 0) or 0) == 1 else 0
            key = (match, seat)
            if key not in agents:
                agents[key] = CokObserver(source, pack)
            action = agents[key].act(obs, payload.get("configuration", {}))
            record = copy.deepcopy(agents[key].last_record)
            record["match_id"], record["input_line"] = match, number
            if "expected_action" in payload:
                record["expected_action_matches"] = action == payload["expected_action"]
            outgoing.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            rows.append(record)
    report = summarize(rows)
    Path(summary_path).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_jsonl(args.source, args.pack, args.input, args.output, args.summary)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f"observer: {type(exc).__name__}: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return int(any(a["telemetry_errors"] or a["expected_action_mismatches"] for a in report["actors"]))


if __name__ == "__main__":
    sys.exit(main())
