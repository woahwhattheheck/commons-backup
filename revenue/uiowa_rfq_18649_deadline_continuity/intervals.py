#!/usr/bin/env python3
"""UIOWA-107 -- assumptions and the interval arithmetic they drive.

Why intervals and not point estimates: the work order requires that
"dependency and capacity assumptions are explicit". A point estimate is the
opposite of explicit -- it hides the width of what nobody actually knows
behind a number that looks measured. So every quantity here carries a range
and a BASIS saying where it came from, and the arithmetic propagates both.

The important case is UNKNOWN. An assumption nobody has resolved does not get
a default, a midpoint, or a plausible-looking stand-in. It becomes an interval
with a lower bound of zero and **no upper bound**, which propagates through
the sum and makes any conclusion that depended on it come out
NOT_DETERMINED. That is the honest answer, and it is far more useful than a
confident number resting on an input nobody has.
"""

import math

BASES = ("MEASURED", "ESTIMATED", "ASSUMED", "UNKNOWN")

BASIS_MEANING = {
    "MEASURED": "taken from a record; the range is the observed spread",
    "ESTIMATED": "a practitioner's range, not a measurement",
    "ASSUMED": "a working figure with nothing behind it yet",
    "UNKNOWN": "nobody has established this; no bound is available",
}


class AssumptionError(ValueError):
    pass


def _quantity(value, label):
    """Keep booleans, text and non-finite values out of hour arithmetic.

    Integers/floats must be representable as finite Python floats because
    the retained human-readable renderer formats quantities using %g.
    No conversion is applied to the accepted value.
    """
    valid = type(value) in (int, float)
    if valid:
        try:
            valid = math.isfinite(value)
        except OverflowError:
            valid = False
    if not valid:
        raise AssumptionError("%s must be a finite non-Boolean int or float" % label)
    return value


class Interval(object):
    """A non-negative quantity. `high is None` means unbounded above --
    genuinely unknown, not "very large"."""

    __slots__ = ("low", "high")

    def __init__(self, low, high):
        _quantity(low, "interval lower bound")
        if high is not None:
            _quantity(high, "interval upper bound")
        if low < 0:
            raise AssumptionError("interval lower bound must be a non-negative number, got %r" % low)
        if high is not None and high < low:
            raise AssumptionError("interval upper bound %r is below its lower bound %r" % (high, low))
        self.low = low
        self.high = high

    @property
    def bounded(self):
        return self.high is not None

    def __add__(self, other):
        high = None if (self.high is None or other.high is None) else self.high + other.high
        return Interval(self.low + other.low, high)

    def scaled(self, factor):
        _quantity(factor, "multiplier")
        if factor < 0:
            raise AssumptionError("multiplier must be non-negative, got %r" % factor)
        return Interval(self.low * factor, None if self.high is None else self.high * factor)

    def strictly_below(self, other):
        """True only when this interval ends before the other one starts.

        An unbounded interval is below nothing. That is the point: you cannot
        conclude a comparison you have not bounded."""
        return self.high is not None and self.high < other.low

    def overlaps(self, other):
        return not (self.strictly_below(other) or other.strictly_below(self))

    def as_dict(self):
        return {"low": self.low, "high": self.high}

    def __eq__(self, other):
        return isinstance(other, Interval) and self.low == other.low and self.high == other.high

    def __hash__(self):
        return hash((self.low, self.high))

    def __repr__(self):
        return "%g-%s" % (self.low, "%g" % self.high if self.bounded else "UNBOUNDED")


ZERO = Interval(0, 0)


class Assumption(object):
    __slots__ = ("id", "statement", "basis", "unit", "low", "high", "stated_by", "source_ref")

    def __init__(self, record):
        self.id = record.get("id")
        self.statement = record.get("statement")
        self.basis = record.get("basis")
        self.unit = record.get("unit")
        self.low = record.get("low")
        self.high = record.get("high")
        self.stated_by = record.get("stated_by")
        self.source_ref = record.get("source_ref")
        self._validate()

    def _validate(self):
        if not self.id:
            raise AssumptionError("an assumption needs an id")
        if not self.statement:
            raise AssumptionError("%s: an assumption must state what it assumes" % self.id)
        if self.basis not in BASES:
            raise AssumptionError("%s: basis must be one of %s, got %r" % (self.id, list(BASES), self.basis))
        if self.basis == "UNKNOWN":
            if self.low is not None or self.high is not None:
                raise AssumptionError(
                    "%s: an UNKNOWN assumption carries no numbers. A value here would be an "
                    "invented figure wearing an UNKNOWN label." % self.id
                )
            return
        if self.low is None or self.high is None:
            raise AssumptionError("%s: a %s assumption needs both bounds" % (self.id, self.basis))
        if self.basis == "MEASURED" and not self.source_ref:
            raise AssumptionError(
                "%s: MEASURED means somebody can point at the record. Supply a source_ref "
                "or call it ESTIMATED." % self.id
            )
        # Validate even unused assumptions: every displayed numeric record
        # must satisfy the same contract as a quantity used by an option.
        Interval(self.low, self.high)

    @property
    def resolved(self):
        return self.basis != "UNKNOWN"

    def interval(self):
        if not self.resolved:
            # Zero to unbounded: no claim in either direction.
            return Interval(0, None)
        return Interval(self.low, self.high)

    def pinned(self, end):
        """The interval this assumption would have if it were resolved to one
        end of its range. Returns None when that end cannot be pinned --
        which is exactly the UNKNOWN upper bound, and saying so is the useful
        result."""
        if not self.resolved:
            return Interval(0, 0) if end == "low" else None
        value = self.low if end == "low" else self.high
        return Interval(value, value)

    def as_dict(self):
        return {
            "id": self.id,
            "statement": self.statement,
            "basis": self.basis,
            "basis_meaning": BASIS_MEANING[self.basis],
            "unit": self.unit,
            "low": self.low,
            "high": self.high,
            "stated_by": self.stated_by,
            "source_ref": self.source_ref,
            "resolved": self.resolved,
        }
