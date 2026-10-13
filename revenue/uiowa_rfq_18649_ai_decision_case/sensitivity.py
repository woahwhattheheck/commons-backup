"""Assumption flow: what actually changes the answer, and by how much.

"Rankings remain revisable when real evidence arrives" is a disclaimer. This
module is the mechanism: change an assumption, re-run the case, and see which
statements in the explanation changed and whether the verdict moved.

The finding this produces on every case here is worth stating plainly, because
it is not obvious and it is the opposite of where most attention goes: THE COST
ASSUMPTIONS CANNOT CHANGE WHETHER ASSISTANCE HELPS. Hourly cost, document
volume and horizon are all strictly positive multipliers on a signed quantity,
so they scale the magnitude and can never flip the sign. What decides the
question is the recorded checking and rework effort. This module does not
assert that -- it re-runs the decision at each assumption's declared bounds and
reports what actually happened, so the classification is measured rather than
argued.
"""
from __future__ import annotations

import copy
import dataclasses
import difflib
import math

from case import UNDECIDABLE, Decision, decide
from model import Case, is_known

DECISION_CRITICAL = "DECISION_CRITICAL"
SCALES_ONLY = "SCALES_ONLY"

_FLIP_SEARCH_LIMIT = 1000.0   # minutes per document; wider than any real tail
_FLIP_TOLERANCE = 0.05


def with_assumption(case: Case, name: str, value: float) -> Case:
    """A copy of the case with one assumption replaced.

    The declared low/high widen to admit the new value rather than silently
    leaving a value outside its own stated range -- the loader rejects that
    state and it would be dishonest to construct it here.
    """
    new = copy.deepcopy(case)
    a = new.assumption(name)
    if not math.isfinite(value) or value < 0:
        raise ValueError("assumptions must be finite and nonnegative")
    new.assumptions[name] = dataclasses.replace(
        a, value=float(value), low=min(a.low, float(value)),
        high=max(a.high, float(value)), basis="OVERRIDE")
    return new


def with_assisted_checking_delta(case: Case, delta_minutes: float) -> Case:
    """A copy with `delta_minutes` added to every assisted document's checking step.

    This is the knob the decision actually turns on, so it is the one worth
    probing. Applied to CHECK where present, otherwise REPAIR.
    """
    new = copy.deepcopy(case)
    for doc in new.docs_for("ASSISTED"):
        target = None
        for kind in ("CHECK", "REPAIR"):
            for event in doc.sorted_events():
                if event.kind == kind and is_known(event.minutes):
                    target = event
                    break
            if target:
                break
        if target is not None:
            target.minutes = max(0.0, target.minutes + delta_minutes)
    return new


def find_verdict_flip(case: Case) -> dict:
    """How far the current verdict survives, in minutes per assisted document.

    Bisection on an empirically monotonic quantity: adding checking minutes to
    the assisted variant can only reduce net value. Returns the signed delta at
    which the verdict stops being what it is now, or None when it never does
    inside the search limit.
    """
    nominal = decide(case).verdict
    if nominal == UNDECIDABLE:
        return {"nominal_verdict": nominal, "flip_delta_minutes": None,
                "note": "an undecidable case has no margin to measure; supply the "
                        "missing records first"}

    def verdict_at(delta: float) -> str:
        return decide(with_assisted_checking_delta(case, delta)).verdict

    for direction in (1.0, -1.0):
        far = direction * _FLIP_SEARCH_LIMIT
        if verdict_at(far) == nominal:
            continue
        lo, hi = 0.0, far
        while abs(hi - lo) > _FLIP_TOLERANCE:
            mid = (lo + hi) / 2.0
            if verdict_at(mid) == nominal:
                lo = mid
            else:
                hi = mid
        return {
            "nominal_verdict": nominal,
            "flip_delta_minutes": round(hi, 2),
            "flip_to": verdict_at(hi),
            "note": (f"the {nominal} verdict survives a change of "
                     f"{round(lo, 2)} minutes per assisted document in this "
                     f"direction; beyond that it becomes {verdict_at(hi)}"),
        }
    return {"nominal_verdict": nominal, "flip_delta_minutes": None,
            "note": f"the {nominal} verdict did not flip anywhere within "
                    f"+/-{_FLIP_SEARCH_LIMIT:.0f} minutes per assisted document"}


def classify_assumptions(case: Case) -> list[dict]:
    """Re-run the decision at each assumption's own declared bounds."""
    nominal = decide(case)
    out = []
    for name in sorted(case.assumptions):
        a = case.assumption(name)
        verdicts = {}
        magnitudes = {}
        for edge in ("low", "high"):
            endpoint = with_assumption(case, name, getattr(a, edge))
            endpoint.assumptions[name] = dataclasses.replace(
                endpoint.assumption(name), low=getattr(a, edge), high=getattr(a, edge))
            probed = decide(endpoint)
            verdicts[edge] = probed.verdict
            lo, hi = probed.net_money_over_horizon
            magnitudes[edge] = (round(float(lo), 0), round(float(hi), 0)) \
                if is_known(lo) and is_known(hi) else None
        flips = any(v != nominal.verdict for v in verdicts.values())
        out.append({
            "assumption": name,
            "id": a.id,
            "declared_range": [a.low, a.high],
            "basis": a.basis,
            "classification": (UNDECIDABLE if nominal.verdict == UNDECIDABLE else
                               DECISION_CRITICAL if flips else SCALES_ONLY),
            "verdict_at_low": verdicts["low"],
            "verdict_at_high": verdicts["high"],
            "net_money_at_low": magnitudes["low"],
            "net_money_at_high": magnitudes["high"],
            "note": ("missing records prevent a sensitivity conclusion"
                     if nominal.verdict == UNDECIDABLE else
                     "varying this assumption across its own declared range changes "
                     "the verdict" if flips else
                     "varying this assumption across its own declared range changes "
                     "the size of the result but never its sign"),
        })
    return out


def explanation_diff(before: str, after: str) -> list[str]:
    """Line-level diff of two rendered explanations.

    This is what "changed assumptions flow through the explanation" means
    operationally: not a promise that the prose updates, but a printed list of
    exactly which statements moved.
    """
    return [line for line in difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile="explanation (nominal)", tofile="explanation (overridden)",
        lineterm="", n=0)]
