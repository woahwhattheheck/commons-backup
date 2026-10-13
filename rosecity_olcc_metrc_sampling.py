#!/usr/bin/env python3
"""Rose City OLCC request-to-Metrc sampling operations ledger.

Read-only ledger linking web request, confirmed appointment/batch count,
Metrc transfer, field pickup/custody, accession, and result-email
destination. Synthetic fixtures and read-only adapters only.

Demand: rosecity-olcc-metrc-sampling-lims-01
Buyer: Rose City Laboratories / Chris Griffey

HOLD / BUILD-AND-VERIFY. No Metrc/state write, compliance decision,
outreach, prospect-facing demo, email send, or automatic result/CoA
release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "rosecity-olcc-metrc-sampling-lims-01"
SCHEMA = "commons-rosecity-olcc-metrc-sampling-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Rose City Laboratories / Chris Griffey"

HOLD_CODES = (
    "MISSING_METRC_TRANSFER",
    "BATCH_COUNT_MISMATCH",
    "DUPLICATE_PACKAGE_ID",
    "UNCONFIRMED_APPOINTMENT",
)

ACCEPTANCE_COUNTS = {
    "input_rows": 100,
    "complete": 75,
    "missing_metrc_transfer": 8,
    "batch_count_mismatch": 7,
    "duplicate_package_id": 5,
    "unconfirmed_appointment": 5,
    "dispatch_ready": 75,
    "hold": 25,
}

DUP_PACKAGE_ID = "1A4FF0000000000000DUP1"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _package_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text:
            out.append(text)
    return out


def _pkg(tag: str, n: int) -> str:
    return "1A4FF00000000000%s%04d" % (tag, n)


def dispatch_id(request_id: str) -> str:
    return "DSP-" + sha256_hex(
        {"demand_id": DEMAND_ID, "kind": "dispatch", "request_id": request_id}
    )[:12]


def custody_id(request_id: str) -> str:
    return "CUS-" + sha256_hex(
        {"demand_id": DEMAND_ID, "kind": "custody", "request_id": request_id}
    )[:12]


def accession_id(request_id: str, package_ids: list[str]) -> str:
    return "ACC-" + sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "accession",
            "package_ids": list(package_ids),
            "request_id": request_id,
        }
    )[:12]


def pickup_id(request_id: str) -> str:
    return "PCK-" + sha256_hex(
        {"demand_id": DEMAND_ID, "kind": "pickup", "request_id": request_id}
    )[:12]


class ReadOnlyMetrcAdapter:
    """Lookup-only Metrc adapter. Writes are denied and never applied."""

    def __init__(self, transfers: dict[str, dict[str, Any] | None] | None = None) -> None:
        self._transfers = deepcopy(transfers or {})
        self.read_count = 0
        self.write_attempts = 0

    def get_transfer(self, request_id: str) -> dict[str, Any] | None:
        self.read_count += 1
        found = self._transfers.get(request_id)
        return None if found is None else deepcopy(found)

    def write_transfer(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.write_attempts += 1
        return {
            "ok": False,
            "code": "METRC_WRITE_DENIED",
            "adapter": "READ_ONLY",
            "applied": False,
        }


class ReadOnlyEmailAdapter:
    """Destination lookup only. Sends are denied and never applied."""

    def __init__(self, destinations: dict[str, str] | None = None) -> None:
        self._destinations = dict(destinations or {})
        self.read_count = 0
        self.send_attempts = 0
        self.sent: list[dict[str, Any]] = []

    def destination_for(self, request_id: str) -> str | None:
        self.read_count += 1
        dest = _text(self._destinations.get(request_id))
        return dest or None

    def send(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.send_attempts += 1
        return {
            "ok": False,
            "code": "EMAIL_SEND_DENIED",
            "adapter": "READ_ONLY",
            "sent": False,
            "released": False,
        }


def _row(
    n: int,
    *,
    confirmed: bool,
    metrc: bool,
    request_batch: int,
    metrc_batch: int | None,
    package_ids: list[str],
    defect: str | None,
) -> dict[str, Any]:
    request_id = "RCL-%03d" % n
    email = "results+%03d@rosecity.example.test" % n
    web_packages = list(package_ids)
    metrc_packages = list(package_ids)
    if defect == "BATCH_COUNT_MISMATCH":
        metrc_packages = web_packages[:1] or [_pkg("X", n)]
    record: dict[str, Any] = {
        "row_id": "R%03d" % n,
        "request_id": request_id,
        "web_request": {
            "submitted_at": "2026-08-31T12:%02d:00Z" % (n % 60),
            "client_license": "060-100%04d" % n,
            "batch_count": request_batch,
            "package_ids": web_packages,
            "result_email": email,
        },
        "appointment": {
            "confirmed": confirmed,
            "scheduled_at": "2026-08-31T14:%02d:00Z" % (n % 60),
            "batch_count": request_batch,
        },
        "metrc_transfer": None,
        "defect": defect,
    }
    if metrc:
        record["metrc_transfer"] = {
            "transfer_id": "TR-%03d" % n,
            "package_ids": metrc_packages,
            "batch_count": request_batch if metrc_batch is None else metrc_batch,
            "adapter": "READ_ONLY",
        }
    return record


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """100-row PASS fixture for rosecity-olcc-metrc-sampling-lims-01.

    75 complete, 8 missing Metrc transfer, 7 request/Metrc batch-count
    mismatches, 5 duplicate package IDs, 5 unconfirmed appointments.
    """
    rows: list[dict[str, Any]] = []
    for n in range(1, 76):
        batch = 2 if n % 5 == 0 else 1
        packages = [_pkg("C", n)]
        if batch == 2:
            packages.append(_pkg("D", n))
        rows.append(
            _row(
                n,
                confirmed=True,
                metrc=True,
                request_batch=batch,
                metrc_batch=batch,
                package_ids=packages,
                defect=None,
            )
        )
    for n in range(76, 84):
        rows.append(
            _row(
                n,
                confirmed=True,
                metrc=False,
                request_batch=1,
                metrc_batch=None,
                package_ids=[_pkg("M", n)],
                defect="MISSING_METRC_TRANSFER",
            )
        )
    for n in range(84, 91):
        rows.append(
            _row(
                n,
                confirmed=True,
                metrc=True,
                request_batch=2,
                metrc_batch=1,
                package_ids=[_pkg("B", n), _pkg("E", n)],
                defect="BATCH_COUNT_MISMATCH",
            )
        )
    for n in range(91, 96):
        rows.append(
            _row(
                n,
                confirmed=True,
                metrc=True,
                request_batch=1,
                metrc_batch=1,
                package_ids=[DUP_PACKAGE_ID],
                defect="DUPLICATE_PACKAGE_ID",
            )
        )
    for n in range(96, 101):
        rows.append(
            _row(
                n,
                confirmed=False,
                metrc=True,
                request_batch=1,
                metrc_batch=1,
                package_ids=[_pkg("U", n)],
                defect="UNCONFIRMED_APPOINTMENT",
            )
        )
    if len(rows) != 100:
        raise RuntimeError("acceptance fixture must be exactly 100 rows, got %s" % len(rows))
    return rows


def adapters_from_rows(
    rows: list[dict[str, Any]],
) -> tuple[ReadOnlyMetrcAdapter, ReadOnlyEmailAdapter]:
    transfers: dict[str, dict[str, Any] | None] = {}
    destinations: dict[str, str] = {}
    for row in rows:
        request_id = _text(row.get("request_id"))
        transfers[request_id] = row.get("metrc_transfer")
        destinations[request_id] = _text((row.get("web_request") or {}).get("result_email"))
    return ReadOnlyMetrcAdapter(transfers), ReadOnlyEmailAdapter(destinations)


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "verdicts": {},
        "dispatches": {},
        "custody_chains": {},
        "accessions": {},
        "holds": [],
        "events": [],
        "emails_sent": [],
        "metrc_writes": [],
        "coa_releases": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def request_packages(row: dict[str, Any]) -> list[str]:
    web = row.get("web_request") or {}
    return _package_ids(web.get("package_ids"))


def package_frequency(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count each package ID across requests.

    A package listed twice on one request counts as a duplicate. The same
    package on a request and its matching Metrc transfer does not.
    """
    counts: dict[str, int] = {}
    for row in rows:
        packages = request_packages(row)
        seen: set[str] = set()
        for pkg in packages:
            if pkg in seen:
                counts[pkg] = counts.get(pkg, 0) + 1
            seen.add(pkg)
        for pkg in seen:
            counts[pkg] = counts.get(pkg, 0) + 1
    return counts


def classify_request(
    row: dict[str, Any],
    package_counts: dict[str, int] | None = None,
    metrc_adapter: ReadOnlyMetrcAdapter | None = None,
) -> dict[str, Any]:
    request_id = _text(row.get("request_id"))
    web = row.get("web_request") or {}
    appointment = row.get("appointment") or {}
    transfer = row.get("metrc_transfer")
    if metrc_adapter is not None:
        transfer = metrc_adapter.get_transfer(request_id)
    packages = _package_ids(web.get("package_ids"))
    request_batch = _int(web.get("batch_count"))
    appt_batch = _int(appointment.get("batch_count"), request_batch)
    confirmed = _flag(appointment.get("confirmed"))
    email = _text(web.get("result_email"))

    base = {
        "request_id": request_id,
        "package_ids": packages,
        "request_batch_count": request_batch,
        "appointment_batch_count": appt_batch,
        "appointment_confirmed": confirmed,
        "result_email": email or None,
        "metrc_transfer_id": None if not transfer else _text(transfer.get("transfer_id")) or None,
    }

    if not confirmed:
        return {"ok": False, "status": "HOLD", "code": "UNCONFIRMED_APPOINTMENT", **base}
    if not transfer:
        return {"ok": False, "status": "HOLD", "code": "MISSING_METRC_TRANSFER", **base}

    metrc_batch = _int(transfer.get("batch_count"))
    if request_batch != metrc_batch or appt_batch != metrc_batch:
        return {
            "ok": False,
            "status": "HOLD",
            "code": "BATCH_COUNT_MISMATCH",
            "metrc_batch_count": metrc_batch,
            **base,
        }

    counts = package_counts or {}
    if len(packages) != len(set(packages)) or any(counts.get(pkg, 1) > 1 for pkg in packages):
        return {"ok": False, "status": "HOLD", "code": "DUPLICATE_PACKAGE_ID", **base}

    return {
        "ok": True,
        "status": "DISPATCH_READY",
        "code": None,
        "metrc_batch_count": metrc_batch,
        **base,
    }


def _custody_link(seq: int, kind: str, ref: str, payload: dict[str, Any], prev: str | None) -> dict[str, Any]:
    body = {
        "kind": kind,
        "payload": payload,
        "prev": prev,
        "ref": ref,
        "seq": seq,
    }
    return {**body, "hash": sha256_hex(body)}


def build_custody_chain(row: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    request_id = verdict["request_id"]
    packages = list(verdict["package_ids"])
    acc_id = accession_id(request_id, packages)
    pck_id = pickup_id(request_id)
    cus_id = custody_id(request_id)
    transfer = row.get("metrc_transfer") or {}
    web = row.get("web_request") or {}
    appointment = row.get("appointment") or {}

    links = []
    prev = None
    steps = [
        (
            "WEB_REQUEST",
            request_id,
            {
                "batch_count": _int(web.get("batch_count")),
                "package_ids": packages,
                "submitted_at": _text(web.get("submitted_at")),
            },
        ),
        (
            "APPOINTMENT",
            request_id + ":appt",
            {
                "batch_count": _int(appointment.get("batch_count")),
                "confirmed": True,
                "scheduled_at": _text(appointment.get("scheduled_at")),
            },
        ),
        (
            "METRC_TRANSFER",
            _text(transfer.get("transfer_id")),
            {
                "batch_count": _int(transfer.get("batch_count")),
                "package_ids": _package_ids(transfer.get("package_ids")),
                "transfer_id": _text(transfer.get("transfer_id")),
            },
        ),
        (
            "FIELD_PICKUP",
            pck_id,
            {"package_ids": packages, "pickup_id": pck_id},
        ),
        (
            "ACCESSION",
            acc_id,
            {"accession_id": acc_id, "package_ids": packages},
        ),
    ]
    for seq, (kind, ref, payload) in enumerate(steps, start=1):
        link = _custody_link(seq, kind, ref, payload, prev)
        links.append(link)
        prev = link["hash"]

    chain = {
        "accession_id": acc_id,
        "chain_hash": sha256_hex({"custody_id": cus_id, "links": links}),
        "custody_id": cus_id,
        "immutable": True,
        "links": links,
        "pickup_id": pck_id,
        "request_id": request_id,
        "sealed": True,
    }
    return chain


def seal_custody(chain: dict[str, Any]) -> dict[str, Any]:
    sealed = deepcopy(chain)
    sealed["immutable"] = True
    sealed["sealed"] = True
    sealed["chain_hash"] = sha256_hex(
        {"custody_id": sealed.get("custody_id"), "links": sealed.get("links")}
    )
    return sealed


def mutate_custody(chain: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    if chain.get("immutable") or chain.get("sealed"):
        return {
            "ok": False,
            "code": "IMMUTABLE_CUSTODY",
            "custody_id": chain.get("custody_id"),
            "applied": False,
        }
    return {"ok": False, "code": "IMMUTABLE_CUSTODY", "applied": False}


def attempt_email_send(
    journal: dict[str, Any],
    request_id: str,
    email_adapter: ReadOnlyEmailAdapter | None = None,
) -> dict[str, Any]:
    if email_adapter is not None:
        denied = email_adapter.send(request_id)
    else:
        denied = {
            "ok": False,
            "code": "EMAIL_SEND_DENIED",
            "adapter": "READ_ONLY",
            "sent": False,
            "released": False,
        }
    _event(journal, "EMAIL_SEND_DENIED", {"request_id": request_id, **denied})
    return denied


def attempt_metrc_write(
    journal: dict[str, Any],
    request_id: str,
    metrc_adapter: ReadOnlyMetrcAdapter | None = None,
) -> dict[str, Any]:
    if metrc_adapter is not None:
        denied = metrc_adapter.write_transfer(request_id)
    else:
        denied = {
            "ok": False,
            "code": "METRC_WRITE_DENIED",
            "adapter": "READ_ONLY",
            "applied": False,
        }
    journal["metrc_writes"].append({"request_id": request_id, **denied})
    _event(journal, "METRC_WRITE_DENIED", {"request_id": request_id, **denied})
    return denied


def attempt_coa_release(journal: dict[str, Any], request_id: str) -> dict[str, Any]:
    denied = {
        "ok": False,
        "code": "AUTO_RELEASE_DENIED",
        "released": False,
        "sent": False,
    }
    journal["coa_releases"].append({"request_id": request_id, **denied})
    _event(journal, "AUTO_RELEASE_DENIED", {"request_id": request_id, **denied})
    return denied


def ingest_row(
    journal: dict[str, Any],
    row: dict[str, Any],
    *,
    package_counts: dict[str, int] | None = None,
    metrc_adapter: ReadOnlyMetrcAdapter | None = None,
    email_adapter: ReadOnlyEmailAdapter | None = None,
) -> dict[str, Any]:
    request_id = _text(row.get("request_id"))
    existing = journal["verdicts"].get(request_id)
    if existing is not None:
        _event(journal, "REPLAY_NOOP", {"request_id": request_id, "status": existing.get("status")})
        return {"kind": "REPLAY_NOOP", "request_id": request_id, "status": existing.get("status")}

    verdict = classify_request(row, package_counts, metrc_adapter=metrc_adapter)
    destination = None
    if email_adapter is not None:
        destination = email_adapter.destination_for(request_id)
    if not destination:
        destination = verdict.get("result_email")

    if not verdict["ok"]:
        hold = {
            "request_id": request_id,
            "code": verdict["code"],
            "status": "HOLD",
            "dispatch_id": None,
            "custody_id": None,
            "accession_id": None,
            "result_email": destination,
            "email_linked": bool(destination),
            "email_sent": False,
            "coa_released": False,
        }
        journal["verdicts"][request_id] = hold
        journal["holds"].append(hold)
        _event(journal, "HOLD", {"request_id": request_id, "code": verdict["code"]})
        return {"kind": "HOLD", "request_id": request_id, "code": verdict["code"], "dispatch": None}

    packages = list(verdict["package_ids"])
    dsp_id = dispatch_id(request_id)
    chain = seal_custody(build_custody_chain(row, verdict))
    acc_id = chain["accession_id"]
    cus_id = chain["custody_id"]

    accession = {
        "accession_id": acc_id,
        "custody_id": cus_id,
        "dispatch_id": dsp_id,
        "package_ids": packages,
        "request_id": request_id,
        "state": "ACCESSIONED",
    }
    dispatch = {
        "accession_id": acc_id,
        "coa_released": False,
        "custody_id": cus_id,
        "dispatch_id": dsp_id,
        "email_destination": destination,
        "email_linked": bool(destination),
        "email_sent": False,
        "package_ids": packages,
        "pickup_id": chain["pickup_id"],
        "request_id": request_id,
        "status": "DISPATCH_READY",
        "auto_release": False,
    }
    ready = {
        "accession_id": acc_id,
        "code": None,
        "coa_released": False,
        "custody_id": cus_id,
        "dispatch_id": dsp_id,
        "email_linked": bool(destination),
        "email_sent": False,
        "result_email": destination,
        "request_id": request_id,
        "status": "DISPATCH_READY",
    }
    journal["verdicts"][request_id] = ready
    journal["dispatches"][dsp_id] = dispatch
    journal["custody_chains"][cus_id] = chain
    journal["accessions"][acc_id] = accession
    _event(
        journal,
        "DISPATCH_READY",
        {
            "accession_id": acc_id,
            "custody_id": cus_id,
            "dispatch_id": dsp_id,
            "request_id": request_id,
        },
    )
    return {
        "kind": "DISPATCH_READY",
        "request_id": request_id,
        "dispatch_id": dsp_id,
        "custody_id": cus_id,
        "accession_id": acc_id,
    }


def ingest_fixture(
    journal: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    metrc_adapter: ReadOnlyMetrcAdapter | None = None,
    email_adapter: ReadOnlyEmailAdapter | None = None,
) -> list[dict[str, Any]]:
    counts = package_frequency(rows)
    return [
        ingest_row(
            journal,
            row,
            package_counts=counts,
            metrc_adapter=metrc_adapter,
            email_adapter=email_adapter,
        )
        for row in rows
    ]


def replay_into(
    journal: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
    *,
    metrc_adapter: ReadOnlyMetrcAdapter | None = None,
    email_adapter: ReadOnlyEmailAdapter | None = None,
) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_dispatch = set(journal["dispatches"])
    before_custody = set(journal["custody_chains"])
    before_acc = set(journal["accessions"])
    before_holds = len(journal["holds"])
    effects = ingest_fixture(
        journal,
        inbound,
        metrc_adapter=metrc_adapter,
        email_adapter=email_adapter,
    )
    return {
        "added_accessions": sorted(set(journal["accessions"]) - before_acc),
        "added_accession_count": len(set(journal["accessions"]) - before_acc),
        "added_custody_count": len(set(journal["custody_chains"]) - before_custody),
        "added_dispatch_count": len(set(journal["dispatches"]) - before_dispatch),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "dispatch_count": len(journal["dispatches"]),
        "hold_count": len(journal["holds"]),
        "accession_count": len(journal["accessions"]),
        "custody_count": len(journal["custody_chains"]),
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    metrc_adapter, email_adapter = adapters_from_rows(inbound)
    journal = empty_journal()
    effects = ingest_fixture(
        journal,
        inbound,
        metrc_adapter=metrc_adapter,
        email_adapter=email_adapter,
    )
    email_denials = []
    release_denials = []
    for request_id, verdict in journal["verdicts"].items():
        if verdict.get("status") == "DISPATCH_READY":
            email_denials.append(attempt_email_send(journal, request_id, email_adapter))
            release_denials.append(attempt_coa_release(journal, request_id))
    metrc_denial = attempt_metrc_write(journal, "LEDGER", metrc_adapter)

    hold_codes = sorted(item["code"] for item in journal["holds"])
    hold_code_counts: dict[str, int] = {}
    for item in journal["holds"]:
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1

    ready = [item for item in journal["verdicts"].values() if item.get("status") == "DISPATCH_READY"]
    holds = [item for item in journal["verdicts"].values() if item.get("status") == "HOLD"]
    custody_ok = all(
        journal["custody_chains"][item["custody_id"]]["immutable"]
        and journal["custody_chains"][item["custody_id"]]["sealed"]
        and journal["custody_chains"][item["custody_id"]]["accession_id"] == item["accession_id"]
        and len(journal["custody_chains"][item["custody_id"]]["links"]) == 5
        for item in ready
    )
    hold_dispatches = sum(1 for item in holds if item.get("dispatch_id"))
    emails_sent = sum(1 for item in journal["dispatches"].values() if item.get("email_sent"))
    released = sum(1 for item in journal["dispatches"].values() if item.get("coa_released"))

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "dispatch_ready": len(ready),
        "hold": len(holds),
        "hold_codes": hold_codes,
        "hold_code_counts": {
            "MISSING_METRC_TRANSFER": hold_code_counts.get("MISSING_METRC_TRANSFER", 0),
            "BATCH_COUNT_MISMATCH": hold_code_counts.get("BATCH_COUNT_MISMATCH", 0),
            "DUPLICATE_PACKAGE_ID": hold_code_counts.get("DUPLICATE_PACKAGE_ID", 0),
            "UNCONFIRMED_APPOINTMENT": hold_code_counts.get("UNCONFIRMED_APPOINTMENT", 0),
        },
        "dispatch_count": len(journal["dispatches"]),
        "hold_dispatch_count": hold_dispatches,
        "custody_count": len(journal["custody_chains"]),
        "accession_count": len(journal["accessions"]),
        "ready_request_ids": sorted(item["request_id"] for item in ready),
        "hold_request_ids": sorted(item["request_id"] for item in holds),
        "dispatch_ids": sorted(journal["dispatches"]),
        "custody_ids": sorted(journal["custody_chains"]),
        "accession_ids": sorted(journal["accessions"]),
        "email_linked": sum(1 for item in journal["dispatches"].values() if item.get("email_linked")),
        "emails_sent": emails_sent,
        "coa_released": released,
        "email_send_denied": len(email_denials),
        "auto_release_denied": len(release_denials),
        "metrc_write_denied": metrc_denial.get("code") == "METRC_WRITE_DENIED",
        "metrc_write_count": metrc_adapter.write_attempts,
        "email_send_attempts": email_adapter.send_attempts,
        "email_adapter_sent": len(email_adapter.sent),
        "custody_immutable": custody_ok,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "email_denials": email_denials,
        "release_denials": release_denials,
        "metrc_denial": metrc_denial,
        "dispatches": sorted(journal["dispatches"].values(), key=lambda item: item["request_id"]),
        "holds": deepcopy(journal["holds"]),
        "custody_chains": sorted(
            journal["custody_chains"].values(), key=lambda item: item["request_id"]
        ),
        "accessions": sorted(journal["accessions"].values(), key=lambda item: item["request_id"]),
        "interface_live": False,
        "interfaces": "READ_ONLY_SYNTHETIC",
        "metrc_write": False,
        "state_write": False,
        "compliance_decision": False,
        "outreach": False,
        "prospect_demo": False,
        "automatic_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("input_rows") != 100:
        failures.append("input_rows!=100")
    if result.get("dispatch_ready") != 75:
        failures.append("dispatch_ready!=75")
    if result.get("hold") != 25:
        failures.append("hold!=25")
    if result.get("dispatch_count") != 75:
        failures.append("dispatch_count!=75")
    if result.get("hold_dispatch_count") != 0:
        failures.append("hold_produced_dispatch")
    if result.get("custody_count") != 75:
        failures.append("custody_count!=75")
    if result.get("accession_count") != 75:
        failures.append("accession_count!=75")
    expected_holds = {
        "MISSING_METRC_TRANSFER": 8,
        "BATCH_COUNT_MISMATCH": 7,
        "DUPLICATE_PACKAGE_ID": 5,
        "UNCONFIRMED_APPOINTMENT": 5,
    }
    if result.get("hold_code_counts") != expected_holds:
        failures.append("hold_code_counts")
    if result.get("email_linked") != 75:
        failures.append("email_linked!=75")
    if result.get("emails_sent") != 0:
        failures.append("emails_sent!=0")
    if result.get("coa_released") != 0:
        failures.append("coa_released!=0")
    if result.get("email_adapter_sent") != 0:
        failures.append("email_adapter_sent")
    if result.get("metrc_write") is not False:
        failures.append("metrc_write")
    if result.get("state_write") is not False:
        failures.append("state_write")
    if result.get("automatic_release") is not False:
        failures.append("automatic_release")
    if result.get("metrc_write_denied") is not True:
        failures.append("metrc_write_not_denied")
    if result.get("email_send_denied") != 75:
        failures.append("email_send_denied!=75")
    if result.get("auto_release_denied") != 75:
        failures.append("auto_release_denied!=75")
    if result.get("custody_immutable") is not True:
        failures.append("custody_not_immutable")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "READ_ONLY_SYNTHETIC":
        failures.append("interfaces")
    if len(set(result.get("dispatch_ids") or [])) != 75:
        failures.append("dispatch_ids_not_unique")
    if len(set(result.get("custody_ids") or [])) != 75:
        failures.append("custody_ids_not_unique")
    if len(set(result.get("accession_ids") or [])) != 75:
        failures.append("accession_ids_not_unique")
    if not all(item.get("email_linked") and not item.get("email_sent") for item in result.get("dispatches") or []):
        failures.append("dispatch_email_not_linked_only")
    if not all(item.get("code") == "EMAIL_SEND_DENIED" for item in result.get("email_denials") or []):
        failures.append("email_not_denied")
    if not all(item.get("code") == "AUTO_RELEASE_DENIED" for item in result.get("release_denials") or []):
        failures.append("release_not_denied")
    for chain in result.get("custody_chains") or []:
        if not chain.get("immutable") or not chain.get("sealed"):
            failures.append("custody_unsealed")
            break
        if len(chain.get("links") or []) != 5:
            failures.append("custody_link_count")
            break
        kinds = [link.get("kind") for link in chain.get("links") or []]
        if kinds != ["WEB_REQUEST", "APPOINTMENT", "METRC_TRANSFER", "FIELD_PICKUP", "ACCESSION"]:
            failures.append("custody_link_kinds")
            break
        if mutate_custody(chain).get("code") != "IMMUTABLE_CUSTODY":
            failures.append("custody_mutated")
            break
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    rows = build_acceptance_fixture()
    metrc_adapter, email_adapter = adapters_from_rows(rows)
    ingest_fixture(journal, rows, metrc_adapter=metrc_adapter, email_adapter=email_adapter)
    replay = replay_into(journal, rows, metrc_adapter=metrc_adapter, email_adapter=email_adapter)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_dispatch_count") != 0:
        failures.append("replay_added_dispatches")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_custody_count") != 0:
        failures.append("replay_added_custody")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "dispatch_ready": first.get("dispatch_ready"),
        "hold": first.get("hold"),
        "hold_code_counts": first.get("hold_code_counts"),
        "dispatch_count": first.get("dispatch_count"),
        "hold_dispatch_count": first.get("hold_dispatch_count"),
        "custody_count": first.get("custody_count"),
        "accession_count": first.get("accession_count"),
        "emails_sent": first.get("emails_sent"),
        "coa_released": first.get("coa_released"),
        "replay_added_dispatches": replay.get("added_dispatch_count"),
        "replay_noops": replay.get("replay_noops"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
