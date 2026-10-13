#!/usr/bin/env python3
"""Evidence register and document manifest (UIOWA-031).

STATUS: PROPOSED ASSESSMENT TOOLING / NOT A UNIVERSITY FINDING.

What the order asks for
-----------------------
An evidence register covering source ID, group, assessment area, owner, supplied
date, version, document location, excerpt locator, and the practice supported;
CSV and JSON interchange; a populated synthetic packet. It completes when every
example document can be found from its register entry, and a round trip
preserves IDs, versions and locators - including documents used by more than one
assessment cell.

Why this is two tables, not one
-------------------------------
"Documents used by more than one assessment cell" is the requirement that
decides the shape. A single flat register repeats a document's location, version
and owner on every row that cites it, and the moment one copy is edited the
register disagrees with itself about what version was supplied. So:

- **manifest**  - one row per document. Location, version, owner, supplied date,
  digest. The document is described exactly once.
- **register**  - one row per evidence item. It carries its own claim, scope and
  confidence, and points at a document by `source_id` plus an `excerpt_locator`
  saying where in that document the support is.

A document cited by ESS/SD and again by IAM/SEC is one manifest row and two
register rows. Its version cannot drift between the two, because there is only
one place it is written down.

Field names
-----------
The register extends the existing convention in
`uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv`
rather than inventing a second one. Every field that register already defines
keeps its exact name; UIOWA-031's additions (`source_id`, `excerpt_locator`,
`practice_supported`) are new columns, and the document-level attributes move to
the manifest where they belong.

Python 3 standard library only. No network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKET = os.path.join(HERE, "packet")

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

MANIFEST_FIELDS = [
    "source_id",          # UIOWA-031: "source ID"
    "title",
    "document_location",  # UIOWA-031: "document location"
    "document_version",   # UIOWA-031: "version"
    "owner",              # UIOWA-031: "owner"
    "supplied_date",      # UIOWA-031: "supplied date"
    "source_type",        # name reused from the 023 register
    "sha256",
    "retention_note",
]

# The 023 register's field names, unchanged, plus this order's three additions.
REGISTER_FIELDS_FROM_023 = [
    "evidence_id",
    "observation_id",
    "finding_id",
    "group",
    "area",
    "source_type",
    "source_ref",
    "custodian_or_owner",
    "content_digest",
    "captured_at",
    "represented_period",
    "claim",
    "scope_limit",
    "directness",
    "recency",
    "representativeness",
    "corroboration",
    "evidence_state",
    "confidence",
    "conflict_group",
    "universe_definition",
    "enumerator_authority",
    "completeness_basis",
    "follow_up"
]
REGISTER_FIELDS_ADDED_BY_031 = [
    "source_id",           # which manifest document backs this entry
    "excerpt_locator",     # where inside that document
    "practice_supported",  # "the practice it supports"
]
REGISTER_FIELDS = REGISTER_FIELDS_FROM_023 + REGISTER_FIELDS_ADDED_BY_031

GROUPS = ("ESS", "RIS", "IAM")
AREAS = ("SD", "SEC", "DEP", "AI")

# Excerpt locator grammar. Deliberately small, and every form is resolvable
# against the real bytes - a locator nobody can follow is not a locator.
#   lines:12-18      a line range in a text document
#   section:Heading  a markdown heading
#   key:a.b.c        a path into a JSON document
#   row:ID           a CSV row by its first-column value
_LOC = re.compile(r"^(lines|section|key|row):(.+)$")

OK = "OK"
MISSING_DOCUMENT = "MISSING_DOCUMENT"
UNRESOLVED_LOCATOR = "UNRESOLVED_LOCATOR"
DANGLING_SOURCE_ID = "DANGLING_SOURCE_ID"
DIGEST_MISMATCH = "DIGEST_MISMATCH"
BAD_LOCATOR_SYNTAX = "BAD_LOCATOR_SYNTAX"
UNKNOWN_FIELD = "UNKNOWN_FIELD"
DUPLICATE_ID = "DUPLICATE_ID"
ORPHAN_DOCUMENT = "ORPHAN_DOCUMENT"
CUSTODY_MISMATCH = "CUSTODY_MISMATCH"
CONTENT_DIGEST_MISMATCH = "CONTENT_DIGEST_MISMATCH"


@dataclass
class Issue:
    code: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.subject}: {self.detail}"


@dataclass
class Packet:
    """A manifest, a register, and the documents they describe."""
    root: str
    manifest: list = field(default_factory=list)
    register: list = field(default_factory=list)

    def __post_init__(self) -> None:
        """Materialize current-023 custody mirrors only when the native row lacks them.

        The manifest remains authoritative. Existing nonblank values are never
        rewritten here, so validation can detect drift instead of healing it.
        """
        docs = {d.get("source_id", ""): d for d in self.manifest}
        for row in self.register:
            doc = docs.get(row.get("source_id", ""))
            if doc is None:
                continue
            if not (row.get("custodian_or_owner") or "").strip():
                row["custodian_or_owner"] = doc.get("owner", "")
            if not (row.get("content_digest") or "").strip():
                digest = (doc.get("sha256") or "").strip()
                row["content_digest"] = ("sha256:" + digest) if digest else ""

    def document(self, source_id: str) -> dict | None:
        return next((d for d in self.manifest if d.get("source_id") == source_id), None)

    def entries_for(self, source_id: str) -> list:
        return [e for e in self.register if e.get("source_id") == source_id]

    def cells_for(self, source_id: str) -> set:
        return {(e.get("group"), e.get("area")) for e in self.entries_for(source_id)}

    def multi_cell_documents(self) -> list:
        """Documents cited by more than one assessment cell - the case the order
        singles out, so it is a first-class query rather than a footnote."""
        return sorted((d["source_id"] for d in self.manifest
                       if len(self.cells_for(d["source_id"])) > 1))


# --------------------------------------------------------------------------
# Interchange: CSV and JSON, both directions
# --------------------------------------------------------------------------

def _read_csv(path: str, fields: Sequence[str]) -> tuple[list, list]:
    issues: list[Issue] = []
    if not os.path.exists(path):
        return [], [Issue(MISSING_DOCUMENT, os.path.basename(path), "file not found")]
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        extra = [h for h in (r.fieldnames or []) if h not in fields]
        for h in extra:
            issues.append(Issue(UNKNOWN_FIELD, os.path.basename(path),
                                f"column {h!r} is not in the schema; it is preserved on "
                                f"round trip but nothing validates it"))
        rows = [dict(x) for x in r]
    return rows, issues


def load_packet(root: str = DEFAULT_PACKET) -> tuple[Packet, list]:
    issues: list[Issue] = []
    man, i1 = _read_csv(os.path.join(root, "manifest.csv"), MANIFEST_FIELDS)
    reg, i2 = _read_csv(os.path.join(root, "register.csv"), REGISTER_FIELDS)
    issues.extend(i1 + i2)
    return Packet(root=root, manifest=man, register=reg), issues


def save_packet_csv(p: Packet, root: str) -> list:
    os.makedirs(root, exist_ok=True)
    written = []
    for name, rows, fields in (("manifest.csv", p.manifest, MANIFEST_FIELDS),
                               ("register.csv", p.register, REGISTER_FIELDS)):
        path = os.path.join(root, name)
        # Preserve any column the schema does not know about rather than
        # dropping it: an unrecognised field is somebody's data.
        extra = [k for r in rows for k in r if k not in fields]
        cols = list(fields) + sorted(set(extra))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
        written.append(path)
    return written


def to_json(p: Packet) -> dict:
    return {
        "status": "SYNTHETIC PACKET / NOT A UNIVERSITY FINDING",
        "schema": {"manifest_fields": MANIFEST_FIELDS,
                   "register_fields": REGISTER_FIELDS,
                   "register_fields_from_023": REGISTER_FIELDS_FROM_023,
                   "register_fields_added_by_031": REGISTER_FIELDS_ADDED_BY_031},
        "manifest": p.manifest,
        "register": p.register,
    }


def save_packet_json(p: Packet, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_json(p), f, indent=2, ensure_ascii=False)
    return path


def load_packet_json(path: str, root: str = "") -> Packet:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return Packet(root=root or os.path.dirname(path),
                  manifest=d.get("manifest", []), register=d.get("register", []))


# --------------------------------------------------------------------------
# Resolution: can the document, and the excerpt inside it, actually be found?
# --------------------------------------------------------------------------

def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_document(p: Packet, source_id: str) -> tuple[str, str]:
    """(absolute path, '') or ('', reason)."""
    doc = p.document(source_id)
    if doc is None:
        return "", f"no manifest entry for source_id {source_id!r}"
    loc = (doc.get("document_location") or "").strip()
    if not loc:
        return "", "manifest entry has no document_location"
    path = loc if os.path.isabs(loc) else os.path.join(p.root, loc)
    if not os.path.exists(path):
        return "", f"document_location {loc!r} does not resolve to a file"
    return path, ""


def resolve_excerpt(path: str, locator: str) -> tuple[str, str]:
    """Return (excerpt_text, '') or ('', reason). Reads the real bytes."""
    m = _LOC.match((locator or "").strip())
    if not m:
        return "", (f"locator {locator!r} is not one of lines:A-B, section:H, "
                    f"key:a.b, row:ID")
    kind, arg = m.group(1), m.group(2)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"cannot read document: {exc}"

    if kind == "lines":
        mm = re.match(r"^(\d+)(?:-(\d+))?$", arg)
        if not mm:
            return "", f"line range {arg!r} is malformed"
        a = int(mm.group(1))
        b = int(mm.group(2)) if mm.group(2) else a
        lines = text.split("\n")
        if a < 1 or b > len(lines) or a > b:
            return "", f"lines {a}-{b} are outside the document (it has {len(lines)})"
        return "\n".join(lines[a - 1:b]), ""

    if kind == "section":
        for i, line in enumerate(text.split("\n")):
            if line.lstrip("#").strip().lower() == arg.strip().lower() and line.startswith("#"):
                body = []
                for nxt in text.split("\n")[i + 1:]:
                    if nxt.startswith("#"):
                        break
                    body.append(nxt)
                return "\n".join([line] + body).strip(), ""
        return "", f"no heading named {arg!r} in the document"

    if kind == "key":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return "", f"document is not JSON: {exc}"
        cur = data
        for part in arg.split("."):
            if isinstance(cur, list):
                if not part.isdigit() or int(part) >= len(cur):
                    return "", f"key path {arg!r} does not resolve at {part!r}"
                cur = cur[int(part)]
            elif isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return "", f"key path {arg!r} does not resolve at {part!r}"
        return json.dumps(cur, ensure_ascii=False), ""

    if kind == "row":
        rows = list(csv.reader(text.splitlines()))
        if not rows:
            return "", "document has no rows"
        for row in rows[1:]:
            if row and row[0] == arg:
                return ",".join(row), ""
        return "", f"no row whose first column is {arg!r}"

    return "", f"unsupported locator kind {kind!r}"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate(p: Packet, check_digests: bool = True) -> list:
    """Every document findable from its entry; every locator resolvable."""
    issues: list[Issue] = []

    seen: set[str] = set()
    for d in p.manifest:
        sid = d.get("source_id", "")
        if sid in seen:
            issues.append(Issue(DUPLICATE_ID, sid,
                                "appears twice in the manifest; a reference to it is ambiguous"))
        seen.add(sid)

    seen_e: set[str] = set()
    for e in p.register:
        eid = e.get("evidence_id", "")
        if eid in seen_e:
            issues.append(Issue(DUPLICATE_ID, eid, "appears twice in the register"))
        seen_e.add(eid)

    for d in p.manifest:
        sid = d.get("source_id", "")
        path, why = resolve_document(p, sid)
        if why:
            issues.append(Issue(MISSING_DOCUMENT, sid, why))
            continue
        if check_digests and (declared := (d.get("sha256") or "").strip()):
            actual = sha256_of(path)
            if actual != declared:
                issues.append(Issue(
                    DIGEST_MISMATCH, sid,
                    f"manifest records {declared[:16]}..., the file on disk is "
                    f"{actual[:16]}... - the document changed after it was registered"))
        if not p.entries_for(sid):
            issues.append(Issue(ORPHAN_DOCUMENT, sid,
                                "document is in the manifest but no register entry cites it"))

    for e in p.register:
        eid = e.get("evidence_id", "")
        sid = (e.get("source_id") or "").strip()
        if not sid:
            issues.append(Issue(DANGLING_SOURCE_ID, eid, "entry names no source_id"))
            continue
        path, why = resolve_document(p, sid)
        if why:
            issues.append(Issue(DANGLING_SOURCE_ID, eid, why))
            continue
        doc = p.document(sid)
        expected_owner = (doc.get("owner") or "").strip()
        expected_digest = "sha256:" + (doc.get("sha256") or "").strip()
        if (e.get("custodian_or_owner") or "").strip() != expected_owner:
            issues.append(Issue(
                CUSTODY_MISMATCH, eid,
                "custodian_or_owner must mirror the manifest owner for the exact source_id"))
        if (e.get("content_digest") or "").strip().lower() != expected_digest.lower():
            issues.append(Issue(
                CONTENT_DIGEST_MISMATCH, eid,
                "content_digest must be sha256:<manifest sha256> for the exact source_id"))
        loc = (e.get("excerpt_locator") or "").strip()
        if not loc:
            issues.append(Issue(UNRESOLVED_LOCATOR, eid,
                                "entry has no excerpt_locator, so the support cannot be "
                                "located inside the document"))
            continue
        _, why = resolve_excerpt(path, loc)
        if why:
            code = BAD_LOCATOR_SYNTAX if "is not one of" in why else UNRESOLVED_LOCATOR
            issues.append(Issue(code, eid, why))

    return issues


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------

ROUND_TRIP_KEYS = ("source_id", "document_version", "document_location")
REGISTER_TRIP_KEYS = ("evidence_id", "source_id", "excerpt_locator",
                      "custodian_or_owner", "content_digest", "finding_id",
                      "observation_id", "group", "area")


def round_trip(p: Packet, workdir: str) -> tuple[Packet, list]:
    """CSV -> JSON -> CSV, then compare what the order says must survive.

    IDs, versions and locators are checked explicitly rather than relying on a
    whole-object comparison, because the order names those three.
    """
    issues: list[Issue] = []
    os.makedirs(workdir, exist_ok=True)
    jpath = save_packet_json(p, os.path.join(workdir, "packet.json"))
    viaj = load_packet_json(jpath, root=p.root)
    csvdir = os.path.join(workdir, "csv")
    save_packet_csv(viaj, csvdir)
    # The documents themselves are not copied; the round-tripped packet points at
    # the original root so locators must still resolve.
    back, load_issues = load_packet(csvdir)
    back.root = p.root
    issues.extend(load_issues)

    def index(rows, key):
        return {r.get(key, ""): r for r in rows}

    a, b = index(p.manifest, "source_id"), index(back.manifest, "source_id")
    if set(a) != set(b):
        issues.append(Issue("ROUND_TRIP_LOST_ROWS", "manifest",
                            f"source_ids before={sorted(set(a) - set(b))} "
                            f"after={sorted(set(b) - set(a))}"))
    for sid in sorted(set(a) & set(b)):
        for k in ROUND_TRIP_KEYS:
            if (a[sid].get(k) or "") != (b[sid].get(k) or ""):
                issues.append(Issue("ROUND_TRIP_CHANGED", f"{sid}.{k}",
                                    f"{a[sid].get(k)!r} -> {b[sid].get(k)!r}"))

    ra, rb = index(p.register, "evidence_id"), index(back.register, "evidence_id")
    if set(ra) != set(rb):
        issues.append(Issue("ROUND_TRIP_LOST_ROWS", "register",
                            f"evidence_ids before={sorted(set(ra) - set(rb))} "
                            f"after={sorted(set(rb) - set(ra))}"))
    for eid in sorted(set(ra) & set(rb)):
        for k in REGISTER_TRIP_KEYS:
            if (ra[eid].get(k) or "") != (rb[eid].get(k) or ""):
                issues.append(Issue("ROUND_TRIP_CHANGED", f"{eid}.{k}",
                                    f"{ra[eid].get(k)!r} -> {rb[eid].get(k)!r}"))

    # The multi-cell case the order calls out: the same document must still be
    # cited by the same set of cells afterwards.
    for sid in p.multi_cell_documents():
        before, after = p.cells_for(sid), back.cells_for(sid)
        if before != after:
            issues.append(Issue("ROUND_TRIP_CHANGED", f"{sid}.cells",
                                f"{sorted(before)} -> {sorted(after)}"))

    return back, issues


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def render(p: Packet, issues: Sequence[Issue], title: str = "") -> str:
    L = [f"EVIDENCE REGISTER{(' - ' + title) if title else ''}", "=" * 58,
         f"documents : {len(p.manifest)}",
         f"entries   : {len(p.register)}",
         f"cells     : {len({(e.get('group'), e.get('area')) for e in p.register})} of 12",
         f"multi-cell documents: {', '.join(p.multi_cell_documents()) or 'none'}",
         f"issues    : {len(issues)}", ""]
    for i in issues:
        L.append("  " + str(i))
    if not issues:
        L.append("  none - every document resolves and every locator is followable")
    return "\n".join(L)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evidence register and document manifest.")
    ap.add_argument("--packet", default=DEFAULT_PACKET)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--round-trip", metavar="WORKDIR", default=None)
    ap.add_argument("--export-json", metavar="PATH", default=None)
    ap.add_argument("--show-excerpts", action="store_true",
                    help="print the text each excerpt_locator actually resolves to")
    a = ap.parse_args(argv)

    p, issues = load_packet(a.packet)
    rc = 0

    if a.validate or not any([a.round_trip, a.export_json, a.show_excerpts]):
        issues = issues + validate(p)
        print(render(p, issues, "validate"))
        if issues:
            rc = 1

    if a.show_excerpts:
        print()
        for e in p.register:
            path, why = resolve_document(p, e.get("source_id", ""))
            if why:
                print(f"{e.get('evidence_id')}: UNRESOLVED - {why}")
                continue
            text, why = resolve_excerpt(path, e.get("excerpt_locator", ""))
            head = text.replace("\n", " / ")[:110] if not why else f"UNRESOLVED - {why}"
            print(f"{e.get('evidence_id')}  {e.get('source_id')}  "
                  f"{e.get('excerpt_locator')}\n    {head}")

    if a.export_json:
        print("wrote " + save_packet_json(p, a.export_json))

    if a.round_trip:
        _, rt = round_trip(p, a.round_trip)
        print()
        print(render(p, rt, "round trip"))
        if rt:
            rc = 1

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
