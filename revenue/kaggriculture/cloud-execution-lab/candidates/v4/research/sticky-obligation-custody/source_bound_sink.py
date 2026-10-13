#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound FEED/FERTILIZE transition evidence for STICKY CARRY proofs.

Research-only.  The incumbent sticky proof cannot treat projected action syntax,
or a caller-supplied ``consumption_authenticated=True`` bit, as evidence that the
official engine actually consumed WHEAT/FERTILIZER.  This module authenticates
one exact official engine/spec snapshot, derives the transition from normalized
pre-state under those source semantics, and returns an opaque in-process
capability.  Positive CARRY sink accounting accepts only capabilities issued by
this producer and bound to the upstream-authenticated projected pre-state.

The producer does not authenticate the caller's projection itself.  It binds the
supplied pre-state, actor, callback and action into the evidence and removes the
strictly weaker "caller asserts the effect" seam.  Upstream projection custody
must hand the consumer the exact projected-prestate SHA256 that the evidence
bound; missing or mismatched handoff data contributes zero sink capacity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types
from typing import Any, Mapping, Sequence
import weakref

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_ENGINE_SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
EXPECTED_STICKY_BLOB = "41b887cb96fe684522a1f19124cf4b0377207a9c"
STANDARD_TURNS_PER_DAY = 24

HERE = Path(__file__).resolve().parent
V4_ROOT = HERE.parents[1]
LAB_ROOT = V4_ROOT.parent.parent
ENGINE_PATH = LAB_ROOT / "reference" / "engine" / "kaggriculture.py"
ENGINE_SPEC_PATH = LAB_ROOT / "reference" / "engine" / "kaggriculture.json"
STICKY_PATH = HERE / "sticky_obligation.py"

ENGINE_MARKERS = (
    'if op == "FERTILIZE":',
    'if not _inv_take(inv, "FERTILIZER", 1):',
    'tile["fertilized_until_day"] = max(tile.get("fertilized_until_day", -1), day + 2)',
    'if op == "FEED":',
    'if tile["fed_today"]:',
    'if not _inv_take(inv, "WHEAT", 1):',
    'tile["fed_today"] = True',
)


class SourceBoundSinkError(ValueError):
    """The transition or one of its source authorities is not trustworthy."""


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise SourceBoundSinkError("transition state must be canonical JSON data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _plain_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SourceBoundSinkError(f"{label} must be a nonnegative plain integer")
    return value


def _actor(value: Any) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SourceBoundSinkError("actor must be an opaque string/int id")
    if isinstance(value, str) and not value:
        raise SourceBoundSinkError("actor must be nonempty")
    if isinstance(value, int) and value < 0:
        raise SourceBoundSinkError("integer actor must be nonnegative")
    return value


def _read_authenticated_sources(
    *,
    engine_path: Path = ENGINE_PATH,
    spec_path: Path = ENGINE_SPEC_PATH,
) -> tuple[bytes, bytes]:
    engine = Path(engine_path).read_bytes()
    spec = Path(spec_path).read_bytes()
    engine_blob = _git_blob(engine)
    spec_blob = _git_blob(spec)
    if engine_blob != EXPECTED_ENGINE_BLOB:
        raise SourceBoundSinkError(
            f"official engine drift: expected {EXPECTED_ENGINE_BLOB}, got {engine_blob}"
        )
    if spec_blob != EXPECTED_ENGINE_SPEC_BLOB:
        raise SourceBoundSinkError(
            f"official engine spec drift: expected {EXPECTED_ENGINE_SPEC_BLOB}, got {spec_blob}"
        )
    try:
        text = engine.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceBoundSinkError("official engine is not UTF-8") from exc
    missing = [marker for marker in ENGINE_MARKERS if marker not in text]
    if missing:
        raise SourceBoundSinkError(f"official sink semantics drifted: missing {missing!r}")
    try:
        doc = json.loads(spec.decode("utf-8"))
        entry = doc["configuration"]["turnsPerDay"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SourceBoundSinkError("official turnsPerDay contract is unavailable") from exc
    if (
        not isinstance(entry, dict)
        or entry.get("type") != "integer"
        or type(entry.get("default")) is not int
        or entry.get("default") != STANDARD_TURNS_PER_DAY
    ):
        raise SourceBoundSinkError("official turnsPerDay default drifted")
    return engine, spec


def source_authority_receipt() -> dict[str, Any]:
    engine, spec = _read_authenticated_sources()
    return {
        "engine_git_blob": _git_blob(engine),
        "engine_spec_git_blob": _git_blob(spec),
        "turns_per_day": STANDARD_TURNS_PER_DAY,
        "profiles": ["official-feed-consumption", "official-fertilize-consumption"],
    }


_ISSUER = object()
_ISSUED: "weakref.WeakSet[SinkTransitionEvidence]" = weakref.WeakSet()


class SinkTransitionEvidence:
    """Opaque producer-issued transition capability; intentionally not serializable."""

    __slots__ = (
        "_actor", "_step", "_op", "_item", "_consumed_units",
        "_engine_blob", "_spec_blob", "_before_sha256", "_after_sha256",
        "_sealed", "__weakref__",
    )

    def __init__(
        self,
        token: object,
        *,
        actor: str | int,
        step: int,
        op: str,
        item: str,
        consumed_units: int,
        engine_blob: str,
        spec_blob: str,
        before_sha256: str,
        after_sha256: str,
    ) -> None:
        if token is not _ISSUER:
            raise TypeError("SinkTransitionEvidence is producer-issued only")
        object.__setattr__(self, "_actor", actor)
        object.__setattr__(self, "_step", step)
        object.__setattr__(self, "_op", op)
        object.__setattr__(self, "_item", item)
        object.__setattr__(self, "_consumed_units", consumed_units)
        object.__setattr__(self, "_engine_blob", engine_blob)
        object.__setattr__(self, "_spec_blob", spec_blob)
        object.__setattr__(self, "_before_sha256", before_sha256)
        object.__setattr__(self, "_after_sha256", after_sha256)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("sink transition evidence is immutable")
        object.__setattr__(self, name, value)

    @property
    def actor(self) -> str | int:
        return self._actor

    @property
    def step(self) -> int:
        return self._step

    @property
    def op(self) -> str:
        return self._op

    @property
    def item(self) -> str:
        return self._item

    @property
    def consumed_units(self) -> int:
        return self._consumed_units

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "titan-v4-source-bound-sink/v1",
            "engine_git_blob": self._engine_blob,
            "engine_spec_git_blob": self._spec_blob,
            "actor": self._actor,
            "step": self._step,
            "op": self._op,
            "item": self._item,
            "consumed_units": self._consumed_units,
            "before_sha256": self._before_sha256,
            "after_sha256": self._after_sha256,
        }


def _canonical_tile(tile: Any) -> dict[str, Any] | None:
    if tile is None:
        return None
    if not isinstance(tile, Mapping):
        raise SourceBoundSinkError("tile must be a mapping or null")
    raw = dict(tile)
    return json.loads(_canonical_bytes(raw).decode("ascii"))


def derive_sink_transition(
    *,
    actor: str | int,
    step: int,
    op: str,
    tile: Mapping[str, Any] | None,
    inventory_units: int,
    engine_path: Path = ENGINE_PATH,
    spec_path: Path = ENGINE_SPEC_PATH,
) -> SinkTransitionEvidence:
    """Derive one official FEED/FERTILIZE inventory transition from pre-state."""
    engine, spec = _read_authenticated_sources(
        engine_path=engine_path, spec_path=spec_path
    )
    actor_id = _actor(actor)
    callback = _plain_nonnegative_int(step, "step")
    units = _plain_nonnegative_int(inventory_units, "inventory_units")
    if not isinstance(op, str) or not op:
        raise SourceBoundSinkError("op must be nonempty")
    operation = op.upper()
    if operation not in ("FEED", "FERTILIZE"):
        raise SourceBoundSinkError("only FEED/FERTILIZE transitions are supported")
    item = "WHEAT" if operation == "FEED" else "FERTILIZER"
    before_tile = _canonical_tile(tile)
    after_tile = None if before_tile is None else dict(before_tile)
    after_units = units
    consumed = 0

    if operation == "FEED":
        if before_tile is not None and "animal" in before_tile:
            fed = before_tile.get("fed_today")
            if type(fed) is not bool:
                raise SourceBoundSinkError("animal fed_today must be a bool")
            if fed is False and units > 0:
                consumed = 1
                after_units -= 1
                after_tile["fed_today"] = True
    else:
        if before_tile is not None and before_tile.get("kind") == "PLANT":
            previous_until = before_tile.get("fertilized_until_day", -1)
            if type(previous_until) is not int:
                raise SourceBoundSinkError("plant fertilized_until_day must be a plain integer")
            if units > 0:
                consumed = 1
                after_units -= 1
                day = callback // STANDARD_TURNS_PER_DAY
                after_tile["fertilized_until_day"] = max(previous_until, day + 2)

    before = {
        "actor": actor_id,
        "step": callback,
        "op": operation,
        "item": item,
        "inventory_units": units,
        "tile": before_tile,
    }
    after = {
        "actor": actor_id,
        "step": callback,
        "op": operation,
        "item": item,
        "inventory_units": after_units,
        "tile": after_tile,
    }
    evidence = SinkTransitionEvidence(
        _ISSUER,
        actor=actor_id,
        step=callback,
        op=operation,
        item=item,
        consumed_units=consumed,
        engine_blob=_git_blob(engine),
        spec_blob=_git_blob(spec),
        before_sha256=_digest(before),
        after_sha256=_digest(after),
    )
    _ISSUED.add(evidence)
    return evidence


def _load_sticky_snapshot():
    raw = STICKY_PATH.read_bytes()
    actual = _git_blob(raw)
    if actual != EXPECTED_STICKY_BLOB:
        raise SourceBoundSinkError(
            f"sticky proof drift: expected {EXPECTED_STICKY_BLOB}, got {actual}"
        )
    name = "_titan_v4_sticky_snapshot_" + actual[:16]
    module = types.ModuleType(name)
    module.__file__ = str(STICKY_PATH)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(STICKY_PATH), "exec"), module.__dict__)
    except Exception as exc:
        raise SourceBoundSinkError("cannot load authenticated sticky proof snapshot") from exc
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def _sink_units(
    transition: Any,
    *,
    actor: str | int,
    step: int,
    op: str,
    item: str,
    projected_prestate_sha256: Any,
) -> int:
    if transition is None:
        return 0
    if not isinstance(transition, SinkTransitionEvidence) or transition not in _ISSUED:
        raise SourceBoundSinkError("sink transition is not producer-issued evidence")
    receipt = transition.receipt()
    expected = {
        "actor": actor,
        "step": step,
        "op": op,
        "item": item,
    }
    for key, want in expected.items():
        if receipt.get(key) != want or type(receipt.get(key)) is not type(want):
            raise SourceBoundSinkError(f"sink transition {key} mismatch")
    if receipt["engine_git_blob"] != EXPECTED_ENGINE_BLOB:
        raise SourceBoundSinkError("sink transition engine authority mismatch")
    if receipt["engine_spec_git_blob"] != EXPECTED_ENGINE_SPEC_BLOB:
        raise SourceBoundSinkError("sink transition spec authority mismatch")
    consumed = receipt["consumed_units"]
    if type(consumed) is not int or consumed not in (0, 1):
        raise SourceBoundSinkError("sink transition consumption must be 0/1")

    # Upstream projection custody must hand over the exact authenticated digest
    # of the pre-state whose transition was derived.  Missing/malformed/mismatched
    # bindings are ordinary non-authorizing rows: they contribute zero sink.
    before_sha256 = receipt.get("before_sha256")
    if (
        type(before_sha256) is not str
        or len(before_sha256) != 64
        or any(c not in "0123456789abcdef" for c in before_sha256)
    ):
        raise SourceBoundSinkError("producer prestate digest is malformed")
    if type(projected_prestate_sha256) is not str:
        return 0
    if projected_prestate_sha256 != before_sha256:
        return 0
    return consumed


def prove_carry_consumption_source_bound(
    obligation: Any,
    projected_rows: Sequence[Mapping[str, Any]],
    *,
    current_inventory_units: int,
) -> dict[str, Any]:
    """Existing CARRY accounting with source-derived, prestate-bound effects.

    Old row fields ``consumption_authenticated``, ``consumed_item`` and
    ``consumed_units`` are intentionally ignored.  A FEED/FERTILIZE contributes
    one sink unit only when ``row['sink_transition']`` is producer-issued for
    that exact actor/step/op/item *and* ``row['projected_prestate_sha256']`` is
    the upstream-authenticated digest of the same pre-state bound by evidence.
    """
    sticky = _load_sticky_snapshot()
    _read_authenticated_sources()
    if hasattr(obligation, "to_dict") and callable(obligation.to_dict):
        obligation = obligation.to_dict()
    ob = sticky.validate_obligation(obligation)
    if ob.kind != sticky.CARRY_KIND or ob.actor is None or ob.item is None:
        raise SourceBoundSinkError("expected carry-consumption obligation")
    burden = sticky._nonnegative_int(
        current_inventory_units, "current_inventory_units"
    )
    sinks = 0
    sink_op = sticky.CARRY_SINK[ob.item]
    rows = sticky._rows(projected_rows)

    seen_actor_steps: set[int] = set()
    for row in rows:
        step = sticky._nonnegative_int(row.get("step"), "projected row step")
        if step <= ob.created_step:
            continue
        if step > ob.due_end:
            break
        if sticky._actor(row.get("actor"), "projected row actor") != ob.actor:
            continue
        if step in seen_actor_steps:
            raise SourceBoundSinkError("duplicate obligated actor row in callback")
        seen_actor_steps.add(step)

    for row in rows:
        step = sticky._nonnegative_int(row.get("step"), "projected row step")
        if step <= ob.created_step:
            continue
        if step > ob.due_end:
            break
        actor = sticky._actor(row.get("actor"), "projected row actor")
        if actor != ob.actor:
            continue
        operation = sticky._op(row)
        if operation == "DROP":
            return sticky._report(
                ob,
                False,
                "lossy_drop_before_reserved_sink",
                sink_units=sinks,
                competing_units=burden,
                boundary_step=step,
                sink_evidence_authority="source_bound_transition+projected_prestate",
            )
        if ob.item == "WHEAT" and operation == "HARVEST":
            return sticky._report(
                ob,
                False,
                "unknown_wheat_harvest_acquisition_before_sink",
                sink_units=sinks,
                competing_units=burden,
                boundary_step=step,
                sink_evidence_authority="source_bound_transition+projected_prestate",
            )
        if operation == "PICKUP":
            burden += sticky._pickup_quantity(row, ob.item)
            continue
        if ob.item == "FERTILIZER" and operation == "COLLECT_FERTILIZER":
            burden += 1
            continue
        if operation == sink_op:
            consumed = _sink_units(
                row.get("sink_transition"),
                actor=actor,
                step=step,
                op=sink_op,
                item=ob.item,
                projected_prestate_sha256=row.get("projected_prestate_sha256"),
            )
            if consumed == 0:
                continue
            sinks += consumed
            if max(0, sinks - burden) >= ob.quantity:
                return sticky._report(
                    ob,
                    True,
                    "actor_local_source_bound_consumption_capacity_proved",
                    sink_step=step,
                    sink_units=sinks,
                    competing_units=burden,
                    reserved_units=ob.quantity,
                    sink_evidence_authority="source_bound_transition+projected_prestate",
                    engine_git_blob=EXPECTED_ENGINE_BLOB,
                )

    return sticky._report(
        ob,
        False,
        "insufficient_actor_local_source_bound_consumption_capacity",
        sink_units=sinks,
        competing_units=burden,
        reserved_units=ob.quantity,
        sink_evidence_authority="source_bound_transition+projected_prestate",
        engine_git_blob=EXPECTED_ENGINE_BLOB,
    )
