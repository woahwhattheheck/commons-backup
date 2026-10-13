from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
UTC = timezone.utc


class TemporalEvidenceError(ValueError):
    """Raised when evidence violates the temporal graph contract."""


def _parse_ts(value: str | datetime | None, *, field: str, allow_none: bool = False) -> datetime | None:
    if value is None:
        if allow_none:
            return None
        raise TemporalEvidenceError(f"{field} is required")
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise TemporalEvidenceError(f"{field} must not be empty")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise TemporalEvidenceError(f"{field} must be ISO-8601: {value!r}") from exc
    else:
        raise TemporalEvidenceError(f"{field} must be a datetime or ISO-8601 string")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise TemporalEvidenceError(f"{field} must be timezone-aware")
    return dt.astimezone(UTC)


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise TemporalEvidenceError(f"{field} must be a string")
    value = value.strip()
    if not value:
        raise TemporalEvidenceError(f"{field} must not be empty")
    if "\x00" in value:
        raise TemporalEvidenceError(f"{field} must not contain NUL")
    return value


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemporalEvidenceError("confidence must be a finite number")
    value = float(value)
    if not math.isfinite(value) or not (0.0 <= value <= 1.0):
        raise TemporalEvidenceError("confidence must be finite and within [0, 1]")
    return value


def _sha256(value: Any, *, field: str = "source_sha256") -> str:
    value = _text(value, field=field).lower()
    if not _HEX64.fullmatch(value):
        raise TemporalEvidenceError(f"{field} must be a 64-hex SHA-256")
    return value


def canonical_json(value: Any) -> str:
    """Serialize a JSON-domain value deterministically and reject non-finite numbers."""

    def walk(obj: Any) -> Any:
        if obj is None or isinstance(obj, (str, bool, int)):
            return obj
        if isinstance(obj, float):
            if not math.isfinite(obj):
                raise TemporalEvidenceError("non-finite numbers are forbidden")
            return obj
        if isinstance(obj, (list, tuple)):
            return [walk(v) for v in obj]
        if isinstance(obj, Mapping):
            out: dict[str, Any] = {}
            for key, val in obj.items():
                if not isinstance(key, str):
                    raise TemporalEvidenceError("JSON object keys must be strings")
                if key in out:
                    raise TemporalEvidenceError(f"duplicate key {key!r}")
                out[key] = walk(val)
            return out
        raise TemporalEvidenceError(f"unsupported JSON-domain type: {type(obj).__name__}")

    return json.dumps(walk(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TemporalEvidenceError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def strict_json_loads(text: str) -> Any:
    def bad_constant(value: str) -> Any:
        raise TemporalEvidenceError(f"non-finite JSON number {value!r} is forbidden")

    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=bad_constant)
    except TemporalEvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise TemporalEvidenceError(f"malformed JSON: {exc.msg}") from exc


@dataclass(frozen=True, slots=True)
class Fact:
    subject: str
    predicate: str
    object: str
    valid_from: datetime
    valid_to: datetime | None
    observed_at: datetime
    source_id: str
    source_sha256: str
    confidence: float = 1.0
    fact_id: str = ""

    @classmethod
    def create(
        cls,
        *,
        subject: str,
        predicate: str,
        object: str,
        valid_from: str | datetime,
        valid_to: str | datetime | None,
        observed_at: str | datetime,
        source_id: str,
        source_sha256: str,
        confidence: float = 1.0,
    ) -> "Fact":
        vf = _parse_ts(valid_from, field="valid_from")
        vt = _parse_ts(valid_to, field="valid_to", allow_none=True)
        obs = _parse_ts(observed_at, field="observed_at")
        if vf is None or obs is None:  # defensive for static type narrowing
            raise TemporalEvidenceError("fact timestamps are required")
        if vt is not None and not vf < vt:
            raise TemporalEvidenceError("valid_to must be strictly after valid_from")
        core = {
            "confidence": _confidence(confidence),
            "object": _text(object, field="object"),
            "observed_at": _ts(obs),
            "predicate": _text(predicate, field="predicate"),
            "source_id": _text(source_id, field="source_id"),
            "source_sha256": _sha256(source_sha256),
            "subject": _text(subject, field="subject"),
            "valid_from": _ts(vf),
            "valid_to": _ts(vt),
        }
        return cls(
            subject=core["subject"],
            predicate=core["predicate"],
            object=core["object"],
            valid_from=vf,
            valid_to=vt,
            observed_at=obs,
            source_id=core["source_id"],
            source_sha256=core["source_sha256"],
            confidence=core["confidence"],
            fact_id=digest_json(core),
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "Fact":
        required = {
            "subject", "predicate", "object", "valid_from", "valid_to",
            "observed_at", "source_id", "source_sha256", "confidence",
        }
        unknown = set(record) - (required | {"fact_id", "kind"})
        missing = required - set(record)
        if missing:
            raise TemporalEvidenceError(f"fact missing fields: {sorted(missing)}")
        if unknown:
            raise TemporalEvidenceError(f"fact has unknown fields: {sorted(unknown)}")
        fact = cls.create(**{k: record[k] for k in required})
        supplied = record.get("fact_id")
        if supplied is not None and supplied != fact.fact_id:
            raise TemporalEvidenceError("fact_id does not match canonical fact content")
        return fact

    def canonical_record(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "fact_id": self.fact_id,
            "object": self.object,
            "observed_at": _ts(self.observed_at),
            "predicate": self.predicate,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "subject": self.subject,
            "valid_from": _ts(self.valid_from),
            "valid_to": _ts(self.valid_to),
        }

    def valid_at(self, when: datetime) -> bool:
        return self.valid_from <= when and (self.valid_to is None or when < self.valid_to)


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    action: str
    target_fact_id: str
    observed_at: datetime
    source_id: str
    source_sha256: str
    replacement_fact_id: str | None = None
    event_id: str = ""

    @classmethod
    def create(
        cls,
        *,
        action: str,
        target_fact_id: str,
        observed_at: str | datetime,
        source_id: str,
        source_sha256: str,
        replacement_fact_id: str | None = None,
    ) -> "EvidenceEvent":
        action = _text(action, field="action").lower()
        if action not in {"retract", "supersede"}:
            raise TemporalEvidenceError("action must be 'retract' or 'supersede'")
        target = _sha256(target_fact_id, field="target_fact_id")
        replacement = None
        if action == "supersede":
            replacement = _sha256(replacement_fact_id, field="replacement_fact_id")
            if replacement == target:
                raise TemporalEvidenceError("supersession replacement must differ from target")
        elif replacement_fact_id is not None:
            raise TemporalEvidenceError("retract event must not have replacement_fact_id")
        obs = _parse_ts(observed_at, field="observed_at")
        if obs is None:
            raise TemporalEvidenceError("observed_at is required")
        core = {
            "action": action,
            "observed_at": _ts(obs),
            "replacement_fact_id": replacement,
            "source_id": _text(source_id, field="source_id"),
            "source_sha256": _sha256(source_sha256),
            "target_fact_id": target,
        }
        return cls(
            action=action,
            target_fact_id=target,
            observed_at=obs,
            source_id=core["source_id"],
            source_sha256=core["source_sha256"],
            replacement_fact_id=replacement,
            event_id=digest_json(core),
        )

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "EvidenceEvent":
        required = {"action", "target_fact_id", "observed_at", "source_id", "source_sha256"}
        allowed = required | {"replacement_fact_id", "event_id", "kind"}
        missing = required - set(record)
        unknown = set(record) - allowed
        if missing:
            raise TemporalEvidenceError(f"event missing fields: {sorted(missing)}")
        if unknown:
            raise TemporalEvidenceError(f"event has unknown fields: {sorted(unknown)}")
        event = cls.create(
            action=record["action"],
            target_fact_id=record["target_fact_id"],
            observed_at=record["observed_at"],
            source_id=record["source_id"],
            source_sha256=record["source_sha256"],
            replacement_fact_id=record.get("replacement_fact_id"),
        )
        supplied = record.get("event_id")
        if supplied is not None and supplied != event.event_id:
            raise TemporalEvidenceError("event_id does not match canonical event content")
        return event

    def canonical_record(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "event_id": self.event_id,
            "observed_at": _ts(self.observed_at),
            "replacement_fact_id": self.replacement_fact_id,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "target_fact_id": self.target_fact_id,
        }


class TemporalEvidenceGraph:
    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._events: dict[str, EvidenceEvent] = {}

    @property
    def facts(self) -> tuple[Fact, ...]:
        return tuple(self._facts[k] for k in sorted(self._facts))

    @property
    def events(self) -> tuple[EvidenceEvent, ...]:
        return tuple(self._events[k] for k in sorted(self._events))

    def add_fact(self, fact: Fact) -> str:
        current = self._facts.get(fact.fact_id)
        if current is not None and current != fact:
            raise TemporalEvidenceError("canonical fact ID collision")
        self._facts[fact.fact_id] = fact
        return fact.fact_id

    def assert_fact(self, **kwargs: Any) -> str:
        return self.add_fact(Fact.create(**kwargs))

    def add_event(self, event: EvidenceEvent) -> str:
        target = self._facts.get(event.target_fact_id)
        if target is None:
            raise TemporalEvidenceError("event target fact is not present")
        if event.observed_at < target.observed_at:
            raise TemporalEvidenceError("event cannot predate observation of its target fact")
        if event.action == "supersede":
            if event.replacement_fact_id is None:
                raise TemporalEvidenceError("supersession replacement is required")
            replacement = self._facts.get(event.replacement_fact_id)
            if replacement is None:
                raise TemporalEvidenceError("supersession replacement fact is not present")
            if replacement.observed_at > event.observed_at:
                raise TemporalEvidenceError("supersession cannot reference a replacement not yet observed")
        current = self._events.get(event.event_id)
        if current is not None and current != event:
            raise TemporalEvidenceError("canonical event ID collision")
        self._events[event.event_id] = event
        return event.event_id

    def retract(self, target_fact_id: str, *, observed_at: str | datetime, source_id: str, source_sha256: str) -> str:
        return self.add_event(EvidenceEvent.create(
            action="retract", target_fact_id=target_fact_id, observed_at=observed_at,
            source_id=source_id, source_sha256=source_sha256,
        ))

    def supersede(
        self,
        target_fact_id: str,
        replacement_fact_id: str,
        *,
        observed_at: str | datetime,
        source_id: str,
        source_sha256: str,
    ) -> str:
        return self.add_event(EvidenceEvent.create(
            action="supersede", target_fact_id=target_fact_id, replacement_fact_id=replacement_fact_id,
            observed_at=observed_at, source_id=source_id, source_sha256=source_sha256,
        ))

    def _inactive_ids(self, known_at: datetime) -> set[str]:
        return {
            event.target_fact_id
            for event in self._events.values()
            if event.observed_at <= known_at
        }

    def active_facts(
        self,
        *,
        valid_at: str | datetime,
        known_at: str | datetime,
        subject: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        min_confidence: float = 0.0,
    ) -> tuple[Fact, ...]:
        valid = _parse_ts(valid_at, field="valid_at")
        known = _parse_ts(known_at, field="known_at")
        if valid is None or known is None:
            raise TemporalEvidenceError("query timestamps are required")
        threshold = _confidence(min_confidence)
        inactive = self._inactive_ids(known)
        result = [
            fact for fact in self._facts.values()
            if fact.observed_at <= known
            and fact.fact_id not in inactive
            and fact.valid_at(valid)
            and fact.confidence >= threshold
            and (subject is None or fact.subject == subject)
            and (predicate is None or fact.predicate == predicate)
            and (object is None or fact.object == object)
        ]
        return tuple(sorted(result, key=lambda fact: fact.fact_id))

    def snapshot_receipt(
        self,
        *,
        valid_at: str | datetime,
        known_at: str | datetime,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        valid = _parse_ts(valid_at, field="valid_at")
        known = _parse_ts(known_at, field="known_at")
        if valid is None or known is None:
            raise TemporalEvidenceError("query timestamps are required")
        facts = self.active_facts(valid_at=valid, known_at=known, min_confidence=min_confidence)
        payload = {
            "schema": "temporal-evidence-snapshot/v1",
            "valid_at": _ts(valid),
            "known_at": _ts(known),
            "min_confidence": _confidence(min_confidence),
            "fact_count": len(facts),
            "facts": [fact.canonical_record() for fact in facts],
        }
        return {**payload, "receipt_sha256": digest_json(payload)}

    @staticmethod
    def verify_snapshot_receipt(receipt: Mapping[str, Any]) -> bool:
        expected_keys = {
            "schema", "valid_at", "known_at", "min_confidence",
            "fact_count", "facts", "receipt_sha256",
        }
        if set(receipt) != expected_keys or receipt.get("schema") != "temporal-evidence-snapshot/v1":
            return False
        try:
            valid = _parse_ts(receipt["valid_at"], field="valid_at")
            known = _parse_ts(receipt["known_at"], field="known_at")
            if valid is None or known is None:
                return False
            threshold = _confidence(receipt["min_confidence"])
            facts_raw = receipt["facts"]
            if not isinstance(facts_raw, list):
                return False
            facts = [Fact.from_record(record) for record in facts_raw]
            if len(facts) != receipt["fact_count"]:
                return False
            ids = [fact.fact_id for fact in facts]
            if ids != sorted(ids) or len(ids) != len(set(ids)):
                return False
            if any(fact.observed_at > known or not fact.valid_at(valid) or fact.confidence < threshold for fact in facts):
                return False
            payload = {key: receipt[key] for key in expected_keys if key != "receipt_sha256"}
            return digest_json(payload) == receipt["receipt_sha256"]
        except (TemporalEvidenceError, TypeError, KeyError):
            return False

    def time_respecting_path(
        self,
        start: str,
        goal: str,
        *,
        earliest: str | datetime,
        latest: str | datetime,
        known_at: str | datetime,
        predicates: Iterable[str] | None = None,
        max_hops: int = 6,
        min_confidence: float = 0.0,
    ) -> tuple[tuple[Fact, datetime], ...] | None:
        start = _text(start, field="start")
        goal = _text(goal, field="goal")
        begin = _parse_ts(earliest, field="earliest")
        end = _parse_ts(latest, field="latest")
        known = _parse_ts(known_at, field="known_at")
        if begin is None or end is None or known is None:
            raise TemporalEvidenceError("path timestamps are required")
        if begin > end:
            raise TemporalEvidenceError("earliest must not be after latest")
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 0 <= max_hops <= 64:
            raise TemporalEvidenceError("max_hops must be an integer in [0, 64]")
        threshold = _confidence(min_confidence)
        allowed = None if predicates is None else {_text(p, field="predicate") for p in predicates}
        if start == goal:
            return ()
        inactive = self._inactive_ids(known)
        edges = [
            fact for fact in self._facts.values()
            if fact.observed_at <= known
            and fact.fact_id not in inactive
            and fact.confidence >= threshold
            and (allowed is None or fact.predicate in allowed)
            and fact.valid_from <= end
            and (fact.valid_to is None or begin < fact.valid_to)
        ]
        edges.sort(key=lambda fact: (fact.subject, fact.valid_from, fact.fact_id))
        outgoing: dict[str, list[Fact]] = {}
        for fact in edges:
            outgoing.setdefault(fact.subject, []).append(fact)

        queue = deque([(start, begin, tuple(), frozenset({start}))])
        best: dict[tuple[str, int], datetime] = {(start, 0): begin}
        while queue:
            node, current_time, path, visited = queue.popleft()
            if len(path) >= max_hops:
                continue
            for fact in outgoing.get(node, []):
                hop_time = max(current_time, fact.valid_from, begin)
                if hop_time > end:
                    continue
                if fact.valid_to is not None and not hop_time < fact.valid_to:
                    continue
                next_node = fact.object
                next_path = path + ((fact, hop_time),)
                if next_node == goal:
                    return next_path
                if next_node in visited:
                    continue
                key = (next_node, len(next_path))
                previous = best.get(key)
                if previous is not None and previous <= hop_time:
                    continue
                best[key] = hop_time
                queue.append((next_node, hop_time, next_path, visited | {next_node}))
        return None

    def path_receipt(
        self,
        start: str,
        goal: str,
        *,
        earliest: str | datetime,
        latest: str | datetime,
        known_at: str | datetime,
        predicates: Iterable[str] | None = None,
        max_hops: int = 6,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        path = self.time_respecting_path(
            start, goal, earliest=earliest, latest=latest, known_at=known_at,
            predicates=predicates, max_hops=max_hops, min_confidence=min_confidence,
        )
        begin = _parse_ts(earliest, field="earliest")
        end = _parse_ts(latest, field="latest")
        known = _parse_ts(known_at, field="known_at")
        if begin is None or end is None or known is None:
            raise TemporalEvidenceError("path timestamps are required")
        predicate_list = None if predicates is None else sorted({_text(p, field="predicate") for p in predicates})
        hops = None if path is None else [
            {"fact": fact.canonical_record(), "hop_time": _ts(hop_time)}
            for fact, hop_time in path
        ]
        payload = {
            "schema": "temporal-evidence-path/v1",
            "start": _text(start, field="start"),
            "goal": _text(goal, field="goal"),
            "earliest": _ts(begin),
            "latest": _ts(end),
            "known_at": _ts(known),
            "predicates": predicate_list,
            "max_hops": max_hops,
            "min_confidence": _confidence(min_confidence),
            "found": path is not None,
            "hops": hops,
        }
        return {**payload, "receipt_sha256": digest_json(payload)}

    @staticmethod
    def verify_path_receipt(receipt: Mapping[str, Any]) -> bool:
        expected = {
            "schema", "start", "goal", "earliest", "latest", "known_at",
            "predicates", "max_hops", "min_confidence", "found", "hops", "receipt_sha256",
        }
        if set(receipt) != expected or receipt.get("schema") != "temporal-evidence-path/v1":
            return False
        try:
            start = _text(receipt["start"], field="start")
            goal = _text(receipt["goal"], field="goal")
            begin = _parse_ts(receipt["earliest"], field="earliest")
            end = _parse_ts(receipt["latest"], field="latest")
            known = _parse_ts(receipt["known_at"], field="known_at")
            if begin is None or end is None or known is None or begin > end:
                return False
            max_hops = receipt["max_hops"]
            if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 0 <= max_hops <= 64:
                return False
            threshold = _confidence(receipt["min_confidence"])
            predicates = receipt["predicates"]
            if predicates is not None:
                if not isinstance(predicates, list) or predicates != sorted(set(predicates)):
                    return False
                predicates = {_text(value, field="predicate") for value in predicates}
            found = receipt["found"]
            if not isinstance(found, bool):
                return False
            hops = receipt["hops"]
            if found:
                if not isinstance(hops, list) or len(hops) > max_hops:
                    return False
                if start != goal and not hops:
                    return False
                node = start
                current_time = begin
                for hop in hops:
                    if not isinstance(hop, Mapping) or set(hop) != {"fact", "hop_time"}:
                        return False
                    fact = Fact.from_record(hop["fact"])
                    hop_time = _parse_ts(hop["hop_time"], field="hop_time")
                    if hop_time is None:
                        return False
                    if fact.subject != node:
                        return False
                    if predicates is not None and fact.predicate not in predicates:
                        return False
                    if fact.observed_at > known or fact.confidence < threshold:
                        return False
                    if hop_time < current_time or hop_time < begin or hop_time > end:
                        return False
                    if not fact.valid_at(hop_time):
                        return False
                    node = fact.object
                    current_time = hop_time
                if node != goal:
                    return False
            elif hops is not None:
                return False
            payload = {key: receipt[key] for key in expected if key != "receipt_sha256"}
            return digest_json(payload) == receipt["receipt_sha256"]
        except (TemporalEvidenceError, TypeError, KeyError):
            return False

    @classmethod
    def from_jsonl(cls, text: str) -> "TemporalEvidenceGraph":
        graph = cls()
        pending_events: list[EvidenceEvent] = []
        for line_no, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                record = strict_json_loads(raw)
                if not isinstance(record, Mapping):
                    raise TemporalEvidenceError("JSONL record must be an object")
                kind = record.get("kind")
                if kind == "fact":
                    graph.add_fact(Fact.from_record(record))
                elif kind == "event":
                    pending_events.append(EvidenceEvent.from_record(record))
                else:
                    raise TemporalEvidenceError("record kind must be 'fact' or 'event'")
            except TemporalEvidenceError as exc:
                raise TemporalEvidenceError(f"line {line_no}: {exc}") from exc
        for event in sorted(pending_events, key=lambda item: (item.observed_at, item.event_id)):
            graph.add_event(event)
        return graph

    def to_jsonl(self) -> str:
        lines: list[str] = []
        for fact in self.facts:
            lines.append(canonical_json({"kind": "fact", **fact.canonical_record()}))
        for event in self.events:
            lines.append(canonical_json({"kind": "event", **event.canonical_record()}))
        return "\n".join(lines) + ("\n" if lines else "")


def _load_graph(path: str) -> TemporalEvidenceGraph:
    return TemporalEvidenceGraph.from_jsonl(Path(path).read_text(encoding="utf-8"))


def _print_receipt(receipt: Mapping[str, Any]) -> None:
    print(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bitemporal evidence graph and offline receipt verifier")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="emit a point-in-time evidence snapshot")
    snapshot.add_argument("jsonl")
    snapshot.add_argument("--valid-at", required=True)
    snapshot.add_argument("--known-at", required=True)
    snapshot.add_argument("--min-confidence", type=float, default=0.0)

    path = sub.add_parser("path", help="emit a time-respecting path receipt")
    path.add_argument("jsonl")
    path.add_argument("start")
    path.add_argument("goal")
    path.add_argument("--earliest", required=True)
    path.add_argument("--latest", required=True)
    path.add_argument("--known-at", required=True)
    path.add_argument("--predicate", action="append", dest="predicates")
    path.add_argument("--max-hops", type=int, default=6)
    path.add_argument("--min-confidence", type=float, default=0.0)

    verify = sub.add_parser("verify", help="verify a saved snapshot/path receipt offline")
    verify.add_argument("receipt")

    args = parser.parse_args(argv)
    if args.command == "snapshot":
        graph = _load_graph(args.jsonl)
        _print_receipt(graph.snapshot_receipt(
            valid_at=args.valid_at, known_at=args.known_at, min_confidence=args.min_confidence,
        ))
        return 0
    if args.command == "path":
        graph = _load_graph(args.jsonl)
        _print_receipt(graph.path_receipt(
            args.start, args.goal, earliest=args.earliest, latest=args.latest,
            known_at=args.known_at, predicates=args.predicates,
            max_hops=args.max_hops, min_confidence=args.min_confidence,
        ))
        return 0
    raw = strict_json_loads(Path(args.receipt).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        print("INVALID")
        return 2
    valid = TemporalEvidenceGraph.verify_snapshot_receipt(raw) or TemporalEvidenceGraph.verify_path_receipt(raw)
    print("VALID" if valid else "INVALID")
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
