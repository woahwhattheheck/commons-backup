from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "civic-action-ledger/v1"
BUNDLE_SCHEMA = "civic-action-ledger-bundle/v1"
MAX_SOURCE_BYTES = 1_000_000
KINDS = {"agenda", "minutes", "addendum"}
DECISIONS = {"APPROVED", "DENIED", "CONTINUED", "WITHDRAWN"}
ITEM_RE = re.compile(r"^\s*(?:\[ITEM\s+([A-Za-z0-9_.-]+)\]|ITEM\s+([A-Za-z0-9_.-]+)\s*[:\-—])\s*(.+?)\s*$", re.I)
FIELD_RE = re.compile(r"^\s*(Decision|Owner|Assigned|Deadline|Due|Action)\s*:\s*(.*?)\s*$", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ContractError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json_loads(text: str) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise ContractError(f"duplicate JSON key: {k}")
            out[k] = v
        return out

    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"non-finite JSON constant: {x}")))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def _canonical_bytes(obj: Any) -> bytes:
    try:
        return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"non-canonical value: {exc}") from exc


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError("timestamp must be a non-empty string")
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError(f"invalid timestamp: {value}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ContractError("timestamp must include UTC offset")
    return dt.astimezone(timezone.utc)


def _validate_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ContractError("source_url must be a bounded string")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ContractError("source_url must be an http(s) URL without embedded credentials")
    return value


def _validate_id(label: str, value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
        raise ContractError(f"invalid {label}")
    return value


@dataclass(frozen=True)
class DocumentSnapshot:
    meeting_id: str
    doc_id: str
    kind: str
    source_url: str
    observed_at: str
    text: str
    sha256: str

    @classmethod
    def create(
        cls,
        *,
        meeting_id: str,
        doc_id: str,
        kind: str,
        source_url: str,
        observed_at: str,
        text: str,
    ) -> "DocumentSnapshot":
        _validate_id("meeting_id", meeting_id)
        _validate_id("doc_id", doc_id)
        if kind not in KINDS:
            raise ContractError(f"unsupported kind: {kind}")
        _validate_url(source_url)
        _parse_time(observed_at)
        if not isinstance(text, str):
            raise ContractError("text must be a string")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        raw = normalized.encode("utf-8")
        if not raw or len(raw) > MAX_SOURCE_BYTES:
            raise ContractError("source text must be 1..1,000,000 UTF-8 bytes")
        return cls(meeting_id, doc_id, kind, source_url, observed_at, normalized, _sha256(raw))

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "DocumentSnapshot":
        required = {"meeting_id", "doc_id", "kind", "source_url", "observed_at", "text", "sha256"}
        if set(obj) != required:
            raise ContractError("snapshot fields mismatch")
        snap = cls.create(
            meeting_id=obj["meeting_id"],
            doc_id=obj["doc_id"],
            kind=obj["kind"],
            source_url=obj["source_url"],
            observed_at=obj["observed_at"],
            text=obj["text"],
        )
        if obj["sha256"] != snap.sha256:
            raise ContractError(f"snapshot digest mismatch: {snap.doc_id}")
        return snap

    def to_dict(self) -> dict[str, Any]:
        return {
            "meeting_id": self.meeting_id,
            "doc_id": self.doc_id,
            "kind": self.kind,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "text": self.text,
            "sha256": self.sha256,
        }


class Ledger:
    def __init__(self, meeting_id: str):
        self.meeting_id = _validate_id("meeting_id", meeting_id)
        self._snapshots: dict[str, DocumentSnapshot] = {}

    @property
    def snapshots(self) -> tuple[DocumentSnapshot, ...]:
        return tuple(sorted(self._snapshots.values(), key=lambda s: (_parse_time(s.observed_at), s.kind, s.doc_id)))

    def add(self, snap: DocumentSnapshot) -> bool:
        if snap.meeting_id != self.meeting_id:
            raise ContractError("snapshot meeting_id mismatch")
        old = self._snapshots.get(snap.doc_id)
        if old is None:
            self._snapshots[snap.doc_id] = snap
            return True
        if old == snap:
            return False
        raise ContractError(f"doc_id replay changed bytes or metadata: {snap.doc_id}")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "meeting_id": self.meeting_id, "snapshots": [s.to_dict() for s in self.snapshots]}

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> "Ledger":
        if set(obj) != {"schema", "meeting_id", "snapshots"} or obj.get("schema") != SCHEMA:
            raise ContractError("workspace schema mismatch")
        if not isinstance(obj["snapshots"], list):
            raise ContractError("snapshots must be a list")
        ledger = cls(obj["meeting_id"])
        for raw in obj["snapshots"]:
            if not isinstance(raw, dict):
                raise ContractError("snapshot must be an object")
            ledger.add(DocumentSnapshot.from_dict(raw))
        return ledger


def _evidence(snap: DocumentSnapshot, line_no: int, label: str, value: str) -> dict[str, Any]:
    line = snap.text.splitlines()[line_no - 1]
    return {
        "doc_id": snap.doc_id,
        "kind": snap.kind,
        "source_url": snap.source_url,
        "source_sha256": snap.sha256,
        "observed_at": snap.observed_at,
        "line": line_no,
        "label": label,
        "value": value,
        "line_sha256": _sha256(line.encode("utf-8")),
    }


def _extract_items(snap: DocumentSnapshot) -> list[dict[str, Any]]:
    lines = snap.text.splitlines()
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    seen_ids: set[str] = set()
    for idx, line in enumerate(lines, 1):
        m = ITEM_RE.match(line)
        if m:
            item_id = (m.group(1) or m.group(2)).upper()
            title = m.group(3).strip()
            if item_id in seen_ids:
                raise ContractError(f"duplicate item id {item_id} inside {snap.doc_id}")
            seen_ids.add(item_id)
            current = {
                "item_id": item_id,
                "title": title,
                "title_evidence": _evidence(snap, idx, "title", title),
                "fields": {},
            }
            items.append(current)
            continue
        if current is None:
            continue
        f = FIELD_RE.match(line)
        if not f:
            continue
        key_raw, value = f.group(1).lower(), f.group(2).strip()
        if not value:
            continue
        key = {
            "assigned": "owner",
            "owner": "owner",
            "due": "deadline",
            "deadline": "deadline",
            "decision": "decision",
            "action": "action",
        }[key_raw]
        if key in current["fields"]:
            raise ContractError(f"duplicate field {key} for {current['item_id']} in {snap.doc_id}")
        if key == "decision":
            value = value.upper()
            if value not in DECISIONS:
                raise ContractError(f"unsupported decision {value} in {snap.doc_id}")
        if key == "deadline":
            if not DATE_RE.fullmatch(value):
                raise ContractError(f"deadline must be YYYY-MM-DD in {snap.doc_id}")
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise ContractError(f"invalid deadline {value}") from exc
        current["fields"][key] = {"value": value, "evidence": _evidence(snap, idx, key, value)}
    return items


def _fact_key(f: dict[str, Any]) -> tuple[Any, ...]:
    ev = f["evidence"]
    return (_parse_time(ev["observed_at"]), ev["kind"], ev["doc_id"], ev["line"])


def compile_ledger(
    ledger: Ledger,
    *,
    as_of: str,
    max_source_age_days: int = 90,
) -> dict[str, Any]:
    as_of_dt = _parse_time(as_of)
    if not isinstance(max_source_age_days, int) or isinstance(max_source_age_days, bool) or not (1 <= max_source_age_days <= 3650):
        raise ContractError("max_source_age_days must be int 1..3650")
    snaps = ledger.snapshots
    if not snaps:
        raise ContractError("workspace has no snapshots")
    for s in snaps:
        if _parse_time(s.observed_at) > as_of_dt:
            raise ContractError(f"future snapshot relative to as_of: {s.doc_id}")

    latest_dt = max(_parse_time(s.observed_at) for s in snaps)
    age_days = (as_of_dt - latest_dt).total_seconds() / 86400
    freshness = "CURRENT" if age_days <= max_source_age_days else "STALE_SOURCE"

    by_id: dict[str, dict[str, Any]] = {}
    document_index: list[dict[str, Any]] = []
    for snap in snaps:
        extracted = _extract_items(snap)
        document_index.append({
            "doc_id": snap.doc_id,
            "kind": snap.kind,
            "source_url": snap.source_url,
            "observed_at": snap.observed_at,
            "sha256": snap.sha256,
            "items_extracted": len(extracted),
        })
        for raw in extracted:
            item = by_id.setdefault(raw["item_id"], {
                "item_id": raw["item_id"],
                "titles": [],
                "facts": {"decision": [], "owner": [], "deadline": [], "action": []},
            })
            item["titles"].append({"value": raw["title"], "evidence": raw["title_evidence"]})
            for key, fact in raw["fields"].items():
                item["facts"][key].append(fact)

    compiled_items: list[dict[str, Any]] = []
    for item_id in sorted(by_id):
        raw = by_id[item_id]
        titles = sorted(raw["titles"], key=_fact_key)
        current_title = titles[-1]
        title_changes = []
        prev = None
        for t in titles:
            if prev is None or t["value"] != prev["value"]:
                title_changes.append(t)
                prev = t

        minute_decisions = [f for f in raw["facts"]["decision"] if f["evidence"]["kind"] == "minutes"]
        unique_decisions = sorted({f["value"] for f in minute_decisions})
        conflict = len(unique_decisions) > 1
        if conflict:
            state = "HOLD_CONFLICT"
            decision = None
            decision_evidence = [f["evidence"] for f in sorted(minute_decisions, key=_fact_key)]
        elif len(unique_decisions) == 1:
            decision = unique_decisions[0]
            state = f"DECIDED_{decision}"
            decision_evidence = [f["evidence"] for f in sorted(minute_decisions, key=_fact_key)]
        else:
            decision = None
            has_minutes = any(s.kind == "minutes" for s in snaps)
            state = "UNKNOWN_DECISION" if has_minutes else "PROPOSED"
            decision_evidence = []

        fields_out: dict[str, Any] = {}
        changes: list[dict[str, Any]] = []
        for field in ("owner", "deadline", "action"):
            facts = sorted(raw["facts"][field], key=_fact_key)
            if facts:
                current = facts[-1]
                fields_out[field] = current["value"]
                fields_out[field + "_evidence"] = current["evidence"]
                previous_value = None
                for fact in facts:
                    if previous_value is None or fact["value"] != previous_value:
                        changes.append({"field": field, "value": fact["value"], "evidence": fact["evidence"]})
                        previous_value = fact["value"]
            else:
                fields_out[field] = None
                fields_out[field + "_evidence"] = None
        for t in title_changes:
            changes.append({"field": "title", "value": t["value"], "evidence": t["evidence"]})
        changes.sort(key=lambda c: (_parse_time(c["evidence"]["observed_at"]), c["evidence"]["doc_id"], c["evidence"]["line"], c["field"]))

        compiled_items.append({
            "item_id": item_id,
            "title": current_title["value"],
            "title_evidence": current_title["evidence"],
            "state": state,
            "decision": decision,
            "decision_evidence": decision_evidence,
            "conflict": conflict,
            **fields_out,
            "changes": changes,
        })

    result = {
        "schema": SCHEMA,
        "meeting_id": ledger.meeting_id,
        "as_of": as_of,
        "max_source_age_days": max_source_age_days,
        "freshness": freshness,
        "latest_source_observed_at": latest_dt.isoformat().replace("+00:00", "Z"),
        "documents": document_index,
        "items": compiled_items,
        "authority": {
            "external_actions_authorized": False,
            "legal_or_policy_judgment": False,
            "unsupported_inference_allowed": False,
            "statement": "Only exact source-backed fields are emitted; conflicts and missing decisions remain visible.",
        },
    }
    result["compile_sha256"] = _sha256(_canonical_bytes(result))
    return result


def write_workspace(ledger: Ledger, path: str | os.PathLike[str]) -> None:
    _atomic_write(Path(path), _canonical_bytes(ledger.to_dict()))


def read_workspace(path: str | os.PathLike[str]) -> Ledger:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read workspace: {exc}") from exc
    if len(data) > 4_000_000:
        raise ContractError("workspace too large")
    return Ledger.from_dict(_strict_json_loads(data.decode("utf-8")))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".civic-ledger-", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def _render_markdown(compiled: dict[str, Any]) -> str:
    out = [
        f"# Civic Action Ledger — {compiled['meeting_id']}",
        "",
        f"Freshness: **{compiled['freshness']}** · As of `{compiled['as_of']}`",
        "",
        "| Item | State | Decision | Owner | Deadline | Action |",
        "|---|---|---|---|---|---|",
    ]
    esc = lambda v: str(v or "—").replace("|", "\\|").replace("\n", " ")
    for item in compiled["items"]:
        out.append(f"| {esc(item['item_id'] + ' — ' + item['title'])} | {esc(item['state'])} | {esc(item['decision'])} | {esc(item['owner'])} | {esc(item['deadline'])} | {esc(item['action'])} |")
    out += ["", "## Evidence anchors", ""]
    for item in compiled["items"]:
        ev = item["title_evidence"]
        out.append(f"- **{item['item_id']}** title: `{ev['doc_id']}:{ev['line']}` · {ev['source_url']}")
        if item["decision_evidence"]:
            refs = ", ".join(f"`{e['doc_id']}:{e['line']}`" for e in item["decision_evidence"])
            out.append(f"  - decision evidence: {refs}")
    out += ["", "> This artifact does not make legal, policy, or eligibility judgments and authorizes no external action.", ""]
    return "\n".join(out)


def _render_csv(compiled: dict[str, Any]) -> bytes:
    sio = io.StringIO(newline="")
    writer = csv.writer(sio, lineterminator="\n")
    writer.writerow(["meeting_id", "item_id", "title", "state", "decision", "owner", "deadline", "action", "evidence_url"])
    for item in compiled["items"]:
        writer.writerow([
            compiled["meeting_id"], item["item_id"], item["title"], item["state"], item["decision"] or "",
            item["owner"] or "", item["deadline"] or "", item["action"] or "", item["title_evidence"]["source_url"],
        ])
    return sio.getvalue().encode("utf-8")


def write_bundle(compiled: dict[str, Any], output_dir: str | os.PathLike[str]) -> dict[str, Any]:
    if compiled.get("schema") != SCHEMA:
        raise ContractError("compiled schema mismatch")
    clone = dict(compiled)
    expected = clone.pop("compile_sha256", None)
    actual = _sha256(_canonical_bytes(clone))
    if expected != actual:
        raise ContractError("compiled digest mismatch")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        "ledger.json": _canonical_bytes(compiled),
        "ledger.csv": _render_csv(compiled),
        "ledger.md": _render_markdown(compiled).encode("utf-8"),
    }
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "meeting_id": compiled["meeting_id"],
        "compile_sha256": expected,
        "files": {name: _sha256(data) for name, data in sorted(payloads.items())},
    }
    for name, data in payloads.items():
        _atomic_write(root / name, data)
    _atomic_write(root / "manifest.json", _canonical_bytes(manifest))
    return manifest


def verify_bundle(output_dir: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(output_dir)
    manifest = _strict_json_loads((root / "manifest.json").read_text("utf-8"))
    if set(manifest) != {"schema", "meeting_id", "compile_sha256", "files"} or manifest["schema"] != BUNDLE_SCHEMA:
        raise ContractError("bundle manifest schema mismatch")
    if not isinstance(manifest["files"], dict) or set(manifest["files"]) != {"ledger.json", "ledger.csv", "ledger.md"}:
        raise ContractError("bundle file set mismatch")
    for name, digest in manifest["files"].items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ContractError(f"bundle file unavailable: {name}")
        data = path.read_bytes()
        if _sha256(data) != digest:
            raise ContractError(f"bundle file digest mismatch: {name}")
    ledger_obj = _strict_json_loads((root / "ledger.json").read_text("utf-8"))
    if ledger_obj.get("meeting_id") != manifest["meeting_id"] or ledger_obj.get("compile_sha256") != manifest["compile_sha256"]:
        raise ContractError("bundle ledger identity mismatch")
    clone = dict(ledger_obj)
    digest = clone.pop("compile_sha256", None)
    if _sha256(_canonical_bytes(clone)) != digest:
        raise ContractError("ledger compile digest mismatch")
    return {"ok": True, "meeting_id": manifest["meeting_id"], "compile_sha256": digest, "files": sorted(manifest["files"])}
