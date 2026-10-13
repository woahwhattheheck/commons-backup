#!/usr/bin/env python3
"""Deterministic, truth-bounded acceptance compiler for the Westfield workshare.

Metadata only: this does not train a donor model, consume donor PII, authenticate
live procurement sources, or create buyer/prime/payment/revenue authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class _SemanticRoot:
    """Detached compatibility mirror; never the authority object used by the API."""
    schema: str
    receipt_schema: str
    commercial_state: str
    commercial_role: str
    pricing_posture: str
    opportunity: tuple[tuple[str, str], ...]
    sources: tuple[tuple[str, str, str], ...]
    source_provenance_mode: str
    entity_key_policy: str
    time_anchor_policy: str
    deliverables: tuple[str, ...]
    exclusions: tuple[str, ...]
    handoff_artifacts: tuple[str, ...]
    metrics: tuple[tuple[str, str], ...]
    required_checks: frozenset[str]
    authority_keys: frozenset[str]


class ContractError(ValueError):
    pass


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate key: {key}")
        out[key] = value
    return out


def load_strict_json(text: str) -> dict[str, Any]:
    def bad_constant(value: str) -> None:
        raise ContractError(f"non-finite number: {value}")

    try:
        obj = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=bad_constant,
        )
    except ContractError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError("invalid JSON") from exc
    if not isinstance(obj, dict):
        raise ContractError("top-level JSON must be an object")
    return obj


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not canonical-JSON encodable") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _build_semantic_api():
    """Build one import-generation authority closure.

    The semantic root is a closure-local ordinary dict made only from immutable
    values.  It is deliberately never returned or stored in module data.  The
    `_SEALED_ROOT` exposed below is a distinct compatibility mirror.
    """
    root = {
        "schema": "advancement-model-acceptance/v2",
        "receipt_schema": "advancement-model-acceptance-receipt/v2",
        "commercial_state": "PROPOSED_NOT_ACCEPTED",
        "commercial_role": "paid_subcontract_workshare",
        "pricing_posture": "UNPRICED_SCOPE_NEGOTIATION_REQUIRED",
        "opportunity": (
            ("buyer", "Westfield State University"),
            ("solicitation", "RFP #2027-002 Advancement Data Modeling"),
            ("deadline", "2026-09-25"),
            ("submission_route", "Bonfire/Euna"),
        ),
        "sources": (
            (
                "buyer_official",
                "https://www.westfield.ma.edu/offices/open-general-bids",
                "Pinned public source identity only; compiler does not authenticate live availability.",
            ),
            (
                "partner_public",
                "https://khowconsulting.com/",
                "Pinned public profile identity only; not evidence of pursuit, partnership, or solicitation-specific qualification.",
            ),
        ),
        "source_provenance_mode": (
            "PINNED_PUBLIC_IDENTITIES_NOT_LIVE_PROVIDER_AUTHENTICATED"
        ),
        "entity_key_policy": "CONSTITUENT_HOUSEHOLD_GROUP_BEFORE_SPLIT_V1",
        "time_anchor_policy": "FEATURES_KNOWABLE_AT_CUTOFF_OUTCOMES_STRICTLY_AFTER_V1",
        "deliverables": (
            "source-to-feature provenance ledger",
            "entity and household duplicate-control report",
            "time-anchored training and holdout contract",
            "calibration and ranked-lift acceptance report",
            "reproducible model-card and handoff receipt",
        ),
        "exclusions": (
            "buyer portal submission",
            "prime responsibility",
            "reference ownership",
            "production-data custody",
            "campaign strategy representation",
        ),
        "handoff_artifacts": (
            "data dictionary/provenance map",
            "split manifest",
            "metric definitions",
            "model/config digest",
            "acceptance exception log",
        ),
        "metrics": (
            ("calibration", "brier_and_reliability"),
            ("ranking", "lift_at_k"),
            ("evaluation_split", "temporal_holdout"),
        ),
        "required_checks": frozenset(
            {
                "source_provenance",
                "entity_deduplication",
                "household_leakage",
                "temporal_leakage",
                "target_window",
                "calibration",
                "ranking_lift",
                "reproducible_handoff",
            }
        ),
        "authority_keys": frozenset(
            {
                "prime_vendor_confirmed",
                "buyer_approved",
                "references_verified",
                "production_data_access",
                "award_received",
                "payment_received",
                "revenue_recognized",
            }
        ),
    }

    # Capture every executable dependency consumed by the retained public API.
    _ContractError = ContractError
    _json_dumps = json.dumps
    _sha256 = hashlib.sha256

    def _canonical(value: Any) -> str:
        try:
            return _json_dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise _ContractError("value is not canonical-JSON encodable") from exc

    def _digest(value: Any) -> str:
        return _sha256(_canonical(value).encode("utf-8")).hexdigest()

    def _expect_keys(
        obj: dict[str, Any],
        *,
        required: set[str] | frozenset[str],
        optional: set[str] | frozenset[str] | None = None,
        where: str,
    ) -> None:
        optional = optional or frozenset()
        missing = required - obj.keys()
        extra = obj.keys() - required - optional
        if missing:
            raise _ContractError(f"{where}: missing keys {sorted(missing)}")
        if extra:
            raise _ContractError(f"{where}: unexpected keys {sorted(extra)}")

    def _expect_bool(value: Any, where: str) -> bool:
        if type(value) is not bool:
            raise _ContractError(f"{where}: must be boolean")
        return value

    def _expect_str(value: Any, where: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise _ContractError(f"{where}: must be non-empty string")
        if value != value.strip():
            raise _ContractError(f"{where}: surrounding whitespace is not admitted")
        return value

    def _expect_str_list(value: Any, where: str) -> list[str]:
        if not isinstance(value, list) or not value:
            raise _ContractError(f"{where}: must be non-empty array")
        out: list[str] = []
        for i, item in enumerate(value):
            item = _expect_str(item, f"{where}[{i}]")
            if item in out:
                raise _ContractError(f"{where}: duplicate value {item!r}")
            out.append(item)
        return out

    def _expect_exact_str_list(
        value: Any,
        expected: tuple[str, ...],
        where: str,
    ) -> list[str]:
        if not isinstance(value, list) or len(value) != len(expected):
            raise _ContractError(
                f"{where}: must equal the code-owned Westfield values in canonical order"
            )
        out = _expect_str_list(value, where)
        if tuple(out) != expected:
            raise _ContractError(
                f"{where}: must equal the code-owned Westfield values in canonical order"
            )
        return list(expected)

    def _validate_authority(authority: dict[str, Any]) -> None:
        keys = root["authority_keys"]
        _expect_keys(authority, required=keys, where="authority")
        for key in sorted(authority):
            if _expect_bool(authority[key], f"authority.{key}"):
                raise _ContractError(
                    f"authority.{key}: must remain false in this pre-award carrier"
                )

    def _validate_opportunity(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise _ContractError("opportunity: must be object")
        expected = dict(root["opportunity"])
        _expect_keys(value, required=frozenset(expected), where="opportunity")
        normalized = {
            key: _expect_str(value[key], f"opportunity.{key}")
            for key in expected
        }
        for key, expected_value in expected.items():
            if normalized[key] != expected_value:
                raise _ContractError(
                    f"opportunity.{key}: must equal the code-owned Westfield value"
                )
        return expected

    def _validate_sources(value: Any) -> list[dict[str, str]]:
        expected = {kind: (url, note) for kind, url, note in root["sources"]}
        if not isinstance(value, list) or len(value) != len(expected):
            raise _ContractError(
                f"sources: exactly {len(expected)} admitted source rows required"
            )
        by_kind: dict[str, dict[str, str]] = {}
        for i, row in enumerate(value):
            if not isinstance(row, dict):
                raise _ContractError(f"sources[{i}]: must be object")
            _expect_keys(
                row,
                required={"kind", "url", "note"},
                where=f"sources[{i}]",
            )
            kind = _expect_str(row["kind"], f"sources[{i}].kind")
            url = _expect_str(row["url"], f"sources[{i}].url")
            note = _expect_str(row["note"], f"sources[{i}].note")
            if kind in by_kind:
                raise _ContractError(f"sources[{i}].kind: duplicate {kind!r}")
            if kind not in expected:
                raise _ContractError(f"sources[{i}].kind: unadmitted source role")
            expected_url, expected_note = expected[kind]
            if url != expected_url:
                raise _ContractError(
                    f"sources[{i}].url: does not match code-owned {kind!r} source"
                )
            if note != expected_note:
                raise _ContractError(
                    f"sources[{i}].note: must equal the code-owned {kind!r} boundary note"
                )
            by_kind[kind] = {"kind": kind, "url": url, "note": note}
        if set(by_kind) != set(expected):
            raise _ContractError("sources: all code-owned source roles are required")
        return [by_kind[kind] for kind in sorted(by_kind)]

    def _validate_metrics(metrics: dict[str, Any]) -> dict[str, str]:
        expected = dict(root["metrics"])
        _expect_keys(
            metrics,
            required=frozenset(expected),
            where="model_acceptance.metrics",
        )
        normalized = {
            key: _expect_str(metrics[key], f"model_acceptance.metrics.{key}")
            for key in expected
        }
        for key, expected_value in expected.items():
            if normalized[key] != expected_value:
                raise _ContractError(
                    f"model_acceptance.metrics.{key}: "
                    "must equal the code-owned Westfield value"
                )
        return expected

    def compile_acceptance(manifest: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, dict):
            raise _ContractError("manifest: must be object")
        _expect_keys(
            manifest,
            required={
                "schema",
                "opportunity",
                "commercial",
                "sources",
                "authority",
                "workshare",
                "model_acceptance",
            },
            where="manifest",
        )
        if manifest["schema"] != root["schema"]:
            raise _ContractError(f"schema: expected {root['schema']!r}")

        opportunity = _validate_opportunity(manifest["opportunity"])

        commercial = manifest["commercial"]
        if not isinstance(commercial, dict):
            raise _ContractError("commercial: must be object")
        _expect_keys(
            commercial,
            required={"role", "state", "pricing_posture"},
            where="commercial",
        )
        if commercial["role"] != root["commercial_role"]:
            raise _ContractError(
                f"commercial.role: {root['commercial_role']} required"
            )
        if commercial["state"] != root["commercial_state"]:
            raise _ContractError(
                "commercial.state: this pre-award carrier is pinned to "
                "PROPOSED_NOT_ACCEPTED"
            )
        if commercial["pricing_posture"] != root["pricing_posture"]:
            raise _ContractError(
                "commercial.pricing_posture: unpriced scope-negotiation sentinel required"
            )

        sources = _validate_sources(manifest["sources"])

        authority = manifest["authority"]
        if not isinstance(authority, dict):
            raise _ContractError("authority: must be object")
        _validate_authority(authority)

        workshare = manifest["workshare"]
        if not isinstance(workshare, dict):
            raise _ContractError("workshare: must be object")
        _expect_keys(
            workshare,
            required={"deliverables", "exclusions"},
            where="workshare",
        )
        deliverables = _expect_exact_str_list(
            workshare["deliverables"],
            root["deliverables"],
            "workshare.deliverables",
        )
        exclusions = _expect_exact_str_list(
            workshare["exclusions"],
            root["exclusions"],
            "workshare.exclusions",
        )

        model_acceptance = manifest["model_acceptance"]
        if not isinstance(model_acceptance, dict):
            raise _ContractError("model_acceptance: must be object")
        _expect_keys(
            model_acceptance,
            required={
                "entity_key_policy",
                "time_anchor_policy",
                "required_checks",
                "metrics",
                "handoff_artifacts",
            },
            where="model_acceptance",
        )
        if model_acceptance["entity_key_policy"] != root["entity_key_policy"]:
            raise _ContractError(
                "model_acceptance.entity_key_policy: expected "
                f"{root['entity_key_policy']}"
            )
        if model_acceptance["time_anchor_policy"] != root["time_anchor_policy"]:
            raise _ContractError(
                "model_acceptance.time_anchor_policy: expected "
                f"{root['time_anchor_policy']}"
            )

        checks = set(
            _expect_str_list(
                model_acceptance["required_checks"],
                "model_acceptance.required_checks",
            )
        )
        if checks != root["required_checks"]:
            raise _ContractError(
                "model_acceptance.required_checks: must equal the closed required set"
            )

        metrics = model_acceptance["metrics"]
        if not isinstance(metrics, dict):
            raise _ContractError("model_acceptance.metrics: must be object")
        normalized_metrics = _validate_metrics(metrics)
        handoff = _expect_exact_str_list(
            model_acceptance["handoff_artifacts"],
            root["handoff_artifacts"],
            "model_acceptance.handoff_artifacts",
        )

        return {
            "schema": root["schema"],
            "opportunity": opportunity,
            "commercial": {
                "role": root["commercial_role"],
                "state": root["commercial_state"],
                "pricing_posture": root["pricing_posture"],
            },
            "sources": sources,
            "source_provenance": {
                "mode": root["source_provenance_mode"],
                "live_provider_authenticated": False,
            },
            "authority": {key: False for key in sorted(root["authority_keys"])},
            "acceptance_plan": {
                "entity_key_policy": root["entity_key_policy"],
                "time_anchor_policy": root["time_anchor_policy"],
                "required_checks": sorted(root["required_checks"]),
                "metrics": normalized_metrics,
                "deliverables": deliverables,
                "handoff_artifacts": handoff,
                "exclusions": exclusions,
            },
        }

    def make_receipt(manifest: dict[str, Any]) -> dict[str, Any]:
        plan = compile_acceptance(manifest)
        return {
            "schema": root["receipt_schema"],
            "manifest_sha256": _digest(manifest),
            "plan_sha256": _digest(plan),
            "truth": {
                "commercial_state": root["commercial_state"],
                "source_provenance_mode": root["source_provenance_mode"],
                "live_provider_authenticated": False,
                "submission_authorized": False,
                "award_received": False,
                "payment_received": False,
                "revenue_recognized": False,
            },
        }

    def verify_receipt(
        manifest: dict[str, Any],
        receipt: dict[str, Any],
    ) -> bool:
        try:
            return _canonical(receipt) == _canonical(make_receipt(manifest))
        except (_ContractError, TypeError, ValueError):
            return False

    # Return only a detached compatibility mirror plus the public closure API.
    # No module object receives a reference to `root`.
    mirror = _SemanticRoot(
        schema=root["schema"],
        receipt_schema=root["receipt_schema"],
        commercial_state=root["commercial_state"],
        commercial_role=root["commercial_role"],
        pricing_posture=root["pricing_posture"],
        opportunity=tuple(root["opportunity"]),
        sources=tuple(root["sources"]),
        source_provenance_mode=root["source_provenance_mode"],
        entity_key_policy=root["entity_key_policy"],
        time_anchor_policy=root["time_anchor_policy"],
        deliverables=tuple(root["deliverables"]),
        exclusions=tuple(root["exclusions"]),
        handoff_artifacts=tuple(root["handoff_artifacts"]),
        metrics=tuple(root["metrics"]),
        required_checks=frozenset(root["required_checks"]),
        authority_keys=frozenset(root["authority_keys"]),
    )
    return mirror, compile_acceptance, make_receipt, verify_receipt


(
    _SEALED_ROOT,
    compile_acceptance,
    make_receipt,
    verify_receipt,
) = _build_semantic_api()

# Compatibility/introspection mirrors. Deliberately not an authority source.
SCHEMA = _SEALED_ROOT.schema
RECEIPT_SCHEMA = _SEALED_ROOT.receipt_schema
COMMERCIAL_STATE = _SEALED_ROOT.commercial_state
COMMERCIAL_ROLE = _SEALED_ROOT.commercial_role
PRICING_POSTURE = _SEALED_ROOT.pricing_posture
EXPECTED_OPPORTUNITY = dict(_SEALED_ROOT.opportunity)
EXPECTED_SOURCE_URLS = {kind: url for kind, url, _ in _SEALED_ROOT.sources}
EXPECTED_SOURCE_NOTES = {kind: note for kind, _, note in _SEALED_ROOT.sources}
SOURCE_PROVENANCE_MODE = _SEALED_ROOT.source_provenance_mode
ENTITY_KEY_POLICY = _SEALED_ROOT.entity_key_policy
TIME_ANCHOR_POLICY = _SEALED_ROOT.time_anchor_policy
EXPECTED_DELIVERABLES = _SEALED_ROOT.deliverables
EXPECTED_EXCLUSIONS = _SEALED_ROOT.exclusions
EXPECTED_HANDOFF_ARTIFACTS = _SEALED_ROOT.handoff_artifacts
EXPECTED_METRICS = dict(_SEALED_ROOT.metrics)
REQUIRED_CHECKS = _SEALED_ROOT.required_checks
AUTHORITY_KEYS = _SEALED_ROOT.authority_keys


def main() -> int:
    import argparse
    import pathlib

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--receipt")
    args = parser.parse_args()

    manifest = load_strict_json(
        pathlib.Path(args.manifest).read_text(encoding="utf-8")
    )
    plan = compile_acceptance(manifest)
    receipt = make_receipt(manifest)
    print(canonical_json({"plan": plan, "receipt": receipt}))
    if args.receipt:
        pathlib.Path(args.receipt).write_text(
            canonical_json(receipt) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
