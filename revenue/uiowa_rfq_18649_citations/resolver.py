"""Resolve supplied identities against retained bytes and the real compiler report."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

from .contract import CitationError, TRACE_SCHEMA, LABEL, canonical, digest, relative_path, validate_packet
from .integration import extract_snapshot, verify_inspection


class Resolver:
    def __init__(self, packet: dict, report: dict, root: Path):
        validate_packet(packet)
        self.integrity = verify_inspection(report)
        if packet["compiler_receipt_sha256"] != report["receipt_sha256"]:
            raise CitationError("Citation packet belongs to a different compiler receipt")
        if packet["generation"] != report["evidence_authority"]["generation"]:
            raise CitationError("Citation packet belongs to a different evidence generation")
        self.packet, self.report = copy.deepcopy(packet), copy.deepcopy(report)
        self.root = root.resolve()
        self.authority = {row["source_id"]: row for row in self.report["evidence_authority"]["sources"]}
        self.retained: dict[str, tuple[bytes, dict]] = {}
        self.cache: dict[tuple, tuple] = {}

    def _source(self, source: dict):
        key = (source["path"], tuple(source.get("aliases", [])), source["sha256"])
        if key in self.cache:
            return self.cache[key]
        candidates, changed = [], []
        for location in dict.fromkeys([source["path"], *source.get("aliases", [])]):
            path = self.root.joinpath(*relative_path(location).parts).resolve()
            if not path.is_relative_to(self.root):
                raise CitationError("Source path leaves the supplied bundle root")
            if not path.is_file():
                continue
            if path.stat().st_size > 50 * 1024 * 1024:
                raise CitationError("Source exceeds extractor's 50 MiB limit")
            data = path.read_bytes()
            if digest(data) != source["sha256"]:
                changed.append(location)
                continue
            candidates.append((location, data))
        if not candidates:
            result = (None, None, None, "CONTENT_HASH_MISMATCH" if changed else "MISSING_SOURCE_BYTES")
        else:
            location, data = candidates[0]
            # The immutable byte copy is both extracted and later exported.
            extraction = extract_snapshot(data, Path(location).name)
            stored = "original/" + location
            if stored in self.retained and self.retained[stored][0] != data:
                raise CitationError("One source path refers to different retained bytes")
            self.retained[stored] = (data, extraction)
            result = (location, stored, extraction, None)
        self.cache[key] = result
        return result

    def resolve(self, ref: dict, finding: dict) -> dict:
        result = {"source_id": ref["source_id"], "version": ref["version"],
                  "sha256": ref["sha256"], "segment_id": ref["segment_id"],
                  "requested_locator": ref["locator"], "requested_quote": ref["quote"],
                  "resolved": False, "diagnostics": [], "citation": None}
        def stop(code):
            result["diagnostics"].append(code)
            return result
        by_id = [row for row in self.packet["sources"] if row["source_id"] == ref["source_id"]]
        if not by_id:
            return stop("MISSING_SOURCE_ID")
        versions = [row for row in by_id if row["version"] == ref["version"]]
        if not versions:
            return stop("MISSING_VERSION")
        if len(versions) != 1:
            return stop("AMBIGUOUS_SOURCE_VERSION")
        source = versions[0]
        if source["sha256"] != ref["sha256"]:
            return stop("REFERENCE_DIGEST_MISMATCH")
        authority = self.authority.get(ref["source_id"])
        if authority is None:
            return stop("SOURCE_NOT_IN_COMPILER_REPORT")
        if (authority["group"], authority["dimension"]) != (finding["group"], finding["dimension"]):
            return stop("SOURCE_SCOPE_MISMATCH")
        current = authority["source_content_sha256"] == ref["sha256"]
        if not current:
            result["diagnostics"].append("SOURCE_VERSION_NOT_IN_COMPILER_REPORT")
        try:
            location, stored, extraction, error = self._source(source)
        except (OSError, ValueError) as exc:
            return stop("SOURCE_READ_ERROR: " + str(exc))
        except Exception as exc:
            return stop("EXTRACTION_ERROR: " + type(exc).__name__ + ": " + str(exc))
        if error:
            return stop(error)
        matches = [row for row in extraction["segments"] if row["segment_id"] == ref["segment_id"]]
        if len(matches) != 1:
            return stop("MISSING_SEGMENT" if not matches else "AMBIGUOUS_SEGMENT")
        segment = matches[0]
        if segment["kind"] == "unreadable" or not segment["text"].strip():
            return stop("UNREADABLE_SEGMENT")
        if segment["locator"] != ref["locator"]:
            return stop("LOCATOR_MISMATCH")
        if ref["quote"] not in segment["text"]:
            return stop("QUOTE_MISMATCH")
        if location != source["path"]:
            result["diagnostics"].append("RENAMED_SOURCE_RESOLVED_BY_DECLARED_ALIAS")
        if source.get("superseded_by"):
            result["diagnostics"].append("SUPERSEDED_VERSION: " + source["superseded_by"])
        warnings = list(dict.fromkeys(extraction["warnings"] + segment["warnings"]))
        if warnings:
            result["diagnostics"].append("EXTRACTION_LIMITATIONS_RETAINED")
        result["resolved"] = True
        result["bound_to_compiler_source"] = current
        result["citation"] = {"title": source["title"], "source_path": location,
                              "retained_path": stored, "locator": segment["locator"],
                              "heading_path": segment["heading_path"], "quote": ref["quote"],
                              "context": segment["text"], "warnings": warnings,
                              "evidence_kind": authority["evidence_kind"],
                              "observed_at": authority["observed_at"] if current else None}
        return result

    def source_inventory(self) -> list[dict]:
        inventory = []
        for source in self.packet["sources"]:
            try:
                location, stored, extraction, error = self._source(source)
            except Exception as exc:
                location, stored, error = None, None, type(exc).__name__ + ": " + str(exc)
            inventory.append({"source_id": source["source_id"], "version": source["version"],
                              "sha256": source["sha256"], "requested_path": source["path"],
                              "source_path": location, "retained_path": stored,
                              "byte_status": error or "EXACT_BYTES_RETAINED",
                              "superseded_by": source.get("superseded_by")})
        return inventory

    def run(self) -> dict:
        inventory = self.source_inventory()
        findings, counts = [], Counter({"resolved": 0, "unresolved": 0})
        for finding in self.packet["findings"]:
            references = []
            for ordinal, ref in enumerate(finding["evidence_refs"], 1):
                row = self.resolve(ref, finding)
                row["citation_id"] = finding["finding_id"] + "-C" + str(ordinal)
                references.append(row)
                counts["resolved" if row["resolved"] else "unresolved"] += 1
            review = any(not row["resolved"] or not row.get("bound_to_compiler_source") or
                         any(d.startswith("SUPERSEDED_VERSION") for d in row["diagnostics"])
                         for row in references)
            findings.append({**{k: v for k, v in finding.items() if k != "evidence_refs"},
                             "trace_status": "REVIEW_REQUIRED" if review else "SOURCE_LINKS_RESOLVED",
                             "citations": references})
        return copy.deepcopy({"schema": TRACE_SCHEMA, "label": LABEL,
                "compiler_receipt_sha256": self.report["receipt_sha256"],
                "packet_sha256": digest(canonical(self.packet)), "generation": self.packet["generation"],
                "compiler_integrity": self.integrity, "counts": dict(sorted(counts.items())),
                "interpretation_verified": False, "external_authority": self.report["external_authority"],
                "assessment_matrix": self.report["assessment_matrix"], "findings": findings,
                "source_inventory": inventory,
                "recommendations": self.packet["recommendations"],
                "executive_summary": self.packet["executive_summary"],
                "limits": "Resolved links prove byte/locator correspondence, not truth, completeness, "
                          "representativeness, maturity, approval, or recommendation validity."})
