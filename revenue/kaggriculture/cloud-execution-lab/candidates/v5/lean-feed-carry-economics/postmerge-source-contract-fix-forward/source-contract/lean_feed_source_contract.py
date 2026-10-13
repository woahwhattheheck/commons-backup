#!/usr/bin/env python3
"""Source authority for the TITAN V5 lean-feed economics carrier.

This module is deliberately independent of caller evidence.  The checked-in
contract can only describe source facts already pinned here; it cannot mint a
new feed domain, reserve vector, or promotion authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from lean_feed_core import EvidenceError

SOURCE_CONTRACT_SCHEMA = "titan-v5-lean-feed-source-contract-v2"
SOURCE_ASSESSMENT_SCHEMA = "titan-v5-lean-feed-source-assessment-v1"
SOURCE_BLOCKED_REPORT_SCHEMA = "titan-v5-lean-feed-carry-report-v1"

D2_ARCHIVE_SHA256 = "3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8"
D2_MAIN_SHA256 = "ae7032281ba680cc70fdfc333bb55cbd4aab7127c277c5150f18746c12f549d3"
OFFICIAL_ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
OFFICIAL_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
MECHANICS_SHA256 = "579965e589237d1e5bbcc8b8448188f91b173d4480430d34b3a7f0e07e0c48d3"
LINEAGE_RUNTIME_GIT_BLOB = "998bf5da08f61f82eafaf5750c8a86fc3adad7fb"
LINEAGE_OPERATING_STOCK_GIT_BLOB = "80b372bfd34d04a2c9e2376fa02917f21f659c41"

FEED_ITEM = "WHEAT"
SUPPORTED_BUY_PRODUCTS = ("FERTILIZER", "WHEAT")
RUNTIME_SEAM = "TitanAgent._feed_stock_selected"
HELPER_SEAM = "operating_stock.protect_feed_stock"
MECHANISM = "selected_sell_wheat_reservation"
FORBIDDEN_FICTIONAL_FEEDS = frozenset({"Corn", "Pasture", "Straw", "PIG"})


class SourceContractError(EvidenceError):
    """Raised when the retained source contract is malformed or drifts."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SourceContractError(message)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def default_contract_path() -> Path:
    return Path(__file__).with_name("d2_contract.json")


def _strict_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SourceContractError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                SourceContractError(f"non-finite JSON constant: {token}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise SourceContractError("contract is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise SourceContractError("contract is not valid JSON") from exc
    _require(isinstance(parsed, dict), "contract root must be an object")
    return parsed


def assess_retained_source_contract(
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Authenticate the retained contract and return a non-authorizing verdict.

    The exact D2 archive bytes/member manifest are not retained in this source
    carrier.  Consequently, even a source-correct WHEAT model cannot claim it is
    the exact active D2 policy.  The only safe result today is SOURCE_MODEL_BLOCKED.
    """
    path = default_contract_path() if contract_path is None else Path(contract_path)
    contract = _strict_json_object(path)

    expected_keys = {
        "schema",
        "archive_sha256",
        "archive_member_count",
        "main_sha256",
        "official_engine_sha256",
        "official_engine_git_blob",
        "mechanics_sha256",
        "lineage_runtime_git_blob",
        "lineage_operating_stock_git_blob",
        "feed_item",
        "supported_buy_products",
        "runtime_seam",
        "helper_seam",
        "mechanism",
        "fixed_reserve_vector",
        "d2_member_binding",
        "promotion_authorized",
    }
    _require(set(contract) == expected_keys, "contract key set mismatch")
    _require(contract["schema"] == SOURCE_CONTRACT_SCHEMA, "wrong contract schema")
    _require(contract["archive_sha256"] == D2_ARCHIVE_SHA256, "wrong D2 archive")
    _require(contract["archive_member_count"] == 94, "wrong D2 member count")
    _require(contract["main_sha256"] == D2_MAIN_SHA256, "wrong D2 main SHA-256")
    _require(
        contract["official_engine_sha256"] == OFFICIAL_ENGINE_SHA256,
        "wrong official engine SHA-256",
    )
    _require(
        contract["official_engine_git_blob"] == OFFICIAL_ENGINE_GIT_BLOB,
        "wrong official engine Git blob",
    )
    _require(contract["mechanics_sha256"] == MECHANICS_SHA256, "wrong mechanics SHA-256")
    _require(
        contract["lineage_runtime_git_blob"] == LINEAGE_RUNTIME_GIT_BLOB,
        "wrong retained runtime lineage blob",
    )
    _require(
        contract["lineage_operating_stock_git_blob"]
        == LINEAGE_OPERATING_STOCK_GIT_BLOB,
        "wrong retained operating-stock lineage blob",
    )
    _require(contract["feed_item"] == FEED_ITEM, "feed item must be WHEAT")
    products = contract["supported_buy_products"]
    _require(
        isinstance(products, list) and tuple(sorted(products)) == SUPPORTED_BUY_PRODUCTS,
        "BUY_PRODUCT domain must be WHEAT/FERTILIZER",
    )
    _require(contract["runtime_seam"] == RUNTIME_SEAM, "wrong runtime seam")
    _require(contract["helper_seam"] == HELPER_SEAM, "wrong helper seam")
    _require(contract["mechanism"] == MECHANISM, "wrong mechanism")
    _require(contract["fixed_reserve_vector"] is None, "fixed reserve vector is forbidden")
    _require(
        contract["d2_member_binding"] == "BLOCKED_RAW_ARCHIVE_BYTES_NOT_RETAINED",
        "D2 member binding must remain blocked without exact archive bytes",
    )
    _require(contract["promotion_authorized"] is False, "source contract cannot authorize promotion")

    serialized = json.dumps(contract, sort_keys=True, ensure_ascii=False)
    for token in FORBIDDEN_FICTIONAL_FEEDS:
        _require(token not in serialized, f"fictional feed token retained: {token}")

    facts = {
        "feed_item": FEED_ITEM,
        "animal_feed_action": "FEED consumes one WHEAT",
        "supported_buy_products": list(SUPPORTED_BUY_PRODUCTS),
        "buy_execution": "per-unit lockstep; quote at post-buy inventory",
        "runtime_seam": RUNTIME_SEAM,
        "helper_seam": HELPER_SEAM,
        "known_lineage_theorem": (
            "protect_feed_stock edits SELL WHEAT only and, on a certified changed "
            "window, leaves the route-proven required_wheat; it is not a generic feed buyer"
        ),
    }
    reasons = [
        "the merged v1 Corn/Pasture/Straw purchase model is outside the official engine domain",
        "the official FEED action consumes WHEAT only",
        "BUY_PRODUCT executes WHEAT/FERTILIZER per unit against changing market inventory",
        "the retained current-lineage helper is a dynamic SELL WHEAT reservation, not a fixed purchase vector",
        "exact D2 archive member bytes are not retained here, so active D2 policy identity cannot be authenticated",
    ]
    assessment: dict[str, Any] = {
        "schema": SOURCE_ASSESSMENT_SCHEMA,
        "state": "SOURCE_MODEL_BLOCKED",
        "promotion_authorized": False,
        "candidate_build_authorized": False,
        "contract_sha256": _sha256_json(contract),
        "facts": facts,
        "reasons": reasons,
        "required_next_evidence": [
            "exact D2 archive bytes matching archive_sha256",
            "safe member manifest proving active runtime/helper source identities",
            "WHEAT-only public-state census of current SELL-reservation behavior",
            "paired official-engine evidence only if that census proves reachable excess",
        ],
    }
    assessment["assessment_sha256"] = _sha256_json(assessment)
    return assessment


def build_source_blocked_report(
    document: Mapping[str, Any], assessment: Mapping[str, Any]
) -> dict[str, Any]:
    """Emit a deterministic non-authorizing report without evaluating fake arms."""
    _require(isinstance(document, Mapping), "evidence root must be an object")
    archive = None
    authority = document.get("authority")
    if isinstance(authority, Mapping):
        archive = authority.get("archive_sha256")
    _require(archive == D2_ARCHIVE_SHA256, "wrong D2 archive SHA-256")
    reasons = list(assessment["reasons"])
    report: dict[str, Any] = {
        "schema": SOURCE_BLOCKED_REPORT_SCHEMA,
        "authority": {
            "archive_sha256": D2_ARCHIVE_SHA256,
            "archive_member_count": 94,
            "main_sha256": D2_MAIN_SHA256,
            "official_engine_sha256": OFFICIAL_ENGINE_SHA256,
        },
        "source_contract": dict(assessment),
        "design": {"cells": 0, "dev_opponents": [], "holdout_opponents": []},
        "promotion": {
            "conclusion": "SOURCE_MODEL_BLOCKED",
            "selected_arm": None,
            "dev_mean_delta_m": 0.0,
            "holdout_mean_delta_m": 0.0,
            "active_dev_windows": 0,
            "active_holdout_windows": 0,
            "dev_downstream_cash_used": 0.0,
            "holdout_downstream_cash_used": 0.0,
            "obligation_failures": 0,
            "productivity_loss": 0.0,
            "survival_loss": 0.0,
            "strata": [],
            "falsifiers": reasons,
        },
        "census": [],
        "paired_deltas": [],
        "runs": [],
        "input_sha256": _sha256_json(document),
    }
    report["report_sha256"] = _sha256_json(report)
    return report
