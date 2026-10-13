"""Typed quantities, the UNKNOWN sentinel, and the case record types.

WHY THE TYPES ARE LOAD-BEARING.

This kit mixes three quantities that look alike in a spreadsheet and are not
interchangeable: minutes of human effort, money, and document volume. The
classic failure of an "AI value model" is adding across them -- summing a
one-time build cost into a recurring monthly load, or treating minutes as if
they were currency. Here they are separate types and adding across them raises
UnitError rather than producing a number nobody can defend.

WHY UNKNOWN IS A SENTINEL AND NOT None OR 0.

An unrecorded checking step is not a free checking step. If missing effort
coerced to zero, the workflow with the WORST evidence would score as the
CHEAPEST -- exactly backwards. So UNKNOWN is an object with no arithmetic at
all: any attempt to compute with it raises by name, which makes the gap loud
instead of flattering.

All records in this kit are fiction.
"""
from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

MINUTES = "minutes"
CURRENCY = "currency"
DOCUMENTS_PER_MONTH = "documents_per_month"
MONTHS = "months"
CURRENCY_PER_HOUR = "currency_per_hour"


class UnitError(TypeError):
    """Raised when two quantities of different units are combined."""


class UnknownError(TypeError):
    """Raised when an UNKNOWN value is used in a calculation.

    Deliberately loud. A silently-defaulted unknown is the single most common
    way a benefit model reports a confident number it has no basis for.
    """


class _Unknown:
    """The absence of a measurement. Supports no arithmetic whatsoever."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __str__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False

    def _refuse(self, *_a, **_k):
        raise UnknownError(
            "an UNKNOWN measurement cannot take part in a calculation; it is "
            "not zero and it is not an average -- supply the missing record "
            "or accept an UNDECIDABLE result")

    __add__ = __radd__ = __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _refuse
    __lt__ = __le__ = __gt__ = __ge__ = _refuse


UNKNOWN = _Unknown()


def is_known(value: Any) -> bool:
    return value is not UNKNOWN and value is not None


@dataclasses.dataclass(frozen=True)
class Quantity:
    """A number that knows what it measures."""
    amount: float
    unit: str

    def _check(self, other: "Quantity") -> None:
        if not isinstance(other, Quantity):
            raise UnitError(f"cannot combine Quantity with {type(other).__name__}")
        if self.unit != other.unit:
            raise UnitError(
                f"refusing to combine {self.unit} with {other.unit}; these are "
                "different things and a total across them means nothing")

    def __add__(self, other: "Quantity") -> "Quantity":
        self._check(other)
        return Quantity(self.amount + other.amount, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self._check(other)
        return Quantity(self.amount - other.amount, self.unit)

    def scaled(self, factor: float) -> "Quantity":
        """Multiply by a DIMENSIONLESS factor. Scaling is allowed; adding
        across units is not."""
        return Quantity(self.amount * factor, self.unit)

    def __str__(self) -> str:
        if self.unit == CURRENCY:
            return f"{self.amount:,.0f} (currency units)"
        if self.unit == MINUTES:
            return f"{self.amount:,.1f} min"
        return f"{self.amount:,.2f} {self.unit}"


def minutes(x: float) -> Quantity:
    return Quantity(float(x), MINUTES)


def money(x: float) -> Quantity:
    return Quantity(float(x), CURRENCY)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

# Event kinds, split at the moment that actually matters commercially.
PRE_ACCEPT_KINDS = ("AUTHOR", "GENERATE", "CHECK", "REPAIR")
POST_ACCEPT_KINDS = ("REWORK_AFTER_ACCEPT", "MAINTENANCE_EDIT")
ALL_KINDS = PRE_ACCEPT_KINDS + ("ACCEPT",) + POST_ACCEPT_KINDS

BASELINE = "BASELINE"
ASSISTED = "ASSISTED"


@dataclasses.dataclass
class Event:
    id: str
    kind: str
    minutes: Any          # float or UNKNOWN
    day: int

    @property
    def is_post_accept(self) -> bool:
        return self.kind in POST_ACCEPT_KINDS


@dataclasses.dataclass
class Document:
    id: str
    variant: str
    events: list[Event]

    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: (e.day, e.id))


@dataclasses.dataclass
class QualityMeasurement:
    id: str
    document_id: str
    required_elements: int
    correct_elements: int
    fabricated_references: int

    @property
    def completeness(self) -> float:
        if self.required_elements == 0:
            return 0.0
        return self.correct_elements / self.required_elements


@dataclasses.dataclass
class Assumption:
    id: str
    name: str
    value: float
    unit: str
    low: float
    high: float
    basis: str
    source: str


@dataclasses.dataclass
class Case:
    case_id: str
    workflow: str
    synthetic: bool
    documents: list[Document]
    quality: list[QualityMeasurement]
    assumptions: dict[str, Assumption]

    # -- record index, used by the explanation auditor to prove a citation
    #    actually resolves to something
    def record_ids(self) -> set[str]:
        ids = {self.case_id}
        for d in self.documents:
            ids.add(d.id)
            ids.update(e.id for e in d.events)
        ids.update(q.id for q in self.quality)
        ids.update(a.id for a in self.assumptions.values())
        return ids

    def docs_for(self, variant: str) -> list[Document]:
        return sorted([d for d in self.documents if d.variant == variant],
                      key=lambda d: d.id)

    def assumption(self, name: str) -> Assumption:
        if name not in self.assumptions:
            raise KeyError(f"no assumption named {name!r}")
        return self.assumptions[name]


class CaseLoadError(ValueError):
    pass


def _event(raw: dict) -> Event:
    kind = raw["kind"]
    if kind not in ALL_KINDS:
        raise CaseLoadError(f"event {raw.get('id')!r} has unknown kind {kind!r}")
    mins = raw.get("minutes", None)
    # An explicitly null / absent duration is UNKNOWN. It is NOT zero, and the
    # loader will not invent one.
    value = UNKNOWN if mins is None else float(mins)
    if is_known(value) and (not math.isfinite(value) or value < 0):
        raise CaseLoadError(f"event {raw.get('id')!r} minutes must be finite and nonnegative")
    return Event(id=raw["id"], kind=kind, minutes=value, day=int(raw["day"]))


def load_case(path: str) -> Case:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    documents = []
    seen_ids: set[str] = set()
    for d in raw.get("documents", []):
        if d["variant"] not in (BASELINE, ASSISTED):
            raise CaseLoadError(f"document {d['id']!r} has unknown variant {d['variant']!r}")
        events = [_event(e) for e in d.get("events", [])]
        for e in events:
            if e.id in seen_ids:
                raise CaseLoadError(f"duplicate record id {e.id!r}")
            seen_ids.add(e.id)
        documents.append(Document(id=d["id"], variant=d["variant"], events=events))

    quality = [QualityMeasurement(
        id=q["id"], document_id=q["document_id"],
        required_elements=int(q["required_elements"]),
        correct_elements=int(q["correct_elements"]),
        fabricated_references=int(q.get("fabricated_references", 0)),
    ) for q in raw.get("quality_measurements", [])]

    known_docs = {d.id for d in documents}
    for q in quality:
        if q.document_id not in known_docs:
            raise CaseLoadError(
                f"quality measurement {q.id!r} cites document {q.document_id!r}, "
                "which is not in this case")

    assumptions = {}
    for a in raw.get("assumptions", []):
        assumptions[a["name"]] = Assumption(
            id=a["id"], name=a["name"], value=float(a["value"]), unit=a["unit"],
            low=float(a["low"]), high=float(a["high"]),
            basis=a.get("basis", "ASSUMED"), source=a.get("source", ""))
        assumption = assumptions[a["name"]]
        if any(not math.isfinite(value) or value < 0
               for value in (assumption.low, assumption.value, assumption.high)):
            raise CaseLoadError(f"assumption {a['name']!r} must be finite and nonnegative")
        expected_unit = {
            "analyst_hourly_cost": CURRENCY_PER_HOUR,
            "documents_per_month": DOCUMENTS_PER_MONTH,
            "evaluation_horizon_months": MONTHS,
        }.get(a["name"])
        if expected_unit and assumption.unit != expected_unit:
            raise CaseLoadError(f"assumption {a['name']!r} must use {expected_unit}")
        if not (assumptions[a["name"]].low <= assumptions[a["name"]].value
                <= assumptions[a["name"]].high):
            raise CaseLoadError(
                f"assumption {a['name']!r} has value outside its own declared range")

    if not raw.get("synthetic"):
        raise CaseLoadError(
            "every case in this kit must be explicitly marked synthetic:true; "
            "this tool does not carry real engagement data")

    return Case(case_id=raw["case_id"], workflow=raw["workflow"], synthetic=True,
                documents=documents, quality=quality, assumptions=assumptions)
