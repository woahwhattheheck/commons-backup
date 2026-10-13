"""Byte binding and lossless result support for the existing UIOWA-127 ranker.

No network calls or second ranking engine. A digest is integrity evidence, not
proof that a publisher or an underlying fictional document is authentic.
"""
from __future__ import annotations

import hashlib
import io
import csv
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote

MAX_BYTES = 50 * 1024 * 1024
NOTICE = "Search relevance is not evidence confidence, truth, maturity, or proof of absence."
TOKEN = re.compile(r"\w+", re.UNICODE)


class SearchError(ValueError):
    pass


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SearchError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(SearchError(f"nonfinite JSON: {x}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SearchError(f"invalid JSON: {exc}") from exc


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise SearchError("invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise SearchError("path must stay inside the declared root")
    return path


def _read_local(root, name):
    rel = _relative(name)
    path = (root / str(rel)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SearchError(f"path missing or outside root: {name}")
    if path.stat().st_size > MAX_BYTES:
        raise SearchError(f"file exceeds byte limit: {name}")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise SearchError(f"file exceeds byte limit: {name}")
    return raw


def _string(value, field, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise SearchError(f"expected string: {field}")
    return value


def _string_list(value, field):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise SearchError(f"expected string list: {field}")
    return value


def native_rows(raw, adapter):
    """Return native records and exact physical CSV line ranges, preserving extras."""
    if adapter in {"evidence_csv", "findings_csv"}:
        needed = {"evidence_csv": {"evidence_id", "service", "source_name", "locator", "observation", "evidence_state"},
                  "findings_csv": {"finding_id", "service", "title", "statement", "evidence_ids", "confidence", "limitation"}}[adapter]
        try:
            reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
            headers = next(reader)
            if any(not x for x in headers) or len(headers) != len(set(headers)):
                raise SearchError("duplicate CSV header")
            if needed - set(headers):
                raise SearchError("missing CSV columns: " + ", ".join(sorted(needed - set(headers))))
            result, previous = [], reader.line_num
            for cells in reader:
                start, end = previous + 1, reader.line_num
                previous = end
                if not cells:
                    continue
                if len(cells) != len(headers):
                    raise SearchError(f"CSV column width mismatch: lines {start}-{end}")
                row = dict(zip(headers, cells))
                result.append((row, start, end))
            return result, None
        except (UnicodeError, csv.Error, StopIteration) as exc:
            raise SearchError(f"invalid CSV: {exc}") from exc
    payload = read_json(raw)
    if not isinstance(payload, dict):
        raise SearchError("native JSON must be an object")
    if adapter == "authority":
        rows = payload.get("sources")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SearchError("authority sources must be an array of objects")
        for row in rows:
            _string(row.get("source_id"), "source_id")
            _string(row.get("claim", ""), "claim", empty=True)
        return [(row, None, None) for row in rows], payload
    if adapter != "extraction":
        raise SearchError(f"unknown adapter: {adapter}")
    if payload.get("schema") != "uiowa.document-extraction.v1":
        raise SearchError("unexpected extraction schema")
    if payload.get("status") not in {"ok", "partial", "unreadable", "error"}:
        raise SearchError("unexpected extraction status")
    doc, segments = payload.get("document"), payload.get("segments")
    if not isinstance(doc, dict) or not isinstance(segments, list):
        raise SearchError("invalid extraction document or segments")
    _string(doc.get("name"), "document.name")
    _string_list(payload.get("warnings"), "document.warnings")
    for seg in segments:
        if not isinstance(seg, dict):
            raise SearchError("segment must be an object")
        for key in ("segment_id", "locator", "kind"):
            _string(seg.get(key), "segment." + key)
        _string(seg.get("text"), "segment.text", empty=True)
        _string_list(seg.get("warnings"), "segment.warnings")
        _string_list(seg.get("heading_path"), "segment.heading_path")
    return [(row, None, None) for row in segments], payload


def verified_sources(path):
    path = Path(path).resolve()
    manifest = read_json(_read_local(path.parent, path.name))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list) or not manifest["sources"]:
        raise SearchError("manifest requires a nonempty sources array")
    if len(manifest["sources"]) > 100:
        raise SearchError("manifest exceeds 100 sources")
    for src in manifest["sources"]:
        if not isinstance(src, dict):
            raise SearchError("source specification must be an object")
        ref = src.get("upstream_ref")
        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{40}", ref):
            raise SearchError("upstream_ref must be an explicit immutable 40-hex revision")
        if type(src.get("synthetic")) is not bool:
            raise SearchError("synthetic must be an explicit boolean")
        _relative(src.get("upstream_path"))
        expected = src.get("upstream_blob_sha")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{40}", expected):
            raise SearchError("invalid upstream blob SHA")
        raw = _read_local(path.parent, src.get("local_file"))
        local_sha = git_blob(raw)
        if local_sha != src.get("local_blob_sha", expected):
            raise SearchError(f"local blob SHA mismatch: {src['local_file']}")
        adapter = src.get("adapter")
        rows, payload = native_rows(raw, adapter)
        if len(rows) > 10000:
            raise SearchError("source exceeds 10000 records")
        proof = {"local_bytes_verified": True, "local_blob_sha": local_sha,
                 "local_sha256": hashlib.sha256(raw).hexdigest(), "upstream_ref": ref,
                 "revision_status": "declared_immutable_ref", "underlying_status": "not_included"}
        if adapter == "extraction":
            original = _read_local(path.parent, src.get("source_local_file"))
            if git_blob(original) != expected:
                raise SearchError("underlying source blob SHA mismatch")
            doc = payload["document"]
            if payload["status"] != "error" and (doc.get("sha256") != hashlib.sha256(original).hexdigest() or doc.get("bytes") != len(original)):
                raise SearchError("extracted document digest or byte count mismatch")
            proof.update(underlying_status="verified_source_bytes", extraction_status=payload["status"],
                         source_sha256=hashlib.sha256(original).hexdigest())
        elif local_sha != expected:
            raise SearchError("direct source blob SHA mismatch; undeclared transformations are not accepted")
        yield src, raw, proof


def _line_link(url, start, end):
    return url + f"#L{start}" + (f"-L{end}" if start != end else "")


def enrich(records, src, raw, proof):
    native, payload = native_rows(raw, src["adapter"])
    adapter = src["adapter"]
    native_map = {}
    for row, start, end in native:
        key = row.get("evidence_id" if adapter == "evidence_csv" else "finding_id" if adapter == "findings_csv" else "source_id" if adapter == "authority" else "segment_id")
        _string(key, "native record ID")
        if adapter == "extraction":
            key = f"EXTRACT:{payload['document']['name']}:{key}"
        if key in native_map:
            raise SearchError(f"duplicate native record ID: {key}")
        native_map[key] = (row, start, end)
    url = f"https://github.com/woahwhattheheck/commons/blob/{src['upstream_ref']}/{quote(src['upstream_path'], safe='/')}"
    for rec in records:
        original, start, end = native_map.get(rec["record_id"], (payload or {}, None, None))
        text_key = {"authority": "claim", "evidence_csv": "observation", "findings_csv": "statement", "extraction": "text"}[adapter]
        rec.update(original=original, original_text=original.get(text_key, ""), synthetic=src["synthetic"],
                   provenance=dict(proof), record_url=url, record_locator=rec["locator"], underlying_source_url=None,
                   warnings=list(rec.get("warnings", [])))
        # Keep native synthetic:// references for compatibility; add an actual immutable record link.
        if not rec["source_url"].startswith("synthetic://"):
            rec["source_url"] = url
        if start is not None:
            rec["record_locator"] = f"lines {start}-{end}"
            rec["record_url"] = _line_link(url, start, end)
        if adapter == "extraction":
            rec["underlying_source_url"] = url
            rec["warnings"] = list(dict.fromkeys(rec["warnings"] + list(payload["warnings"])))
            match = re.fullmatch(r"lines? (\d+)(?:-(\d+))?", rec["locator"])
            if match:
                rec["record_url"] = _line_link(url, int(match[1]), int(match[2] or match[1]))
        else:
            rec["warnings"].append("Underlying document not included; record citation is not a document citation.")
    return records


def exact_excerpt(text, terms, radius=95):
    terms = set(terms)
    spans = [(m.start(), m.end()) for m in TOKEN.finditer(text) if m.group().casefold() in terms]
    first = spans[0][0] if spans else 0
    start, end = max(0, first - radius), min(len(text), max(first + radius, spans[0][1] if spans else 0))
    return {"text": text[start:end], "start": start, "end": end,
            "highlights": [[a - start, b - start] for a, b in spans if start <= a and b <= end],
            "truncated_before": start > 0, "truncated_after": end < len(text)}


def exact_snippet(record, terms):
    fields = [("original_text", record.get("original_text", "")), ("title", record.get("title", "")),
              ("record_id", record["record_id"]), ("metadata", json.dumps(record.get("metadata", {}), ensure_ascii=False, sort_keys=True)),
              ("original", json.dumps(record.get("original", {}), ensure_ascii=False, sort_keys=True)),
              ("text", record.get("text", ""))]
    for field, text in fields:
        excerpt = exact_excerpt(text, terms)
        if excerpt["highlights"]:
            return dict(excerpt, field=field)
    return dict(exact_excerpt(record.get("original_text", record.get("text", "")), terms), field="original_text")


def index_digest(index):
    core = {k: v for k, v in index.items() if k != "content_digest"}
    return hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify_index(index):
    if "content_digest" in index and index["content_digest"] != index_digest(index):
        raise SearchError("index content digest mismatch; rebuild from verified inputs")
    if not isinstance(index.get("documents"), list) or not isinstance(index.get("postings"), dict):
        raise SearchError("invalid index structure")
    ids = [row.get("record_id") for row in index["documents"] if isinstance(row, dict)]
    if len(ids) != len(index["documents"]) or any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise SearchError("invalid or duplicate index record IDs")
    id_set = set(ids)
    for term, posting in index["postings"].items():
        if not isinstance(term, str) or not isinstance(posting, dict):
            raise SearchError("invalid index posting")
        for rid, count in posting.items():
            if rid not in id_set or type(count) is not int or count <= 0:
                raise SearchError("invalid index posting reference or frequency")
