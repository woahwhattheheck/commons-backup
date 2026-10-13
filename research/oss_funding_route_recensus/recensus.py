#!/usr/bin/env python3
"""Deterministic offline recensus compiler for retained OSS funding routes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRIOR_SCHEMA = "oss-sponsor-route-map/v1"
PRIOR_OPERATION = "OSS-SPONSOR-ROUTE-EVIDENCE-MAP-20260916"
OBS_SCHEMA = "oss-funding-route-observation-set/v1"
REPORT_SCHEMA = "oss-funding-route-recensus-report/v1"
OPERATION = "OSS-FUNDING-ROUTE-FRESHNESS-RECENSUS-20260916-ZSOL17"
ADAPTER_AUTHORITY = "TRUSTED_EVIDENCE_ADAPTER"
MAX_AGE_SECONDS = 72 * 60 * 60
MAX_BYTES = 2_000_000
OPEN_STATES = {"OPEN", "ROLLING", "ACTIVE_MECHANISM"}
OBS_STATES = OPEN_STATES | {"CLOSED"}
OUTCOMES = {"SAME_OPEN", "CHANGED_REVIEW", "CLOSED", "STALE", "CONFLICT"}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class RecensusError(ValueError):
    pass


def _strict_json_bytes(raw: bytes, label: str) -> Any:
    if len(raw) > MAX_BYTES:
        raise RecensusError(f"{label}: exceeds {MAX_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecensusError(f"{label}: must be UTF-8") from exc

    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise RecensusError(f"{label}: duplicate JSON key {key!r}")
            out[key] = value
        return out

    try:
        return json.loads(
            text,
            object_pairs_hook=hook,
            parse_constant=lambda token: (_ for _ in ()).throw(
                RecensusError(f"{label}: non-finite JSON constant {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RecensusError(f"{label}: invalid JSON: {exc}") from exc


def _read(path: str | Path, label: str) -> tuple[bytes, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise RecensusError(f"{label}: read failed: {exc}") from exc
    return raw, _strict_json_bytes(raw, label)


def _obj(value: Any, required: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RecensusError(f"{where}: must be object")
    missing = required - set(value)
    extra = set(value) - required
    if missing:
        raise RecensusError(f"{where}: missing fields {sorted(missing)}")
    if extra:
        raise RecensusError(f"{where}: unsupported fields {sorted(extra)}")
    return value


def _text(value: Any, where: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RecensusError(f"{where}: must be trimmed non-empty string")
    return value


def _sha(value: Any, where: str) -> str:
    text = _text(value, where)
    if SHA_RE.fullmatch(text) is None:
        raise RecensusError(f"{where}: must be lowercase sha256 hex")
    return text


def _utc(value: Any, where: str) -> datetime:
    text = _text(value, where)
    if UTC_RE.fullmatch(text) is None:
        raise RecensusError(f"{where}: must be exact UTC seconds")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise RecensusError(f"{where}: invalid timestamp") from exc


def _canon(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return (text + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RecensusError(f"canonical JSON failure: {exc}") from exc


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_digest(value: Any) -> str:
    return _digest(_canon(value))


def _source_record_digest(source: dict[str, Any]) -> str:
    kept = {
        "id": source["id"],
        "url": source["url"],
        "authority": source["authority"],
        "observed_at_utc": source["observed_at_utc"],
        "currentness_fact": source["currentness_fact"],
    }
    return _canonical_digest(kept)


def _validate_prior(data: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    root = _obj(
        data,
        {
            "schema", "operation", "generated_at_utc", "as_of_date",
            "authority_profiles", "fence_profiles", "reward_state_definitions",
            "action_profiles", "gate_profiles", "proof_catalog",
            "sources", "opportunities", "summary",
        },
        "prior",
    )
    if root["schema"] != PRIOR_SCHEMA or root["operation"] != PRIOR_OPERATION:
        raise RecensusError("prior: wrong schema/operation")
    _utc(root["generated_at_utc"], "prior.generated_at_utc")
    if type(root["sources"]) is not list or type(root["opportunities"]) is not list:
        raise RecensusError("prior: sources/opportunities must be arrays")

    sources: dict[str, dict[str, Any]] = {}
    for i, value in enumerate(root["sources"]):
        src = _obj(
            value,
            {"id", "url", "authority", "observed_at_utc", "currentness_fact"},
            f"prior.sources[{i}]",
        )
        sid = _text(src["id"], f"prior.sources[{i}].id")
        if sid in sources:
            raise RecensusError(f"prior: duplicate source {sid}")
        if not _text(src["url"], f"prior source {sid}.url").startswith("https://"):
            raise RecensusError(f"prior source {sid}: https URL required")
        _utc(src["observed_at_utc"], f"prior source {sid}.observed_at_utc")
        _text(src["currentness_fact"], f"prior source {sid}.currentness_fact")
        sources[sid] = src

    opportunities: dict[str, dict[str, Any]] = {}
    for i, value in enumerate(root["opportunities"]):
        if type(value) is not dict:
            raise RecensusError(f"prior.opportunities[{i}]: must be object")
        needed = {
            "id", "name", "source", "route", "reward", "current", "priority",
            "fit", "action", "gate", "econ", "proof", "fence", "authority",
        }
        if set(value) != needed:
            raise RecensusError(f"prior.opportunities[{i}]: schema drift")
        oid = _text(value["id"], f"prior.opportunities[{i}].id")
        if oid in opportunities:
            raise RecensusError(f"prior: duplicate opportunity {oid}")
        if value["source"] not in sources:
            raise RecensusError(f"prior opportunity {oid}: unknown source")
        if value["current"] not in OPEN_STATES:
            raise RecensusError(f"prior opportunity {oid}: unexpected current state")
        econ = value["econ"]
        if type(econ) is not dict or set(econ) != {"cash_kind", "advertised_value"}:
            raise RecensusError(f"prior opportunity {oid}: malformed econ")
        opportunities[oid] = value

    if not opportunities:
        raise RecensusError("prior: no opportunities")
    return root, sources, opportunities


def _validate_observations(
    data: Any,
    prior_raw: bytes,
    prior: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    opportunities: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], datetime]:
    root = _obj(
        data,
        {"schema", "operation", "generated_at_utc", "adapter", "prior_generation", "observations"},
        "observations",
    )
    if root["schema"] != OBS_SCHEMA or root["operation"] != OPERATION:
        raise RecensusError("observations: wrong schema/operation")
    generated = _utc(root["generated_at_utc"], "observations.generated_at_utc")
    prior_generated = _utc(prior["generated_at_utc"], "prior.generated_at_utc")
    if generated < prior_generated:
        raise RecensusError("observations: generated before prior snapshot")

    adapter = _obj(root["adapter"], {"id", "generation", "authority"}, "observations.adapter")
    _text(adapter["id"], "observations.adapter.id")
    _text(adapter["generation"], "observations.adapter.generation")
    if adapter["authority"] != ADAPTER_AUTHORITY:
        raise RecensusError("observations.adapter.authority must be TRUSTED_EVIDENCE_ADAPTER")

    binding = _obj(
        root["prior_generation"],
        {"operation", "generated_at_utc", "map_sha256"},
        "observations.prior_generation",
    )
    if binding["operation"] != PRIOR_OPERATION:
        raise RecensusError("observations: prior operation mismatch")
    if binding["generated_at_utc"] != prior["generated_at_utc"]:
        raise RecensusError("observations: prior generation mismatch")
    if _sha(binding["map_sha256"], "observations.prior_generation.map_sha256") != _digest(prior_raw):
        raise RecensusError("observations: prior map digest mismatch")

    values = root["observations"]
    if type(values) is not list:
        raise RecensusError("observations.observations must be array")
    by_id: dict[str, dict[str, Any]] = {}
    alias_owner: dict[str, str] = {}
    for i, value in enumerate(values):
        obs = _obj(
            value,
            {
                "opportunity_id", "source_id", "source_url", "source_sha256",
                "observed_at_utc", "current", "currentness_fact", "econ",
                "aliases", "conflicts",
            },
            f"observations[{i}]",
        )
        oid = _text(obs["opportunity_id"], f"observations[{i}].opportunity_id")
        if oid not in opportunities:
            raise RecensusError(f"observations: unknown opportunity {oid}")
        if oid in by_id:
            raise RecensusError(f"observations: duplicate opportunity {oid}")
        prior_opp = opportunities[oid]
        sid = _text(obs["source_id"], f"{oid}.source_id")
        if sid != prior_opp["source"]:
            raise RecensusError(f"{oid}: source substitution")
        prior_source = sources[sid]
        if obs["source_url"] != prior_source["url"]:
            raise RecensusError(f"{oid}: source URL substitution")
        _sha(obs["source_sha256"], f"{oid}.source_sha256")
        observed = _utc(obs["observed_at_utc"], f"{oid}.observed_at_utc")
        if observed > generated:
            raise RecensusError(f"{oid}: future observation")
        if obs["current"] not in OBS_STATES:
            raise RecensusError(f"{oid}: invalid current state")
        _text(obs["currentness_fact"], f"{oid}.currentness_fact")

        econ = _obj(obs["econ"], {"cash_kind", "advertised_value"}, f"{oid}.econ")
        _text(econ["cash_kind"], f"{oid}.econ.cash_kind")
        if econ["advertised_value"] is not None:
            _text(econ["advertised_value"], f"{oid}.econ.advertised_value")

        aliases = obs["aliases"]
        if type(aliases) is not list:
            raise RecensusError(f"{oid}.aliases: must be array")
        seen_local = set()
        for j, alias in enumerate(aliases):
            alias = _text(alias, f"{oid}.aliases[{j}]")
            if alias == oid:
                raise RecensusError(f"{oid}: canonical id may not be repeated as alias")
            if alias in seen_local:
                raise RecensusError(f"{oid}: duplicate alias {alias}")
            seen_local.add(alias)
            owner = alias_owner.setdefault(alias, oid)
            if owner != oid or alias in opportunities:
                raise RecensusError(f"{oid}: ambiguous alias {alias}")

        conflicts = obs["conflicts"]
        if type(conflicts) is not list:
            raise RecensusError(f"{oid}.conflicts: must be array")
        for j, item in enumerate(conflicts):
            _text(item, f"{oid}.conflicts[{j}]")
        by_id[oid] = obs

    missing = sorted(set(opportunities) - set(by_id))
    extra = sorted(set(by_id) - set(opportunities))
    if missing or extra:
        raise RecensusError(f"observations: coverage mismatch missing={missing} extra={extra}")
    return root, by_id, generated


def _changed_fields(prior_opp: dict[str, Any], prior_source: dict[str, Any], obs: dict[str, Any]) -> list[str]:
    changed = []
    if obs["current"] != prior_opp["current"]:
        changed.append("current")
    if obs["currentness_fact"] != prior_source["currentness_fact"]:
        changed.append("source.currentness_fact")
    if obs["econ"]["cash_kind"] != prior_opp["econ"]["cash_kind"]:
        changed.append("econ.cash_kind")
    if obs["econ"]["advertised_value"] != prior_opp["econ"]["advertised_value"]:
        changed.append("econ.advertised_value")
    return changed


def _classify(
    prior_opp: dict[str, Any],
    prior_source: dict[str, Any],
    obs: dict[str, Any],
    generated: datetime,
) -> tuple[str, list[str], list[str]]:
    changed = _changed_fields(prior_opp, prior_source, obs)
    observed = _utc(obs["observed_at_utc"], f"{prior_opp['id']}.observed_at_utc")
    age_seconds = int((generated - observed).total_seconds())
    if obs["conflicts"]:
        return "CONFLICT", changed, ["CONFLICTING_TRUSTED_OBSERVATIONS"]
    if age_seconds > MAX_AGE_SECONDS:
        return "STALE", changed, ["OBSERVATION_EXCEEDS_72H_FRESHNESS"]
    if obs["current"] == "CLOSED":
        return "CLOSED", changed, ["SOURCE_REPORTS_ROUTE_CLOSED"]
    if changed:
        reasons = ["SOURCE_OR_ECONOMIC_FIELDS_CHANGED"]
        if any(field.startswith("econ.") for field in changed):
            reasons.append("ECONOMIC_REVIEW_REQUIRED")
        return "CHANGED_REVIEW", changed, reasons
    return "SAME_OPEN", [], []


def compile_report(prior_raw: bytes, prior_data: Any, obs_raw: bytes, obs_data: Any) -> dict[str, Any]:
    prior, sources, opportunities = _validate_prior(prior_data)
    obs_root, observations, generated = _validate_observations(
        obs_data, prior_raw, prior, sources, opportunities
    )
    rows = []
    counts = {key: 0 for key in sorted(OUTCOMES)}
    for oid in sorted(opportunities):
        prior_opp = opportunities[oid]
        prior_source = sources[prior_opp["source"]]
        obs = observations[oid]
        outcome, changed, reasons = _classify(prior_opp, prior_source, obs, generated)
        counts[outcome] += 1
        rows.append(
            {
                "opportunity_id": oid,
                "source_id": prior_opp["source"],
                "source_url": prior_source["url"],
                "previous_source_record_sha256": _source_record_digest(prior_source),
                "new_source_sha256": obs["source_sha256"],
                "previous_observed_at_utc": prior_source["observed_at_utc"],
                "new_observed_at_utc": obs["observed_at_utc"],
                "outcome": outcome,
                "changed_fields": changed,
                "downstream_block_reasons": reasons,
            }
        )

    report = {
        "schema": REPORT_SCHEMA,
        "operation": OPERATION,
        "generated_at_utc": obs_root["generated_at_utc"],
        "authority": {
            "external_action_authorized": False,
            "submission_authorized": False,
            "provider_mutation_authorized": False,
            "payment_or_revenue_claimed": False,
        },
        "binding": {
            "prior_operation": prior["operation"],
            "prior_generated_at_utc": prior["generated_at_utc"],
            "prior_map_sha256": _digest(prior_raw),
            "observation_set_sha256": _digest(obs_raw),
            "adapter_id": obs_root["adapter"]["id"],
            "adapter_generation": obs_root["adapter"]["generation"],
        },
        "routes": rows,
        "summary": {
            "route_count": len(rows),
            "outcome_counts": counts,
            "all_downstream_clear": all(row["outcome"] == "SAME_OPEN" for row in rows),
        },
    }
    return report


def verify_report(prior_path: str | Path, observation_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    prior_raw, prior_data = _read(prior_path, "prior")
    obs_raw, obs_data = _read(observation_path, "observations")
    report_raw, report_data = _read(report_path, "report")
    expected = compile_report(prior_raw, prior_data, obs_raw, obs_data)
    if report_raw != _canon(expected):
        raise RecensusError("report bytes do not match exact recomputation")
    return expected


def _write_exclusive(path: str | Path, raw: bytes) -> None:
    target = Path(path)
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise RecensusError(f"output parent does not exist: {parent}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(target), flags, 0o600)
    except OSError as exc:
        raise RecensusError(f"exclusive output create failed: {exc}") from exc
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def make_reference_observations(prior_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    prior_raw, prior_data = _read(prior_path, "prior")
    prior, sources, opportunities = _validate_prior(prior_data)
    generated = prior["generated_at_utc"]
    observations = []
    for oid in sorted(opportunities):
        opp = opportunities[oid]
        src = sources[opp["source"]]
        observations.append(
            {
                "opportunity_id": oid,
                "source_id": src["id"],
                "source_url": src["url"],
                "source_sha256": _source_record_digest(src),
                "observed_at_utc": generated,
                "current": opp["current"],
                "currentness_fact": src["currentness_fact"],
                "econ": {
                    "cash_kind": opp["econ"]["cash_kind"],
                    "advertised_value": opp["econ"]["advertised_value"],
                },
                "aliases": [],
                "conflicts": [],
            }
        )
    data = {
        "schema": OBS_SCHEMA,
        "operation": OPERATION,
        "generated_at_utc": generated,
        "adapter": {
            "id": "synthetic-reference-adapter",
            "generation": "reference-v1",
            "authority": ADAPTER_AUTHORITY,
        },
        "prior_generation": {
            "operation": prior["operation"],
            "generated_at_utc": prior["generated_at_utc"],
            "map_sha256": _digest(prior_raw),
        },
        "observations": observations,
    }
    _write_exclusive(output_path, _canon(data))
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--prior", required=True)
    compile_p.add_argument("--observations", required=True)
    compile_p.add_argument("--output", required=True)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--prior", required=True)
    verify_p.add_argument("--observations", required=True)
    verify_p.add_argument("--report", required=True)

    ref_p = sub.add_parser("make-reference-observations")
    ref_p.add_argument("--prior", required=True)
    ref_p.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            prior_raw, prior_data = _read(args.prior, "prior")
            obs_raw, obs_data = _read(args.observations, "observations")
            report = compile_report(prior_raw, prior_data, obs_raw, obs_data)
            _write_exclusive(args.output, _canon(report))
            print(f"WROTE {args.output} routes={report['summary']['route_count']} counts={report['summary']['outcome_counts']}")
        elif args.command == "verify":
            report = verify_report(args.prior, args.observations, args.report)
            print(f"VERIFIED routes={report['summary']['route_count']} counts={report['summary']['outcome_counts']}")
        else:
            data = make_reference_observations(args.prior, args.output)
            print(f"WROTE {args.output} observations={len(data['observations'])}")
    except (OSError, RecensusError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
