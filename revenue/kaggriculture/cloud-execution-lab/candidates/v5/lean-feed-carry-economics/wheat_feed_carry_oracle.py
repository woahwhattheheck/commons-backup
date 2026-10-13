#!/usr/bin/env python3
"""Post-authenticated WHEAT carry census for TITAN V5 D2.

Research/evidence only. This module does not import or mutate gameplay policy.
It binds the retained D2 authentication receipt and independently compares the
exact source-derived `protect_feed_stock` withholding equation with the minimum
withholding required to preserve its certified WHEAT obligation.

A negative result here is scoped to the final certified helper seam. Upstream
action selection may still under-offer otherwise balance-permitted WHEAT without
contradicting the helper theorem; that remains an explicit empirical census gate.
"""
from __future__ import annotations

import json
from hashlib import sha256 as _sha256_source
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "titan-v5-d2-wheat-carry-census-v1"
STATUS_SCHEMA = "titan-v5-d2-recovery-status-v1"

D2_ARCHIVE_SHA256 = "3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8"
D2_ARCHIVE_BYTES = 424145
D2_MEMBER_COUNT = 94
AUTH_RECEIPT_SHA256 = "df11fce3b91bcf36ad280942ed38e1faed743ce3b23fbb6f8b8e8a5ada65fb46"
SAFE_MANIFEST_SHA256 = "d0c150d5be46a6f5e5b3275197c0f3279f4f7345b61e0ff917196db5a1eca84c"
RUNTIME_MEMBER = "titan_runtime.py"
RUNTIME_GIT_BLOB = "e0cdcf5a5dbe350d442d3b492795d37507449853"
OPERATING_STOCK_GIT_BLOB = "80b372bfd34d04a2c9e2376fa02917f21f659c41"
OFFICIAL_ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
HARNESS_SHA256 = "853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4"
D2_STATUS_SHA256 = "fc4617e4f0075098e101d19dd859b574090b0cc8ef43add0d6d028c26cedb371"

STATE_AUTHENTICATED = "D2_SOURCE_AUTHENTICATED"
NEGATIVE = "NO_DISCRETIONARY_EXCESS_AT_CERTIFIED_WHEAT_SEAM"
UNCERTIFIED = "CURRENT_POLICY_UNCERTIFIED"
CONTRADICTION = "SOURCE_CONTRADICTION"
UPSTREAM_GATE = "UPSTREAM_SELECTED_WHEAT_OFFER_CENSUS_REQUIRED"
MAX_SHED_CAPACITY = 100
MAX_HELPER_WITHHOLD = 2
MAX_STATUS_BYTES = 64 * 1024
MAX_STATUS_JSON_DEPTH = 64
MAX_STATUS_JSON_NODES = 4096


class WheatCensusError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WheatCensusError(message)


def _whole(value: Any, label: str, *, maximum: int | None = None) -> int:
    _require(type(value) is int and value >= 0, f"{label} must be a non-negative exact int")
    if maximum is not None:
        _require(value <= maximum, f"{label} exceeds {maximum}")
    return value


def _check_status_shape(value: Any) -> None:
    """Bound parsed status depth/node work and reject unsupported JSON scalars."""
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        _require(nodes <= MAX_STATUS_JSON_NODES, "status JSON has too many nodes")
        _require(depth <= MAX_STATUS_JSON_DEPTH, "status JSON is too deeply nested")
        if item is None or type(item) in {bool, int, str}:
            continue
        if type(item) is list:
            if len(item) > MAX_STATUS_JSON_NODES - nodes:
                raise WheatCensusError("status JSON has too many nodes")
            stack.extend((child, depth + 1) for child in item)
            continue
        if type(item) is dict:
            if len(item) > MAX_STATUS_JSON_NODES - nodes:
                raise WheatCensusError("status JSON has too many nodes")
            stack.extend((child, depth + 1) for child in item.values())
            continue
        raise WheatCensusError(f"unsupported status JSON type: {type(item).__name__}")


def _parse_status_bytes(raw: bytes) -> dict[str, Any]:
    """Strictly parse bounded status bytes without granting source authority."""
    _require(type(raw) is bytes, "status input must be bytes")
    _require(len(raw) <= MAX_STATUS_BYTES, "status file too large")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            _require(type(key) is str, "status key must be string")
            _require(key not in out, f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def parse_int(token: str) -> int:
        _require(len(token.lstrip("-")) <= 128, "integer token too long")
        try:
            return int(token)
        except ValueError as exc:
            raise WheatCensusError("invalid integer token") from exc

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_int=parse_int,
            parse_float=lambda token: (_ for _ in ()).throw(
                WheatCensusError(f"floating point JSON forbidden: {token}")
            ),
            parse_constant=lambda token: (_ for _ in ()).throw(
                WheatCensusError(f"non-finite JSON constant: {token}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise WheatCensusError("status is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise WheatCensusError("status is not valid JSON") from exc
    except RecursionError as exc:
        raise WheatCensusError("status JSON is too deeply nested") from exc
    _check_status_shape(value)
    _require(type(value) is dict, "status root must be object")
    return value


def _strict_json_object(path: Path) -> dict[str, Any]:
    """Test/diagnostic parser only; parsing arbitrary paths never grants authority."""
    return _parse_status_bytes(Path(path).read_bytes())


def default_status_path() -> Path:
    return Path(__file__).with_name("D2_RECOVERY_STATUS.json")


def _build_status_validator(
    *,
    status_path: Path = default_status_path(),
    sha256_fn=_sha256_source,
    parse_status=_parse_status_bytes,
    require_fn=_require,
    expected_status_sha256: str = D2_STATUS_SHA256,
    status_schema: str = STATUS_SCHEMA,
    authenticated_state: str = STATE_AUTHENTICATED,
    archive_sha256: str = D2_ARCHIVE_SHA256,
    archive_bytes: int = D2_ARCHIVE_BYTES,
    archive_members: int = D2_MEMBER_COUNT,
    auth_receipt_sha256: str = AUTH_RECEIPT_SHA256,
    safe_manifest_sha256: str = SAFE_MANIFEST_SHA256,
    runtime_member: str = RUNTIME_MEMBER,
    runtime_git_blob: str = RUNTIME_GIT_BLOB,
    operating_stock_git_blob: str = OPERATING_STOCK_GIT_BLOB,
    official_engine_sha256: str = OFFICIAL_ENGINE_SHA256,
    harness_sha256: str = HARNESS_SHA256,
):
    """Seal the one retained source-authority generation at module initialization."""
    read_status = status_path.read_bytes
    top_keys = frozenset(
        {
            "archive",
            "blocked_receipt_sha256",
            "candidate_build_authorized",
            "checked_surfaces",
            "date",
            "empirical_result",
            "execution_inputs_ready",
            "issue",
            "model",
            "next_step",
            "operation",
            "operator_host_archive_authentication",
            "promotion_authorized",
            "retained_source_bindings",
            "schema",
            "seat",
            "source_authority_verified",
            "state",
            "verifier_validation",
        }
    )
    archive_keys = frozenset({"bytes", "main_sha256", "member_count", "name", "sha256"})
    auth_keys = frozenset(
        {
            "archive_path",
            "execution_inputs_ready",
            "receipt_sha256",
            "safe_member_manifest_sha256",
            "source_authority_verified",
        }
    )
    binding_keys = frozenset(
        {
            "runtime_member",
            "runtime_git_blob",
            "operating_stock_git_blob",
            "official_engine_sha256",
            "harness_sha256",
        }
    )
    expected_bindings = {
        "runtime_member": runtime_member,
        "runtime_git_blob": runtime_git_blob,
        "operating_stock_git_blob": operating_stock_git_blob,
        "official_engine_sha256": official_engine_sha256,
        "harness_sha256": harness_sha256,
    }

    def validate_authenticated_status() -> dict[str, Any]:
        """Authenticate only the exact retained in-tree D2 status generation."""
        try:
            raw = read_status()
        except OSError as exc:
            raise WheatCensusError("cannot read retained D2 status generation") from exc
        require_fn(
            sha256_fn(raw).hexdigest() == expected_status_sha256,
            "retained D2 status generation digest mismatch",
        )
        status = parse_status(raw)
        require_fn(set(status) == top_keys, "retained status key set mismatch")
        require_fn(status.get("schema") == status_schema, "wrong status schema")
        require_fn(status.get("state") == authenticated_state, "D2 source is not authenticated")
        require_fn(status.get("source_authority_verified") is True, "root source authority must be true")
        require_fn(status.get("execution_inputs_ready") is True, "execution inputs are not ready")
        require_fn(status.get("candidate_build_authorized") is False, "status cannot authorize candidate")
        require_fn(status.get("promotion_authorized") is False, "status cannot authorize promotion")

        archive = status.get("archive")
        require_fn(type(archive) is dict and set(archive) == archive_keys, "archive status key set mismatch")
        require_fn(archive.get("sha256") == archive_sha256, "wrong archive sha256")
        require_fn(archive.get("bytes") == archive_bytes, "wrong archive byte count")
        require_fn(archive.get("member_count") == archive_members, "wrong archive member count")

        auth = status.get("operator_host_archive_authentication")
        require_fn(type(auth) is dict and set(auth) == auth_keys, "operator authentication key set mismatch")
        require_fn(auth.get("source_authority_verified") is True, "nested source authority must be true")
        require_fn(auth.get("execution_inputs_ready") is True, "nested execution inputs not ready")
        require_fn(auth.get("receipt_sha256") == auth_receipt_sha256, "wrong auth receipt")
        require_fn(auth.get("safe_member_manifest_sha256") == safe_manifest_sha256, "wrong safe manifest")

        bindings = status.get("retained_source_bindings")
        require_fn(type(bindings) is dict and set(bindings) == binding_keys, "retained binding key set mismatch")
        for key, expected_value in expected_bindings.items():
            require_fn(bindings.get(key) == expected_value, f"wrong retained binding: {key}")

        return {
            "state": authenticated_state,
            "status_generation_sha256": expected_status_sha256,
            "archive_sha256": archive_sha256,
            "authentication_receipt_sha256": auth_receipt_sha256,
            "safe_member_manifest_sha256": safe_manifest_sha256,
            "runtime_member": runtime_member,
            "runtime_git_blob": runtime_git_blob,
            "operating_stock_git_blob": operating_stock_git_blob,
            "official_engine_sha256": official_engine_sha256,
            "harness_sha256": harness_sha256,
        }

    return validate_authenticated_status


validate_authenticated_status = _build_status_validator()
del _build_status_validator, _sha256_source


def minimum_required_withheld(
    observed_shed_wheat: int,
    eod_wheat_credit: int,
    required_wheat: int,
    offered_wheat: int,
) -> int:
    """Minimum current SELL-WHEAT units that must be withheld."""
    stock = _whole(observed_shed_wheat, "observed_shed_wheat", maximum=MAX_SHED_CAPACITY)
    returned = _whole(eod_wheat_credit, "eod_wheat_credit", maximum=MAX_SHED_CAPACITY)
    required = _whole(required_wheat, "required_wheat", maximum=MAX_SHED_CAPACITY * 2)
    offered = _whole(offered_wheat, "offered_wheat", maximum=MAX_SHED_CAPACITY)
    _require(required <= stock + returned, "observed wheat cannot cover source-proven obligation")
    executable_offer = min(stock, offered)
    remaining_if_unchanged = stock - executable_offer + returned
    return min(executable_offer, max(0, required - remaining_if_unchanged))


def balance_permitted_sale(
    observed_shed_wheat: int,
    eod_wheat_credit: int,
    required_wheat: int,
) -> int:
    """Maximum current WHEAT sale allowed by the certified stock balance alone.

    This is a census comparator, not proof that upstream policy can or should
    select that sale after all other action constraints.
    """
    stock = _whole(observed_shed_wheat, "observed_shed_wheat", maximum=MAX_SHED_CAPACITY)
    returned = _whole(eod_wheat_credit, "eod_wheat_credit", maximum=MAX_SHED_CAPACITY)
    required = _whole(required_wheat, "required_wheat", maximum=MAX_SHED_CAPACITY * 2)
    _require(required <= stock + returned, "observed wheat cannot cover source-proven obligation")
    return min(stock, max(0, stock + returned - required))


def upstream_balance_offer_gap(
    observed_shed_wheat: int,
    eod_wheat_credit: int,
    required_wheat: int,
    offered_wheat: int,
) -> int:
    """Balance-permitted WHEAT not present in the selected upstream sale offer."""
    stock = _whole(observed_shed_wheat, "observed_shed_wheat", maximum=MAX_SHED_CAPACITY)
    offered = _whole(offered_wheat, "offered_wheat", maximum=MAX_SHED_CAPACITY)
    permitted = balance_permitted_sale(stock, eod_wheat_credit, required_wheat)
    return max(0, permitted - min(stock, offered))


def source_current_policy_withheld(
    observed_shed_wheat: int,
    eod_wheat_credit: int,
    required_wheat: int,
    offered_wheat: int,
) -> int:
    """Exact arithmetic from D2 `operating_stock.protect_feed_stock`."""
    stock = _whole(observed_shed_wheat, "observed_shed_wheat", maximum=MAX_SHED_CAPACITY)
    returned = _whole(eod_wheat_credit, "eod_wheat_credit", maximum=MAX_SHED_CAPACITY)
    required = _whole(required_wheat, "required_wheat", maximum=MAX_SHED_CAPACITY * 2)
    offered = _whole(offered_wheat, "offered_wheat", maximum=MAX_SHED_CAPACITY)
    _require(required <= stock + returned, "observed wheat cannot cover source-proven obligation")
    permitted = min(stock, max(0, stock + returned - required))
    withheld = max(0, min(stock, offered) - permitted)
    _require(withheld <= MAX_HELPER_WITHHOLD, "feed reservation exceeds source helper ceiling")
    return withheld


def analyze_certified_window(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one retained `protect_feed_stock` report and classify the seam."""
    _require(isinstance(packet, Mapping), "packet must be object")
    expected = {
        "observed_shed_wheat",
        "eod_wheat_credit",
        "required_wheat",
        "offered_wheat",
        "helper_report",
    }
    _require(set(packet) == expected, "packet key set mismatch")

    stock = _whole(packet["observed_shed_wheat"], "observed_shed_wheat", maximum=MAX_SHED_CAPACITY)
    returned = _whole(packet["eod_wheat_credit"], "eod_wheat_credit", maximum=MAX_SHED_CAPACITY)
    required = _whole(packet["required_wheat"], "required_wheat", maximum=MAX_SHED_CAPACITY * 2)
    offered = _whole(packet["offered_wheat"], "offered_wheat", maximum=MAX_SHED_CAPACITY)

    report = packet["helper_report"]
    _require(type(report) is dict, "helper_report must be object")
    if report.get("certified") is not True:
        return {
            "schema": SCHEMA,
            "state": UNCERTIFIED,
            "candidate_build_authorized": False,
            "promotion_authorized": False,
            "reason": str(report.get("reason", "uncertified current-policy window")),
        }

    current = source_current_policy_withheld(stock, returned, required, offered)
    minimum = minimum_required_withheld(stock, returned, required, offered)

    # Numeric equality alone would admit True as 1 and 0.0 as 0. Recorded
    # helper counts must obey the same exact-integer contract as input counts.
    for label, expected_value, maximum in (
        ("required_wheat", required, MAX_SHED_CAPACITY * 2),
        ("observed_shed_wheat", stock, MAX_SHED_CAPACITY),
        ("eod_wheat_credit", returned, MAX_SHED_CAPACITY),
        ("withheld_units", current, MAX_HELPER_WITHHOLD),
    ):
        recorded = _whole(report.get(label), f"helper {label}", maximum=maximum)
        _require(recorded == expected_value, f"helper {label} mismatch")
    _require(report.get("changed") is (current > 0), "helper changed flag mismatch")

    if current != minimum:
        return {
            "schema": SCHEMA,
            "state": CONTRADICTION,
            "candidate_build_authorized": False,
            "promotion_authorized": False,
            "current_policy_withheld": current,
            "min_provable_withheld": minimum,
            "reason": "retained current-policy equation diverges from independent minimum balance",
        }

    saleable = min(stock, offered)
    plus_one = min(saleable, minimum + 1)
    upstream_gap = upstream_balance_offer_gap(stock, returned, required, offered)
    return {
        "schema": SCHEMA,
        "state": NEGATIVE,
        "feed_item": "WHEAT",
        "mechanism": "selected_sell_wheat_reservation",
        "current_policy_withheld": current,
        "min_provable_withheld": minimum,
        "plus_one_withheld": plus_one,
        "discretionary_excess_units": 0,
        "cash_liberated_by_min_provable": 0,
        "cash_liberation_measurement": "ZERO_BY_EQUAL_WITHHOLDING_NO_PRICE_ASSUMPTION",
        "upstream_balance_permitted_sale": balance_permitted_sale(stock, returned, required),
        "upstream_selected_offer": min(stock, offered),
        "upstream_balance_offer_gap_units": upstream_gap,
        "upstream_offer_census_state": UPSTREAM_GATE,
        "candidate_build_authorized": False,
        "promotion_authorized": False,
        "falsifier": "current certified helper reservation equals MIN_PROVABLE",
    }


def _build_source_theorem_receipt(
    authority_validator=validate_authenticated_status,
    schema: str = SCHEMA,
    negative_state: str = NEGATIVE,
    upstream_gate: str = UPSTREAM_GATE,
):
    """Capture retained authority so later module rebinding cannot mint receipts."""

    def source_theorem_receipt() -> dict[str, Any]:
        """Return helper theorem plus the independent upstream empirical gate."""
        authority = authority_validator()
        return {
            "schema": schema,
            "state": negative_state,
            "authority": authority,
            "scope": "certified operating_stock.protect_feed_stock WHEAT SELL reservation only",
            "theorem": (
                "For every supported certified window, the source current-policy "
                "withholding equation equals the independent minimum balance needed "
                "to preserve required_wheat after the offered executable sale."
            ),
            "helper_seam_candidate": False,
            "candidate_build_authorized": False,
            "promotion_authorized": False,
            "empirical_result": None,
            "remaining_gate_state": upstream_gate,
            "upstream_offer_census_required": True,
            "candidate_hypothesis_paths": [
                "AUTHENTICATED_UPSTREAM_UNDER_OFFERING_WITH_HELPER_THEOREM_INTACT",
                "SEPARATELY_REVIEWED_SOURCE_RUNTIME_CONTRADICTION",
            ],
            "empirical_gate": (
                "No official-engine dev/holdout candidate is authorized by this source theorem. "
                "The next retained census must independently test whether authenticated D2 "
                "selected actions under-offer balance-permitted WHEAT while protect_feed_stock "
                "continues to equal MIN_PROVABLE. Such under-offering can keep the helper theorem "
                "intact and may justify a separately reviewed candidate hypothesis. A source/runtime "
                "contradiction is a distinct path and must first be reviewed as drift."
            ),
        }

    return source_theorem_receipt


source_theorem_receipt = _build_source_theorem_receipt()
del _build_source_theorem_receipt
