"""Incremental-import identity tests, independent of any particular mapper.

Adapters translate the neutral fixture into their real input schema and return
`Projection`. This is a test driver, not a second production identity mapper.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Callable

Key = tuple[str, str, str, str]


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


@dataclass
class Projection:
    """Normalized observed results from one real mapper invocation.

Keys include origin, kind, original ID and revision. `records` contains mapper
canonical IDs, not a hash manufactured by the adapter. `references` contains
actual resolved target IDs or an empty tuple for unresolved references.
Unresolved/invalid input must remain visible in `diagnostics` or `rejected`.
"""
    records: dict[Key, str] = field(default_factory=dict)
    references: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    rejected: bool = False
    retained: dict[Key, tuple[str, ...]] = field(default_factory=dict)

    def comparable(self) -> tuple:
        return (sorted(self.records.items()), sorted(self.references.items()),
                sorted(self.diagnostics), self.rejected, sorted(self.retained.items()))


def record(origin: str, kind: str, local_id: str, revision: str = "r1", **payload: object) -> dict:
    return {"origin": origin, "kind": kind, "local_id": local_id,
            "revision": revision, "synthetic": True, "payload": payload}


def key(row: dict) -> Key:
    return tuple(row[k] for k in ("origin", "kind", "local_id", "revision"))


def ref(row: dict, **changes: object) -> dict:
    result = {k: row[k] for k in ("origin", "kind", "local_id", "revision")}
    result.update(changes)
    return result


def fixture() -> dict:
    source = record("registry-a", "source", "SRC-1", note="original source", locator="p3:L8")
    finding = record("registry-a", "finding", "FND-1", note="fictional finding")
    return {"records": [source, finding], "references": [{"id": "support-1", "target": ref(source)}]}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def baseline(adapter: Callable[[dict], Projection], data: dict) -> Projection:
    outcome = adapter(copy.deepcopy(data))
    _require(not outcome.rejected, "valid baseline was rejected")
    _require(set(outcome.records) == {key(r) for r in data["records"]}, "adapter omitted or invented original identities")
    _require(all(isinstance(v, str) and v for v in outcome.records.values()), "canonical IDs missing")
    _require(len(set(outcome.records.values())) == len(outcome.records), "distinct qualified identities collapsed")
    for row in data["records"]:
        _require(encode(row["payload"]) in outcome.retained.get(key(row), ()), "original payload was not retained")
    return outcome


def unrelated_extension(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    before = baseline(adapter, data)
    data["records"] += [record("new-origin", "service", "SVC-9", name="unrelated"),
                        record("aaa-before-everything", "source", "AAA", note="lexically first")]
    after = baseline(adapter, data)
    _require(all(after.records[k] == v for k, v in before.records.items()), "unrelated import re-keyed an established record")
    _require(before.references == after.references, "unrelated import changed an established reference")


def collision_extension(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    before = baseline(adapter, data)
    data["records"].append(record("registry-b", "source", "SRC-1", note="different source"))
    after = baseline(adapter, data)
    _require(all(after.records[k] == v for k, v in before.records.items()), "new origin re-keyed established records")
    _require(before.references == after.references, "same-label import retargeted a qualified reference")
    expected = before.records[key(data["records"][0])]
    _require(after.references.get("support-1") == (expected,), "qualified reference did not retain its exact target")


def permutation(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    data["records"] += [record("registry-" + str(i), "source", "SRC-1", number=i) for i in range(5)]
    expected = baseline(adapter, data).comparable()
    randomizer = random.Random(103)
    for _ in range(40):
        randomizer.shuffle(data["records"])
        randomizer.shuffle(data["references"])
        actual = baseline(adapter, data).comparable()
        _require(actual == expected, "record/reference order changed the normalized result")


def original_spelling(adapter: Callable[[dict], Projection]) -> None:
    data = {"records": [record("a:source:b", "source", "c", value=1),
                        record("a", "source", "b:source:c", value=2),
                        record("literal", "source", "é", value=3),
                        record("literal", "source", "e\u0301", value=4),
                        record("literal", "source", "SRC", value=5),
                        record("literal", "source", "src", value=6),
                        record("literal", "source", " source ", value=7),
                        record("literal", "source", "source", value=8)], "references": []}
    baseline(adapter, data)


def duplicate_conflict(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    data["records"].append(copy.deepcopy(data["records"][0]))
    data["records"][-1]["payload"]["note"] = "contradictory new payload"
    outcome = adapter(copy.deepcopy(data))
    _require(outcome.rejected or bool(outcome.diagnostics), "conflicting duplicate import silently accepted")
    if not outcome.rejected:
        retained = set(outcome.retained.get(key(data["records"][0]), ()))
        expected = {encode(data["records"][i]["payload"]) for i in (0, -1)}
        _require(expected <= retained, "conflict diagnostic discarded one original payload")
        _require(not outcome.references.get("support-1"), "conflicting duplicate still selected one payload as resolved")
    first = outcome.comparable()
    data["records"].reverse()
    _require(adapter(data).comparable() == first, "duplicate-conflict result depends on import order")


def unqualified_collision(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    data["records"].append(record("registry-b", "source", "SRC-1", note="different source"))
    del data["references"][0]["target"]["origin"]
    outcome = adapter(data)
    _require(outcome.rejected or bool(outcome.diagnostics), "unqualified collision has no diagnostic")
    _require(not outcome.references.get("support-1"), "unqualified collision selected a target")


def missing_target(adapter: Callable[[dict], Projection]) -> None:
    data = fixture()
    data["references"][0]["target"]["local_id"] = "DOES-NOT-EXIST"
    outcome = adapter(data)
    _require(outcome.rejected or bool(outcome.diagnostics), "missing reference has no diagnostic")
    _require(not outcome.references.get("support-1"), "missing reference manufactured a target")


def batch_growth(adapter: Callable[[dict], Projection]) -> None:
    data = {"records": [], "references": []}
    prior: dict[Key, str] = {}
    for batch in range(8):
        data["records"] += [record("batch-" + str(batch), "observation", "OBS-" + str(i),
                                   batch=batch, ordinal=i) for i in range(64)]
        outcome = baseline(adapter, data)
        _require(all(outcome.records[k] == v for k, v in prior.items()), "batched append re-keyed previous identities")
        prior = outcome.records


CASES = (unrelated_extension, collision_extension, permutation, original_spelling,
         duplicate_conflict, unqualified_collision, missing_target, batch_growth)


def run(adapter: Callable[[dict], Projection]) -> dict:
    """Execute every case; a broken mapper must not abort unrelated cases."""
    results = []
    for case in CASES:
        try:
            case(adapter)
            results.append({"case": case.__name__, "status": "PASS"})
        except Exception as exc:  # Report each actual target exception, never a pass.
            results.append({"case": case.__name__, "status": "FAIL",
                            "error_type": type(exc).__name__, "detail": str(exc)})
    return {"schema": "uiowa-identity-conformance/v1", "synthetic": True,
            "passed": sum(row["status"] == "PASS" for row in results),
            "failed": sum(row["status"] == "FAIL" for row in results),
            "cases": results,
            "fixture_digest": hashlib.sha256(encode(fixture()).encode("utf-8")).hexdigest()}
