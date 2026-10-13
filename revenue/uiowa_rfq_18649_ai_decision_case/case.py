"""The lifecycle ledger and the net-value verdict.

THE ONE IDEA THIS FILE EXISTS TO ENFORCE: generation speed is not delivery cost.

An assisted workflow's flattering number is the GENERATE event -- six minutes
against ninety-five. It is true, it is easy to measure, and on its own it is
the wrong basis for a decision. What actually lands on the organisation is the
whole lifecycle: generate, check, repair, accept, and then the rework that
arrives AFTER acceptance when something that survived review turns out to be
wrong. This module computes both numbers and reports them side by side, so the
gap between the headline and the delivered cost is visible rather than
available only to whoever goes looking for it.

Second rule: an unbounded unknown cannot be bounded out. If any effort event in
a variant was never recorded, the case is UNDECIDABLE. Not "estimated", not
"excluding incomplete records" -- because the missing records are exactly the
ones most likely to be the expensive ones, and dropping them biases the answer
in the direction everybody already wants it to go.
"""
from __future__ import annotations

import dataclasses
import itertools
from typing import Any

from model import (ASSISTED, BASELINE, POST_ACCEPT_KINDS, PRE_ACCEPT_KINDS,
                   UNKNOWN, Case, Document, Quantity, is_known, minutes, money)

BENEFICIAL = "BENEFICIAL"
UNFAVOURABLE = "UNFAVOURABLE"
UNCERTAIN = "NET_VALUE_UNCERTAIN"
UNDECIDABLE = "UNDECIDABLE"

REQUIRED_ASSUMPTIONS = ("analyst_hourly_cost", "documents_per_month",
                        "evaluation_horizon_months")


@dataclasses.dataclass
class DocumentLedger:
    document_id: str
    pre_accept: Any     # float minutes or UNKNOWN
    post_accept: Any
    total: Any
    generation: Any     # the headline component only
    missing_event_ids: list[str]

    @property
    def complete(self) -> bool:
        return not self.missing_event_ids


@dataclasses.dataclass
class VariantLedger:
    variant: str
    documents: list[DocumentLedger]
    gaps: list[str]              # "DOC-x/EVT-y" strings, named not counted

    def _totals(self) -> list[float]:
        return sorted(d.total for d in self.documents if d.complete)

    @property
    def complete(self) -> bool:
        return not self.gaps and bool(self.documents)

    def mean_total(self) -> Any:
        t = self._totals()
        return sum(t) / len(t) if (self.complete and t) else UNKNOWN

    def min_total(self) -> Any:
        t = self._totals()
        return t[0] if (self.complete and t) else UNKNOWN

    def max_total(self) -> Any:
        t = self._totals()
        return t[-1] if (self.complete and t) else UNKNOWN

    def mean_component(self, attr: str) -> Any:
        vals = [getattr(d, attr) for d in self.documents if d.complete]
        return sum(vals) / len(vals) if (self.complete and vals) else UNKNOWN


def build_document_ledger(doc: Document) -> DocumentLedger:
    pre = post = gen = 0.0
    missing: list[str] = []
    accepted = False
    for event in doc.sorted_events():
        if event.kind == "ACCEPT":
            accepted = True
            continue
        if not is_known(event.minutes):
            missing.append(event.id)
            continue
        if event.kind in POST_ACCEPT_KINDS:
            post += event.minutes
        elif event.kind in PRE_ACCEPT_KINDS:
            pre += event.minutes
        if event.kind in ("GENERATE", "AUTHOR"):
            gen += event.minutes
    # A document nobody accepted has not been delivered; its pre-acceptance
    # effort is real but it is not evidence of a completed workflow, so it is
    # reported as a gap rather than counted as a cheap success.
    if not accepted:
        missing.append(f"{doc.id}:no ACCEPT event")
    if missing:
        return DocumentLedger(doc.id, UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN, missing)
    return DocumentLedger(doc.id, pre, post, pre + post, gen, [])


def build_variant_ledger(case: Case, variant: str) -> VariantLedger:
    ledgers = [build_document_ledger(d) for d in case.docs_for(variant)]
    gaps = [f"{l.document_id}/{m}" for l in ledgers for m in l.missing_event_ids]
    return VariantLedger(variant=variant, documents=ledgers, gaps=gaps)


@dataclasses.dataclass
class QualitySummary:
    documents_measured: int
    mean_completeness: Any
    fabricated_references_total: int
    documents_with_fabrications: list[str]


def build_quality(case: Case, variant: str) -> QualitySummary:
    doc_ids = {d.id for d in case.docs_for(variant)}
    rows = sorted([q for q in case.quality if q.document_id in doc_ids],
                  key=lambda q: q.id)
    if not rows:
        return QualitySummary(0, UNKNOWN, 0, [])
    fabs = sorted({q.document_id for q in rows if q.fabricated_references > 0})
    return QualitySummary(
        documents_measured=len(rows),
        mean_completeness=sum(q.completeness for q in rows) / len(rows),
        fabricated_references_total=sum(q.fabricated_references for q in rows),
        documents_with_fabrications=fabs)


@dataclasses.dataclass
class Decision:
    case_id: str
    verdict: str
    reasons: list[str]
    baseline: VariantLedger
    assisted: VariantLedger
    baseline_quality: QualitySummary
    assisted_quality: QualitySummary
    net_minutes_per_doc: tuple[Any, Any, Any] = (UNKNOWN, UNKNOWN, UNKNOWN)
    net_money_over_horizon: tuple[Any, Any] = (UNKNOWN, UNKNOWN)
    nominal_capacity_hours: Any = UNKNOWN
    nominal_capacity_value: Any = UNKNOWN
    headline_ratio: Any = UNKNOWN
    quality_risk: bool = False

    def to_dict(self) -> dict:
        def q(v):
            return None if not is_known(v) else round(float(v), 2)
        return {
            "case_id": self.case_id,
            "verdict": self.verdict,
            "reasons": self.reasons,
            "headline_generation_speedup_x": q(self.headline_ratio),
            "net_minutes_per_document": {
                "low": q(self.net_minutes_per_doc[0]),
                "mid": q(self.net_minutes_per_doc[1]),
                "high": q(self.net_minutes_per_doc[2])},
            "modeled_capacity_value_over_horizon": {
                "low": q(self.net_money_over_horizon[0]),
                "nominal": q(self.nominal_capacity_value),
                "high": q(self.net_money_over_horizon[1])},
            "modeled_capacity_hours_over_horizon": q(self.nominal_capacity_hours),
            "cash_cost_over_horizon": None,
            "cash_savings_over_horizon": None,
            "realized_opportunity_value_over_horizon": None,
            "baseline": _variant_dict(self.baseline, self.baseline_quality),
            "assisted": _variant_dict(self.assisted, self.assisted_quality),
            "quality_risk": self.quality_risk,
        }


def _variant_dict(v: VariantLedger, quality: QualitySummary) -> dict:
    def q(x):
        return None if not is_known(x) else round(float(x), 2)
    return {
        "documents": len(v.documents),
        "evidence_gaps": v.gaps,
        "mean_pre_acceptance_minutes": q(v.mean_component("pre_accept")),
        "mean_post_acceptance_minutes": q(v.mean_component("post_accept")),
        "mean_generation_minutes": q(v.mean_component("generation")),
        "mean_total_minutes": q(v.mean_total()),
        "min_total_minutes": q(v.min_total()),
        "max_total_minutes": q(v.max_total()),
        "documents_measured_for_quality": quality.documents_measured,
        "mean_completeness": q(quality.mean_completeness),
        "fabricated_references_total": quality.fabricated_references_total,
        "documents_with_fabrications": quality.documents_with_fabrications,
    }


def _money_interval(net_low: float, net_high: float, case: Case) -> tuple[float, float]:
    """Proper interval arithmetic over every assumption corner.

    Enumerating the corners rather than reasoning about signs is three lines
    longer and cannot be got subtly wrong when a net value is negative.
    """
    hourly = case.assumption("analyst_hourly_cost")
    volume = case.assumption("documents_per_month")
    horizon = case.assumption("evaluation_horizon_months")
    products = [
        (n / 60.0) * h * v * m
        for n, h, v, m in itertools.product(
            (net_low, net_high), (hourly.low, hourly.high),
            (volume.low, volume.high), (horizon.low, horizon.high))
    ]
    return min(products), max(products)


def decide(case: Case) -> Decision:
    baseline = build_variant_ledger(case, BASELINE)
    assisted = build_variant_ledger(case, ASSISTED)
    bq = build_quality(case, BASELINE)
    aq = build_quality(case, ASSISTED)

    decision = Decision(case_id=case.case_id, verdict=UNDECIDABLE, reasons=[],
                        baseline=baseline, assisted=assisted,
                        baseline_quality=bq, assisted_quality=aq)

    # Fabrications that survived into an accepted document are a risk on their
    # own terms. They are reported whatever the money says -- cheap and wrong
    # is not a win, and this flag never gets averaged into the verdict.
    decision.quality_risk = bool(aq.documents_with_fabrications)

    for name in REQUIRED_ASSUMPTIONS:
        if name not in case.assumptions:
            decision.reasons.append(
                f"required assumption {name!r} is not declared; it is left "
                "UNKNOWN rather than defaulted")

    if not baseline.documents:
        decision.reasons.append("no BASELINE documents: there is nothing to compare against")
    if not assisted.documents:
        decision.reasons.append("no ASSISTED documents: there is nothing to evaluate")
    for gap in baseline.gaps:
        decision.reasons.append(
            f"baseline evidence gap at {gap}: an unrecorded step is not zero minutes")
    for gap in assisted.gaps:
        decision.reasons.append(
            f"assisted evidence gap at {gap}: an unrecorded step is not zero minutes")

    if decision.reasons:
        return decision

    # -- the headline everyone quotes, computed so it can be put next to the
    #    number that actually decides the question
    base_gen = baseline.mean_component("generation")
    asst_gen = assisted.mean_component("generation")
    if is_known(base_gen) and is_known(asst_gen) and asst_gen > 0:
        decision.headline_ratio = base_gen / asst_gen

    # -- net effect per document. The bound is the OBSERVED spread across the
    #    recorded documents, not an invented percentage band.
    net_low = baseline.min_total() - assisted.max_total()
    net_mid = baseline.mean_total() - assisted.mean_total()
    net_high = baseline.max_total() - assisted.min_total()
    decision.net_minutes_per_doc = (net_low, net_mid, net_high)

    lo, hi = _money_interval(net_low, net_high, case)
    decision.net_money_over_horizon = (lo, hi)
    decision.nominal_capacity_hours = (
        net_mid / 60.0 * case.assumption("documents_per_month").value
        * case.assumption("evaluation_horizon_months").value)
    decision.nominal_capacity_value = (
        decision.nominal_capacity_hours * case.assumption("analyst_hourly_cost").value)

    if lo > 0:
        decision.verdict = BENEFICIAL
        decision.reasons.append(
            "the whole declared assumption range keeps net value above zero")
    elif hi < 0:
        decision.verdict = UNFAVOURABLE
        decision.reasons.append(
            "the whole declared assumption range keeps net value below zero")
    else:
        decision.verdict = UNCERTAIN
        decision.reasons.append(
            "the net-value interval crosses zero inside the declared assumption "
            "range, so the sign of the result is not established")
    return decision
