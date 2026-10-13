#!/usr/bin/env python3
"""Editable, exportable twelve-cell assessment dataset (UIOWA-035).

STATUS: PROPOSED ASSESSMENT TOOLING / NOT A UNIVERSITY FINDING.

The order
---------
Extend the ESS/RIS/IAM by four-area workbench with an editable assessment
dataset and exports that preserve evidence links, strengths, gaps, rationale,
maturity characterization and next-step options. It completes when all twelve
cells can be populated, searched, exported and reopened "without losing evidence
links or silently turning an unassessed cell into a low score".

The whole design is that last clause
------------------------------------
An unassessed cell is a statement about *our evidence*. A low maturity level is a
statement about *the group*. They are different claims, and the place they get
confused is not the screen - it is the export. A blank rank written to CSV comes
back as the empty string, and the next thing that reads it coerces it to 0, which
sorts below "Absent" and now reads as the worst result in the matrix.

So `maturity_rank` is `None` for every non-assessed status and the loader
**refuses** to turn a blank back into a number. `assessment_status` carries the
reason instead, and nothing ranks a cell that has no rank.

Conventions this builds to, rather than forking
-----------------------------------------------
`assessment_status`, `maturity_rank` and `maturity_label` are the UIOWA-021
anchor contract's field names, with `maturity_rank = None` for `unassessed` and
`not_applicable` exactly as that lane defines it. The area vocabulary is 021's
(`development`, `security`, `deployment`, `ai_readiness`); the workbench's
`software_development` and the short `SD/SEC/DEP/AI` codes are accepted as
aliases and canonicalised on the way in, so three existing spellings all load
without a fourth being invented.

Python 3 standard library only. No network.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import re
from dataclasses import dataclass, asdict, field
from typing import Iterable, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASET = os.path.join(HERE, "dataset", "matrix.json")

GROUPS = ("ESS", "RIS", "IAM")

# UIOWA-021's area vocabulary is canonical here, because maturity flows into
# UIOWA-022's rating model through those names.
AREAS = ("development", "security", "deployment", "ai_readiness")

# Three spellings already exist in the tree. All three load; none is renamed in
# anybody's lane, and no fourth is introduced.
AREA_ALIASES = {
    "development": "development", "software_development": "development",
    "software development": "development", "sd": "development", "dev": "development",
    "security": "security", "sec": "security",
    "deployment": "deployment", "deployment/operations": "deployment",
    "operations": "deployment", "dep": "deployment", "ops": "deployment",
    "ai_readiness": "ai_readiness", "ai readiness": "ai_readiness",
    "ai-readiness": "ai_readiness", "ai": "ai_readiness",
}

GROUP_ALIASES = {g.lower(): g for g in GROUPS}

# UIOWA-021: "assessed" plus three statuses that are NOT positions on the scale.
ASSESSED = "assessed"
UNASSESSED = "unassessed"
NOT_APPLICABLE = "not_applicable"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"

NON_RANK_STATUSES = (UNASSESSED, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE)
ASSESSMENT_STATUSES = (ASSESSED,) + NON_RANK_STATUSES

# Level labels by rank, from the UIOWA-021 scale.
LEVEL_LABELS = {
    1: "Absent",
    2: "Defined on paper",
    3: "Practised",
    4: "Repeatable practice",
    5: "Managed and improved",
}

CELL_FIELDS = [
    "group", "area", "assessment_status", "maturity_rank", "maturity_label",
    "strengths", "gaps", "rationale", "next_steps", "evidence_refs",
    "scope_limit", "follow_up_question",
]

# List fields use explicit JSON-array encoding in new CSVs. The legacy
# semicolon grammar is accepted only when the encoding column is absent.
LIST_FIELDS = ("strengths", "gaps", "next_steps", "evidence_refs")
LIST_SEP = ";"
LIST_ENCODING = "json-array/v1"
CSV_FIELDS = CELL_FIELDS + ["list_encoding"]
TEXT_FIELDS = tuple(f for f in CELL_FIELDS if f not in LIST_FIELDS and f != "maturity_rank")


class DatasetError(ValueError):
    """Raised when a write would corrupt the dataset's meaning."""


def canon_group(value: str) -> str:
    if not isinstance(value, str):
        raise DatasetError("group must be text")
    g = GROUP_ALIASES.get(value.strip().lower())
    if not g:
        raise DatasetError(f"unknown group {value!r}; expected one of {', '.join(GROUPS)}")
    return g


def canon_area(value: str) -> str:
    if not isinstance(value, str):
        raise DatasetError("area must be text")
    a = AREA_ALIASES.get(value.strip().lower())
    if not a:
        raise DatasetError(
            f"unknown area {value!r}; expected one of {', '.join(AREAS)} "
            f"(aliases accepted: software_development, SD, SEC, DEP, AI)")
    return a


@dataclass
class Cell:
    group: str
    area: str
    assessment_status: str = UNASSESSED
    maturity_rank: object = None          # int, or None - never 0 for "unknown"
    maturity_label: str = ""
    strengths: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    rationale: str = ""
    next_steps: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    scope_limit: str = ""
    follow_up_question: str = ""

    @property
    def key(self) -> tuple:
        return (self.group, self.area)

    def is_ranked(self) -> bool:
        return (self.assessment_status == ASSESSED
                and type(self.maturity_rank) is int and self.maturity_rank in LEVEL_LABELS)

    def validate(self) -> list:
        issues: list[str] = []
        for name in TEXT_FIELDS:
            if not isinstance(getattr(self, name), str):
                issues.append(f"{name} must be text")
        for name in LIST_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                issues.append(f"{name} must be a list of strings")
        if issues:
            return issues
        if self.group not in GROUPS or self.area not in AREAS:
            issues.append("cell coordinates must use canonical group and area")
        if self.assessment_status not in ASSESSMENT_STATUSES:
            issues.append(f"assessment_status {self.assessment_status!r} is not one of "
                          f"{', '.join(ASSESSMENT_STATUSES)}")
        if self.assessment_status in NON_RANK_STATUSES:
            # The rule the whole order turns on.
            if self.maturity_rank is not None:
                issues.append(
                    f"status is {self.assessment_status!r} but maturity_rank is "
                    f"{self.maturity_rank!r}; a cell that was not assessed has no position "
                    f"on the scale")
            if self.maturity_label:
                issues.append(
                    f"status is {self.assessment_status!r} but maturity_label is "
                    f"{self.maturity_label!r}")
            if self.assessment_status in (UNASSESSED, INSUFFICIENT_EVIDENCE) \
                    and not self.follow_up_question.strip():
                issues.append("a cell that was not assessed must carry the question that "
                              "would resolve it")
        else:
            if self.maturity_rank is None:
                issues.append("status is 'assessed' but no maturity_rank is recorded")
            elif type(self.maturity_rank) is not int or self.maturity_rank not in LEVEL_LABELS:
                issues.append(f"maturity_rank {self.maturity_rank!r} is not 1-5")
            elif self.maturity_label and self.maturity_label != LEVEL_LABELS[self.maturity_rank]:
                issues.append(f"maturity_label {self.maturity_label!r} does not match rank "
                              f"{self.maturity_rank} ({LEVEL_LABELS[self.maturity_rank]})")
            if not self.evidence_refs or any(not v.strip() for v in self.evidence_refs):
                issues.append("an assessed cell states a result with no evidence link")
            if not self.rationale.strip():
                issues.append("an assessed cell states a result with no rationale")
        return issues

    def to_row(self) -> dict:
        d = asdict(self)
        for f in LIST_FIELDS:
            d[f] = json.dumps(d[f], ensure_ascii=False, separators=(",", ":"))
        d["list_encoding"] = LIST_ENCODING
        # An empty rank is written as the empty string and must come back as
        # None, never as 0.
        d["maturity_rank"] = "" if self.maturity_rank is None else str(self.maturity_rank)
        return d

    @staticmethod
    def from_row(row: dict) -> "Cell":
        if not isinstance(row, dict):
            raise DatasetError("each cell must be an object")
        unknown = set(row) - set(CSV_FIELDS)
        if unknown:
            raise DatasetError(f"unknown cell fields: {sorted(unknown, key=str)}")
        encoding = row.get("list_encoding")
        if "list_encoding" in row and encoding != LIST_ENCODING:
            raise DatasetError(f"unsupported list_encoding {encoding!r}")
        values = {}
        for name in TEXT_FIELDS:
            default = UNASSESSED if name == "assessment_status" else ""
            value = row.get(name, default)
            if not isinstance(value, str):
                raise DatasetError(f"{name} must be text")
            values[name] = value
        values["group"] = canon_group(values["group"])
        values["area"] = canon_area(values["area"])
        values["maturity_rank"] = _rank(row.get("maturity_rank"))
        for name in LIST_FIELDS:
            value = row.get(name, [])
            if encoding is not None:
                if not isinstance(value, str):
                    raise DatasetError(f"{name} must contain a JSON array")
                try:
                    value = json.loads(value, parse_constant=_invalid_constant)
                except (ValueError, TypeError) as exc:
                    raise DatasetError(f"invalid JSON array in {name}: {exc}") from exc
                if not isinstance(value, list):
                    raise DatasetError(f"{name} must contain a JSON array")
            values[name] = _split(value)
        return Cell(**values)


def _rank(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if re.fullmatch(r"[+-]?[0-9]+", value) and len(value) <= 16:
            return int(value)
    elif type(value) is int:
        return value
    raise DatasetError(
        f"maturity_rank {value!r} is neither blank nor an integer; "
        "it is not coerced to 0 or truncated from a float/boolean")


def _split(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        if any(not isinstance(v, str) for v in value):
            raise DatasetError("list fields must contain only strings")
        return value.copy()
    if not isinstance(value, str):
        raise DatasetError("list fields must be lists of strings or legacy text")
    return [p.strip() for p in value.split(LIST_SEP) if p.strip()]


def _invalid_constant(value):
    raise DatasetError(f"non-finite JSON number {value!r} is not supported")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DatasetError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


@dataclass
class Matrix:
    """Always twelve cells. A cell nobody reached is present and unassessed,
    never absent - an absent row is how a gap disappears from a report."""
    cells: dict = field(default_factory=dict)

    @staticmethod
    def empty() -> "Matrix":
        m = Matrix()
        for g in GROUPS:
            for a in AREAS:
                m.cells[(g, a)] = Cell(group=g, area=a, assessment_status=UNASSESSED,
                                       follow_up_question="Not yet scheduled with this group.")
        return m

    def get(self, group: str, area: str) -> Cell:
        return self.cells[(canon_group(group), canon_area(area))]

    def put(self, cell: Cell) -> None:
        self.cells[cell.key] = cell

    def ordered(self) -> list:
        """Missing cells are skipped here so that `validate` can report them.
        A KeyError would make an absent cell crash the tool instead of being
        the finding it is."""
        out = []
        for g in GROUPS:
            for a in AREAS:
                c = self.cells.get((g, a))
                if c is not None:
                    out.append(c)
        return out

    def counts(self) -> dict:
        out = {s: 0 for s in ASSESSMENT_STATUSES}
        for c in self.ordered():
            out[c.assessment_status] = out.get(c.assessment_status, 0) + 1
        return out

    def ranked_cells(self) -> list:
        """Only cells that actually have a position on the scale.

        Everything that sorts, averages or charts must come through here, so a
        cell with no rank cannot be swept to the bottom of an ordering.
        """
        return [c for c in self.ordered() if c.is_ranked()]

    def validate(self) -> list:
        issues: list[str] = []
        if len(self.cells) != 12:
            issues.append(f"matrix holds {len(self.cells)} cells; it must always hold 12")
        for g in GROUPS:
            for a in AREAS:
                if (g, a) not in self.cells:
                    issues.append(f"cell {g}/{a} is missing; an absent cell is how a gap "
                                  f"disappears from a report")
        for key, c in self.cells.items():
            if not isinstance(c, Cell):
                issues.append(f"{key!r} is not a Cell")
                continue
            if c.key != key:
                issues.append(f"cell key {key!r} disagrees with coordinates {c.key!r}")
            for msg in c.validate():
                issues.append(f"{key!r}: {msg}")
        return issues


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------

def edit_cell(m: Matrix, group: str, area: str, **changes) -> Cell:
    """Apply changes to one cell, refusing a write that would corrupt meaning.

    The edit is applied to a COPY and only stored if it validates. An earlier
    version mutated the live cell and then raised, which left the matrix holding
    the invalid value it had just refused - a rejected edit has to leave the
    dataset exactly as it was.
    """
    import copy as _copy
    cell = _copy.deepcopy(m.get(group, area))
    unknown = [k for k in changes if k not in CELL_FIELDS]
    if unknown:
        raise DatasetError(f"unknown field(s) {unknown}; known fields: {', '.join(CELL_FIELDS)}")

    for k, v in changes.items():
        if k in LIST_FIELDS:
            setattr(cell, k, _split(v))
        elif k == "maturity_rank":
            setattr(cell, k, _rank(v))
        else:
            setattr(cell, k, v)

    # Keep the label consistent with the rank rather than trusting a typed one.
    if cell.is_ranked():
        cell.maturity_label = LEVEL_LABELS[cell.maturity_rank]
    if cell.assessment_status in NON_RANK_STATUSES:
        # Asking for a non-rank status AND a rank in the same call is a
        # contradiction, not something to resolve quietly. Silently dropping the
        # rank would let a caller believe the rank was accepted.
        asked_for_rank = changes.get("maturity_rank") not in (None, "")
        asked_for_label = bool(changes.get("maturity_label"))
        if asked_for_rank or asked_for_label:
            raise DatasetError(
                f"{group}/{area}: status {cell.assessment_status!r} has no position on the "
                f"scale, but this edit also sets "
                f"{'maturity_rank' if asked_for_rank else 'maturity_label'}. A cell is "
                f"either assessed or it is not; it cannot be both.")
        # A plain demotion drops any stale rank rather than leaving a number
        # behind for an exporter to pick up.
        cell.maturity_rank = None
        cell.maturity_label = ""

    issues = cell.validate()
    if issues:
        raise DatasetError(f"{group}/{area}: " + "; ".join(issues))
    m.put(cell)
    return cell


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(m: Matrix, text: str = "", group: str = "", area: str = "",
           status: str = "", ranked_only: bool = False) -> list:
    """Free-text plus field filters. Matching is case-insensitive substring."""
    needle = (text or "").strip().lower()
    out = []
    for c in m.ordered():
        if group and c.group != canon_group(group):
            continue
        if area and c.area != canon_area(area):
            continue
        if status and c.assessment_status != status:
            continue
        if ranked_only and not c.is_ranked():
            continue
        if needle:
            hay = " ".join([
                c.group, c.area, c.assessment_status, c.maturity_label, c.rationale,
                c.scope_limit, c.follow_up_question,
                " ".join(c.strengths), " ".join(c.gaps),
                " ".join(c.next_steps), " ".join(c.evidence_refs),
            ]).lower()
            if needle not in hay:
                continue
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Export and reopen
# ---------------------------------------------------------------------------

def to_json(m: Matrix) -> dict:
    return {
        "status": "SYNTHETIC ASSESSMENT DATASET / NOT A UNIVERSITY FINDING",
        "schema": {
            "groups": list(GROUPS), "areas": list(AREAS),
            "cell_fields": CELL_FIELDS,
            "assessment_statuses": list(ASSESSMENT_STATUSES),
            "non_rank_statuses": list(NON_RANK_STATUSES),
            "level_labels": {str(k): v for k, v in LEVEL_LABELS.items()},
            "note": ("maturity_rank is null for every non-assessed status. A blank rank is "
                     "not a zero and must never be coerced to one."),
        },
        "cells": [
            {**asdict(c), "maturity_rank": c.maturity_rank} for c in m.ordered()
        ],
    }


def _require_valid(m: Matrix) -> None:
    issues = m.validate()
    if issues:
        raise DatasetError("; ".join(issues))


def _atomic_text(path: str, text: str) -> str:
    """Render/validate before touching the destination; atomically replace it.

    This is ordinary editor save semantics, not a transactional filesystem or a
    concurrency guarantee. CLI input/output aliases are refused separately.
    """
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".matrix-", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def save_json(m: Matrix, path: str) -> str:
    _require_valid(m)
    return _atomic_text(path, json.dumps(to_json(m), indent=2, ensure_ascii=False))


def _from_rows(rows) -> Matrix:
    m = Matrix()
    for row in rows:
        c = Cell.from_row(row)
        if c.key in m.cells:
            raise DatasetError(f"duplicate cell {c.group}/{c.area}; neither row was preferred")
        m.put(c)
    return m


def load_json(path: str) -> Matrix:
    with open(path, encoding="utf-8", newline="") as f:
        try:
            d = json.load(f, object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
        except (ValueError, TypeError) as exc:
            raise DatasetError(f"invalid dataset JSON: {exc}") from exc
    if not isinstance(d, dict) or not isinstance(d.get("cells"), list):
        raise DatasetError("dataset JSON must be an object with a cells array")
    for row in d["cells"]:
        if not isinstance(row, dict) or "list_encoding" in row:
            raise DatasetError("native JSON cells must be objects without CSV list_encoding")
        for name in LIST_FIELDS:
            if name in row and not isinstance(row[name], list):
                raise DatasetError(f"native JSON {name} must be an array")
    return _from_rows(d["cells"])


def save_csv(m: Matrix, path: str) -> str:
    """Lossless interchange; list cells carry an explicitly declared grammar."""
    import io
    _require_valid(m)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(c.to_row() for c in m.ordered())
    return _atomic_text(path, stream.getvalue())


def load_csv(path: str) -> Matrix:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, strict=True)
        header = reader.fieldnames
        if (header is None or len(header) != len(set(header))
                or set(header) not in (set(CELL_FIELDS), set(CSV_FIELDS))):
            raise DatasetError("CSV header must contain each declared field exactly once")
        try:
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise DatasetError(f"CSV record ending on line {reader.line_num} has wrong width")
                rows.append(row)
            return _from_rows(rows)
        except csv.Error as exc:
            raise DatasetError(f"invalid CSV: {exc}") from exc


def round_trip_report(before: Matrix, after: Matrix) -> list:
    """What must survive: evidence links, and the unassessed/low distinction."""
    issues: list[str] = []
    if set(before.cells) != set(after.cells):
        issues.append(f"cell set changed: missing={sorted(set(before.cells) - set(after.cells))} "
                      f"added={sorted(set(after.cells) - set(before.cells))}")
    for k in sorted(set(before.cells) & set(after.cells)):
        a, b = before.cells[k], after.cells[k]
        if a.evidence_refs != b.evidence_refs:
            issues.append(f"{a.group}/{a.area}: evidence_refs {a.evidence_refs} -> "
                          f"{b.evidence_refs}")
        if a.assessment_status != b.assessment_status:
            issues.append(f"{a.group}/{a.area}: assessment_status {a.assessment_status} -> "
                          f"{b.assessment_status}")
        if (type(a.maturity_rank) is not type(b.maturity_rank)
                or a.maturity_rank != b.maturity_rank):
            issues.append(f"{a.group}/{a.area}: maturity_rank {a.maturity_rank!r} -> "
                          f"{b.maturity_rank!r}")
        for f_ in ("strengths", "gaps", "next_steps"):
            if getattr(a, f_) != getattr(b, f_):
                issues.append(f"{a.group}/{a.area}: {f_} changed")
        for f_ in ("group", "area", "rationale", "scope_limit", "maturity_label", "follow_up_question"):
            if getattr(a, f_) != getattr(b, f_):
                issues.append(f"{a.group}/{a.area}: {f_} changed")
    return issues


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_grid(m: Matrix) -> str:
    def cell_text(c: Cell) -> str:
        if c.assessment_status == ASSESSED:
            return f"{c.maturity_rank} {c.maturity_label}"
        return {UNASSESSED: "- not assessed",
                NOT_APPLICABLE: "- not applicable",
                INSUFFICIENT_EVIDENCE: "- insufficient evidence"}[c.assessment_status]

    w = 26
    head = "group \\ area".ljust(14) + "".join(a.ljust(w) for a in AREAS)
    lines = [head, "-" * len(head)]
    for g in GROUPS:
        lines.append(g.ljust(14) + "".join(
            cell_text(m.get(g, a)).ljust(w) for a in AREAS))
    counts = m.counts()
    lines.append("")
    lines.append(f"assessed {counts[ASSESSED]} of 12 | " + " | ".join(
        f"{s} {counts[s]}" for s in NON_RANK_STATUSES))
    lines.append("Cells shown with '-' have no position on the scale. They are a statement "
                 "about the evidence, not about the group,")
    lines.append("and they are excluded from every ranking rather than counted as a low level.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Editable twelve-cell assessment dataset.")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--search", metavar="TEXT", default=None)
    ap.add_argument("--group", default="")
    ap.add_argument("--area", default="")
    ap.add_argument("--status", default="")
    ap.add_argument("--export-csv", metavar="PATH", default=None)
    ap.add_argument("--export-json", metavar="PATH", default=None)
    ap.add_argument("--round-trip", action="store_true",
                    help="export to CSV and JSON, reopen both, and compare")
    a = ap.parse_args(argv)

    try:
        m = load_csv(a.dataset) if str(a.dataset).lower().endswith(".csv") else load_json(a.dataset)
        issues = m.validate()
        if issues:
            print("validation issues: " + str(len(issues)), file=sys.stderr)
            for issue in issues:
                print("  " + issue, file=sys.stderr)
            return 1
        outputs = [p for p in (a.export_csv, a.export_json) if p]
        paths = [a.dataset] + outputs
        for i, left in enumerate(paths):
            for right in paths[i + 1:]:
                same = os.path.realpath(left) == os.path.realpath(right)
                if os.path.exists(left) and os.path.exists(right):
                    same = same or os.path.samefile(left, right)
                if same:
                    raise DatasetError("input and each export must use distinct files")
    except (DatasetError, OSError, UnicodeError) as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 2
    rc = 0

    if a.grid or not any([a.validate, a.search, a.export_csv, a.export_json, a.round_trip]):
        print(render_grid(m))

    if a.validate:
        issues = m.validate()
        print(f"\nvalidation issues: {len(issues)}")
        for i in issues:
            print("  " + i)
        if not issues:
            print("  none")
        rc = rc or (1 if issues else 0)

    if a.search is not None:
        hits = search(m, a.search, a.group, a.area, a.status)
        print(f"\n{len(hits)} cell(s) match")
        for c in hits:
            print(f"  {c.group}/{c.area}  {c.assessment_status}"
                  f"{' rank ' + str(c.maturity_rank) if c.is_ranked() else ''}"
                  f"  evidence={','.join(c.evidence_refs) or 'none'}")

    if a.export_csv:
        print("wrote " + save_csv(m, a.export_csv))
    if a.export_json:
        print("wrote " + save_json(m, a.export_json))

    if a.round_trip:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cpath = save_csv(m, os.path.join(td, "matrix.csv"))
            jpath = save_json(m, os.path.join(td, "matrix.json"))
            issues = (round_trip_report(m, load_csv(cpath))
                      + round_trip_report(m, load_json(jpath)))
        print(f"\nround-trip differences: {len(issues)}")
        for i in issues:
            print("  " + i)
        if not issues:
            print("  none - evidence links and the unassessed/low distinction both survive")
        rc = rc or (1 if issues else 0)

    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetError, OSError, UnicodeError) as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        raise SystemExit(2)
