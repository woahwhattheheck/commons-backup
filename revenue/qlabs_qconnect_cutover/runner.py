#!/usr/bin/env python3
"""Q Connect cutover verification for Q Laboratories.

Demand: qlabs-qconnect-cutover-verification-lims-01
Buyer pairing: Q Laboratories / Jeff Knowles

Catalog-version validation, per-user access migration, submission
preflight, and retry-safe cutover verification.

Immutable 240-case synthetic manifest: 200 valid personal-care/pharma
submissions and 40 predefined holds. Adapters stay simulated / read-only
shadowing. No production write. No outreach. No automatic release.
HOLD / BUILD-AND-VERIFY. cash_usd=0.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "source.json"
FIXTURE_PATH = HERE / "fixture.json"

DEMAND_ID = "qlabs-qconnect-cutover-verification-lims-01"
SCHEMA = "commons-qlabs-qconnect-cutover-verification-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Q Laboratories / Jeff Knowles"
HUMAN_QA = "SYN-QA-OFFICER"
HUMAN_ROLE = "HUMAN_QA"

VALID_COUNT = 200
EXCEPTION_COUNT = 40
INPUT_COUNT = VALID_COUNT + EXCEPTION_COUNT

HOLD_CODES = (
    "OBSOLETE_CODE",
    "WRONG_DEPARTMENT",
    "MISSING_FIELD",
    "INVALID_ACCOUNT",
    "INVALID_USER",
    "SHARED_CREDENTIAL",
    "TIMEOUT_RETRY",
)

# 8 + 8 + 8 + (3+3+2) + 8 = 40
HOLD_FAMILY_COUNTS = {
    "OBSOLETE_CODE": 8,
    "WRONG_DEPARTMENT": 8,
    "MISSING_FIELD": 8,
    "INVALID_ACCOUNT": 3,
    "INVALID_USER": 3,
    "SHARED_CREDENTIAL": 2,
    "TIMEOUT_RETRY": 8,
}

REQUIRED_FIELDS = (
    "case_id",
    "submission_id",
    "account_id",
    "user_id",
    "credential_kind",
    "catalog_version",
    "test_code",
    "department",
    "product_class",
    "sample_id",
    "lot_id",
    "product_name",
)

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "valid": VALID_COUNT,
    "exceptions": EXCEPTION_COUNT,
    "accessions": VALID_COUNT,
    "holds": EXCEPTION_COUNT,
    "testing_entered": 0,
    "obsolete_in_testing": 0,
    "shared_credential_accessions": 0,
    "duplicate_accessions": 0,
    "replay_added_accessions": 0,
    "replay_added_holds": 0,
    "autonomous_released": 0,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_AUDIT_SHA256 = "c551c9a1d98fd421823119b1d52f2df5f6f4e40cc9fd9427960d8497f3ac8c0b"
GOLDEN_MANIFEST_SHA256 = "d484e7c953fb8aa2acff16044596f39684b44ba5d84bfb83dc6b68b64ba37ef5"
GOLDEN_CATALOG_SHA256 = "a5d9efcd018e89fdb73ceefe7dd83c9631af5570facc721ed38cda45144a57d2"


def _load_source() -> dict[str, Any]:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


SOURCE = _load_source()
CATALOG: dict[str, dict[str, Any]] = SOURCE["catalog"]
OBSOLETE: dict[str, dict[str, Any]] = SOURCE["obsolete_catalog"]
ACCOUNTS: dict[str, dict[str, Any]] = SOURCE["accounts"]
USERS: dict[str, dict[str, Any]] = SOURCE["users"]
CATALOG_VERSION = SOURCE["catalog_version"]
SHARED = SOURCE["shared_legacy"]
PC_CODES = tuple(code for code, spec in CATALOG.items() if spec["product_class"] == "personal_care")
PH_CODES = tuple(code for code, spec in CATALOG.items() if spec["product_class"] == "pharma")
OBSOLETE_CODES = tuple(OBSOLETE.keys())
MISSING_FIELD_ROTATION = (
    "sample_id",
    "lot_id",
    "product_name",
    "department",
    "test_code",
    "account_id",
    "user_id",
    "catalog_version",
)


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


CATALOG_SHA256 = sha256_hex(
    {
        "catalog_version": CATALOG_VERSION,
        "catalog": CATALOG,
        "obsolete_catalog": OBSOLETE,
    }
)


def field_provenance(row: dict[str, Any]) -> dict[str, str]:
    return {field: sha256_hex(_text(row.get(field))) for field in REQUIRED_FIELDS}


def source_row_sha256(row: dict[str, Any]) -> str:
    return sha256_hex({field: _text(row.get(field)) for field in REQUIRED_FIELDS})


def accession_id(submission_id: str, test_code: str, sample_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "submission_id": submission_id,
            "test_code": test_code,
            "sample_id": sample_id,
        }
    )
    return "QCC-" + digest[:12]


def expected_route(test_code: str) -> str:
    spec = CATALOG[test_code]
    return spec["route"]


def _account_for_class(product_class: str, index: int) -> tuple[str, str]:
    if product_class == "personal_care":
        keys = ("ACCT-PC-01", "ACCT-PC-02")
    else:
        keys = ("ACCT-PH-01", "ACCT-PH-02")
    account_id = keys[index % len(keys)]
    users = ACCOUNTS[account_id]["users"]
    user_id = users[index % len(users)]
    return account_id, user_id


def _base_valid(index: int) -> dict[str, Any]:
    product_class = "personal_care" if index < 100 else "pharma"
    codes = PC_CODES if product_class == "personal_care" else PH_CODES
    test_code = codes[index % len(codes)]
    spec = CATALOG[test_code]
    account_id, user_id = _account_for_class(product_class, index)
    row: dict[str, Any] = {
        "case_id": f"QCC-V-{index + 1:04d}",
        "submission_id": f"SUB-V-{index + 1:04d}",
        "expected_state": "ACCESSION",
        "expected_hold_code": None,
        "expected_route": spec["route"],
        "account_id": account_id,
        "user_id": user_id,
        "credential_kind": "per_user",
        "catalog_version": CATALOG_VERSION,
        "test_code": test_code,
        "department": spec["department"],
        "product_class": product_class,
        "sample_id": f"SYN-S-{index + 1:04d}",
        "lot_id": f"LOT-{(index % 50) + 1:03d}",
        "product_name": f"SYN-{product_class.replace('_', '-').upper()}-{(index % 20) + 1:02d}",
        "simulate_timeout": False,
    }
    row["source_row_sha256"] = source_row_sha256(row)
    row["field_sha256"] = field_provenance(row)
    row["catalog_sha256"] = CATALOG_SHA256
    return row


def _exception_row(slot: int) -> dict[str, Any]:
    sequence = (
        ["OBSOLETE_CODE"] * HOLD_FAMILY_COUNTS["OBSOLETE_CODE"]
        + ["WRONG_DEPARTMENT"] * HOLD_FAMILY_COUNTS["WRONG_DEPARTMENT"]
        + ["MISSING_FIELD"] * HOLD_FAMILY_COUNTS["MISSING_FIELD"]
        + ["INVALID_ACCOUNT"] * HOLD_FAMILY_COUNTS["INVALID_ACCOUNT"]
        + ["INVALID_USER"] * HOLD_FAMILY_COUNTS["INVALID_USER"]
        + ["SHARED_CREDENTIAL"] * HOLD_FAMILY_COUNTS["SHARED_CREDENTIAL"]
        + ["TIMEOUT_RETRY"] * HOLD_FAMILY_COUNTS["TIMEOUT_RETRY"]
    )
    code = sequence[slot]
    within = sum(1 for item in sequence[:slot] if item == code)
    seed_index = VALID_COUNT + slot
    row = _base_valid(seed_index)
    row["case_id"] = f"QCC-E-{slot + 1:04d}"
    row["submission_id"] = f"SUB-E-{slot + 1:04d}"
    row["sample_id"] = f"SYN-E-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold_code"] = code
    row["expected_route"] = None
    row["simulate_timeout"] = False

    if code == "OBSOLETE_CODE":
        obsolete_code = OBSOLETE_CODES[within % len(OBSOLETE_CODES)]
        obsolete = OBSOLETE[obsolete_code]
        row["test_code"] = obsolete_code
        row["department"] = obsolete["department"]
        row["product_class"] = obsolete["product_class"]
        row["catalog_version"] = SOURCE["prior_catalog_version"]
        account_id, user_id = _account_for_class(obsolete["product_class"], seed_index)
        row["account_id"] = account_id
        row["user_id"] = user_id
    elif code == "WRONG_DEPARTMENT":
        row["department"] = "CHEMISTRY" if row["department"] == "MICROBIOLOGY" else "MICROBIOLOGY"
    elif code == "MISSING_FIELD":
        field = MISSING_FIELD_ROTATION[within % len(MISSING_FIELD_ROTATION)]
        row[field] = ""
        row["missing_field"] = field
    elif code == "INVALID_ACCOUNT":
        row["account_id"] = "ACCT-GONE"
    elif code == "INVALID_USER":
        row["user_id"] = "USR-UNKNOWN"
    elif code == "SHARED_CREDENTIAL":
        row["account_id"] = SHARED["account_id"]
        row["user_id"] = SHARED["user_id"]
        row["credential_kind"] = "shared"
    elif code == "TIMEOUT_RETRY":
        row["simulate_timeout"] = True
    else:
        raise RuntimeError("unmapped hold code %s" % code)

    row["source_row_sha256"] = source_row_sha256(row)
    row["field_sha256"] = field_provenance(row)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_base_valid(i) for i in range(VALID_COUNT)]
    rows.extend(_exception_row(i) for i in range(EXCEPTION_COUNT))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows" % INPUT_COUNT)
    valid = [row for row in rows if row["expected_state"] == "ACCESSION"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(valid) != VALID_COUNT or len(holds) != EXCEPTION_COUNT:
        raise RuntimeError("acceptance fixture split must be 200/40")
    codes = [row["expected_hold_code"] for row in holds]
    for code, count in HOLD_FAMILY_COUNTS.items():
        if codes.count(code) != count:
            raise RuntimeError("%s must appear exactly %s times" % (code, count))
    personal = sum(1 for row in valid if row["product_class"] == "personal_care")
    pharma = sum(1 for row in valid if row["product_class"] == "pharma")
    if personal != 100 or pharma != 100:
        raise RuntimeError("valid split must be 100 personal_care + 100 pharma")
    return rows


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.write_text(_canonical(rows) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if path.is_file():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != INPUT_COUNT:
            raise RuntimeError("fixture.json must contain exactly %s rows" % INPUT_COUNT)
        return rows
    return build_acceptance_fixture()


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "catalog_version": CATALOG_VERSION,
        "catalog_sha256": CATALOG_SHA256,
        "accessions": {},
        "holds": [],
        "events": [],
        "submission_index": {},
        "test_jobs": {},
        "build_state": TRUTH_GATE,
        "released": False,
        "released_by": None,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "production_writes": 0,
        "outreach": False,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_submission(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("simulate_timeout") is True:
        return {"ok": False, "code": "TIMEOUT_RETRY"}

    missing = [field for field in REQUIRED_FIELDS if not _text(row.get(field))]
    if missing:
        return {"ok": False, "code": "MISSING_FIELD", "missing_field": missing[0]}

    credential_kind = _text(row.get("credential_kind")).lower()
    user_id = _text(row.get("user_id"))
    account_id = _text(row.get("account_id"))
    if (
        credential_kind == "shared"
        or user_id == SHARED["user_id"]
        or account_id == SHARED["account_id"]
    ):
        return {"ok": False, "code": "SHARED_CREDENTIAL"}

    if account_id not in ACCOUNTS:
        return {"ok": False, "code": "INVALID_ACCOUNT"}

    user = USERS.get(user_id)
    if user is None or user["account_id"] != account_id:
        return {"ok": False, "code": "INVALID_USER"}
    if user["credential_kind"] != "per_user" or credential_kind != "per_user":
        return {"ok": False, "code": "SHARED_CREDENTIAL"}

    test_code = _text(row.get("test_code"))
    if test_code in OBSOLETE:
        return {"ok": False, "code": "OBSOLETE_CODE"}

    spec = CATALOG.get(test_code)
    if spec is None:
        return {"ok": False, "code": "OBSOLETE_CODE"}

    department = _text(row.get("department"))
    product_class = _text(row.get("product_class"))
    catalog_version = _text(row.get("catalog_version"))
    if department != spec["department"] or product_class != spec["product_class"]:
        return {"ok": False, "code": "WRONG_DEPARTMENT"}
    if catalog_version != CATALOG_VERSION:
        return {"ok": False, "code": "OBSOLETE_CODE"}

    return {
        "ok": True,
        "route": spec["route"],
        "test_code": test_code,
        "department": department,
        "product_class": product_class,
    }


def _hold(journal: dict[str, Any], row: dict[str, Any], code: str) -> dict[str, Any]:
    provenance = {
        "case_id": _text(row.get("case_id")),
        "submission_id": _text(row.get("submission_id")),
        "source_row_sha256": _text(row.get("source_row_sha256")) or source_row_sha256(row),
        "catalog_version": _text(row.get("catalog_version")),
        "catalog_sha256": CATALOG_SHA256,
        "user_id": _text(row.get("user_id")) or None,
        "account_id": _text(row.get("account_id")) or None,
        "field_sha256": row.get("field_sha256") or field_provenance(row),
    }
    hold = {
        "case_id": _text(row.get("case_id")),
        "submission_id": _text(row.get("submission_id")),
        "code": code,
        "state": "HOLD",
        "test_code": _text(row.get("test_code")) or None,
        "department": _text(row.get("department")) or None,
        "product_class": _text(row.get("product_class")) or None,
        "entered_testing": False,
        "test_job": None,
        "provenance": provenance,
    }
    fingerprint = sha256_hex(
        {
            "case_id": hold["case_id"],
            "submission_id": hold["submission_id"],
            "code": hold["code"],
        }
    )
    existing = {
        sha256_hex(
            {
                "case_id": item["case_id"],
                "submission_id": item["submission_id"],
                "code": item["code"],
            }
        )
        for item in journal["holds"]
    }
    if fingerprint not in existing:
        journal["holds"].append(hold)
        journal["submission_index"][_text(row.get("submission_id"))] = {"kind": "HOLD", "code": code}
        _event(journal, "HOLD", {"case_id": hold["case_id"], "code": code})
        return {"kind": "HOLD", "duplicate": False, **hold}
    return {"kind": "HOLD", "duplicate": True, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    submission_id = _text(row.get("submission_id"))
    prior = journal["submission_index"].get(submission_id)
    if prior is not None:
        _event(
            journal,
            "REPLAY_NOOP",
            {"submission_id": submission_id, "prior": prior["kind"]},
        )
        return {"kind": "REPLAY_NOOP", "submission_id": submission_id, "prior": prior["kind"]}

    verdict = classify_submission(row)
    if not verdict["ok"]:
        return _hold(journal, row, verdict["code"])

    sample_id = _text(row.get("sample_id"))
    test_code = verdict["test_code"]
    acc_id = accession_id(submission_id, test_code, sample_id)
    if acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "submission_id": submission_id})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "submission_id": submission_id}

    provenance = {
        "case_id": _text(row.get("case_id")),
        "submission_id": submission_id,
        "source_row_sha256": _text(row.get("source_row_sha256")) or source_row_sha256(row),
        "catalog_version": CATALOG_VERSION,
        "catalog_sha256": CATALOG_SHA256,
        "user_id": _text(row.get("user_id")),
        "account_id": _text(row.get("account_id")),
        "field_sha256": row.get("field_sha256") or field_provenance(row),
    }
    test_job = {
        "job_id": "JOB-" + acc_id[4:],
        "accession_id": acc_id,
        "test_code": test_code,
        "department": verdict["department"],
        "state": "ROUTED",
        "entered_testing": False,
        "interface_state": "SIMULATED",
    }
    record = {
        "accession_id": acc_id,
        "case_id": _text(row.get("case_id")),
        "submission_id": submission_id,
        "sample_id": sample_id,
        "lot_id": _text(row.get("lot_id")),
        "product_name": _text(row.get("product_name")),
        "test_code": test_code,
        "department": verdict["department"],
        "product_class": verdict["product_class"],
        "route": verdict["route"],
        "account_id": _text(row.get("account_id")),
        "user_id": _text(row.get("user_id")),
        "credential_kind": "per_user",
        "catalog_version": CATALOG_VERSION,
        "state": "ACCESSIONED",
        "entered_testing": False,
        "test_job": test_job,
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "provenance": provenance,
    }
    journal["accessions"][acc_id] = record
    journal["test_jobs"][test_job["job_id"]] = test_job
    journal["submission_index"][submission_id] = {"kind": "ACCESSION", "accession_id": acc_id}
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "submission_id": submission_id,
            "route": verdict["route"],
        },
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "route": verdict["route"]}


def release_build(
    journal: dict[str, Any],
    *,
    role_name: str,
    releaser: str,
) -> dict[str, Any]:
    role = _text(role_name).upper()
    if role != HUMAN_ROLE:
        _event(
            journal,
            "RELEASE_DENIED",
            {"code": "AUTONOMOUS_RELEASE_DENIED", "role_name": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if _text(releaser) != HUMAN_QA:
        _event(
            journal,
            "RELEASE_DENIED",
            {"code": "NAMED_HUMAN_QA_REQUIRED", "releaser": _text(releaser) or None},
        )
        return {"ok": False, "code": "NAMED_HUMAN_QA_REQUIRED"}
    if journal["released"]:
        return {"ok": True, "duplicate": True, "build_state": journal["build_state"]}
    journal["released"] = True
    journal["released_by"] = HUMAN_QA
    journal["build_state"] = "HUMAN_QA_RELEASED"
    _event(journal, "BUILD_RELEASED", {"released_by": HUMAN_QA})
    return {"ok": True, "duplicate": False, "build_state": "HUMAN_QA_RELEASED"}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else load_fixture())
    before_acc = set(journal["accessions"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before_acc
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
    }


def _audit_body(journal: dict[str, Any], effects: list[dict[str, Any]]) -> dict[str, Any]:
    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["case_id"])
    holds = deepcopy(journal["holds"])
    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in holds:
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1
    routes = {item["case_id"]: item["route"] for item in accessioned}
    obsolete_in_testing = sum(
        1
        for item in holds
        if item["code"] == "OBSOLETE_CODE" and (item["entered_testing"] or item["test_job"] is not None)
    )
    shared_accessions = sum(1 for item in accessioned if item.get("credential_kind") == "shared")
    def _provenance_ok(item: dict[str, Any]) -> bool:
        prov = item.get("provenance") or {}
        fields = prov.get("field_sha256") or {}
        return bool(
            prov.get("source_row_sha256")
            and prov.get("catalog_sha256")
            and "user_id" in prov
            and "account_id" in prov
            and "case_id" in prov
            and set(fields) == set(REQUIRED_FIELDS)
            and all(fields.values())
        )

    provenance_complete = all(_provenance_ok(item) for item in accessioned + holds)
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "catalog_version": CATALOG_VERSION,
        "catalog_sha256": CATALOG_SHA256,
        "input_rows": len(effects),
        "accessioned": len(accessioned),
        "held": len(holds),
        "hold_codes": sorted({item["code"] for item in holds}),
        "hold_code_counts": hold_code_counts,
        "routes": routes,
        "accession_ids": [item["accession_id"] for item in accessioned],
        "testing_entered": sum(1 for item in accessioned if item["entered_testing"]),
        "obsolete_in_testing": obsolete_in_testing,
        "shared_credential_accessions": shared_accessions,
        "duplicate_accessions": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": [
            {"kind": item.get("kind"), "case_id": item.get("case_id"), "code": item.get("code"), "route": item.get("route")}
            for item in effects
        ],
        "accessions": accessioned,
        "holds": holds,
        "provenance_complete": provenance_complete,
        "build_state": journal["build_state"],
        "released": journal["released"],
        "released_by": journal["released_by"],
        "interface_live": False,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "autonomous_certification": False,
        "autonomous_release": False,
        "production_writes": journal["production_writes"],
        "outreach": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    return body


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else load_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = release_build(journal, role_name="SYSTEM", releaser="autonomous")
    body = _audit_body(journal, effects)
    body["autonomous_release_effects"] = [autonomous]
    body["autonomous_released"] = 1 if journal["released"] else 0
    replay = replay_into(journal, inbound)
    body["replay_added_accessions"] = replay["added_accession_count"]
    body["replay_added_holds"] = replay["added_holds"]
    body["replay_noops_second_pass"] = replay["replay_noops"]
    audit = {
        key: value
        for key, value in body.items()
        if key
        not in {
            "audit_sha256",
            "manifest_sha256",
            "accessions",
            "holds",
            "effects",
            "autonomous_release_effects",
        }
    }
    body["audit_sha256"] = sha256_hex(audit)
    body["manifest_sha256"] = sha256_hex(
        [{"case_id": row["case_id"], "expected_state": row["expected_state"], "expected_hold_code": row.get("expected_hold_code"), "expected_route": row.get("expected_route")} for row in inbound]
    )
    body["journal"] = journal
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != INPUT_COUNT:
        failures.append("input_rows!=240")
    if result.get("accessioned") != VALID_COUNT:
        failures.append("accessioned!=200")
    if result.get("held") != EXCEPTION_COUNT:
        failures.append("held!=40")
    if result.get("hold_code_counts") != HOLD_FAMILY_COUNTS:
        failures.append("hold_code_counts")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT:
        failures.append("accession_ids_not_unique")
    if result.get("testing_entered") != 0:
        failures.append("testing_entered")
    if result.get("obsolete_in_testing") != 0:
        failures.append("obsolete_in_testing")
    if result.get("shared_credential_accessions") != 0:
        failures.append("shared_credential_accessions")
    if result.get("duplicate_accessions") != 0:
        failures.append("duplicate_accessions")
    if result.get("replay_added_accessions") != 0:
        failures.append("replay_added_accessions")
    if result.get("replay_added_holds") != 0:
        failures.append("replay_added_holds")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("provenance_complete") is not True:
        failures.append("provenance_complete")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("shadowing") != "READ_ONLY":
        failures.append("shadowing")
    if result.get("autonomous_released") != 0:
        failures.append("autonomous_released")
    if result.get("released") is not False:
        failures.append("build_auto_released")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("outreach") is not False:
        failures.append("outreach")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("manifest_sha256") != GOLDEN_MANIFEST_SHA256:
        failures.append("manifest_sha256")
    if result.get("catalog_sha256") != GOLDEN_CATALOG_SHA256:
        failures.append("catalog_sha256")
    autonomous = result.get("autonomous_release_effects") or []
    if not autonomous or any(item.get("code") != "AUTONOMOUS_RELEASE_DENIED" for item in autonomous):
        failures.append("autonomous_release_not_denied")
    rows = {row["case_id"]: row for row in load_fixture()}
    for item in result.get("accessions") or []:
        expected = rows.get(item["case_id"])
        if expected is None or expected["expected_state"] != "ACCESSION":
            failures.append("unexpected_accession:%s" % item["case_id"])
            continue
        if item.get("route") != expected.get("expected_route"):
            failures.append("route:%s" % item["case_id"])
        if item.get("entered_testing"):
            failures.append("testing:%s" % item["case_id"])
        if item.get("credential_kind") != "per_user":
            failures.append("shared_user:%s" % item["case_id"])
    for item in result.get("holds") or []:
        expected = rows.get(item["case_id"])
        if expected is None or expected["expected_state"] != "HOLD":
            failures.append("unexpected_hold:%s" % item["case_id"])
            continue
        if item.get("code") != expected.get("expected_hold_code"):
            failures.append("hold_code:%s" % item["case_id"])
        if item.get("entered_testing") or item.get("test_job") is not None:
            failures.append("held_testing:%s" % item["case_id"])
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "valid": VALID_COUNT,
        "exceptions": EXCEPTION_COUNT,
        "accessions": result.get("accessioned"),
        "holds": result.get("held"),
        "testing_entered": result.get("testing_entered"),
        "obsolete_in_testing": result.get("obsolete_in_testing"),
        "shared_credential_accessions": result.get("shared_credential_accessions"),
        "duplicate_accessions": result.get("duplicate_accessions"),
        "replay_added_accessions": result.get("replay_added_accessions"),
        "replay_added_holds": result.get("replay_added_holds"),
        "autonomous_released": result.get("autonomous_released"),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": EXPECTED_COUNTS, "actual": actual, "match": actual == EXPECTED_COUNTS}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--write-fixture":
        write_fixture()
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    rows = load_fixture()
    for row in rows:
        ingest_row(journal, row)
    replay = replay_into(journal, rows)
    human = release_build(journal, role_name=HUMAN_ROLE, releaser=HUMAN_QA)
    failures = pass_contract(first)
    if sha256_hex({k: first[k] for k in ("accessioned", "held", "hold_code_counts", "manifest_sha256")}) != sha256_hex(
        {k: second[k] for k in ("accessioned", "held", "hold_code_counts", "manifest_sha256")}
    ):
        failures.append("replay_mismatch")
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    if not human.get("ok"):
        failures.append("human_qa_release_failed")
    report = {
        "ok": not failures,
        "failures": failures,
        "audit_sha256": first.get("audit_sha256"),
        "manifest_sha256": first.get("manifest_sha256"),
        "catalog_sha256": first.get("catalog_sha256"),
        "accessioned": first.get("accessioned"),
        "held": first.get("held"),
        "hold_code_counts": first.get("hold_code_counts"),
        "testing_entered": first.get("testing_entered"),
        "obsolete_in_testing": first.get("obsolete_in_testing"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "human_qa": human,
        "truth_gate": TRUTH_GATE,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
