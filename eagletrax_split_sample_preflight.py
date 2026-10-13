#!/usr/bin/env python3
"""EagleTrax split-sample portal preflight.

Parent/aliquot linkage. Chemistry/microbiology split-container
validation. Formula-workbook and handling-data binding. Client-status
rules. Retry-safe portal preflight.

Demand: eagletrax-split-sample-preflight-lims-01
Buyer: Eagle Analytical / Ross A. Caputo, PhD

Public Eagle submission facts (eagleanalytical.com/submissions):
- one Sample Submission Form per sample
- two separate containers when potency and microbiology are both requested
- suspensions need a separate sample for microbiological and chemical tests
- formula worksheet / manufacturing batch record for every chemical test
- special-handling requirements must be indicated
- clients who have not sent a sample in six months must re-engage first

HOLD / BUILD-AND-VERIFY. Synthetic/deidentified fixtures only.
Adapters stay simulated/read-only. No production writes, outreach,
prospect-facing demo, or automatic release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime
from typing import Any

DEMAND_ID = "eagletrax-split-sample-preflight-lims-01"
SCHEMA = "commons-eagletrax-split-sample-preflight-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Eagle Analytical / Ross A. Caputo, PhD"
HUMAN_ROLE = "RELEASER"
HUMAN_RELEASER = "SYN-RELEASE-OFFICER"
CLOCK = date(2026, 8, 31)
STALE_BEFORE = date(2026, 3, 1)
MIN_VOLUME_ML = {"CHEM": 5.0, "MICRO": 5.0}
VALID_COUNT = 200
HOLD_COUNT = 40
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
DISCIPLINES = ("CHEM", "MICRO")
MATRICES = ("cream", "suspension", "solution", "capsule", "sterile_injectable")
PREPARATIONS = (
    "progesterone_cream",
    "thyroid_suspension",
    "estradiol_solution",
    "liothyronine_capsule",
    "sterile_injectable_b12",
)

HOLD_CODES = (
    "ABSENT_WORKBOOK",
    "INSUFFICIENT_CONTAINER",
    "UNSPLIT_CONTAINER",
    "MISSING_HANDLING",
    "STALE_CLIENT",
    "FORM_CONTAINER_MISMATCH",
)

HOLD_CODE_COUNTS = {
    "ABSENT_WORKBOOK": 8,
    "INSUFFICIENT_CONTAINER": 8,
    "UNSPLIT_CONTAINER": 8,
    "MISSING_HANDLING": 8,
    "STALE_CLIENT": 4,
    "FORM_CONTAINER_MISMATCH": 4,
}

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "valid": VALID_COUNT,
    "holds": HOLD_COUNT,
    "parents": VALID_COUNT,
    "children": 0,  # filled after fixture build (depends on mix)
    "wrong_child_attachments": 0,
    "released_reports": 0,
    "autonomous_released": 0,
    "production_writes": 0,
}


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _volume(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def parent_accession_id(request_id: str) -> str:
    digest = sha256_hex({"demand_id": DEMAND_ID, "request_id": request_id, "kind": "parent"})
    return "ETX-P-" + digest[:12]


def child_accession_id(request_id: str, discipline: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "request_id": request_id,
            "kind": "aliquot",
            "discipline": discipline,
        }
    )
    prefix = "ETX-C-" if discipline == "CHEM" else "ETX-M-"
    return prefix + digest[:12]


def field_trace(source: str, field: str, value: Any) -> dict[str, Any]:
    payload = {"source": source, "field": field, "value": value}
    return {**payload, "hash": sha256_hex(payload)}


def record_hash(kind: str, record: Any) -> str:
    return sha256_hex({"kind": kind, "record": record})


def _tests_of(row: dict[str, Any]) -> tuple[str, ...]:
    raw = row.get("tests") or []
    out = []
    for item in raw:
        token = _text(item).upper()
        if token in DISCIPLINES and token not in out:
            out.append(token)
    return tuple(out)


def _workbook_present(workbook: Any) -> bool:
    if not isinstance(workbook, dict):
        return False
    if not _flag(workbook.get("present")):
        return False
    return bool(_text(workbook.get("formula_id")) and _text(workbook.get("batch_record_id")))


def _handling_present(handling: Any) -> bool:
    if not isinstance(handling, dict):
        return False
    if not _flag(handling.get("present")):
        return False
    return bool(_text(handling.get("temperature")) and _text(handling.get("special_requirements")))


def _is_stale(last_submission_at: Any) -> bool:
    parsed = _parse_date(last_submission_at)
    if parsed is None:
        return True
    return parsed < STALE_BEFORE


def _containers(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("containers") or []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out


def _form_container_mismatch(row: dict[str, Any]) -> bool:
    request_id = _text(row.get("request_id"))
    sample_id = _text(row.get("sample_id"))
    matrix = _text(row.get("matrix"))
    tests = set(_tests_of(row))
    containers = _containers(row)
    if not containers:
        return True
    for container in containers:
        if _text(container.get("request_id")) != request_id:
            return True
        if _text(container.get("sample_id")) != sample_id:
            return True
        if _text(container.get("matrix")) != matrix:
            return True
        discipline = _text(container.get("discipline")).upper()
        if discipline not in tests:
            return True
    return False


def _split_ok(row: dict[str, Any]) -> bool:
    tests = _tests_of(row)
    if not (("CHEM" in tests) and ("MICRO" in tests)):
        return True
    containers = _containers(row)
    by_disc: dict[str, set[str]] = {"CHEM": set(), "MICRO": set()}
    for container in containers:
        discipline = _text(container.get("discipline")).upper()
        container_id = _text(container.get("container_id"))
        if discipline in by_disc and container_id:
            by_disc[discipline].add(container_id)
    chem_ids = by_disc["CHEM"]
    micro_ids = by_disc["MICRO"]
    if len(chem_ids) != 1 or len(micro_ids) != 1:
        return False
    return next(iter(chem_ids)) != next(iter(micro_ids))


def _insufficient(row: dict[str, Any]) -> bool:
    tests = _tests_of(row)
    volumes: dict[str, float] = {name: 0.0 for name in DISCIPLINES}
    for container in _containers(row):
        discipline = _text(container.get("discipline")).upper()
        if discipline in volumes:
            volumes[discipline] += _volume(container.get("volume_ml"))
    for discipline in tests:
        if volumes[discipline] < MIN_VOLUME_ML[discipline]:
            return True
    return False


def classify_submission(row: dict[str, Any]) -> dict[str, Any]:
    request_id = _text(row.get("request_id"))
    sample_id = _text(row.get("sample_id"))
    client_id = _text(row.get("client_id"))
    matrix = _text(row.get("matrix"))
    tests = _tests_of(row)
    last_submission_at = _text(row.get("last_submission_at"))
    workbook = row.get("workbook") if isinstance(row.get("workbook"), dict) else {}
    handling = row.get("handling") if isinstance(row.get("handling"), dict) else {}

    def hold(code: str) -> dict[str, Any]:
        return {
            "ok": False,
            "state": "HOLD",
            "code": code,
            "request_id": request_id,
            "sample_id": sample_id,
            "client_id": client_id,
            "matrix": matrix,
            "tests": list(tests),
        }

    if _is_stale(last_submission_at):
        return hold("STALE_CLIENT")
    if _form_container_mismatch(row):
        return hold("FORM_CONTAINER_MISMATCH")
    if "CHEM" in tests and not _workbook_present(workbook):
        return hold("ABSENT_WORKBOOK")
    if not _handling_present(handling):
        return hold("MISSING_HANDLING")
    if not _split_ok(row):
        return hold("UNSPLIT_CONTAINER")
    if _insufficient(row):
        return hold("INSUFFICIENT_CONTAINER")
    if not request_id or not sample_id or not tests:
        return hold("FORM_CONTAINER_MISMATCH")

    children = [name for name in DISCIPLINES if name in tests]
    return {
        "ok": True,
        "state": "ACCESSION",
        "request_id": request_id,
        "sample_id": sample_id,
        "client_id": client_id,
        "matrix": matrix,
        "preparation": _text(row.get("preparation")),
        "tests": list(tests),
        "children": children,
        "parent_id": parent_accession_id(request_id),
        "child_ids": {name: child_accession_id(request_id, name) for name in children},
        "workbook": deepcopy(workbook),
        "handling": deepcopy(handling),
        "containers": deepcopy(_containers(row)),
        "last_submission_at": last_submission_at,
    }


def _kind_for_index(index: int) -> str:
    rem = index % 5
    if rem in (0, 1):
        return "CHEM_AND_MICRO"
    if rem in (2, 3):
        return "CHEM_ONLY"
    return "MICRO_ONLY"


def _tests_for_kind(kind: str) -> list[str]:
    if kind == "CHEM_AND_MICRO":
        return ["CHEM", "MICRO"]
    if kind == "CHEM_ONLY":
        return ["CHEM"]
    return ["MICRO"]


def _base_row(index: int, kind: str) -> dict[str, Any]:
    tests = _tests_for_kind(kind)
    request_id = "ETX-REQ-%03d" % index
    sample_id = "ETX-S-%03d" % index
    client_id = "ETX-CL-%03d" % ((index % 40) + 1)
    matrix = MATRICES[(index - 1) % len(MATRICES)]
    preparation = PREPARATIONS[(index - 1) % len(PREPARATIONS)]
    containers = []
    for discipline in tests:
        containers.append(
            {
                "container_id": "%s-%s" % (request_id, discipline),
                "request_id": request_id,
                "sample_id": sample_id,
                "matrix": matrix,
                "discipline": discipline,
                "volume_ml": 10.0,
                "dispensing_container": discipline == "MICRO" and matrix == "sterile_injectable",
            }
        )
    workbook = {
        "present": "CHEM" in tests,
        "formula_id": "WB-%03d" % index if "CHEM" in tests else "",
        "batch_record_id": "MBR-%03d" % index if "CHEM" in tests else "",
        "sha256": sha256_hex({"request_id": request_id, "formula": "WB-%03d" % index}) if "CHEM" in tests else "",
    }
    handling = {
        "present": True,
        "temperature": "cool_pack" if matrix in {"suspension", "sterile_injectable"} else "ambient",
        "special_requirements": "protect_from_light" if index % 2 else "upright_only",
        "cool_pack": matrix in {"suspension", "sterile_injectable"},
    }
    return {
        "row_id": "R%03d" % index,
        "request_id": request_id,
        "sample_id": sample_id,
        "client_id": client_id,
        "matrix": matrix,
        "preparation": preparation,
        "kind": kind,
        "tests": tests,
        "last_submission_at": "2026-06-15",
        "containers": containers,
        "workbook": workbook,
        "handling": handling,
        "expected_state": "ACCESSION",
        "expected_hold_code": None,
        "expected_children": list(tests),
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """240-row PASS fixture: 200 valid + 40 predetermined holds."""
    rows = [_base_row(index, _kind_for_index(index)) for index in range(1, VALID_COUNT + 1)]

    def held(offset: int, code: str, kind: str) -> dict[str, Any]:
        index = VALID_COUNT + offset
        row = _base_row(index, kind)
        row["expected_state"] = "HOLD"
        row["expected_hold_code"] = code
        row["expected_children"] = []
        if code == "STALE_CLIENT":
            row["last_submission_at"] = "2025-08-01"
        elif code == "FORM_CONTAINER_MISMATCH":
            row["containers"][0]["sample_id"] = "ETX-S-MISMATCH-%03d" % index
        elif code == "ABSENT_WORKBOOK":
            row["workbook"] = {"present": False, "formula_id": "", "batch_record_id": "", "sha256": ""}
        elif code == "MISSING_HANDLING":
            row["handling"] = {"present": False, "temperature": "", "special_requirements": "", "cool_pack": False}
        elif code == "UNSPLIT_CONTAINER":
            shared = "%s-SHARED" % row["request_id"]
            row["containers"] = [
                {
                    "container_id": shared,
                    "request_id": row["request_id"],
                    "sample_id": row["sample_id"],
                    "matrix": row["matrix"],
                    "discipline": "CHEM",
                    "volume_ml": 10.0,
                    "dispensing_container": False,
                },
                {
                    "container_id": shared,
                    "request_id": row["request_id"],
                    "sample_id": row["sample_id"],
                    "matrix": row["matrix"],
                    "discipline": "MICRO",
                    "volume_ml": 10.0,
                    "dispensing_container": False,
                },
            ]
        elif code == "INSUFFICIENT_CONTAINER":
            for container in row["containers"]:
                container["volume_ml"] = 1.0
        return row

    holds: list[dict[str, Any]] = []
    cursor = 1
    for _ in range(HOLD_CODE_COUNTS["ABSENT_WORKBOOK"]):
        holds.append(held(cursor, "ABSENT_WORKBOOK", "CHEM_ONLY"))
        cursor += 1
    for _ in range(HOLD_CODE_COUNTS["INSUFFICIENT_CONTAINER"]):
        holds.append(held(cursor, "INSUFFICIENT_CONTAINER", "CHEM_AND_MICRO"))
        cursor += 1
    for _ in range(HOLD_CODE_COUNTS["UNSPLIT_CONTAINER"]):
        holds.append(held(cursor, "UNSPLIT_CONTAINER", "CHEM_AND_MICRO"))
        cursor += 1
    for _ in range(HOLD_CODE_COUNTS["MISSING_HANDLING"]):
        holds.append(held(cursor, "MISSING_HANDLING", "MICRO_ONLY"))
        cursor += 1
    for _ in range(HOLD_CODE_COUNTS["STALE_CLIENT"]):
        holds.append(held(cursor, "STALE_CLIENT", "CHEM_ONLY"))
        cursor += 1
    for _ in range(HOLD_CODE_COUNTS["FORM_CONTAINER_MISMATCH"]):
        holds.append(held(cursor, "FORM_CONTAINER_MISMATCH", "CHEM_AND_MICRO"))
        cursor += 1
    rows.extend(holds)
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (INPUT_COUNT, len(rows)))
    if cursor != HOLD_COUNT + 1:
        raise RuntimeError("hold cursor drifted: %s" % cursor)
    return rows


def expected_child_count(rows: list[dict[str, Any]] | None = None) -> int:
    inbound = rows if rows is not None else build_acceptance_fixture()
    return sum(len(row.get("expected_children") or []) for row in inbound)


EXPECTED_COUNTS["children"] = expected_child_count()


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "accessions": {},
        "children": {},
        "holds": [],
        "events": [],
        "production_writes": 0,
        "adapter": SimulatedEagleTraxAdapter().snapshot(),
    }


class SimulatedEagleTraxAdapter:
    """Read-only portal shadow. Production writes are refused."""

    def __init__(self) -> None:
        self.live = False
        self.read_only = True
        self.writes: list[dict[str, Any]] = []

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"denied": True, "payload_hash": sha256_hex(payload)})
        return {
            "ok": False,
            "code": "PRODUCTION_WRITE_DENIED",
            "interface_state": "SIMULATED",
            "interface_live": False,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": "eagletrax-portal",
            "interface_state": "SIMULATED",
            "interface_live": False,
            "read_only": True,
            "production_writes": 0,
            "denied_writes": len(self.writes),
        }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _provenance(row: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    form = {
        "request_id": row.get("request_id"),
        "sample_id": row.get("sample_id"),
        "client_id": row.get("client_id"),
        "matrix": row.get("matrix"),
        "preparation": row.get("preparation"),
        "tests": row.get("tests"),
        "last_submission_at": row.get("last_submission_at"),
    }
    fields = {
        "form.request_id": field_trace("form", "request_id", form["request_id"]),
        "form.sample_id": field_trace("form", "sample_id", form["sample_id"]),
        "form.client_id": field_trace("form", "client_id", form["client_id"]),
        "form.matrix": field_trace("form", "matrix", form["matrix"]),
        "form.tests": field_trace("form", "tests", form["tests"]),
        "form.last_submission_at": field_trace("form", "last_submission_at", form["last_submission_at"]),
        "workbook.formula_id": field_trace("workbook", "formula_id", (row.get("workbook") or {}).get("formula_id")),
        "handling.special_requirements": field_trace(
            "handling",
            "special_requirements",
            (row.get("handling") or {}).get("special_requirements"),
        ),
    }
    container_hashes = []
    for idx, container in enumerate(_containers(row)):
        key = "container.%s" % idx
        fields[key + ".container_id"] = field_trace(key, "container_id", container.get("container_id"))
        fields[key + ".discipline"] = field_trace(key, "discipline", container.get("discipline"))
        fields[key + ".volume_ml"] = field_trace(key, "volume_ml", container.get("volume_ml"))
        container_hashes.append(record_hash("container", container))
    return {
        "request_hash": record_hash("request", form),
        "form_hash": record_hash("form", form),
        "workbook_hash": record_hash("workbook", row.get("workbook") or {}),
        "handling_hash": record_hash("handling", row.get("handling") or {}),
        "container_hashes": container_hashes,
        "fields": fields,
        "verdict_hash": record_hash("verdict", {k: verdict.get(k) for k in ("ok", "code", "state", "request_id")}),
    }


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    verdict = classify_submission(row)
    request_id = _text(row.get("request_id")) or verdict.get("request_id") or ""
    provenance = _provenance(row, verdict)
    if not verdict["ok"]:
        hold = {
            "row_id": _text(row.get("row_id")),
            "request_id": request_id,
            "sample_id": verdict.get("sample_id") or None,
            "code": verdict["code"],
            "state": "HOLD",
            "matrix": verdict.get("matrix"),
            "tests": verdict.get("tests"),
            "provenance": provenance,
            "interface_state": "SIMULATED",
            "interface_live": False,
        }
        existing = {item["request_id"] for item in journal["holds"]}
        if request_id in existing:
            _event(journal, "REPLAY_NOOP", {"request_id": request_id, "state": "HOLD"})
            return {"kind": "REPLAY_NOOP", "state": "HOLD", "request_id": request_id, "code": verdict["code"]}
        journal["holds"].append(hold)
        _event(journal, "HOLD", {"request_id": request_id, "code": verdict["code"]})
        return {"kind": "HOLD", "request_id": request_id, "code": verdict["code"]}

    parent_id = verdict["parent_id"]
    existing_parent = journal["accessions"].get(parent_id)
    if existing_parent is not None:
        _event(journal, "REPLAY_NOOP", {"request_id": request_id, "parent_id": parent_id})
        return {"kind": "REPLAY_NOOP", "state": "ACCESSION", "request_id": request_id, "parent_id": parent_id}

    parent = {
        "parent_id": parent_id,
        "request_id": verdict["request_id"],
        "sample_id": verdict["sample_id"],
        "client_id": verdict["client_id"],
        "matrix": verdict["matrix"],
        "preparation": verdict["preparation"],
        "kind": _text(row.get("kind")),
        "tests": verdict["tests"],
        "expected_children": list(verdict["children"]),
        "child_ids": dict(verdict["child_ids"]),
        "state": "ACCESSIONED",
        "workbook_bound": bool(verdict["workbook"].get("present")),
        "handling_bound": bool(verdict["handling"].get("present")),
        "workbook": deepcopy(verdict["workbook"]),
        "handling": deepcopy(verdict["handling"]),
        "containers": deepcopy(verdict["containers"]),
        "qc_signoff": False,
        "released": False,
        "released_by": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "provenance": provenance,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["accessions"][parent_id] = parent
    for discipline in verdict["children"]:
        child_id = verdict["child_ids"][discipline]
        journal["children"][child_id] = {
            "child_id": child_id,
            "parent_id": parent_id,
            "aliquot_of": parent_id,
            "request_id": verdict["request_id"],
            "sample_id": verdict["sample_id"],
            "discipline": discipline,
            "state": "ACCESSIONED",
            "result": None,
            "qc_signoff": False,
            "provenance": {
                "parent_id": parent_id,
                "discipline": discipline,
                "child_hash": sha256_hex({"parent_id": parent_id, "discipline": discipline, "request_id": request_id}),
                "source_hashes": {
                    "request": provenance["request_hash"],
                    "form": provenance["form_hash"],
                    "workbook": provenance["workbook_hash"],
                    "handling": provenance["handling_hash"],
                },
            },
            "interface_state": "SIMULATED",
            "interface_live": False,
        }
    _event(
        journal,
        "ACCESSION",
        {
            "request_id": request_id,
            "parent_id": parent_id,
            "children": list(verdict["children"]),
        },
    )
    return {
        "kind": "ACCESSION",
        "request_id": request_id,
        "parent_id": parent_id,
        "children": list(verdict["children"]),
        "child_ids": dict(verdict["child_ids"]),
    }


def attach_result(
    journal: dict[str, Any],
    *,
    target_id: str,
    discipline: str,
    result: Any,
    request_id: str,
) -> dict[str, Any]:
    disc = _text(discipline).upper()
    if target_id in journal["accessions"]:
        _event(journal, "WRONG_CHILD", {"target_id": target_id, "discipline": disc, "request_id": request_id})
        return {"ok": False, "code": "WRONG_CHILD", "attached": False}
    child = journal["children"].get(target_id)
    if child is None:
        _event(journal, "WRONG_CHILD", {"target_id": target_id, "discipline": disc, "request_id": request_id})
        return {"ok": False, "code": "WRONG_CHILD", "attached": False}
    parent = journal["accessions"].get(child["parent_id"])
    if parent is None or parent["request_id"] != _text(request_id):
        _event(journal, "WRONG_CHILD", {"target_id": target_id, "discipline": disc, "request_id": request_id})
        return {"ok": False, "code": "WRONG_CHILD", "attached": False}
    if child["discipline"] != disc:
        _event(journal, "WRONG_CHILD", {"target_id": target_id, "discipline": disc, "request_id": request_id})
        return {"ok": False, "code": "WRONG_CHILD", "attached": False}
    if result in (None, ""):
        return {"ok": False, "code": "EMPTY_RESULT", "attached": False}
    if child["result"] is not None:
        if child["result"] == result:
            return {"ok": True, "duplicate": True, "attached": True, "child_id": target_id}
        _event(journal, "WRONG_CHILD", {"target_id": target_id, "discipline": disc, "reason": "result_already_bound"})
        return {"ok": False, "code": "WRONG_CHILD", "attached": False}
    child["result"] = deepcopy(result)
    child["state"] = "RESULTED"
    parent["report_status"] = report_status(parent, journal)
    _event(journal, "RESULT", {"child_id": target_id, "discipline": disc, "request_id": request_id})
    return {"ok": True, "duplicate": False, "attached": True, "child_id": target_id}


def qc_signoff(journal: dict[str, Any], parent_id: str) -> dict[str, Any]:
    parent = journal["accessions"].get(parent_id)
    if parent is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    parent["qc_signoff"] = True
    for child in journal["children"].values():
        if child["parent_id"] == parent_id:
            child["qc_signoff"] = True
    parent["report_status"] = report_status(parent, journal)
    _event(journal, "QC_SIGNOFF", {"parent_id": parent_id})
    return {"ok": True, "report_status": parent["report_status"]}


def report_status(parent: dict[str, Any], journal: dict[str, Any]) -> str:
    if parent.get("released"):
        return "RELEASED"
    children = [child for child in journal["children"].values() if child["parent_id"] == parent["parent_id"]]
    if not children or any(child.get("result") is None for child in children):
        return "BLOCKED_MISSING_RESULT"
    if not parent.get("qc_signoff"):
        return "BLOCKED_MISSING_QC"
    return "READY_FOR_HUMAN_RELEASE"


def release_report(
    journal: dict[str, Any],
    parent_id: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    parent = journal["accessions"].get(parent_id)
    if parent is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or not name:
        _event(
            journal,
            "RELEASE_DENIED",
            {"parent_id": parent_id, "code": "AUTONOMOUS_RELEASE_DENIED", "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "report_status": report_status(parent, journal)}
    status = report_status(parent, journal)
    if status != "READY_FOR_HUMAN_RELEASE" and status != "RELEASED":
        _event(journal, "RELEASE_DENIED", {"parent_id": parent_id, "code": "REPORT_BLOCKED", "report_status": status})
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if parent["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    parent["released"] = True
    parent["released_by"] = name
    parent["report_status"] = "RELEASED"
    _event(journal, "RELEASED", {"parent_id": parent_id, "released_by": name})
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_parents = set(journal["accessions"])
    before_children = set(journal["children"])
    before_holds = {item["request_id"] for item in journal["holds"]}
    effects = [ingest_row(journal, row) for row in inbound]
    return {
        "added_parents": sorted(set(journal["accessions"]) - before_parents),
        "added_parent_count": len(set(journal["accessions"]) - before_parents),
        "added_children": sorted(set(journal["children"]) - before_children),
        "added_child_count": len(set(journal["children"]) - before_children),
        "added_holds": len({item["request_id"] for item in journal["holds"]} - before_holds),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "parent_count": len(journal["accessions"]),
        "child_count": len(journal["children"]),
        "hold_count": len(journal["holds"]),
    }


def _probe_wrong_child(journal: dict[str, Any]) -> list[dict[str, Any]]:
    probes = []
    parents = list(journal["accessions"].values())
    chem_and_micro = [item for item in parents if item["kind"] == "CHEM_AND_MICRO"]
    if len(chem_and_micro) < 2:
        return probes
    first, second = chem_and_micro[0], chem_and_micro[1]
    chem_id = first["child_ids"]["CHEM"]
    micro_id = first["child_ids"]["MICRO"]
    other_chem = second["child_ids"]["CHEM"]
    probes.append(attach_result(journal, target_id=first["parent_id"], discipline="CHEM", result={"potency": 1}, request_id=first["request_id"]))
    probes.append(attach_result(journal, target_id=micro_id, discipline="CHEM", result={"potency": 1}, request_id=first["request_id"]))
    probes.append(attach_result(journal, target_id=chem_id, discipline="MICRO", result={"sterility": "NG"}, request_id=first["request_id"]))
    probes.append(attach_result(journal, target_id=other_chem, discipline="CHEM", result={"potency": 1}, request_id=first["request_id"]))
    probes.append(attach_result(journal, target_id="ETX-MISSING", discipline="CHEM", result={"potency": 1}, request_id=first["request_id"]))
    return probes


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    adapter = SimulatedEagleTraxAdapter()
    write_attempt = adapter.write({"action": "production_accession", "count": len(inbound)})
    effects = [ingest_row(journal, row) for row in inbound]
    wrong_child_probes = _probe_wrong_child(journal)
    autonomous = []
    for parent_id in journal["accessions"]:
        autonomous.append(release_report(journal, parent_id, actor_role="SYSTEM", actor="autonomous"))

    parents = sorted(journal["accessions"].values(), key=lambda item: item["request_id"])
    children = sorted(journal["children"].values(), key=lambda item: (item["request_id"], item["discipline"]))
    holds = deepcopy(journal["holds"])
    hold_codes = sorted(item["code"] for item in holds)
    hold_code_counts = {code: sum(1 for item in holds if item["code"] == code) for code in HOLD_CODES}
    parent_children = {item["request_id"]: list(item["expected_children"]) for item in parents}
    blocked = [item["parent_id"] for item in parents if item["report_status"] != "RELEASED"]

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "valid": sum(1 for row in inbound if row.get("expected_state") == "ACCESSION"),
        "accessioned_parents": len(parents),
        "accessioned_children": len(children),
        "held": len(holds),
        "hold_codes": hold_codes,
        "hold_code_counts": hold_code_counts,
        "parent_children": parent_children,
        "parent_ids": [item["parent_id"] for item in parents],
        "child_ids": [item["child_id"] for item in children],
        "blocked_reports": len(blocked),
        "released_reports": 0,
        "wrong_child_probes": len(wrong_child_probes),
        "wrong_child_blocked": sum(1 for item in wrong_child_probes if item.get("code") == "WRONG_CHILD"),
        "wrong_child_attached": sum(1 for item in wrong_child_probes if item.get("attached")),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": [{"kind": item.get("kind"), "request_id": item.get("request_id"), "code": item.get("code")} for item in effects],
        "autonomous_release_effects": autonomous,
        "accessions": parents,
        "children": children,
        "holds": holds,
        "adapter": adapter.snapshot(),
        "adapter_write_attempt": write_attempt,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "production_writes": 0,
    }
    body["audit_sha256"] = sha256_hex(
        {
            "demand_id": body["demand_id"],
            "input_rows": body["input_rows"],
            "accessioned_parents": body["accessioned_parents"],
            "accessioned_children": body["accessioned_children"],
            "held": body["held"],
            "hold_code_counts": body["hold_code_counts"],
            "parent_children": body["parent_children"],
            "parent_ids": body["parent_ids"],
            "child_ids": body["child_ids"],
            "wrong_child_attached": body["wrong_child_attached"],
            "released_reports": body["released_reports"],
            "production_writes": body["production_writes"],
        }
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    rows = build_acceptance_fixture()
    expected_children_total = expected_child_count(rows)
    if result.get("input_rows") != INPUT_COUNT:
        failures.append("input_rows!=240")
    if result.get("accessioned_parents") != VALID_COUNT:
        failures.append("parents!=200")
    if result.get("accessioned_children") != expected_children_total:
        failures.append("children!=%s" % expected_children_total)
    if result.get("held") != HOLD_COUNT:
        failures.append("held!=40")
    if result.get("hold_code_counts") != HOLD_CODE_COUNTS:
        failures.append("hold_code_counts")
    expected_map = {row["request_id"]: list(row["expected_children"]) for row in rows if row["expected_state"] == "ACCESSION"}
    if result.get("parent_children") != expected_map:
        failures.append("parent_children")
    if len(set(result.get("parent_ids") or [])) != VALID_COUNT:
        failures.append("parent_ids_not_unique")
    if len(set(result.get("child_ids") or [])) != expected_children_total:
        failures.append("child_ids_not_unique")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if result.get("blocked_reports") != VALID_COUNT:
        failures.append("blocked_reports!=200")
    if result.get("wrong_child_attached") != 0:
        failures.append("wrong_child_attached")
    if result.get("wrong_child_blocked") != result.get("wrong_child_probes"):
        failures.append("wrong_child_probes_not_blocked")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    held_ids = {item["request_id"] for item in result.get("holds") or []}
    accessioned_ids = {item["request_id"] for item in result.get("accessions") or []}
    expected_holds = {row["request_id"] for row in rows if row["expected_state"] == "HOLD"}
    expected_acc = {row["request_id"] for row in rows if row["expected_state"] == "ACCESSION"}
    if held_ids != expected_holds:
        failures.append("held_request_ids")
    if accessioned_ids != expected_acc:
        failures.append("accessioned_request_ids")
    for parent in result.get("accessions") or []:
        if not parent.get("provenance") or not parent["provenance"].get("fields"):
            failures.append("missing_parent_provenance")
            break
        if "CHEM" in parent["tests"] and not parent.get("workbook_bound"):
            failures.append("chem_workbook_unbound")
            break
        if not parent.get("handling_bound"):
            failures.append("handling_unbound")
            break
    for child in result.get("children") or []:
        if child.get("aliquot_of") != child.get("parent_id"):
            failures.append("aliquot_link")
            break
        if not child.get("provenance") or not child["provenance"].get("source_hashes"):
            failures.append("missing_child_provenance")
            break
    for hold in result.get("holds") or []:
        if not hold.get("provenance") or not hold["provenance"].get("fields"):
            failures.append("missing_hold_provenance")
            break
    if result.get("adapter", {}).get("read_only") is not True:
        failures.append("adapter_not_read_only")
    if (result.get("adapter_write_attempt") or {}).get("code") != "PRODUCTION_WRITE_DENIED":
        failures.append("adapter_write_not_denied")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if replay.get("added_parent_count") != 0:
        failures.append("replay_added_parents")
    if replay.get("added_child_count") != 0:
        failures.append("replay_added_children")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "audit_sha256": first.get("audit_sha256"),
        "input_rows": first.get("input_rows"),
        "accessioned_parents": first.get("accessioned_parents"),
        "accessioned_children": first.get("accessioned_children"),
        "held": first.get("held"),
        "hold_code_counts": first.get("hold_code_counts"),
        "wrong_child_attached": first.get("wrong_child_attached"),
        "blocked_reports": first.get("blocked_reports"),
        "replay_added_parents": replay.get("added_parent_count"),
        "replay_added_children": replay.get("added_child_count"),
        "replay_added_holds": replay.get("added_holds"),
        "truth_gate": TRUTH_GATE,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
