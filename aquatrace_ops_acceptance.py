#!/usr/bin/env python3
"""AquaTrace leftover AT-GROK-OPS-ACCEPTANCE-01 — ops acceptance runner.

Lane: production operations proof design.

Loads a candidate-bound acceptance matrix and fail-closes on missing
hash or freshness. The runner never promotes a NOT_READY row to READY.
Named-human release only. Replay is idempotent.

Cite, do not clone, private AquaTrace SHA
e380a587e1ba12a3a07b248c4054940afa3f61a9 (e380a58) and later official
SHA b616894fd3329c48867dba8c18376ce22e7f78a8. Path names are citations.
Private docs are not duplicated. A cite is not local bytes.

Official command:
    python3 aquatrace_ops_acceptance.py

HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.
No City contact. No bid submission. No certification claim.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

LEFTOVER_ID = "AT-GROK-OPS-ACCEPTANCE-01"
SCHEMA = "commons-aquatrace-ops-acceptance/v1"
COMMAND = "python3 aquatrace_ops_acceptance.py"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
CASH_USD = 0
CLOCK = "2026-08-31T12:00:00Z"
HUMAN_APPROVER = "SYN-OPS-RELEASER"
FRESHNESS_WINDOW = 86400

PRIVATE_CITE_SHA = "e380a587e1ba12a3a07b248c4054940afa3f61a9"
PRIVATE_CITE_SHA_SHORT = "e380a58"
LATER_OFFICIAL_SHA = "b616894fd3329c48867dba8c18376ce22e7f78a8"
PRIVATE_CITE_REPO = "woahwhattheheck/aquatrace-lims"

ROW_IDS = (
    "identity_mfa_session",
    "tenant_lab_rbac",
    "encryption_secrets",
    "monitoring",
    "backup_restore_dr",
    "support_incident_response",
    "accessibility",
    "training_uat",
    "buyer_signoff",
)

AUTONOMOUS_NAMES = frozenset(
    {"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE", "UNNAMED", "UNKNOWN", "HELD"}
)
FORBIDDEN_LABELS = frozenset(
    {
        "CERTIFIED",
        "CERTIFICATION",
        "COMPLIANT",
        "COMPLIANCE",
        "PRODUCTION_READY",
        "PRODUCTION-READY",
        "DEPLOYED",
        "SUBMITTED",
        "BUYER_ACCEPTED",
        "BUYER-ACCEPTED",
    }
)
PRODUCTION_LIKE_VERBS = frozenset(
    {
        "contact_city",
        "submit_bid",
        "connect_live_lims",
        "write_production",
        "claim_production_ready",
        "claim_deployed",
        "claim_buyer_accepted",
        "claim_certified",
    }
)
PROMOTE_VERBS = frozenset({"promote", "promote_ready", "mark_ready"})
UNKNOWN_TOKENS = frozenset({"", "UNKNOWN", "NONE", "NULL"})

HERE = Path(__file__).resolve().parent
PACK = HERE / "revenue" / "aquatrace_ops_acceptance"
MATRIX_PATH = PACK / "matrix.json"
SOURCE_PATH = PACK / "source.json"
UNKNOWN_LEDGER_PATH = PACK / "unknown_ledger.json"
FIXTURE_DIR = PACK / "fixtures" / "complete"

# Locked after the first measured battery. Fail-closed if the journal moves.
GOLDEN_AUDIT_SHA256 = "875a4268e7f79545063d4a7d7646695faba9528558dc3eb27d65beb716dafba5"
GOLDEN_DEFAULT_READY = 0
GOLDEN_DEFAULT_NOT_READY = 9
GOLDEN_COMPLETE_READY = 9
GOLDEN_RELEASE_COUNT = 1
GOLDEN_DENY_COUNT = 8
GOLDEN_CASE_COUNT = 16


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, Path):
        return hashlib.sha256(value.read_bytes()).hexdigest()
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_matrix(path: Path = MATRIX_PATH) -> dict[str, Any]:
    return deepcopy(load_json(path))


def load_unknown_ledger(path: Path = UNKNOWN_LEDGER_PATH) -> dict[str, Any]:
    return load_json(path)


def matrix_rows(matrix: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = matrix if matrix is not None else load_matrix()
    rows = spec.get("rows") or []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def fixture_relpath(row_id: str) -> str:
    return "revenue/aquatrace_ops_acceptance/fixtures/complete/%s.json" % row_id


def parse_clock(value: str) -> dt.datetime:
    text = _text(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return dt.datetime.fromisoformat(text)


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    return _text(value).upper() in UNKNOWN_TOKENS


def is_sha256(value: str) -> bool:
    text = value.lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def build_complete_overlay() -> list[dict[str, Any]]:
    overlay: list[dict[str, Any]] = []
    for row_id in ROW_IDS:
        rel = fixture_relpath(row_id)
        path = HERE / rel
        overlay.append(
            {
                "id": row_id,
                "owner": HUMAN_APPROVER,
                "artifact": rel,
                "artifact_hash": sha256_hex(path) if path.is_file() else "",
                "freshness": CLOCK,
                "freshness_max_age_seconds": FRESHNESS_WINDOW,
                "label": "MEASURED",
                "source": "commons-synthetic",
            }
        )
    return overlay


class OpsAcceptancePlane:
    """Fail-closed evaluator for the ops-acceptance matrix."""

    def __init__(self, matrix: dict[str, Any] | None = None) -> None:
        self.clock = CLOCK
        self.matrix = deepcopy(matrix) if matrix is not None else load_matrix()
        self.matrix_sha256 = sha256_hex(self.matrix)
        self.source_matrix_sha256 = sha256_hex(load_json(MATRIX_PATH))
        self.audit: list[dict[str, Any]] = []
        self.records: dict[str, dict[str, Any]] = {}
        self.seq = 0

    def _record(
        self,
        kind: str,
        request: dict[str, Any],
        decision: str,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.seq += 1
        event = {
            "seq": self.seq,
            "at": self.clock,
            "kind": kind,
            "request_id": _text(request.get("request_id")),
            "actor": _text(request.get("named_human") or request.get("actor")),
            "verb": _text(request.get("verb") or kind),
            "decision": decision,
            "reason": reason,
            "cash_usd": CASH_USD,
            "city_contact": False,
            "city_submission": False,
            "live_lims": False,
            "private_repo_cloned": False,
            "promoted": False,
        }
        if extra:
            event.update(extra)
        self.audit.append(event)
        return event

    def evaluate_row(
        self,
        row: dict[str, Any],
        overlay: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row_id = _text(row.get("id"))
        merged = {
            "owner": row.get("owner"),
            "artifact": row.get("artifact"),
            "artifact_hash": row.get("artifact_hash"),
            "freshness": row.get("freshness"),
            "freshness_max_age_seconds": row.get("freshness_max_age_seconds"),
            "label": "",
            "source": "",
        }
        if overlay:
            for key in merged:
                if key in overlay and overlay[key] not in (None, ""):
                    merged[key] = overlay[key]

        owner = _text(merged["owner"])
        artifact = _text(merged["artifact"])
        digest = _text(merged["artifact_hash"]).lower()
        freshness = _text(merged["freshness"])
        max_age = merged["freshness_max_age_seconds"]
        label = _text(merged["label"]).upper().replace(" ", "_")
        source = _text(merged["source"])

        base = {
            "id": row_id,
            "area": _text(row.get("area")),
            "owner": owner or "UNKNOWN",
            "command": _text(row.get("command")),
            "procedure": _text(row.get("procedure")),
            "artifact": artifact or "UNKNOWN",
            "artifact_hash": digest or "UNKNOWN",
            "freshness": freshness or "UNKNOWN",
            "state": "NOT_READY",
        }

        if label in FORBIDDEN_LABELS:
            return {**base, "reason": "forbidden_label", "label": label}
        if is_unknown(digest):
            return {**base, "reason": "missing_hash"}
        if is_unknown(freshness) or max_age is None:
            return {**base, "reason": "missing_freshness"}
        if not is_sha256(digest):
            return {**base, "reason": "hash_not_sha256"}
        try:
            age = parse_clock(self.clock) - parse_clock(freshness)
        except ValueError:
            return {**base, "reason": "freshness_unparseable"}
        if age.total_seconds() < 0 or age.total_seconds() > int(max_age):
            return {**base, "reason": "freshness_stale"}
        if not owner or owner.upper() in AUTONOMOUS_NAMES:
            return {**base, "reason": "named_human_missing"}
        if source == "private-aquatrace-cite":
            return {**base, "reason": "private_cite_unverified"}
        if is_unknown(artifact):
            return {**base, "reason": "artifact_missing"}
        local = HERE / artifact
        if not local.is_file():
            return {**base, "reason": "artifact_missing", "path": artifact}
        measured = sha256_hex(local)
        if measured != digest:
            return {**base, "reason": "hash_mismatch", "path": artifact}

        # Overlay evaluation may report READY. The loaded default matrix is
        # never rewritten. evaluate_matrix() never copies this back.
        return {
            **base,
            "state": "READY",
            "reason": "durable_hash_and_freshness",
            "path": artifact,
            "recorded_by": owner,
        }

    def evaluate_matrix(
        self,
        overlay: list[dict[str, Any]] | None = None,
        request_id: str = "MATRIX",
    ) -> dict[str, Any]:
        by_id = {
            _text(item.get("id")): item
            for item in (overlay or [])
            if isinstance(item, dict) and _text(item.get("id"))
        }
        rows: list[dict[str, Any]] = []
        for row in matrix_rows(self.matrix):
            rows.append(self.evaluate_row(row, by_id.get(_text(row.get("id")))))

        # Never promote: a default-matrix evaluation stays NOT_READY even if
        # an overlay would satisfy the runner-contract path. Overlay results
        # are returned only when an overlay was supplied.
        if overlay is None:
            for row in rows:
                row["state"] = "NOT_READY"
                if row.get("reason") == "durable_hash_and_freshness":
                    row["reason"] = "promotion_forbidden"

        ready = [row["id"] for row in rows if row["state"] == "READY"]
        not_ready = [row["id"] for row in rows if row["state"] != "READY"]
        product_state = "MATRIX_SATISFIED" if overlay is not None and not not_ready else "NOT_READY"
        event = self._record(
            "EVALUATE_MATRIX",
            {"request_id": request_id, "verb": "evaluate_matrix"},
            "ALLOW" if product_state == "MATRIX_SATISFIED" else "HOLD",
            "all_rows_ready" if product_state == "MATRIX_SATISFIED" else "unresolved_rows",
            {
                "product_state": product_state,
                "ready_count": len(ready),
                "not_ready_count": len(not_ready),
            },
        )
        return {
            "ok": True,
            "product_state": product_state,
            "truth_gate": TRUTH_GATE,
            "ready": ready,
            "not_ready": not_ready,
            "ready_count": len(ready),
            "not_ready_count": len(not_ready),
            "rows": rows,
            "event": event,
            "matrix_sha256": self.matrix_sha256,
            "source_matrix_unchanged": sha256_hex(load_json(MATRIX_PATH))
            == self.source_matrix_sha256,
            "invented_certification": False,
            "production_ready": False,
            "deployed": False,
            "submitted": False,
            "buyer_accepted": False,
            "promoted": False,
        }

    def evaluate_release(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = _text(request.get("request_id"))
        named = _text(request.get("named_human"))
        verb = _text(request.get("verb") or "release")
        overlay = request.get("overlay")
        if overlay is not None and not isinstance(overlay, list):
            overlay = []

        if request_id and request_id in self.records:
            event = self._record(verb, request, "DENY", "replay_suppressed")
            return {**event, "ok": False, "effect_count": len(self.records)}

        if verb in PROMOTE_VERBS:
            event = self._record(verb, request, "DENY", "promotion_forbidden")
            return {**event, "ok": False, "effect_count": len(self.records)}

        if verb in PRODUCTION_LIKE_VERBS:
            if not named:
                event = self._record(verb, request, "DENY", "named_human_missing")
                return {**event, "ok": False, "effect_count": len(self.records)}
            event = self._record(verb, request, "DENY", "production_destination_absent")
            return {**event, "ok": False, "effect_count": len(self.records)}

        if not named:
            event = self._record(verb, request, "DENY", "named_human_missing")
            return {**event, "ok": False, "effect_count": len(self.records)}
        if named.upper() in AUTONOMOUS_NAMES:
            reason = (
                "held_release_denied"
                if named.upper() == "HELD"
                else "autonomous_release_denied"
            )
            event = self._record(verb, request, "DENY", reason)
            return {**event, "ok": False, "effect_count": len(self.records)}

        snapshot = self.evaluate_matrix(overlay, request_id="REL-%s" % (request_id or "anon"))
        if snapshot["product_state"] != "MATRIX_SATISFIED":
            event = self._record(verb, request, "DENY", "rows_not_ready")
            return {
                **event,
                "ok": False,
                "effect_count": len(self.records),
                "not_ready": snapshot["not_ready"],
            }

        record = {
            "request_id": request_id,
            "released_by": named,
            "at": self.clock,
            "state": "RELEASE_RECORDED",
            "product_state": "MATRIX_SATISFIED",
            "cash_usd": CASH_USD,
            "production_ready": False,
            "deployed": False,
            "submitted": False,
            "buyer_accepted": False,
            "promoted": False,
        }
        if request_id:
            self.records[request_id] = record
        event = self._record(
            verb, request, "ALLOW", "named_human_release", {"state": "RELEASE_RECORDED"}
        )
        return {
            **event,
            "ok": True,
            "effect": record,
            "effect_count": len(self.records),
        }


def run_default() -> dict[str, Any]:
    plane = OpsAcceptancePlane()
    snapshot = plane.evaluate_matrix(request_id="DEFAULT")
    snapshot["audit_sha256"] = sha256_hex(plane.audit)
    snapshot["command"] = COMMAND
    snapshot["id"] = LEFTOVER_ID
    snapshot["cash_usd"] = CASH_USD
    snapshot["unknown_ledger"] = load_unknown_ledger()
    snapshot["cites"] = {
        "private_repo": PRIVATE_CITE_REPO,
        "private_sha": PRIVATE_CITE_SHA,
        "private_sha_short": PRIVATE_CITE_SHA_SHORT,
        "later_official_sha": LATER_OFFICIAL_SHA,
        "cloned": False,
        "duplicated": False,
    }
    return snapshot


def run_battery() -> dict[str, Any]:
    plane = OpsAcceptancePlane()
    source_before = MATRIX_PATH.read_bytes()
    default = plane.evaluate_matrix(request_id="DEFAULT")
    complete_overlay = build_complete_overlay()
    complete = plane.evaluate_matrix(complete_overlay, request_id="COMPLETE")

    cases: list[dict[str, Any]] = []

    def _case(case_id: str, title: str, ok: bool, detail: Any) -> None:
        cases.append({"id": case_id, "title": title, "ok": ok, "detail": detail})

    _case(
        "OPS-01",
        "default matrix stays NOT_READY on every row",
        default["product_state"] == "NOT_READY"
        and default["ready_count"] == 0
        and default["not_ready_count"] == 9
        and default["not_ready"] == list(ROW_IDS)
        and all(row["reason"] == "missing_hash" for row in default["rows"]),
        {"ready": default["ready"], "not_ready": default["not_ready"]},
    )
    _case(
        "OPS-02",
        "complete overlay reports MATRIX_SATISFIED without production labels",
        complete["product_state"] == "MATRIX_SATISFIED"
        and complete["ready_count"] == 9
        and complete["not_ready_count"] == 0
        and complete["production_ready"] is False
        and complete["promoted"] is False,
        {"ready": complete["ready"]},
    )

    system = plane.evaluate_release(
        {
            "request_id": "REL-SYSTEM",
            "named_human": "SYSTEM",
            "verb": "release",
            "overlay": complete_overlay,
        }
    )
    _case(
        "OPS-03",
        "SYSTEM release is denied",
        system["decision"] == "DENY" and system["reason"] == "autonomous_release_denied",
        system,
    )

    unnamed = plane.evaluate_release(
        {
            "request_id": "REL-UNNAMED",
            "named_human": "",
            "verb": "release",
            "overlay": complete_overlay,
        }
    )
    _case(
        "OPS-04",
        "unnamed release is denied",
        unnamed["decision"] == "DENY" and unnamed["reason"] == "named_human_missing",
        unnamed,
    )

    held = plane.evaluate_release(
        {
            "request_id": "REL-HELD",
            "named_human": "HELD",
            "verb": "release",
            "overlay": complete_overlay,
        }
    )
    _case(
        "OPS-05",
        "HELD release is denied",
        held["decision"] == "DENY" and held["reason"] == "held_release_denied",
        held,
    )

    early = plane.evaluate_release(
        {
            "request_id": "REL-EARLY",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
        }
    )
    _case(
        "OPS-06",
        "named human cannot release while default rows are NOT_READY",
        early["decision"] == "DENY" and early["reason"] == "rows_not_ready",
        early,
    )

    first = plane.evaluate_release(
        {
            "request_id": "REL-OK",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
            "overlay": complete_overlay,
        }
    )
    replay = plane.evaluate_release(
        {
            "request_id": "REL-OK",
            "named_human": HUMAN_APPROVER,
            "verb": "release",
            "overlay": complete_overlay,
        }
    )
    _case(
        "OPS-07",
        "named-human release records once and still is not production-ready",
        first["decision"] == "ALLOW"
        and first["reason"] == "named_human_release"
        and first.get("effect", {}).get("state") == "RELEASE_RECORDED"
        and first.get("effect", {}).get("production_ready") is False
        and first.get("effect", {}).get("promoted") is False,
        first,
    )
    _case(
        "OPS-08",
        "replay is idempotent — zero duplicate records",
        replay["decision"] == "DENY"
        and replay["reason"] == "replay_suppressed"
        and replay["effect_count"] == 1
        and first["effect_count"] == 1
        and len(plane.records) == 1,
        {"first": first["effect_count"], "replay": replay["effect_count"]},
    )

    forbidden = plane.evaluate_row(
        matrix_rows(plane.matrix)[0],
        {
            "id": "identity_mfa_session",
            "owner": HUMAN_APPROVER,
            "artifact": fixture_relpath("identity_mfa_session"),
            "artifact_hash": sha256_hex(HERE / fixture_relpath("identity_mfa_session")),
            "freshness": CLOCK,
            "freshness_max_age_seconds": FRESHNESS_WINDOW,
            "label": "PRODUCTION_READY",
            "source": "commons-synthetic",
        },
    )
    _case(
        "OPS-09",
        "forbidden certification labels never promote a row",
        forbidden["state"] == "NOT_READY" and forbidden["reason"] == "forbidden_label",
        forbidden,
    )

    missing_hash = plane.evaluate_row(
        matrix_rows(plane.matrix)[0],
        {
            "id": "identity_mfa_session",
            "owner": HUMAN_APPROVER,
            "artifact": fixture_relpath("identity_mfa_session"),
            "artifact_hash": "UNKNOWN",
            "freshness": CLOCK,
            "freshness_max_age_seconds": FRESHNESS_WINDOW,
            "label": "MEASURED",
        },
    )
    _case(
        "OPS-10",
        "missing hash fails closed",
        missing_hash["state"] == "NOT_READY" and missing_hash["reason"] == "missing_hash",
        missing_hash,
    )

    missing_fresh = plane.evaluate_row(
        matrix_rows(plane.matrix)[1],
        {
            "id": "tenant_lab_rbac",
            "owner": HUMAN_APPROVER,
            "artifact": fixture_relpath("tenant_lab_rbac"),
            "artifact_hash": sha256_hex(HERE / fixture_relpath("tenant_lab_rbac")),
            "freshness": "UNKNOWN",
            "freshness_max_age_seconds": FRESHNESS_WINDOW,
            "label": "MEASURED",
        },
    )
    _case(
        "OPS-11",
        "missing freshness fails closed",
        missing_fresh["state"] == "NOT_READY"
        and missing_fresh["reason"] == "missing_freshness",
        missing_fresh,
    )

    stale = plane.evaluate_row(
        matrix_rows(plane.matrix)[2],
        {
            "id": "encryption_secrets",
            "owner": HUMAN_APPROVER,
            "artifact": fixture_relpath("encryption_secrets"),
            "artifact_hash": sha256_hex(HERE / fixture_relpath("encryption_secrets")),
            "freshness": "2020-01-01T00:00:00Z",
            "freshness_max_age_seconds": FRESHNESS_WINDOW,
            "label": "MEASURED",
        },
    )
    _case(
        "OPS-12",
        "stale freshness fails closed",
        stale["state"] == "NOT_READY" and stale["reason"] == "freshness_stale",
        stale,
    )

    declared = deepcopy(matrix_rows(plane.matrix)[0])
    declared["state"] = "READY"
    declared_eval = plane.evaluate_row(declared)
    _case(
        "OPS-13",
        "declared READY without hash stays NOT_READY — no prose promotion",
        declared_eval["state"] == "NOT_READY" and declared_eval["reason"] == "missing_hash",
        declared_eval,
    )

    city = plane.evaluate_release(
        {
            "request_id": "REL-CITY",
            "named_human": HUMAN_APPROVER,
            "verb": "contact_city",
            "overlay": complete_overlay,
        }
    )
    bid = plane.evaluate_release(
        {
            "request_id": "REL-BID",
            "named_human": HUMAN_APPROVER,
            "verb": "submit_bid",
            "overlay": complete_overlay,
        }
    )
    promote = plane.evaluate_release(
        {
            "request_id": "REL-PROMOTE",
            "named_human": HUMAN_APPROVER,
            "verb": "promote",
            "overlay": complete_overlay,
        }
    )
    _case(
        "OPS-14",
        "City contact and bid submission stay closed",
        city["decision"] == "DENY"
        and city["reason"] == "production_destination_absent"
        and bid["decision"] == "DENY"
        and bid["reason"] == "production_destination_absent"
        and len(plane.records) == 1,
        {"city": city["reason"], "bid": bid["reason"]},
    )
    _case(
        "OPS-15",
        "promote verb cannot flip NOT_READY to READY",
        promote["decision"] == "DENY" and promote["reason"] == "promotion_forbidden",
        promote,
    )
    _case(
        "OPS-16",
        "default matrix bytes are unchanged after evaluate and release",
        MATRIX_PATH.read_bytes() == source_before
        and default["source_matrix_unchanged"] is True,
        {"unchanged": MATRIX_PATH.read_bytes() == source_before},
    )

    deny_count = sum(1 for event in plane.audit if event["decision"] == "DENY")
    audit_sha = sha256_hex(plane.audit)
    contract_failures: list[str] = []
    if default["ready_count"] != GOLDEN_DEFAULT_READY:
        contract_failures.append("default_ready moved")
    if default["not_ready_count"] != GOLDEN_DEFAULT_NOT_READY:
        contract_failures.append("default_not_ready moved")
    if complete["ready_count"] != GOLDEN_COMPLETE_READY:
        contract_failures.append("complete_ready moved")
    if len(plane.records) != GOLDEN_RELEASE_COUNT:
        contract_failures.append("release_count moved")
    if deny_count != GOLDEN_DENY_COUNT:
        contract_failures.append("deny_count %s != %s" % (deny_count, GOLDEN_DENY_COUNT))
    if len(cases) != GOLDEN_CASE_COUNT:
        contract_failures.append("case_count moved")
    if GOLDEN_AUDIT_SHA256.startswith("PLACEHOLDER"):
        contract_failures.append("audit_sha256 unlocked:%s" % audit_sha)
    elif audit_sha != GOLDEN_AUDIT_SHA256:
        contract_failures.append("audit_sha256 moved:%s" % audit_sha)
    ok = all(item["ok"] for item in cases) and not contract_failures
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": COMMAND,
        "truth_gate": TRUTH_GATE,
        "cash_usd": CASH_USD,
        "city_contact": False,
        "city_submission": False,
        "live_lims": False,
        "private_repo_cloned": False,
        "cites": {
            "private_repo": PRIVATE_CITE_REPO,
            "private_sha": PRIVATE_CITE_SHA,
            "later_official_sha": LATER_OFFICIAL_SHA,
        },
        "ok": ok,
        "product_state": default["product_state"],
        "default_ready_count": default["ready_count"],
        "default_not_ready_count": default["not_ready_count"],
        "complete_ready_count": complete["ready_count"],
        "release_count": len(plane.records),
        "deny_count": deny_count,
        "case_count": len(cases),
        "cases_ok": sum(1 for item in cases if item["ok"]),
        "audit_count": len(plane.audit),
        "audit_sha256": audit_sha,
        "failures": contract_failures + [item["id"] for item in cases if not item["ok"]],
        "cases": cases,
        "default": default,
        "complete": complete,
        "invented_certification": False,
        "production_ready": False,
        "deployed": False,
        "submitted": False,
        "buyer_accepted": False,
        "promoted": False,
    }


def summarize(result: dict[str, Any]) -> str:
    lines = [
        "%s cases=%s/%s default=%s/%s-ready complete=%s/9-ready releases=%s cash_usd=0"
        % (
            "PASS" if result["ok"] else "FAIL",
            result["cases_ok"],
            result["case_count"],
            result["default_ready_count"],
            result["default_not_ready_count"],
            result["complete_ready_count"],
            result["release_count"],
        ),
        "product_state %s" % result["product_state"],
        "truth_gate %s" % TRUTH_GATE,
        "audit_sha256 %s" % result["audit_sha256"],
        "cite %s later %s" % (PRIVATE_CITE_SHA, LATER_OFFICIAL_SHA),
        "command %s" % COMMAND,
    ]
    if not result["ok"]:
        for case in result["cases"]:
            if case["ok"]:
                continue
            lines.append("%s FAIL" % case["id"])
        for item in result["failures"]:
            lines.append(" - %s" % item)
    return "\n".join(lines)


class OpsAcceptanceSelfTest(unittest.TestCase):
    """Fail-closed unittest hosted by the product CLI."""

    def test_battery_holds(self) -> None:
        result = run_battery()
        self.assertTrue(result["ok"], summarize(result))
        self.assertEqual(result["case_count"], GOLDEN_CASE_COUNT)
        self.assertEqual(result["cases_ok"], GOLDEN_CASE_COUNT)
        self.assertEqual(result["product_state"], "NOT_READY")
        self.assertEqual(result["audit_sha256"], GOLDEN_AUDIT_SHA256)

    def test_default_fixture_is_hold(self) -> None:
        snapshot = run_default()
        self.assertEqual(snapshot["product_state"], "NOT_READY")
        self.assertEqual(snapshot["ready_count"], 0)
        self.assertEqual(snapshot["not_ready_count"], 9)

    def test_held_and_system_stay_closed(self) -> None:
        plane = OpsAcceptancePlane()
        overlay = build_complete_overlay()
        system = plane.evaluate_release(
            {"request_id": "T-SYS", "named_human": "SYSTEM", "overlay": overlay}
        )
        held = plane.evaluate_release(
            {"request_id": "T-HOLD", "named_human": "HELD", "overlay": overlay}
        )
        self.assertEqual(system["reason"], "autonomous_release_denied")
        self.assertEqual(held["reason"], "held_release_denied")
        self.assertEqual(len(plane.records), 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the AquaTrace ops-acceptance battery"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--row", default="", help="Evaluate one default matrix row")
    parser.add_argument(
        "--named-human",
        default="",
        help="Name the human for a release probe; default matrix still stays NOT_READY",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(OpsAcceptanceSelfTest)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.row:
        plane = OpsAcceptancePlane()
        match = next((row for row in matrix_rows(plane.matrix) if row["id"] == args.row), None)
        if match is None:
            print("ERROR: unknown row %s" % args.row, file=sys.stderr)
            return 2
        evaluated = plane.evaluate_row(match)
        if args.json:
            print(json.dumps(evaluated, indent=2, sort_keys=True))
        else:
            print("%s state=%s reason=%s" % (evaluated["id"], evaluated["state"], evaluated["reason"]))
        return 0 if evaluated["state"] != "READY" else 0
    battery = run_battery()
    default = run_default()
    if args.named_human:
        plane = OpsAcceptancePlane()
        probe = plane.evaluate_release(
            {
                "request_id": "CLI-REL",
                "named_human": args.named_human,
                "verb": "release",
            }
        )
        battery["named_human_probe"] = {
            "decision": probe["decision"],
            "reason": probe["reason"],
        }
    if args.json:
        printable = {
            key: value
            for key, value in battery.items()
            if key not in {"default", "complete", "cases"}
        }
        printable["default_product_state"] = default["product_state"]
        print(json.dumps(printable, indent=2, sort_keys=True))
    else:
        print(summarize(battery))
        print(
            "default_product_state=%s invented_certification=false production_ready=false"
            % default["product_state"]
        )
    return 0 if battery["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
