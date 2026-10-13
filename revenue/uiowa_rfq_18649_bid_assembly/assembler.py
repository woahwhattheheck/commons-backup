"""UIOWA-136 version-bound bidder attachment assembly.

Isolated path: revenue/uiowa_rfq_18649_bid_assembly/

Turns prepared proposal components plus a hash-bound attachment
manifest into a review-draft folder: stable names, attachment index,
missing financial/qualification placeholders (never invented
credentials), source/version register, RFQ reconciliation, and
PDF/DOCX/HTML with real internal navigation.

This is not a University submission, buyer contact, invoice, payment,
revenue event, or qualification certification.

PDF/DOCX writers recovered from OP5-TOPAZ bid_pack (credited). TOPAZ
retains original assembler credit. This package consumes UIOWA-132
commercial-facts and adds the currentness/workshare-vs-prime-fee holds
that bid_pack on main currently lacks.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil

try:
    from . import canonical, docxwrite, htmlwrite, pdfwrite
except ImportError:  # unittest from the package directory
    import canonical
    import docxwrite
    import htmlwrite
    import pdfwrite

SCHEMA = "uiowa-136-bid-assembly/1"
MAX_PAGINATION_PASSES = 8
MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 8_000_000

ERROR, WARN, INFO = "ERROR", "WARN", "INFO"
REF_RE = re.compile(r"\[\[([A-Za-z0-9_.\-]+)\]\]")

REQUIRED_TOP_KEYS = ("schema", "submission", "sections", "attachments")
REQUIRED_SECTION_KEYS = ("id", "title")
REQUIRED_ATTACHMENT_KEYS = ("id", "title", "category")


class AssemblyError(Exception):
    """The pack cannot be assembled without inventing something."""


class PaginationError(Exception):
    """Page numbers did not settle, so no page number is trustworthy."""


def slugify(text, limit=48):
    s = re.sub(r"[^0-9A-Za-z]+", "-", (text or "")).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)
    return (s[:limit].strip("-")) or "untitled"


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return sha256_bytes(fh.read())


def _safe_join(root, rel):
    if os.path.isabs(rel):
        raise AssemblyError("source path must be relative to the pack root: %r" % rel)
    full = os.path.normpath(os.path.join(root, rel))
    if not (full == root or full.startswith(root + os.sep)):
        raise AssemblyError("source path escapes the pack root: %r" % rel)
    return full


def _read_bounded(path, budget):
    st = os.stat(path)
    if st.st_size > MAX_FILE_BYTES:
        raise AssemblyError(
            "input %r is %d bytes; refusing to silently overflow (limit %d)"
            % (path, st.st_size, MAX_FILE_BYTES)
        )
    if st.st_size > budget:
        raise AssemblyError(
            "input %r would exceed remaining pack budget %d bytes" % (path, budget)
        )
    with open(path, "rb") as fh:
        blob = fh.read()
    if len(blob) != st.st_size:
        raise AssemblyError("input %r changed size while reading" % path)
    return blob


def load_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise AssemblyError("manifest not found: %s" % path)
    except json.JSONDecodeError as exc:
        raise AssemblyError("manifest is not valid JSON (%s): %s" % (path, exc))
    validate_manifest(data)
    return data


def validate_manifest(data):
    if not isinstance(data, dict):
        raise AssemblyError("manifest must be a JSON object")
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        raise AssemblyError("manifest is missing required key(s): %s" % ", ".join(sorted(missing)))
    if data.get("schema") != SCHEMA:
        raise AssemblyError(
            "unsupported manifest schema %r (expected %r)" % (data.get("schema"), SCHEMA)
        )
    for name, items, keys in (
        ("sections", data["sections"], REQUIRED_SECTION_KEYS),
        ("attachments", data["attachments"], REQUIRED_ATTACHMENT_KEYS),
    ):
        if not isinstance(items, list):
            raise AssemblyError("%s must be a list" % name)
        seen = set()
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise AssemblyError("%s[%d] must be an object" % (name, i))
            gone = [k for k in keys if not item.get(k)]
            if gone:
                raise AssemblyError(
                    "%s[%d] is missing required field(s): %s" % (name, i, ", ".join(gone))
                )
            if item["id"] in seen:
                raise AssemblyError("duplicate id %r in %s" % (item["id"], name))
            seen.add(item["id"])
    if not data["sections"]:
        raise AssemblyError("manifest declares no sections; there is nothing to assemble")
    status = str(data.get("submission", {}).get("status_label") or "")
    low = status.lower()
    for tok in canonical.FORBIDDEN_STATUS_TOKENS:
        if tok in low:
            raise AssemblyError(
                "submission.status_label %r invents an approval/submission state; "
                "this assembler only emits review drafts" % status
            )


def _section_row(section, page_map):
    row = {k: v for k, v in section.items() if k != "body"}
    row["page"] = page_map[section["id"]] + 1 if section["id"] in page_map else None
    return row


class BidAssembly(object):
    def __init__(self, manifest, root):
        self.m = manifest
        self.root = os.path.abspath(root)
        self.issues = []
        self.budget = MAX_TOTAL_BYTES
        self.source_register = []

    def _issue(self, severity, code, detail, ref=None):
        self.issues.append(
            {"severity": severity, "code": code, "detail": detail, "ref": ref}
        )

    def _consume(self, path):
        blob = _read_bounded(path, self.budget)
        self.budget -= len(blob)
        digest = sha256_bytes(blob)
        rel = os.path.relpath(path, self.root)
        self.source_register.append(
            {"path": rel.replace("\\", "/"), "bytes": len(blob), "sha256": digest}
        )
        return blob, digest

    def _assign_filenames(self):
        taken = {}
        explicit = {}
        out = {}
        for prefix, items in (("", self.m["sections"]), ("A", self.m["attachments"])):
            for i, item in enumerate(items, start=1):
                ext = item.get("ext")
                if not ext:
                    src = item.get("source") or ""
                    ext = os.path.splitext(src)[1] or (".md" if prefix == "" else ".txt")
                if item.get("filename"):
                    name = item["filename"]
                    key = name.lower()
                    if key in explicit:
                        raise AssemblyError(
                            "two entries declare the same filename %r (%s and %s)"
                            % (name, explicit[key], item["id"])
                        )
                    explicit[key] = item["id"]
                else:
                    name = "%s%02d-%s%s" % (prefix, i, slugify(item["title"]), ext)
                key = name.lower()
                if key in taken:
                    base, e = os.path.splitext(name)
                    name = "%s--%s%s" % (base, slugify(item["id"]), e)
                    self._issue(
                        INFO,
                        "FILENAME_COLLISION_RESOLVED",
                        "filename collided with %s (case-insensitively); disambiguated to %r"
                        % (taken[key], name),
                        item["id"],
                    )
                    key = name.lower()
                taken[key] = item["id"]
                out[item["id"]] = name
        return out

    def _load_sections(self, names):
        out = []
        for i, sec in enumerate(self.m["sections"], start=1):
            body, status, digest = "", "NOT_SUPPLIED", None
            src = sec.get("source")
            if not src:
                self._issue(
                    WARN,
                    "SECTION_CONTENT_NOT_SUPPLIED",
                    "section %s (%s) declares no source file" % (sec["id"], sec["title"]),
                    sec["id"],
                )
            else:
                path = _safe_join(self.root, src)
                if not os.path.isfile(path):
                    self._issue(
                        WARN,
                        "SECTION_CONTENT_NOT_SUPPLIED",
                        "section %s declares source %r which does not exist" % (sec["id"], src),
                        sec["id"],
                    )
                else:
                    blob, digest = self._consume(path)
                    body = blob.decode("utf-8")
                    status = "SUPPLIED"
            out.append(
                {
                    "id": sec["id"],
                    "ordinal": i,
                    "title": sec["title"],
                    "filename": names[sec["id"]],
                    "content_status": status,
                    "body": body,
                    "source": src,
                    "sha256": digest,
                }
            )
        return out

    def _load_attachments(self, names):
        out = []
        for i, att in enumerate(self.m["attachments"], start=1):
            src = att.get("source")
            declared = bool(att.get("provided"))
            path = _safe_join(self.root, src) if src else None
            present = bool(path and os.path.isfile(path))
            size = sha = None
            if present:
                blob, sha = self._consume(path)
                size = len(blob)
                status = "SUPPLIED"
                if size == 0:
                    status = "SUPPLIED-EMPTY FILE"
                    self._issue(
                        WARN,
                        "ATTACHMENT_EMPTY_FILE",
                        "attachment %s is present but zero bytes; an empty file is not evidence"
                        % att["id"],
                        att["id"],
                    )
                if not declared:
                    self._issue(
                        INFO,
                        "ATTACHMENT_PRESENT_NOT_DECLARED",
                        "attachment %s has a file on disk but the manifest does not mark it provided"
                        % att["id"],
                        att["id"],
                    )
            else:
                status = "PLACEHOLDER-NOT SUPPLIED"
                if declared:
                    self._issue(
                        ERROR,
                        "ATTACHMENT_DECLARED_PROVIDED_BUT_ABSENT",
                        "attachment %s is marked provided=true but %r is not on disk"
                        % (att["id"], src or "(no source)"),
                        att["id"],
                    )
                sev = WARN if att.get("required") else INFO
                self._issue(
                    sev,
                    "ATTACHMENT_NOT_SUPPLIED",
                    "%s attachment %s (%s) has no file; emitted as a placeholder"
                    % (
                        "required" if att.get("required") else "optional",
                        att["id"],
                        att["title"],
                    ),
                    att["id"],
                )
            out.append(
                {
                    "id": att["id"],
                    "ordinal": i,
                    "title": att["title"],
                    "category": att.get("category", "UNKNOWN"),
                    "required": bool(att.get("required")),
                    "status": status,
                    "present": present,
                    "filename": names[att["id"]] if present else None,
                    "bytes": size,
                    "sha256": sha,
                    "source": src,
                    "note": att.get("note", ""),
                    "rfq_attr": att.get("rfq_attr"),
                }
            )
        return out

    def _extra_files(self, sections, attachments):
        declared = set()
        declared.add("manifest.json")
        for item in list(sections) + list(attachments):
            src = item.get("source")
            if src:
                declared.add(os.path.normpath(src).replace("\\", "/"))
        extras = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root).replace("\\", "/")
                if rel not in declared:
                    extras.append(rel)
        extras.sort()
        for rel in extras:
            self._issue(
                ERROR,
                "UNDECLARED_FILE_IN_PACK",
                "file %r is in the pack root but not in the hash-bound manifest" % rel,
                rel,
            )
        return extras

    def _reconcile(self, sections, attachments):
        facts, source, mismatch = canonical.commercial_facts()
        hold = {
            "rfq_printed_deadline": canonical.RFQ_PRINTED_DEADLINE,
            "workshare_overlay_deadline": canonical.WORKSHARE_OVERLAY_DEADLINE,
            "official_refresh_confirmed": False,
            "status": "CURRENTNESS_HOLD",
            "note": (
                "The recovered Bid Invitation prints 2026-09-22 15:00 CT. "
                "The workshare carrier documents 2026-09-29 15:00 CT. "
                "UIOWA-132 pins 2026-09-22. This assembler does not pick a "
                "winner. Official eBid refresh is unconfirmed."
            ),
            "commercial_facts_source": source,
            "commercial_facts_mismatch": list(mismatch),
            "workshare_base_usd": canonical.WORKSHARE_BASE_USD,
            "workshare_option_usd": canonical.WORKSHARE_OPTION_USD,
            "workshare_is_not_prime_fee": True,
            "attribute_15": "NOT_FILLED — blank has certification effect; no invented no-exceptions response",
            "authority": dict(canonical.AUTHORITY),
        }
        if mismatch:
            self._issue(
                ERROR,
                "COMMERCIAL_FACTS_DIVERGED",
                "local pins disagree with landed UIOWA-132 on: %s" % ", ".join(mismatch),
            )
        else:
            self._issue(
                INFO,
                "COMMERCIAL_FACTS_CONSUMED",
                "consumed UIOWA-132 commercial-facts from %s; $%d is TJLabs subcontract workshare, not the prime bid fee"
                % (source, canonical.WORKSHARE_BASE_USD),
            )
        if canonical.RFQ_PRINTED_DEADLINE != canonical.WORKSHARE_OVERLAY_DEADLINE:
            self._issue(
                WARN,
                "DEADLINE_CURRENTNESS_HOLD",
                "RFQ print %s vs workshare overlay %s; official refresh unconfirmed"
                % (canonical.RFQ_PRINTED_DEADLINE, canonical.WORKSHARE_OVERLAY_DEADLINE),
            )
        text = " ".join(s.get("body") or "" for s in sections).lower()
        if "no exceptions" in text and "invented" not in text:
            # A supplied section that actually asserts no-exceptions is a hold,
            # not auto-certified.
            self._issue(
                WARN,
                "ATTRIBUTE_15_NO_EXCEPTIONS_UNVERIFIED",
                "prepared text mentions no-exceptions; Attribute 15 is not filled as a certification",
            )
        fee_present = any(a["id"] == "ATT-FEE-01" and a["present"] for a in attachments)
        if not fee_present:
            self._issue(
                WARN,
                "PRIME_FEE_NOT_SUPPLIED",
                "$%d workshare is not the Attribute 9 / Bid Line 1 all-inclusive prime fee"
                % canonical.WORKSHARE_BASE_USD,
            )
        return facts, hold

    def _resolve(self, text, sections, attachments, page_map, owner):
        secs = {s["id"]: s for s in sections}
        atts = {a["id"]: a for a in attachments}
        refs = []

        def page_of(anchor):
            p = page_map.get(anchor)
            return str(p + 1) if p is not None else "--"

        def repl(match):
            rid = match.group(1)
            if rid in secs:
                s = secs[rid]
                refs.append(
                    {
                        "from": owner,
                        "to": rid,
                        "kind": "section",
                        "status": "RESOLVED",
                        "label": s["title"],
                    }
                )
                return "Section %d (%s), page %s" % (s["ordinal"], s["title"], page_of(rid))
            if rid in atts:
                a = atts[rid]
                state = "" if a["present"] else " - PLACEHOLDER, NOT SUPPLIED"
                refs.append(
                    {
                        "from": owner,
                        "to": rid,
                        "kind": "attachment",
                        "status": "RESOLVED",
                        "label": a["title"],
                    }
                )
                return (
                    "Attachment %s (%s)%s - see attachment index, page %s"
                    % (rid, a["title"], state, page_of("IDX-" + rid))
                )
            refs.append(
                {
                    "from": owner,
                    "to": rid,
                    "kind": "unknown",
                    "status": "UNRESOLVED",
                    "label": None,
                }
            )
            return "[UNRESOLVED REFERENCE: %s]" % rid

        return REF_RE.sub(repl, text), refs

    def _readiness(self, attachments):
        req = [a for a in attachments if a["required"]]
        present = [a for a in req if a["present"] and a["bytes"]]
        missing = [a["id"] for a in req if not (a["present"] and a["bytes"])]
        if missing:
            status = "SUBMISSION_INCOMPLETE"
        elif not req:
            status = "NO_REQUIRED_ATTACHMENTS_DECLARED"
        else:
            status = "ALL_DECLARED_REQUIRED_ATTACHMENTS_PRESENT"
        return {
            "required_declared": len(req),
            "required_present": len(present),
            "required_not_supplied": missing,
            "status": status,
            "note": (
                "Counts describe declared-vs-present documents in this pack only. "
                "This is not a readiness score and not University completeness."
            ),
        }

    def _blocks(self, sections, attachments, page_map, hold, facts):
        sub = self.m["submission"]
        all_refs = []
        notice = self.m.get("fiction_notice") or canonical.FICTION_NOTICE
        b = [
            {
                "kind": "title",
                "text": sub.get("title") or "Proposal",
                "anchor": "DOC-TOP",
            }
        ]
        for line in (
            "Solicitation: %s" % sub.get("solicitation_id", "UNKNOWN"),
            "Bidder of record: %s" % sub.get("bidder_name", "UNKNOWN"),
            "Assembly status: %s" % sub.get("status_label", "REVIEW_DRAFT"),
            "Assembled by: assembler.py (%s)" % SCHEMA,
            "TJLabs workshare (subcontract, not prime fee): $%s USD base + $%s optional readout"
            % (
                "{:,}".format(facts["base_amount_usd"]),
                "{:,}".format(facts["option_amount_usd"]),
            ),
            "Deadline currentness: %s (RFQ print %s; workshare overlay %s)"
            % (
                hold["status"],
                hold["rfq_printed_deadline"],
                hold["workshare_overlay_deadline"],
            ),
        ):
            b.append({"kind": "body", "text": line})
        b.append({"kind": "spacer", "height": 10})
        b.append({"kind": "body", "text": notice})

        b.append({"kind": "pagebreak"})
        b.append(
            {
                "kind": "heading",
                "text": "Document Map",
                "anchor": "TOC",
                "outline": "Document Map",
            }
        )
        b.append(
            {
                "kind": "body",
                "text": "Every row below is a live link in the PDF, a bookmark in the DOCX, and a fragment in the HTML.",
            }
        )
        b.append({"kind": "spacer", "height": 6})
        for s in sections:
            page = page_map.get(s["id"])
            pg = str(page + 1) if page is not None else "--"
            dots = "." * max(3, 62 - len(s["title"]))
            flag = "" if s["content_status"] == "SUPPLIED" else "  [CONTENT NOT SUPPLIED]"
            b.append(
                {
                    "kind": "mono",
                    "text": "%2d  %s %s %4s%s" % (s["ordinal"], s["title"], dots, pg, flag),
                    "dest": s["id"],
                }
            )

        b.append({"kind": "spacer", "height": 12})
        b.append(
            {
                "kind": "heading",
                "text": "Attachment Index",
                "anchor": "ATTIDX",
                "outline": "Attachment Index",
            }
        )
        b.append(
            {
                "kind": "body",
                "text": "UNKNOWN means no file was supplied, so size and digest could not be measured. It is not zero and it is not a pass.",
            }
        )
        b.append({"kind": "spacer", "height": 6})
        b.append(
            {
                "kind": "mono",
                "text": "%-12s %-26s %-10s %-16s" % ("ID", "STATUS", "BYTES", "SHA256[:16]"),
            }
        )
        b.append({"kind": "mono", "text": "-" * 66})
        for a in attachments:
            size = "UNKNOWN" if a["bytes"] is None else "{:,}".format(a["bytes"])
            sha = a["sha256"][:16] if a["sha256"] else "UNKNOWN"
            b.append(
                {
                    "kind": "mono",
                    "text": "%-12s %-26s %-10s %-16s" % (a["id"], a["status"], size, sha),
                    "anchor": "IDX-" + a["id"],
                }
            )
            tail = a["filename"] if a["present"] else "(no file supplied)"
            req = "required" if a["required"] else "optional"
            b.append(
                {
                    "kind": "mono",
                    "text": "             %s [%s, %s] -> %s"
                    % (a["title"], a["category"], req, tail),
                }
            )

        ready = self._readiness(attachments)
        b.append({"kind": "spacer", "height": 12})
        b.append({"kind": "subheading", "text": "Submission completeness"})
        b.append({"kind": "body", "text": "Status: %s" % ready["status"]})
        b.append(
            {
                "kind": "body",
                "text": "Required attachments declared: %d. Present: %d. Not supplied: %d."
                % (
                    ready["required_declared"],
                    ready["required_present"],
                    len(ready["required_not_supplied"]),
                ),
            }
        )
        if ready["required_not_supplied"]:
            b.append(
                {
                    "kind": "body",
                    "text": "Not supplied: %s" % ", ".join(ready["required_not_supplied"]),
                }
            )
        b.append({"kind": "body", "text": ready["note"]})
        b.append({"kind": "body", "text": hold["note"]})
        b.append({"kind": "body", "text": hold["attribute_15"]})
        b.append(
            {
                "kind": "body",
                "text": "Principal remains prime; specialist remains subcontract. Roles are not collapsed.",
            }
        )

        b.append({"kind": "pagebreak"})
        b.append(
            {
                "kind": "heading",
                "text": "Source and version register",
                "anchor": "S-REGISTER",
                "outline": "Source and version register",
            }
        )
        b.append(
            {
                "kind": "body",
                "text": "Every supplied source below is hashed. Missing required inputs stay missing.",
            }
        )
        if not self.source_register:
            b.append({"kind": "body", "text": "No supplied source files were hashed."})
        for rec in self.source_register:
            b.append(
                {
                    "kind": "mono",
                    "text": "%s  %s  %s" % (rec["sha256"][:16], rec["bytes"], rec["path"]),
                }
            )

        for s in sections:
            b.append({"kind": "pagebreak"})
            b.append(
                {
                    "kind": "heading",
                    "text": "%d. %s" % (s["ordinal"], s["title"]),
                    "anchor": s["id"],
                    "outline": "%d. %s" % (s["ordinal"], s["title"]),
                }
            )
            if s["content_status"] != "SUPPLIED":
                b.append(
                    {
                        "kind": "body",
                        "text": "[SECTION CONTENT NOT SUPPLIED - this page is a placeholder. No text was written on the bidder's behalf.]",
                    }
                )
                continue
            resolved, refs = self._resolve(
                s["body"], sections, attachments, page_map, s["id"]
            )
            all_refs.extend(refs)
            for para in [p.strip() for p in resolved.split("\n\n")]:
                if para:
                    b.append({"kind": "body", "text": para})
        return b, all_refs

    def assemble(self, out_dir, write_files=True):
        if write_files and os.path.exists(out_dir):
            raise AssemblyError(
                "output directory already exists (%s); refusing to overwrite"
                % out_dir
            )
        names = self._assign_filenames()
        sections = self._load_sections(names)
        attachments = self._load_attachments(names)
        extras = self._extra_files(sections, attachments)
        facts, hold = self._reconcile(sections, attachments)

        page_map, passes = {}, 0
        blocks = None
        pages = None
        refs = []
        for passes in range(1, MAX_PAGINATION_PASSES + 1):
            blocks, refs = self._blocks(sections, attachments, page_map, hold, facts)
            pages = pdfwrite.paginate(blocks)
            new_map = {k: v[0] for k, v in pdfwrite.anchor_pages(pages).items()}
            if new_map == page_map:
                break
            page_map = new_map
        else:
            raise PaginationError(
                "page numbers did not settle after %d passes; refusing to print a "
                "page number that may be wrong" % MAX_PAGINATION_PASSES
            )

        for r in refs:
            if r["status"] == "UNRESOLVED":
                self._issue(
                    WARN,
                    "XREF_UNRESOLVED",
                    "section %s references %r, which is not a section or an attachment"
                    % (r["from"], r["to"]),
                    r["from"],
                )

        sub = self.m["submission"]
        title = sub.get("title") or "Proposal"
        author = sub.get("bidder_name", "")
        pdf_bytes, lost = pdfwrite.write_pdf(pages, title=title, author=author)
        if lost:
            self._issue(
                WARN,
                "UNICODE_NOT_REPRESENTABLE_IN_PDF",
                "%d character(s) outside WinAnsi were replaced with '?' in the PDF"
                % len(lost),
            )

        result = {
            "schema": SCHEMA,
            "submission": sub,
            "fiction_notice": self.m.get("fiction_notice") or canonical.FICTION_NOTICE,
            "sections": [_section_row(s, page_map) for s in sections],
            "attachments": [
                dict(
                    a,
                    index_page=(
                        page_map["IDX-" + a["id"]] + 1
                        if "IDX-" + a["id"] in page_map
                        else None
                    ),
                )
                for a in attachments
            ],
            "cross_references": refs,
            "readiness": self._readiness(attachments),
            "issues": self.issues,
            "reconciliation": hold,
            "commercial_facts": {
                k: (list(v) if isinstance(v, tuple) else v) for k, v in facts.items()
            },
            "source_register": self.source_register,
            "undeclared_files": extras,
            "render": {
                "pdf_pages": len(pages),
                "pagination_passes": passes,
                "pdf_bytes": len(pdf_bytes),
            },
            "authority": dict(canonical.AUTHORITY),
        }

        if write_files:
            self._write(
                out_dir, sections, attachments, blocks, pdf_bytes, result, title, author
            )
        return result

    def _write(self, out_dir, sections, attachments, blocks, pdf_bytes, result, title, author):
        os.makedirs(out_dir)
        docs = os.path.join(out_dir, "documents")
        atts = os.path.join(out_dir, "attachments")
        os.makedirs(docs)
        os.makedirs(atts)

        notice = result["fiction_notice"]
        for s in sections:
            dest = os.path.join(docs, s["filename"])
            if s["content_status"] == "SUPPLIED":
                with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(
                        "<!-- %s -->\n# %d. %s\n\n%s\n"
                        % (notice, s["ordinal"], s["title"], s["body"])
                    )
            else:
                with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(
                        "# %d. %s\n\nSECTION CONTENT NOT SUPPLIED. This file is a "
                        "placeholder so the gap is visible in the folder listing. "
                        "No text was written on the bidder's behalf.\n"
                        % (s["ordinal"], s["title"])
                    )
        for a in attachments:
            if a["present"]:
                shutil.copyfile(
                    _safe_join(self.root, a["source"]),
                    os.path.join(atts, a["filename"]),
                )
            else:
                ph = os.path.join(
                    atts,
                    "A%02d-%s.PLACEHOLDER.txt" % (a["ordinal"], slugify(a["title"])),
                )
                with open(ph, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(
                        "PLACEHOLDER - NOT SUPPLIED\n\n"
                        "Attachment id: %s\nTitle: %s\nCategory: %s\nRequired: %s\n"
                        "RFQ attribute: %s\n\n"
                        "No document was supplied for this attachment. Size and digest "
                        "are UNKNOWN. This file exists so the absence is visible in the "
                        "submission folder; it is not the attachment and must not be "
                        "submitted in its place. Credentials, insurance, audited "
                        "statements, annual reports, and certifications are never invented.\n"
                        % (
                            a["id"],
                            a["title"],
                            a["category"],
                            "yes" if a["required"] else "no",
                            a.get("rfq_attr") or "UNKNOWN",
                        )
                    )

        with open(os.path.join(out_dir, "proposal.pdf"), "wb") as fh:
            fh.write(pdf_bytes)
        docxwrite.write_docx(
            os.path.join(out_dir, "proposal.docx"), blocks, title=title, author=author
        )
        htmlwrite.write_html(
            os.path.join(out_dir, "proposal.html"),
            blocks,
            title=title,
            notice=notice,
        )

        with open(
            os.path.join(out_dir, "attachment_index.csv"),
            "w",
            encoding="utf-8",
            newline="",
        ) as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "attachment_id",
                    "title",
                    "category",
                    "required",
                    "status",
                    "filename",
                    "bytes",
                    "sha256",
                    "index_page",
                ]
            )
            for a in result["attachments"]:
                w.writerow(
                    [
                        a["id"],
                        a["title"],
                        a["category"],
                        "yes" if a["required"] else "no",
                        a["status"],
                        a["filename"] or "UNKNOWN",
                        "UNKNOWN" if a["bytes"] is None else a["bytes"],
                        a["sha256"] or "UNKNOWN",
                        a["index_page"] if a["index_page"] else "UNKNOWN",
                    ]
                )

        payload = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False)
        digest = sha256_bytes(payload.encode("utf-8"))
        with open(os.path.join(out_dir, "assembly.json"), "w", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    dict(result, content_digest=digest),
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            fh.write("\n")
        with open(os.path.join(out_dir, "00-INDEX.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self._index_md(result))

    def _index_md(self, result):
        r = result["readiness"]
        hold = result["reconciliation"]
        out = [
            "# Review-draft assembly index",
            "",
            "> %s" % result["fiction_notice"],
            "",
            "Solicitation: `%s`  " % result["submission"].get("solicitation_id", "UNKNOWN"),
            "Bidder: %s  " % result["submission"].get("bidder_name", "UNKNOWN"),
            "Assembly status: **%s**  " % result["submission"].get("status_label", "REVIEW_DRAFT"),
            "Rendered: `proposal.pdf` (%d pages), `proposal.docx`, `proposal.html`"
            % result["render"]["pdf_pages"],
            "",
            "## Commercial facts consumed (UIOWA-132)",
            "",
            "- RFQ `%s`, currency `%s`"
            % (
                result["commercial_facts"].get("rfq_id"),
                result["commercial_facts"].get("currency"),
            ),
            "- TJLabs subcontract workshare $%s base + $%s option (not the prime bid fee)"
            % (
                "{:,}".format(result["commercial_facts"]["base_amount_usd"]),
                "{:,}".format(result["commercial_facts"]["option_amount_usd"]),
            ),
            "- Split 40/40/20 = $9,600 / $9,600 / $4,800",
            "- Principal = prime, specialist = subcontract",
            "- Deadline currentness: **%s** (RFQ print %s; overlay %s)"
            % (
                hold["status"],
                hold["rfq_printed_deadline"],
                hold["workshare_overlay_deadline"],
            ),
            "",
            "## Documents",
            "",
            "| # | Section | File | PDF page | Content |",
            "|---|---|---|---|---|",
        ]
        for s in result["sections"]:
            out.append(
                "| %d | %s | `documents/%s` | %s | %s |"
                % (
                    s["ordinal"],
                    s["title"],
                    s["filename"],
                    s["page"] or "UNKNOWN",
                    s["content_status"],
                )
            )
        out += [
            "",
            "## Attachment index",
            "",
            "`UNKNOWN` = no file supplied, so nothing could be measured. Not zero.",
            "",
            "| ID | Title | Category | Required | Status | File | Bytes | SHA256 | Index page |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for a in result["attachments"]:
            out.append(
                "| %s | %s | %s | %s | **%s** | %s | %s | %s | %s |"
                % (
                    a["id"],
                    a["title"],
                    a["category"],
                    "yes" if a["required"] else "no",
                    a["status"],
                    "`attachments/%s`" % a["filename"] if a["filename"] else "_(placeholder)_",
                    "UNKNOWN" if a["bytes"] is None else "{:,}".format(a["bytes"]),
                    "`%s`" % a["sha256"][:16] if a["sha256"] else "UNKNOWN",
                    a["index_page"] or "UNKNOWN",
                )
            )
        out += [
            "",
            "## Completeness",
            "",
            "**%s**" % r["status"],
            "",
            "- Required attachments declared: %d" % r["required_declared"],
            "- Present: %d" % r["required_present"],
            "- Not supplied: %s"
            % (
                ", ".join("`%s`" % i for i in r["required_not_supplied"]) or "none"
            ),
            "",
            "> %s" % r["note"],
            "",
            "## Cross-references",
            "",
        ]
        for x in result["cross_references"]:
            out.append(
                "- `%s` -> `%s` (%s) **%s**"
                % (x["from"], x["to"], x["kind"], x["status"])
            )
        out += ["", "## Assembler issues", ""]
        if not result["issues"]:
            out.append("_none_")
        for i in result["issues"]:
            out.append("- **%s** `%s` %s" % (i["severity"], i["code"], i["detail"]))
        return "\n".join(out) + "\n"
