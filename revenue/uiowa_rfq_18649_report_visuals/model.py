"""The data the figures draw, and the counting rules that keep it honest.

The visual rules in palette.py only work if the DATA underneath them keeps the
same distinctions. A chart cannot show "not assessed" as different from "gap"
if something upstream already folded both into a number. So the separation is
enforced here too:

  * `Cell.band` is a band key that must exist. A missing, blank or unknown band
    raises. It never defaults to a rating and never defaults to zero.
  * `MatrixSummary` counts ratings and non-ratings in separate buckets. There
    is no method that returns an average band, because averaging "Strength,
    Gap, Not assessed" into 2.33 would invent a precision this evidence does
    not have -- and would quietly convert our missing evidence into the
    university's low score.
  * Evidence counts distinguish "we collected nothing because this was out of
    scope" (`collected=False`) from "we collected some and it was not enough"
    (`collected=True` with items). Those look identical if you only count
    items, and they mean opposite things.

Python 3 standard library only.
"""

from __future__ import annotations

import json

import palette


class DataError(ValueError):
    """Raised when input is missing or malformed. Never silently repaired."""


def _require(mapping: dict, key: str, where: str):
    if not isinstance(mapping, dict):
        raise DataError(f"{where}: expected an object, got {type(mapping).__name__}")
    if key not in mapping:
        raise DataError(f"{where}: missing required field {key!r}")
    value = mapping[key]
    if value is None or (isinstance(value, str) and not value.strip()):
        raise DataError(
            f"{where}: field {key!r} is empty. An absent input stays UNKNOWN; "
            f"it is not filled in with a default."
        )
    return value


class Cell:
    """One (group, area) intersection of the twelve-cell matrix."""

    __slots__ = ("group", "area", "band_key", "note", "evidence", "evidence_collected",
                 "conflict")

    def __init__(self, group: str, area: str, band_key: str, note: str,
                 evidence: dict, evidence_collected: bool, conflict=None) -> None:
        self.group = group
        self.area = area
        self.band_key = band_key
        self.note = note
        self.evidence = evidence
        self.evidence_collected = evidence_collected
        # Both readings of a disagreement, kept side by side. Never reconciled
        # into one value here -- that is the reviewer's judgement, not ours.
        self.conflict = conflict or []

    @property
    def band(self) -> palette.Band:
        return palette.band(self.band_key)

    @property
    def is_rating(self) -> bool:
        return self.band.on_scale

    @property
    def evidence_total(self) -> int:
        """Sums recorded counts only. NOT_RECORDED never contributes a zero."""
        return sum(v for v in self.evidence.values() if isinstance(v, int))

    @property
    def not_recorded_kinds(self) -> tuple:
        return tuple(k for k, v in self.evidence.items() if v == palette.NOT_RECORDED)

    @property
    def measured_zero_kinds(self) -> tuple:
        """Kinds explicitly counted as zero. A finding, not a hole."""
        return tuple(k for k, v in self.evidence.items()
                     if isinstance(v, int) and v == 0)

    @classmethod
    def from_dict(cls, raw: dict, where: str) -> "Cell":
        group = _require(raw, "group", where)
        area = _require(raw, "area", where)
        band_key = _require(raw, "band", where)
        # Raises on an unknown band rather than substituting one.
        palette.band(band_key)

        collected = raw.get("evidence_collected")
        if not isinstance(collected, bool):
            raise DataError(
                f"{where}: 'evidence_collected' must be true or false. "
                f"It records whether we looked at all, which is different from "
                f"how much we found; it has no safe default."
            )

        counts: dict[str, int] = {}
        raw_counts = raw.get("evidence", {}) or {}
        if not isinstance(raw_counts, dict):
            raise DataError(f"{where}: 'evidence' must be an object of counts")
        for key in palette.EVIDENCE_KEYS:
            # Absent from the object entirely means "not recorded", NOT zero.
            # This is the distinction the whole zero-vs-missing treatment rests
            # on: a supplied 0 is a measurement, an omission is not.
            value = raw_counts.get(key, palette.NOT_RECORDED)
            if value is None:
                value = palette.NOT_RECORDED
            if value == palette.NOT_RECORDED:
                counts[key] = palette.NOT_RECORDED
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise DataError(
                    f"{where}: evidence/{key} must be a whole number or "
                    f"{palette.NOT_RECORDED!r}, got {value!r}")
            if value < 0:
                raise DataError(f"{where}: evidence/{key} cannot be negative ({value})")
            counts[key] = value
        for unknown in set(raw_counts) - set(palette.EVIDENCE_KEYS):
            raise DataError(
                f"{where}: unknown evidence kind {unknown!r}; known kinds: "
                f"{', '.join(palette.EVIDENCE_KEYS)}"
            )

        recorded_total = sum(v for v in counts.values() if isinstance(v, int))
        if not collected and recorded_total > 0:
            raise DataError(
                f"{where}: marked evidence_collected=false but carries "
                f"{recorded_total} evidence items. One of the two is wrong."
            )
        if collected and recorded_total == 0:
            raise DataError(
                f"{where}: marked evidence_collected=true but carries no items. "
                f"Use evidence_collected=false for an area that was not examined."
            )

        conflict = raw.get("conflict") or []
        if not isinstance(conflict, list):
            raise DataError(f"{where}: 'conflict' must be a list of readings")

        cell = cls(group, area, band_key, raw.get("note", ""), counts, collected, conflict)

        # A rating has to rest on something. This is the guard that stops an
        # empty row from arriving in the report as a confident finding.
        if band_key == "CONTRADICTORY":
            # A disagreement needs at least two readings on the record. One
            # reading is not a conflict, and an empty conflict would render as
            # a loud cell with nothing behind it.
            if len(conflict) < 2:
                raise DataError(
                    f"{where}: band 'CONTRADICTORY' needs at least two readings in "
                    f"'conflict', each naming its source. Got {len(conflict)}.")
            for i, reading in enumerate(conflict):
                _require(reading, "source", f"{where}.conflict[{i}]")
                _require(reading, "says", f"{where}.conflict[{i}]")
            if not collected:
                raise DataError(
                    f"{where}: sources cannot disagree when no evidence was collected.")
        elif conflict:
            raise DataError(
                f"{where}: band {band_key!r} carries a 'conflict' record. A disagreement "
                f"must not be resolved into a single band -- use 'CONTRADICTORY' so both "
                f"readings stay on the page.")

        if band_key == "NOT_APPLICABLE" and collected:
            raise DataError(
                f"{where}: 'NOT_APPLICABLE' means the practice does not apply to this "
                f"group, so there is nothing to collect. If evidence exists, this is a "
                f"different band.")

        if cell.is_rating and not collected:
            raise DataError(
                f"{where}: band {band_key!r} is a rating but no evidence was "
                f"collected. An area we did not examine is UNASSESSED, not a rating."
            )
        return cell


class GroupSummary:
    """Per-group counts. Ratings and non-ratings never share a bucket."""

    __slots__ = ("group", "label", "context", "band_counts", "evidence",
                 "rated", "insufficient", "unassessed", "areas",
                 "not_applicable", "contradictory", "recorded", "missing_counts")

    def __init__(self, group, label, context, band_counts, evidence,
                 rated, insufficient, unassessed, areas,
                 not_applicable=0, contradictory=0, recorded=None,
                 missing_counts=None):
        self.group = group
        self.label = label
        self.context = context
        self.band_counts = band_counts
        self.evidence = evidence
        self.rated = rated
        self.insufficient = insufficient
        self.unassessed = unassessed
        self.areas = areas
        self.not_applicable = not_applicable
        self.contradictory = contradictory
        # Which kinds have at least one real count. A kind nobody recorded is
        # not the same as a kind counted at zero.
        self.recorded = recorded or {k: False for k in palette.EVIDENCE_KEYS}
        # How many supplied cells left this kind uncounted. A group total can be
        # "recorded" because one area counted it while three others never did;
        # saying so is the difference between a total and an honest total.
        self.missing_counts = missing_counts or {k: 0 for k in palette.EVIDENCE_KEYS}

    @property
    def evidence_total(self) -> int:
        """Sums recorded counts only. NOT_RECORDED never contributes a zero."""
        return sum(v for v in self.evidence.values() if isinstance(v, int))

    @property
    def not_recorded_kinds(self) -> tuple:
        return tuple(k for k, v in self.evidence.items() if v == palette.NOT_RECORDED)

    @property
    def measured_zero_kinds(self) -> tuple:
        """Kinds explicitly counted as zero. A finding, not a hole."""
        return tuple(k for k, v in self.evidence.items()
                     if isinstance(v, int) and v == 0)

    @property
    def coverage_sentence(self) -> str:
        """The caption that stops a bar length from reading as a score.

        A group with more evidence is not a better group; it is a better
        evidenced group. The sentence says so in words next to the bar.
        """
        parts = [f"{self.rated} of {self.areas} areas rated"]
        if self.insufficient:
            parts.append(f"{self.insufficient} with insufficient evidence")
        if self.unassessed:
            parts.append(f"{self.unassessed} not assessed")
        if self.not_applicable:
            parts.append(f"{self.not_applicable} not applicable to this group")
        if self.contradictory:
            parts.append(f"{self.contradictory} where sources disagree")
        partial = [k for k, n in self.missing_counts.items() if n and self.recorded.get(k)]
        if partial:
            parts.append("counts incomplete for "
                         + ", ".join(palette.evidence_kind(k)["label"].lower()
                                     for k in sorted(partial)))
        parts.append(f"{self.evidence_total} evidence items")
        return "; ".join(parts) + "."


class Matrix:
    """The whole assessment: groups x areas, plus the roadmap that follows."""

    def __init__(self, raw: dict) -> None:
        self.title = _require(raw, "title", "document")
        self.subtitle = raw.get("subtitle", "")
        # Fiction must be labelled fiction, everywhere it can be read.
        self.disclaimer = _require(raw, "disclaimer", "document")
        self.groups = [dict(g) for g in _require(raw, "groups", "document")]
        self.areas = [dict(a) for a in _require(raw, "areas", "document")]
        if not self.groups or not self.areas:
            raise DataError("document: needs at least one group and one area")

        self.group_ids = [str(_require(g, "id", "group")) for g in self.groups]
        self.area_ids = [str(_require(a, "id", "area")) for a in self.areas]
        if len(set(self.group_ids)) != len(self.group_ids):
            raise DataError("document: duplicate group id")
        if len(set(self.area_ids)) != len(self.area_ids):
            raise DataError("document: duplicate area id")

        self.cells: dict[tuple[str, str], Cell] = {}
        for i, raw_cell in enumerate(_require(raw, "cells", "document")):
            cell = Cell.from_dict(raw_cell, f"cells[{i}]")
            if cell.group not in self.group_ids:
                raise DataError(f"cells[{i}]: unknown group {cell.group!r}")
            if cell.area not in self.area_ids:
                raise DataError(f"cells[{i}]: unknown area {cell.area!r}")
            key = (cell.group, cell.area)
            if key in self.cells:
                raise DataError(f"cells[{i}]: duplicate cell for {key}")
            self.cells[key] = cell

        # A cell nobody supplied is reported as UNASSESSED-with-no-record rather
        # than invented. `missing` is surfaced in the figure footnote and the
        # text alternative, so a hole in the input is visible in the output.
        self.missing: list[tuple[str, str]] = [
            (g, a) for g in self.group_ids for a in self.area_ids
            if (g, a) not in self.cells
        ]

        self.roadmap = [dict(item) for item in raw.get("roadmap", [])]
        for i, item in enumerate(self.roadmap):
            _require(item, "id", f"roadmap[{i}]")
            _require(item, "title", f"roadmap[{i}]")
            phase_key = _require(item, "phase", f"roadmap[{i}]")
            palette.phase(phase_key)
            _require(item, "recommendation", f"roadmap[{i}]")

        known_ids = {item["id"] for item in self.roadmap}
        for i, item in enumerate(self.roadmap):
            for dep in item.get("depends_on", []) or []:
                if dep not in known_ids:
                    raise DataError(
                        f"roadmap[{i}]: depends on {dep!r}, which is not in this roadmap. "
                        f"A dangling dependency is not drawn as 'no dependency'."
                    )
                if dep == item["id"]:
                    raise DataError(f"roadmap[{i}]: item depends on itself")
        self._check_phase_order()

    def _check_phase_order(self) -> None:
        """A prerequisite cannot land after the thing that needs it."""
        order = {p["key"]: i for i, p in enumerate(palette.PHASES)}
        by_id = {item["id"]: item for item in self.roadmap}
        for item in self.roadmap:
            for dep in item.get("depends_on", []) or []:
                if order[by_id[dep]["phase"]] > order[item["phase"]]:
                    raise DataError(
                        f"roadmap: {item['id']} ({item['phase']}) depends on "
                        f"{dep} ({by_id[dep]['phase']}), which is scheduled later. "
                        f"The roadmap would be drawn with an arrow pointing backwards."
                    )

    # -- lookups ---------------------------------------------------------
    def group_label(self, gid: str) -> str:
        for g in self.groups:
            if g["id"] == gid:
                return g.get("label", gid)
        raise KeyError(gid)

    def group_context(self, gid: str) -> str:
        """Why two groups are not directly comparable. Printed, not implied."""
        for g in self.groups:
            if g["id"] == gid:
                return g.get("context", "")
        raise KeyError(gid)

    def area_label(self, aid: str) -> str:
        for a in self.areas:
            if a["id"] == aid:
                return a.get("label", aid)
        raise KeyError(aid)

    def cell(self, gid: str, aid: str) -> Cell | None:
        return self.cells.get((gid, aid))

    # -- counting --------------------------------------------------------
    def summarize_group(self, gid: str) -> GroupSummary:
        band_counts = {k: 0 for k in palette.BAND_ORDER}
        evidence = {k: 0 for k in palette.EVIDENCE_KEYS}
        recorded = {k: False for k in palette.EVIDENCE_KEYS}
        missing_counts = {k: 0 for k in palette.EVIDENCE_KEYS}
        for aid in self.area_ids:
            cell = self.cell(gid, aid)
            if cell is None:
                continue
            band_counts[cell.band_key] += 1
            for k, v in cell.evidence.items():
                if isinstance(v, int):
                    evidence[k] += v
                    recorded[k] = True
                elif cell.evidence_collected:
                    # Only counts as an omission where collection happened at
                    # all -- an out-of-scope area is not a missing count.
                    missing_counts[k] += 1
        rated = sum(band_counts[k] for k in palette.ORDINAL_KEYS)
        return GroupSummary(
            group=gid,
            label=self.group_label(gid),
            context=self.group_context(gid),
            band_counts=band_counts,
            evidence=evidence,
            recorded=recorded,
            missing_counts=missing_counts,
            rated=rated,
            insufficient=band_counts["INSUFFICIENT_EVIDENCE"],
            unassessed=band_counts["UNASSESSED"],
            areas=len(self.area_ids),
            not_applicable=band_counts["NOT_APPLICABLE"],
            contradictory=band_counts["CONTRADICTORY"],
        )

    def totals(self) -> dict:
        counts = {k: 0 for k in palette.BAND_ORDER}
        for cell in self.cells.values():
            counts[cell.band_key] += 1
        return {
            "cells_expected": len(self.group_ids) * len(self.area_ids),
            "cells_supplied": len(self.cells),
            "cells_missing": len(self.missing),
            "rated": sum(counts[k] for k in palette.ORDINAL_KEYS),
            "insufficient_evidence": counts["INSUFFICIENT_EVIDENCE"],
            "not_assessed": counts["UNASSESSED"],
            "not_applicable": counts["NOT_APPLICABLE"],
            "contradictory": counts["CONTRADICTORY"],
            "band_counts": counts,
        }

    @classmethod
    def from_json_file(cls, path: str) -> "Matrix":
        with open(path, "r", encoding="utf-8") as fh:
            try:
                raw = json.load(fh)
            except json.JSONDecodeError as exc:
                raise DataError(f"{path}: not valid JSON ({exc})") from exc
        return cls(raw)
