"""Fail-closed sticky-obligation custody for blocked Gemini descendants.

Research only.  This module is a shared proof surface for two source-real ideas
whose post-hoc forms are unsafe on current V4:

* HYDRA / alternate WATER: a skipped established-crop WATER is useful only if
  the vacated slot is replaced by effectful work and a site-bound recovery WATER
  is carried across replans into the next-day service window.
* CARRYBANK / intraday HOIST: a proactive WHEAT/FERTILIZER PICKUP is safe only
  if actor-local future sinks remain available after existing carried stock and
  future acquisitions consume their share of that sink capacity.

The module does not choose a replacement action, edit a route, persist scheduler
state, or authorize runtime/default promotion.  It creates deterministic proof
obligations and checks caller-supplied normalized continuation evidence.  A
runtime composer may consume this contract only after separately authenticating
its own projection/postimage and economics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA = "titan-v4-sticky-obligation/v1"
REPORT_SCHEMA = "titan-v4-sticky-obligation-proof/v1"
WATER_KIND = "RECOVERY_WATER"
CARRY_KIND = "CARRY_CONSUMPTION"
CARRY_ITEMS = frozenset({"WHEAT", "FERTILIZER"})
CARRY_SINK = {"WHEAT": "FEED", "FERTILIZER": "FERTILIZE"}
SITE_INVALIDATORS = frozenset({
    "DIG", "PLANT", "HARVEST", "BUILD_COOP", "BUILD_PASTURE",
})


class UnsupportedObligation(ValueError):
    """Raised when evidence is malformed or cannot prove safe custody."""


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnsupportedObligation(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    value = _nonnegative_int(value, label)
    if value == 0:
        raise UnsupportedObligation(f"{label} must be positive")
    return value


def _actor(value: Any, label: str = "actor") -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise UnsupportedObligation(f"{label} must be an opaque string/int id")
    if isinstance(value, str) and not value:
        raise UnsupportedObligation(f"{label} must be nonempty")
    if isinstance(value, int) and value < 0:
        raise UnsupportedObligation(f"{label} integer id must be nonnegative")
    return value


def _site(value: Any, label: str = "site") -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise UnsupportedObligation(f"{label} must be [x,y]")
    x = _nonnegative_int(value[0], f"{label}.x")
    y = _nonnegative_int(value[1], f"{label}.y")
    return (x, y)


def _op(row: Mapping[str, Any]) -> str:
    op = row.get("op")
    if not isinstance(op, str) or not op:
        raise UnsupportedObligation("projected row op must be a nonempty string")
    return op.upper()


def _canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _obligation_id(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(payload)).hexdigest()


@dataclass(frozen=True)
class StickyObligation:
    schema: str
    kind: str
    created_step: int
    due_start: int
    due_end: int
    quantity: int
    actor: str | int | None = None
    site: tuple[int, int] | None = None
    item: str | None = None
    obligation_id: str = ""

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("obligation_id", None)
        if self.site is not None:
            payload["site"] = list(self.site)
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload_without_id()
        payload["obligation_id"] = self.obligation_id
        return payload


def _seal(**fields: Any) -> StickyObligation:
    draft = StickyObligation(schema=SCHEMA, obligation_id="", **fields)
    digest = _obligation_id(draft.payload_without_id())
    return StickyObligation(schema=SCHEMA, obligation_id=digest, **fields)


def validate_obligation(value: Any) -> StickyObligation:
    if isinstance(value, StickyObligation):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise UnsupportedObligation("obligation must be a mapping or StickyObligation")
    expected_keys = {
        "schema", "kind", "created_step", "due_start", "due_end", "quantity",
        "actor", "site", "item", "obligation_id",
    }
    if set(raw) != expected_keys:
        raise UnsupportedObligation("obligation key set drift")
    if raw.get("schema") != SCHEMA:
        raise UnsupportedObligation("unexpected obligation schema")
    kind = raw.get("kind")
    if kind not in (WATER_KIND, CARRY_KIND):
        raise UnsupportedObligation("unsupported obligation kind")
    created = _nonnegative_int(raw.get("created_step"), "created_step")
    due_start = _nonnegative_int(raw.get("due_start"), "due_start")
    due_end = _nonnegative_int(raw.get("due_end"), "due_end")
    quantity = _positive_int(raw.get("quantity"), "quantity")
    if due_start <= created or due_end < due_start:
        raise UnsupportedObligation("invalid obligation due window")

    actor: str | int | None = None
    site: tuple[int, int] | None = None
    item: str | None = None
    if kind == WATER_KIND:
        if raw.get("actor") is not None or raw.get("item") is not None or quantity != 1:
            raise UnsupportedObligation("recovery WATER must be site-bound, quantity 1")
        site = _site(raw.get("site"))
    else:
        if raw.get("site") is not None:
            raise UnsupportedObligation("carry consumption is actor-bound, not site-bound")
        actor = _actor(raw.get("actor"))
        item_raw = raw.get("item")
        if item_raw not in CARRY_ITEMS:
            raise UnsupportedObligation("unsupported carried item")
        item = str(item_raw)

    rebuilt = _seal(
        kind=kind,
        created_step=created,
        due_start=due_start,
        due_end=due_end,
        quantity=quantity,
        actor=actor,
        site=site,
        item=item,
    )
    supplied_id = raw.get("obligation_id")
    if not isinstance(supplied_id, str) or supplied_id != rebuilt.obligation_id:
        raise UnsupportedObligation("obligation digest/custody mismatch")
    return rebuilt


def issue_recovery_water(
    *,
    site: Sequence[int],
    created_step: int,
    replacement_op: str,
    replacement_effectful: bool,
    turns_per_day: int = 24,
    action_steps: int = 719,
) -> StickyObligation:
    """Issue next-day WATER custody only for an actual productive substitution.

    ``replacement_effectful`` is a proof input from the caller's authenticated
    engine/postimage projection.  This module deliberately does not infer effect
    from an action name.  PASS/WATER cannot mint an action-saving claim.
    """
    created = _nonnegative_int(created_step, "created_step")
    tpd = _positive_int(turns_per_day, "turns_per_day")
    total = _positive_int(action_steps, "action_steps")
    if created >= total:
        raise UnsupportedObligation("created_step is outside executable callbacks")
    if type(replacement_effectful) is not bool or replacement_effectful is not True:
        raise UnsupportedObligation("replacement requires authenticated effectful proof")
    if not isinstance(replacement_op, str) or not replacement_op:
        raise UnsupportedObligation("replacement_op must be nonempty")
    op = replacement_op.upper()
    if op in ("PASS", "WATER"):
        raise UnsupportedObligation("WATER exchange must realize different productive work")

    day = created // tpd
    due_start = (day + 1) * tpd
    due_end = min((day + 2) * tpd - 1, total - 1)
    if due_start > due_end:
        raise UnsupportedObligation("no executable next-day recovery window")
    return _seal(
        kind=WATER_KIND,
        created_step=created,
        due_start=due_start,
        due_end=due_end,
        quantity=1,
        actor=None,
        site=_site(site),
        item=None,
    )


def issue_carry_consumption(
    *,
    actor: str | int,
    item: str,
    quantity: int,
    created_step: int,
    due_end: int,
    capacity_pressure_units: int,
    turns_per_day: int = 24,
) -> StickyObligation:
    """Issue same-day actor-local sink custody for a capacity-useful pickup.

    The existing CARRYBANK owner remains responsible for proving SHED adjacency
    and legal PICKUP syntax.  This contract only refuses to mint more sticky
    inventory than exact capacity pressure can justify, and it never permits the
    obligation to cross the lossy end-of-day carried-inventory boundary.
    """
    actor_id = _actor(actor)
    if item not in CARRY_ITEMS:
        raise UnsupportedObligation("unsupported carried item")
    qty = _positive_int(quantity, "quantity")
    created = _nonnegative_int(created_step, "created_step")
    end = _nonnegative_int(due_end, "due_end")
    pressure = _nonnegative_int(capacity_pressure_units, "capacity_pressure_units")
    tpd = _positive_int(turns_per_day, "turns_per_day")
    day_end = ((created // tpd) + 1) * tpd - 1
    if end <= created:
        raise UnsupportedObligation("carry sink must occur after pickup")
    if end > day_end:
        raise UnsupportedObligation("carry obligation cannot cross end-of-day")
    if pressure < qty:
        raise UnsupportedObligation("pickup exceeds proved shed-capacity pressure")
    return _seal(
        kind=CARRY_KIND,
        created_step=created,
        due_start=created + 1,
        due_end=end,
        quantity=qty,
        actor=actor_id,
        site=None,
        item=item,
    )


def carry_across_replan(previous: Any, carried: Any, *, now: int) -> StickyObligation:
    """Authenticate exact immutable obligation custody across one replan boundary."""
    before = validate_obligation(previous)
    after = validate_obligation(carried)
    step = _nonnegative_int(now, "now")
    if step <= before.created_step or step > before.due_end:
        raise UnsupportedObligation("replan boundary lies outside pending obligation window")
    if before != after:
        raise UnsupportedObligation("replan altered or dropped sticky obligation")
    return after


def _rows(projected_rows: Any) -> list[Mapping[str, Any]]:
    if not isinstance(projected_rows, Sequence) or isinstance(projected_rows, (str, bytes)):
        raise UnsupportedObligation("projected_rows must be a sequence")
    rows: list[Mapping[str, Any]] = []
    last_step = -1
    for row in projected_rows:
        if not isinstance(row, Mapping):
            raise UnsupportedObligation("projected row must be a mapping")
        step = _nonnegative_int(row.get("step"), "projected row step")
        if step < last_step:
            raise UnsupportedObligation("projected rows must be step-sorted")
        _op(row)
        rows.append(row)
        last_step = step
    return rows


def _report(obligation: StickyObligation, proven: bool, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "research_only": True,
        "decision_authority": False,
        "runtime_mutation_authority": False,
        "obligation_id": obligation.obligation_id,
        "kind": obligation.kind,
        "proven": bool(proven),
        "reason": reason,
        **extra,
    }


def prove_recovery_water(obligation: Any, projected_rows: Any) -> dict[str, Any]:
    """Prove exact-site WATER only after its complete callback remains non-destructive."""
    ob = validate_obligation(obligation)
    if ob.kind != WATER_KIND or ob.site is None:
        raise UnsupportedObligation("expected recovery-WATER obligation")

    candidate_step: int | None = None
    for row in _rows(projected_rows):
        step = _nonnegative_int(row.get("step"), "projected row step")
        if step <= ob.created_step:
            continue
        if candidate_step is not None and step > candidate_step:
            return _report(ob, True, "site_recovery_water_proved", sink_step=candidate_step)
        if step > ob.due_end:
            break

        op = _op(row)
        row_site_raw = row.get("site")
        row_site = _site(row_site_raw, "projected row site") if row_site_raw is not None else None
        if row_site != ob.site:
            continue
        if op in SITE_INVALIDATORS:
            return _report(
                ob,
                False,
                "site_invalidated_before_recovery",
                invalidating_step=step,
                invalidating_op=op,
            )
        if op == "WATER" and step >= ob.due_start:
            candidate_step = step

    if candidate_step is not None:
        return _report(ob, True, "site_recovery_water_proved", sink_step=candidate_step)
    return _report(ob, False, "missing_due_window_recovery_water")


def _pickup_quantity(row: Mapping[str, Any], item: str) -> int:
    if row.get("item") != item:
        return 0
    return _positive_int(row.get("quantity", 1), "projected pickup quantity")


def _authenticated_sink_units(
    row: Mapping[str, Any], *, item: str, sink_op: str
) -> int:
    """Return one only for caller-authenticated item consumption.

    Official FEED/FERTILIZE rows are not intrinsically sinks: both can legally
    no-op before inventory is consumed.  This proof therefore refuses to infer
    consumption from action syntax.  The projection owner must explicitly bind
    an authenticated one-unit consumption of the obligation item.
    """
    if _op(row) != sink_op:
        return 0
    authenticated = row.get("consumption_authenticated", False)
    if type(authenticated) is not bool:
        raise UnsupportedObligation("sink consumption_authenticated must be a bool")
    if authenticated is not True:
        return 0
    if row.get("consumed_item") != item:
        raise UnsupportedObligation("authenticated sink consumed_item mismatch")
    units = _positive_int(row.get("consumed_units"), "authenticated sink consumed_units")
    if units != 1:
        raise UnsupportedObligation("official FEED/FERTILIZE sink must consume exactly one item")
    return 1


def prove_carry_consumption(
    obligation: Any,
    projected_rows: Any,
    *,
    current_inventory_units: int,
) -> dict[str, Any]:
    """Prove actor-local sink capacity net of carried stock and later acquisitions.

    Like the corrected CARRYBANK owner, this refuses to reason across DROP and
    treats WHEAT HARVEST as unknown additional acquisition.  The obligation's
    own proactive pickup is *not* included in ``current_inventory_units``; it is
    the extra quantity this proof is trying to reserve sink capacity for.

    FEED/FERTILIZE action names alone do not prove consumption.  A projected
    sink contributes capacity only when the caller explicitly authenticates a
    one-unit consumption of the obligation item on that row.
    """
    ob = validate_obligation(obligation)
    if ob.kind != CARRY_KIND or ob.actor is None or ob.item is None:
        raise UnsupportedObligation("expected carry-consumption obligation")
    burden = _nonnegative_int(current_inventory_units, "current_inventory_units")
    sinks = 0
    sink_op = CARRY_SINK[ob.item]
    rows = _rows(projected_rows)

    # A projected callback can contain at most one unit action for a given actor.
    # Validate the complete relevant window before sink accounting so an early
    # successful FEED/FERTILIZE cannot hide a later impossible duplicate row.
    seen_actor_steps: set[int] = set()
    for row in rows:
        step = _nonnegative_int(row.get("step"), "projected row step")
        if step <= ob.created_step:
            continue
        if step > ob.due_end:
            break
        if _actor(row.get("actor"), "projected row actor") != ob.actor:
            continue
        if step in seen_actor_steps:
            raise UnsupportedObligation("duplicate obligated actor row in callback")
        seen_actor_steps.add(step)

    for row in rows:
        step = _nonnegative_int(row.get("step"), "projected row step")
        if step <= ob.created_step:
            continue
        if step > ob.due_end:
            break
        if _actor(row.get("actor"), "projected row actor") != ob.actor:
            continue
        op = _op(row)
        if op == "DROP":
            return _report(
                ob,
                False,
                "lossy_drop_before_reserved_sink",
                sink_units=sinks,
                competing_units=burden,
                boundary_step=step,
            )
        if ob.item == "WHEAT" and op == "HARVEST":
            return _report(
                ob,
                False,
                "unknown_wheat_harvest_acquisition_before_sink",
                sink_units=sinks,
                competing_units=burden,
                boundary_step=step,
            )
        if op == "PICKUP":
            burden += _pickup_quantity(row, ob.item)
            continue
        if ob.item == "FERTILIZER" and op == "COLLECT_FERTILIZER":
            burden += 1
            continue
        if op == sink_op:
            consumed = _authenticated_sink_units(row, item=ob.item, sink_op=sink_op)
            if consumed == 0:
                continue
            sinks += consumed
            if max(0, sinks - burden) >= ob.quantity:
                return _report(
                    ob,
                    True,
                    "actor_local_consumption_capacity_proved",
                    sink_step=step,
                    sink_units=sinks,
                    competing_units=burden,
                    reserved_units=ob.quantity,
                )

    return _report(
        ob,
        False,
        "insufficient_actor_local_consumption_capacity",
        sink_units=sinks,
        competing_units=burden,
        reserved_units=ob.quantity,
    )