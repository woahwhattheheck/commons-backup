from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

_PARENT = Path(__file__).resolve().parents[1]
_EXPECTED_PARENT_MODULE = (_PARENT / "temporal_evidence.py").resolve()

if __package__ and "." in __package__:  # repository/package import
    from .. import temporal_evidence as _temporal_evidence_module
    from ..temporal_evidence import EvidenceEvent, Fact, TemporalEvidenceError, TemporalEvidenceGraph
else:  # direct execution or top-level ontology package in tests
    _parent_text = str(_PARENT)
    sys.path[:] = [entry for entry in sys.path if entry != _parent_text]
    sys.path.insert(0, _parent_text)
    import temporal_evidence as _temporal_evidence_module
    from temporal_evidence import EvidenceEvent, Fact, TemporalEvidenceError, TemporalEvidenceGraph


PROFILE_VERSION = "nih-temporal-kg-ontology-profile/v1"
RECEIPT_SCHEMA = "nih-temporal-kg-ontology-conformance/v1"
PROFILE = "urn:temporal-kg-interop:profile:v1:"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
TIME = "http://www.w3.org/2006/time#"
PROV = "http://www.w3.org/ns/prov#"
XSD = "http://www.w3.org/2001/XMLSchema#"
BIOLINK = "https://w3id.org/biolink/vocab/"

RDF_TYPE = RDF + "type"
TIME_INTERVAL = TIME + "Interval"
TIME_INSTANT = TIME + "Instant"
TIME_HAS_BEGINNING = TIME + "hasBeginning"
TIME_HAS_END = TIME + "hasEnd"
TIME_IN_XSD_DATETIME = TIME + "inXSDDateTimeStamp"
PROV_ENTITY = PROV + "Entity"
PROV_WAS_DERIVED_FROM = PROV + "wasDerivedFrom"
PROV_GENERATED_AT = PROV + "generatedAtTime"
XSD_DATETIME = XSD + "dateTimeStamp"
XSD_DECIMAL = XSD + "decimal"

P_FACT = PROFILE + "Fact"
P_EVENT = PROFILE + "EvidenceEvent"
P_FACT_ID = PROFILE + "factId"
P_EVENT_ID = PROFILE + "eventId"
P_SUBJECT = PROFILE + "subjectLexeme"
P_PREDICATE = PROFILE + "predicateLexeme"
P_PREDICATE_IRI = PROFILE + "predicateIri"
P_OBJECT = PROFILE + "objectLexeme"
P_INTERVAL = PROFILE + "validInterval"
P_SOURCE_ID = PROFILE + "sourceId"
P_SOURCE_SHA = PROFILE + "sourceSha256"
P_CONFIDENCE = PROFILE + "confidence"
P_ACTION = PROFILE + "action"
P_TARGET = PROFILE + "targetFact"
P_REPLACEMENT = PROFILE + "replacementFact"

_ALLOWED_PROFILE_TERMS = {
    P_FACT, P_EVENT, P_FACT_ID, P_EVENT_ID, P_SUBJECT, P_PREDICATE,
    P_PREDICATE_IRI, P_OBJECT, P_INTERVAL, P_SOURCE_ID, P_SOURCE_SHA,
    P_CONFIDENCE, P_ACTION, P_TARGET, P_REPLACEMENT,
}
_ALLOWED_PREDICATES = {
    RDF_TYPE, TIME_HAS_BEGINNING, TIME_HAS_END, TIME_IN_XSD_DATETIME,
    PROV_WAS_DERIVED_FROM, PROV_GENERATED_AT,
    P_FACT_ID, P_EVENT_ID, P_SUBJECT, P_PREDICATE, P_PREDICATE_IRI,
    P_OBJECT, P_INTERVAL, P_SOURCE_ID, P_SOURCE_SHA, P_CONFIDENCE,
    P_ACTION, P_TARGET, P_REPLACEMENT,
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_BIOLINK_LOCAL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_ABSOLUTE_IRI = re.compile(r"^(?:https?://|urn:)[^\s<>\"{}|^`\\]+$")
_LINE = re.compile(
    r'^<([^<>]+)>[ \t]+<([^<>]+)>[ \t]+'
    r'(?:<([^<>]+)>|"((?:[^"\\\r\n]|\\(?:["\\nrt]|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}))*)"(?:\^\^<([^<>]+)>)?)'
    r'[ \t]+\.[ \t]*$'
)
UTC = timezone.utc


class OntologyProfileError(ValueError):
    """Raised when data falls outside the declared restricted ontology profile."""


@dataclass(frozen=True, slots=True)
class _Object:
    kind: str  # iri | literal
    value: str
    datatype: str | None = None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _validate_scalar_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise OntologyProfileError(f"{field} must be text")
    for ch in value:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF:
            raise OntologyProfileError(f"{field} contains a non-Unicode-scalar code point")
    return value


def _iri(value: str, *, field: str = "IRI") -> str:
    _validate_scalar_text(value, field=field)
    if any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in value):
        raise OntologyProfileError(f"{field} contains a forbidden IRI control character")
    if not _ABSOLUTE_IRI.fullmatch(value):
        raise OntologyProfileError(f"{field} must be an absolute canonical https/http/urn IRI")
    return value


def _escape_literal(value: str) -> str:
    _validate_scalar_text(value, field="literal")
    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif cp < 0x20 or cp == 0x7F:
            out.append(f"\\u{cp:04X}")
        else:
            out.append(ch)
    return "".join(out)


def _unescape_literal(token: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(token):
            raise OntologyProfileError("truncated N-Triples escape")
        code = token[i + 1]
        if code in {'"', "\\"}:
            out.append(code)
            i += 2
        elif code == "n":
            out.append("\n")
            i += 2
        elif code == "r":
            out.append("\r")
            i += 2
        elif code == "t":
            out.append("\t")
            i += 2
        elif code in {"u", "U"}:
            width = 4 if code == "u" else 8
            raw = token[i + 2 : i + 2 + width]
            if len(raw) != width or not re.fullmatch(r"[0-9A-Fa-f]{%d}" % width, raw):
                raise OntologyProfileError("malformed Unicode escape")
            cp = int(raw, 16)
            if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
                raise OntologyProfileError("Unicode escape is not a scalar value")
            out.append(chr(cp))
            i += 2 + width
        else:
            raise OntologyProfileError(f"unsupported N-Triples escape \\{code}")
    value = "".join(out)
    _validate_scalar_text(value, field="literal")
    if _escape_literal(value) != token:
        raise OntologyProfileError("noncanonical literal escaping")
    return value


def _obj_iri(value: str) -> str:
    return f"<{_iri(value)}>"


def _obj_literal(value: str, datatype: str | None = None) -> str:
    token = f'"{_escape_literal(value)}"'
    if datatype is not None:
        token += f"^^<{_iri(datatype, field='datatype IRI')}>"
    return token


def _triple(subject: str, predicate: str, obj: str) -> str:
    return f"<{_iri(subject, field='subject IRI')}> <{_iri(predicate, field='predicate IRI')}> {obj} ."


def _canonical_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise OntologyProfileError("timestamp must be nonempty text")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise OntologyProfileError("timestamp must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise OntologyProfileError("timestamp must be timezone-aware")
    canonical = dt.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if value != canonical:
        raise OntologyProfileError(f"noncanonical xsd:dateTimeStamp lexical form: {value!r}")
    return canonical


def _decimal_lexeme(value: Decimal | float | str) -> str:
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OntologyProfileError("confidence is not a decimal") from exc
    if not dec.is_finite() or dec < 0 or dec > 1:
        raise OntologyProfileError("confidence must be finite within [0,1]")
    if dec == 0:
        dec = Decimal(0)
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


def _parse_decimal(value: str) -> float:
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise OntologyProfileError("malformed xsd:decimal") from exc
    canonical = _decimal_lexeme(dec)
    if canonical != value:
        raise OntologyProfileError("noncanonical xsd:decimal lexical form")
    return float(dec)


def _fact_iri(fact_id: str) -> str:
    if not _HEX64.fullmatch(fact_id):
        raise OntologyProfileError("fact_id must be 64 lowercase hex")
    return f"urn:nih-temporal-kg:fact:{fact_id}"


def _event_iri(event_id: str) -> str:
    if not _HEX64.fullmatch(event_id):
        raise OntologyProfileError("event_id must be 64 lowercase hex")
    return f"urn:nih-temporal-kg:event:{event_id}"


def _interval_iri(fact_id: str) -> str:
    return f"urn:nih-temporal-kg:interval:{fact_id}"


def _instant_iri(fact_id: str, edge: str) -> str:
    if edge not in {"begin", "end"}:
        raise OntologyProfileError("invalid interval edge")
    return f"urn:nih-temporal-kg:instant:{fact_id}:{edge}"


def _source_iri(source_id: str, source_sha256: str) -> str:
    if not _HEX64.fullmatch(source_sha256):
        raise OntologyProfileError("source_sha256 must be 64 lowercase hex")
    return f"urn:nih-temporal-kg:source:{source_sha256}:{_sha256_text(source_id)[:16]}"


def _predicate_iri(predicate: str) -> str:
    if predicate.startswith("biolink:"):
        local = predicate[len("biolink:") :]
        if not _BIOLINK_LOCAL.fullmatch(local):
            raise OntologyProfileError("invalid biolink compact predicate")
        return BIOLINK + local
    return f"urn:nih-temporal-kg:predicate:{_sha256_text(predicate)}"


def _source_triples(source_id: str, source_sha256: str) -> set[str]:
    source = _source_iri(source_id, source_sha256)
    return {
        _triple(source, RDF_TYPE, _obj_iri(PROV_ENTITY)),
        _triple(source, P_SOURCE_ID, _obj_literal(source_id)),
        _triple(source, P_SOURCE_SHA, _obj_literal(source_sha256)),
    }


def export_jsonl_to_ntriples(jsonl_text: str) -> str:
    """Export strict temporal JSONL to the deterministic restricted RDF profile."""
    try:
        graph = TemporalEvidenceGraph.from_jsonl(jsonl_text)
    except TemporalEvidenceError as exc:
        raise OntologyProfileError(str(exc)) from exc

    lines: set[str] = set()
    for fact in graph.facts:
        rec = fact.canonical_record()
        fid = fact.fact_id
        subject = _fact_iri(fid)
        interval = _interval_iri(fid)
        beginning = _instant_iri(fid, "begin")
        source = _source_iri(fact.source_id, fact.source_sha256)
        lines.update(_source_triples(fact.source_id, fact.source_sha256))
        lines.update({
            _triple(subject, RDF_TYPE, _obj_iri(P_FACT)),
            _triple(subject, P_FACT_ID, _obj_literal(fid)),
            _triple(subject, P_SUBJECT, _obj_literal(fact.subject)),
            _triple(subject, P_PREDICATE, _obj_literal(fact.predicate)),
            _triple(subject, P_PREDICATE_IRI, _obj_iri(_predicate_iri(fact.predicate))),
            _triple(subject, P_OBJECT, _obj_literal(fact.object)),
            _triple(subject, P_INTERVAL, _obj_iri(interval)),
            _triple(subject, PROV_GENERATED_AT, _obj_literal(rec["observed_at"], XSD_DATETIME)),
            _triple(subject, PROV_WAS_DERIVED_FROM, _obj_iri(source)),
            _triple(subject, P_SOURCE_ID, _obj_literal(fact.source_id)),
            _triple(subject, P_SOURCE_SHA, _obj_literal(fact.source_sha256)),
            _triple(subject, P_CONFIDENCE, _obj_literal(_decimal_lexeme(fact.confidence), XSD_DECIMAL)),
            _triple(interval, RDF_TYPE, _obj_iri(TIME_INTERVAL)),
            _triple(interval, TIME_HAS_BEGINNING, _obj_iri(beginning)),
            _triple(beginning, RDF_TYPE, _obj_iri(TIME_INSTANT)),
            _triple(beginning, TIME_IN_XSD_DATETIME, _obj_literal(rec["valid_from"], XSD_DATETIME)),
        })
        if rec["valid_to"] is not None:
            end = _instant_iri(fid, "end")
            lines.update({
                _triple(interval, TIME_HAS_END, _obj_iri(end)),
                _triple(end, RDF_TYPE, _obj_iri(TIME_INSTANT)),
                _triple(end, TIME_IN_XSD_DATETIME, _obj_literal(rec["valid_to"], XSD_DATETIME)),
            })

    for event in graph.events:
        rec = event.canonical_record()
        eid = event.event_id
        subject = _event_iri(eid)
        source = _source_iri(event.source_id, event.source_sha256)
        lines.update(_source_triples(event.source_id, event.source_sha256))
        lines.update({
            _triple(subject, RDF_TYPE, _obj_iri(P_EVENT)),
            _triple(subject, P_EVENT_ID, _obj_literal(eid)),
            _triple(subject, P_ACTION, _obj_literal(event.action)),
            _triple(subject, P_TARGET, _obj_iri(_fact_iri(event.target_fact_id))),
            _triple(subject, PROV_GENERATED_AT, _obj_literal(rec["observed_at"], XSD_DATETIME)),
            _triple(subject, PROV_WAS_DERIVED_FROM, _obj_iri(source)),
            _triple(subject, P_SOURCE_ID, _obj_literal(event.source_id)),
            _triple(subject, P_SOURCE_SHA, _obj_literal(event.source_sha256)),
        })
        if event.replacement_fact_id is not None:
            lines.add(_triple(subject, P_REPLACEMENT, _obj_iri(_fact_iri(event.replacement_fact_id))))

    return "\n".join(sorted(lines)) + ("\n" if lines else "")


def _parse_ntriples(text: str) -> list[tuple[str, str, _Object]]:
    if "\r" in text:
        raise OntologyProfileError("CR/CRLF is outside the canonical LF-only profile")
    if text and not text.endswith("\n"):
        raise OntologyProfileError("nonempty canonical N-Triples must end with LF")
    triples: list[tuple[str, str, _Object]] = []
    seen: set[tuple[str, str, _Object]] = set()
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw:
            raise OntologyProfileError(f"line {line_no}: blank lines are outside the canonical profile")
        match = _LINE.fullmatch(raw)
        if match is None:
            raise OntologyProfileError(f"line {line_no}: outside restricted canonical N-Triples grammar")
        subject, predicate, iri_obj, literal_token, datatype = match.groups()
        subject = _iri(subject, field=f"line {line_no} subject")
        predicate = _iri(predicate, field=f"line {line_no} predicate")
        if predicate.startswith(PROFILE) and predicate not in _ALLOWED_PROFILE_TERMS:
            raise OntologyProfileError(f"line {line_no}: unknown profile predicate")
        if predicate not in _ALLOWED_PREDICATES:
            raise OntologyProfileError(f"line {line_no}: predicate outside profile")
        if iri_obj is not None:
            obj = _Object("iri", _iri(iri_obj, field=f"line {line_no} object IRI"), None)
        else:
            value = _unescape_literal(literal_token)
            if datatype is not None:
                datatype = _iri(datatype, field=f"line {line_no} datatype")
                if datatype not in {XSD_DATETIME, XSD_DECIMAL}:
                    raise OntologyProfileError(f"line {line_no}: unsupported literal datatype")
            obj = _Object("literal", value, datatype)
        canonical_object = _obj_iri(obj.value) if obj.kind == "iri" else _obj_literal(obj.value, obj.datatype)
        if raw != _triple(subject, predicate, canonical_object):
            raise OntologyProfileError(f"line {line_no}: noncanonical N-Triples lexical form")
        triple = (subject, predicate, obj)
        if triple in seen:
            raise OntologyProfileError(f"line {line_no}: duplicate triple")
        seen.add(triple)
        triples.append(triple)
    return triples


def _index(triples: list[tuple[str, str, _Object]]) -> dict[str, dict[str, list[_Object]]]:
    out: dict[str, dict[str, list[_Object]]] = {}
    for subject, predicate, obj in triples:
        out.setdefault(subject, {}).setdefault(predicate, []).append(obj)
    return out


def _single(
    index: Mapping[str, Mapping[str, list[_Object]]],
    subject: str,
    predicate: str,
    *,
    kind: str | None = None,
    datatype: str | None = None,
    required: bool = True,
) -> _Object | None:
    values = list(index.get(subject, {}).get(predicate, []))
    if not values and not required:
        return None
    if len(values) != 1:
        raise OntologyProfileError(f"{subject}: {predicate} must have exactly one value")
    value = values[0]
    if kind is not None and value.kind != kind:
        raise OntologyProfileError(f"{subject}: {predicate} has wrong object kind")
    if datatype is not None and value.datatype != datatype:
        raise OntologyProfileError(f"{subject}: {predicate} has wrong datatype")
    if datatype is None and value.kind == "literal" and value.datatype is not None:
        raise OntologyProfileError(f"{subject}: {predicate} must be an untyped literal")
    return value


def _assert_allowed(index: Mapping[str, Mapping[str, list[_Object]]], subject: str, allowed: set[str]) -> None:
    extra = set(index.get(subject, {})) - allowed
    if extra:
        raise OntologyProfileError(f"{subject}: unexpected predicates {sorted(extra)}")


def _resource_type(index: Mapping[str, Mapping[str, list[_Object]]], subject: str) -> str:
    obj = _single(index, subject, RDF_TYPE, kind="iri")
    assert obj is not None
    if obj.value.startswith(PROFILE) and obj.value not in _ALLOWED_PROFILE_TERMS:
        raise OntologyProfileError(f"{subject}: unknown profile type")
    return obj.value


def _validate_source(
    index: Mapping[str, Mapping[str, list[_Object]]],
    source: str,
    source_id: str,
    source_sha: str,
) -> None:
    if source != _source_iri(source_id, source_sha):
        raise OntologyProfileError("source IRI does not bind source_id + source_sha256")
    if _resource_type(index, source) != PROV_ENTITY:
        raise OntologyProfileError("source resource must be prov:Entity")
    _assert_allowed(index, source, {RDF_TYPE, P_SOURCE_ID, P_SOURCE_SHA})
    sid = _single(index, source, P_SOURCE_ID, kind="literal")
    sha = _single(index, source, P_SOURCE_SHA, kind="literal")
    assert sid is not None and sha is not None
    if sid.value != source_id or sha.value != source_sha:
        raise OntologyProfileError("source resource content does not match referring assertion")


def _fact_id_from_iri(value: str) -> str:
    prefix = "urn:nih-temporal-kg:fact:"
    if not value.startswith(prefix) or not _HEX64.fullmatch(value[len(prefix):]):
        raise OntologyProfileError("target/replacement must reference a canonical fact IRI")
    return value[len(prefix):]


def import_ntriples_to_jsonl(ntriples_text: str) -> str:
    """Import only graphs emitted by this versioned profile, rejecting lossy RDF."""
    triples = _parse_ntriples(ntriples_text)
    index = _index(triples)
    if not triples:
        return ""

    typed: dict[str, str] = {}
    for subject in index:
        typed[subject] = _resource_type(index, subject)
        if typed[subject] not in {P_FACT, P_EVENT, PROV_ENTITY, TIME_INTERVAL, TIME_INSTANT}:
            raise OntologyProfileError(f"{subject}: resource type outside profile")

    fact_subjects = sorted(s for s, t in typed.items() if t == P_FACT)
    event_subjects = sorted(s for s, t in typed.items() if t == P_EVENT)
    consumed: set[str] = set()
    graph = TemporalEvidenceGraph()

    for subject in fact_subjects:
        _assert_allowed(index, subject, {
            RDF_TYPE, P_FACT_ID, P_SUBJECT, P_PREDICATE, P_PREDICATE_IRI,
            P_OBJECT, P_INTERVAL, PROV_GENERATED_AT, PROV_WAS_DERIVED_FROM,
            P_SOURCE_ID, P_SOURCE_SHA, P_CONFIDENCE,
        })
        fact_id_o = _single(index, subject, P_FACT_ID, kind="literal")
        subject_o = _single(index, subject, P_SUBJECT, kind="literal")
        predicate_o = _single(index, subject, P_PREDICATE, kind="literal")
        predicate_iri_o = _single(index, subject, P_PREDICATE_IRI, kind="iri")
        object_o = _single(index, subject, P_OBJECT, kind="literal")
        interval_o = _single(index, subject, P_INTERVAL, kind="iri")
        observed_o = _single(index, subject, PROV_GENERATED_AT, kind="literal", datatype=XSD_DATETIME)
        source_o = _single(index, subject, PROV_WAS_DERIVED_FROM, kind="iri")
        source_id_o = _single(index, subject, P_SOURCE_ID, kind="literal")
        source_sha_o = _single(index, subject, P_SOURCE_SHA, kind="literal")
        confidence_o = _single(index, subject, P_CONFIDENCE, kind="literal", datatype=XSD_DECIMAL)
        vals = [fact_id_o, subject_o, predicate_o, predicate_iri_o, object_o, interval_o,
                observed_o, source_o, source_id_o, source_sha_o, confidence_o]
        assert all(v is not None for v in vals)
        fact_id = fact_id_o.value
        if subject != _fact_iri(fact_id):
            raise OntologyProfileError("fact resource IRI does not match factId")
        if predicate_iri_o.value != _predicate_iri(predicate_o.value):
            raise OntologyProfileError("predicateIri does not match predicateLexeme")
        if not _HEX64.fullmatch(source_sha_o.value):
            raise OntologyProfileError("sourceSha256 must be 64 lowercase hex")
        _validate_source(index, source_o.value, source_id_o.value, source_sha_o.value)

        interval = interval_o.value
        if interval != _interval_iri(fact_id) or _resource_type(index, interval) != TIME_INTERVAL:
            raise OntologyProfileError("validInterval is not the canonical interval resource")
        _assert_allowed(index, interval, {RDF_TYPE, TIME_HAS_BEGINNING, TIME_HAS_END})
        begin_o = _single(index, interval, TIME_HAS_BEGINNING, kind="iri")
        end_o = _single(index, interval, TIME_HAS_END, kind="iri", required=False)
        assert begin_o is not None
        if begin_o.value != _instant_iri(fact_id, "begin") or _resource_type(index, begin_o.value) != TIME_INSTANT:
            raise OntologyProfileError("beginning instant is not canonical")
        _assert_allowed(index, begin_o.value, {RDF_TYPE, TIME_IN_XSD_DATETIME})
        begin_ts_o = _single(index, begin_o.value, TIME_IN_XSD_DATETIME, kind="literal", datatype=XSD_DATETIME)
        assert begin_ts_o is not None
        valid_from = _canonical_timestamp(begin_ts_o.value)
        valid_to: str | None = None
        consumed.update({subject, interval, begin_o.value, source_o.value})
        if end_o is not None:
            if end_o.value != _instant_iri(fact_id, "end") or _resource_type(index, end_o.value) != TIME_INSTANT:
                raise OntologyProfileError("ending instant is not canonical")
            _assert_allowed(index, end_o.value, {RDF_TYPE, TIME_IN_XSD_DATETIME})
            end_ts_o = _single(index, end_o.value, TIME_IN_XSD_DATETIME, kind="literal", datatype=XSD_DATETIME)
            assert end_ts_o is not None
            valid_to = _canonical_timestamp(end_ts_o.value)
            consumed.add(end_o.value)

        observed = _canonical_timestamp(observed_o.value)
        confidence = _parse_decimal(confidence_o.value)
        record = {
            "kind": "fact",
            "fact_id": fact_id,
            "subject": subject_o.value,
            "predicate": predicate_o.value,
            "object": object_o.value,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "observed_at": observed,
            "source_id": source_id_o.value,
            "source_sha256": source_sha_o.value,
            "confidence": confidence,
        }
        try:
            fact = Fact.from_record(record)
        except TemporalEvidenceError as exc:
            raise OntologyProfileError(str(exc)) from exc
        if fact.fact_id != fact_id:
            raise OntologyProfileError("factId digest drift")
        graph.add_fact(fact)

    pending_events: list[EvidenceEvent] = []
    for subject in event_subjects:
        _assert_allowed(index, subject, {
            RDF_TYPE, P_EVENT_ID, P_ACTION, P_TARGET, P_REPLACEMENT,
            PROV_GENERATED_AT, PROV_WAS_DERIVED_FROM, P_SOURCE_ID, P_SOURCE_SHA,
        })
        event_id_o = _single(index, subject, P_EVENT_ID, kind="literal")
        action_o = _single(index, subject, P_ACTION, kind="literal")
        target_o = _single(index, subject, P_TARGET, kind="iri")
        replacement_o = _single(index, subject, P_REPLACEMENT, kind="iri", required=False)
        observed_o = _single(index, subject, PROV_GENERATED_AT, kind="literal", datatype=XSD_DATETIME)
        source_o = _single(index, subject, PROV_WAS_DERIVED_FROM, kind="iri")
        source_id_o = _single(index, subject, P_SOURCE_ID, kind="literal")
        source_sha_o = _single(index, subject, P_SOURCE_SHA, kind="literal")
        vals = [event_id_o, action_o, target_o, observed_o, source_o, source_id_o, source_sha_o]
        assert all(v is not None for v in vals)
        event_id = event_id_o.value
        if subject != _event_iri(event_id):
            raise OntologyProfileError("event resource IRI does not match eventId")
        if not _HEX64.fullmatch(source_sha_o.value):
            raise OntologyProfileError("sourceSha256 must be 64 lowercase hex")
        _validate_source(index, source_o.value, source_id_o.value, source_sha_o.value)
        target_id = _fact_id_from_iri(target_o.value)
        replacement_id = None if replacement_o is None else _fact_id_from_iri(replacement_o.value)
        if target_id not in {f.fact_id for f in graph.facts}:
            raise OntologyProfileError("event target fact is absent")
        if replacement_id is not None and replacement_id not in {f.fact_id for f in graph.facts}:
            raise OntologyProfileError("event replacement fact is absent")
        record = {
            "kind": "event",
            "event_id": event_id,
            "action": action_o.value,
            "target_fact_id": target_id,
            "replacement_fact_id": replacement_id,
            "observed_at": _canonical_timestamp(observed_o.value),
            "source_id": source_id_o.value,
            "source_sha256": source_sha_o.value,
        }
        try:
            event = EvidenceEvent.from_record(record)
        except TemporalEvidenceError as exc:
            raise OntologyProfileError(str(exc)) from exc
        if event.event_id != event_id:
            raise OntologyProfileError("eventId digest drift")
        pending_events.append(event)
        consumed.update({subject, source_o.value})

    for event in sorted(pending_events, key=lambda item: (item.observed_at, item.event_id)):
        try:
            graph.add_event(event)
        except TemporalEvidenceError as exc:
            raise OntologyProfileError(str(exc)) from exc

    orphaned = set(index) - consumed
    if orphaned:
        raise OntologyProfileError(f"unreferenced/orphan profile resources: {sorted(orphaned)}")
    return graph.to_jsonl()


def _profile_descriptor_sha256() -> str:
    descriptor = {
        "profile": PROFILE_VERSION,
        "namespaces": {"profile": PROFILE, "rdf": RDF, "time": TIME, "prov": PROV, "xsd": XSD, "biolink": BIOLINK},
        "allowed_profile_terms": sorted(_ALLOWED_PROFILE_TERMS),
    }
    return _sha256_text(_canonical_json(descriptor))


def _implementation_sha256() -> str:
    return _sha256_bytes(Path(__file__).read_bytes())


def _parent_module_path() -> Path:
    module_path = getattr(_temporal_evidence_module, "__file__", None)
    if not module_path:
        raise OntologyProfileError("temporal evidence implementation path is unavailable")
    actual = Path(module_path).resolve()
    if actual != _EXPECTED_PARENT_MODULE:
        raise OntologyProfileError("temporal evidence module is not the exact sibling implementation")
    return actual


def _parent_implementation_sha256() -> str:
    return _sha256_bytes(_parent_module_path().read_bytes())


def build_conformance_receipt(jsonl_text: str, ntriples_text: str | None = None) -> dict[str, Any]:
    try:
        graph = TemporalEvidenceGraph.from_jsonl(jsonl_text)
    except TemporalEvidenceError as exc:
        raise OntologyProfileError(str(exc)) from exc
    canonical_jsonl = graph.to_jsonl()
    canonical_nt = export_jsonl_to_ntriples(jsonl_text)
    nt = canonical_nt if ntriples_text is None else ntriples_text
    if nt != canonical_nt:
        raise OntologyProfileError("supplied N-Triples do not equal the canonical exporter bytes")
    roundtrip = import_ntriples_to_jsonl(nt)
    payload = {
        "schema": RECEIPT_SCHEMA,
        "profile": PROFILE_VERSION,
        "profile_descriptor_sha256": _profile_descriptor_sha256(),
        "implementation_sha256": _implementation_sha256(),
        "parent_temporal_evidence_sha256": _parent_implementation_sha256(),
        "input_jsonl_sha256": _sha256_text(jsonl_text),
        "canonical_input_jsonl_sha256": _sha256_text(canonical_jsonl),
        "ntriples_sha256": _sha256_text(nt),
        "roundtrip_jsonl_sha256": _sha256_text(roundtrip),
        "fact_count": len(graph.facts),
        "event_count": len(graph.events),
        "triple_count": len(_parse_ntriples(nt)),
        "roundtrip_match": roundtrip == canonical_jsonl,
    }
    return {**payload, "receipt_sha256": _sha256_text(_canonical_json(payload))}


def verify_conformance_receipt(receipt: Mapping[str, Any], jsonl_text: str, ntriples_text: str) -> bool:
    try:
        expected = build_conformance_receipt(jsonl_text, ntriples_text)
        return dict(receipt) == expected and bool(expected["roundtrip_match"])
    except (OntologyProfileError, TemporalEvidenceError, OSError, TypeError, ValueError):
        return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restricted OWL-Time / PROV-O / Biolink temporal KG interoperability profile")
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="strict temporal JSONL -> canonical restricted N-Triples")
    export_p.add_argument("jsonl")
    export_p.add_argument("ntriples")
    export_p.add_argument("--receipt")

    import_p = sub.add_parser("import", help="restricted N-Triples -> strict canonical temporal JSONL")
    import_p.add_argument("ntriples")
    import_p.add_argument("jsonl")

    verify_p = sub.add_parser("verify", help="verify conformance receipt against exact JSONL and N-Triples bytes")
    verify_p.add_argument("receipt")
    verify_p.add_argument("jsonl")
    verify_p.add_argument("ntriples")

    args = parser.parse_args(argv)
    if args.command == "export":
        jsonl_text = Path(args.jsonl).read_text(encoding="utf-8")
        nt = export_jsonl_to_ntriples(jsonl_text)
        Path(args.ntriples).write_text(nt, encoding="utf-8")
        if args.receipt:
            receipt = build_conformance_receipt(jsonl_text, nt)
            Path(args.receipt).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return 0
    if args.command == "import":
        nt = Path(args.ntriples).read_text(encoding="utf-8")
        Path(args.jsonl).write_text(import_ntriples_to_jsonl(nt), encoding="utf-8")
        return 0
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    valid = verify_conformance_receipt(
        receipt,
        Path(args.jsonl).read_text(encoding="utf-8"),
        Path(args.ntriples).read_text(encoding="utf-8"),
    )
    print("VALID" if valid else "INVALID")
    return 0 if valid else 2



def _seal_runtime_generation() -> dict[str, Any]:
    """Freeze this module's function/helper generation after first load.

    Public functions are rebound to copies whose globals dictionary is private
    to this generation.  Runtime leaves that matter to canonicalization and
    hashing are captured as immutable attribute surfaces so later rebinding of
    this module's public names cannot change conformance semantics.
    """
    from types import FunctionType

    class _FrozenJSON:
        __slots__ = ()
        dumps = staticmethod(json.dumps)
        loads = staticmethod(json.loads)
        JSONDecodeError = json.JSONDecodeError

    class _FrozenHashlib:
        __slots__ = ()
        sha256 = staticmethod(hashlib.sha256)

    class _FrozenRegex:
        __slots__ = ()
        compile = staticmethod(re.compile)
        fullmatch = staticmethod(re.fullmatch)

    live = globals()
    frozen_globals = dict(live)
    frozen_globals["json"] = _FrozenJSON()
    frozen_globals["hashlib"] = _FrozenHashlib()
    frozen_globals["re"] = _FrozenRegex()

    originals = {
        name: value
        for name, value in live.items()
        if isinstance(value, FunctionType)
        and value.__module__ == __name__
        and name != "_seal_runtime_generation"
    }
    sealed: dict[str, Any] = {}
    for name, function in originals.items():
        clone = FunctionType(
            function.__code__,
            frozen_globals,
            function.__name__,
            function.__defaults__,
            function.__closure__,
        )
        clone.__kwdefaults__ = (
            dict(function.__kwdefaults__) if function.__kwdefaults__ else None
        )
        clone.__annotations__ = dict(function.__annotations__)
        clone.__doc__ = function.__doc__
        clone.__module__ = function.__module__
        clone.__qualname__ = function.__qualname__
        sealed[name] = clone

    # Cross-calls within the cloned functions resolve through this exact graph.
    frozen_globals.update(sealed)
    return sealed


globals().update(_seal_runtime_generation())
del _seal_runtime_generation

if __name__ == "__main__":
    raise SystemExit(main())
