#!/usr/bin/env python3
"""Build a source-authenticated opponent registry for the existing TITAN V4 gauntlet.

This tool is wiring only. It does not run games, schedule a panel, score a
candidate, or authorize promotion. It binds already-owned opponent sources into
one deterministic registry and emits a strict SPECTRUM-compatible identity
panel.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Callable

REGISTRY_SCHEMA = "titan.gauntlet.opponent-registry.v1"
PANEL_SCHEMA = "titan.gauntlet.panel.v1"
REF_REGISTRY_SCHEMA = "titan.v4.reference-registry.v1"
ORCHARD_SCHEMA = "titan.gauntlet.opponent_family.v1"
REFORGE_SCHEMA = "titan.v4.reforge.public-bank.v1"

DEFAULT_PINS = {
    "reference_manifest": "6bce02dad705ccc57656ff2e2139db215f9fcc57",
    "reforge_validation": "9ce7ced6885394f1e77d5891db924e541a5b9c14",
    "reforge_generator": "71c847e119635fd917ac106e3331cd1b2f41de53",
    "orchard_manifest": "be46d9d733dbfff456c1228bb134be098ddee1b6",
    "market_pressure": "3648c39b2d5efcd4c82af8fbfac178563a5f1960",
    "spectrum_validator": "68bac86adf100e3e1941a71a2185c50ae059591a",
}

REFERENCE_REL = Path("research/reference-policy-bank/REFERENCE-POLICIES.json")
REFORGE_VALIDATION_REL = Path("research/reference-policy-bank/REFORGE-RECOVERY-VALIDATION.json")
REFORGE_GENERATOR_REL = Path("research/reference-policy-bank/prepare_public_bank.py")
ORCHARD_REL = Path("research/opponent-challengers/OPPONENTS.json")
PRESSURE_REL = Path("research/market-pressure/market_pressure.py")
SPECTRUM_REL = Path("research/gauntlet-panel-diversity/panel_diversity.py")


class RegistryError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def git_blob_file(path: Path) -> str:
    return git_blob_bytes(path.read_bytes())


def _reject_constant(value: str) -> None:
    raise RegistryError(f"non-finite JSON number: {value}")


def _object_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RegistryError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_no_dupes,
            parse_constant=_reject_constant,
        )
    except RegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RegistryError(f"cannot parse {path}: {exc}") from exc


def _safe_rel(value: str, where: str) -> PurePosixPath:
    if type(value) is not str or not value or value.startswith("./") or "//" in value:
        raise RegistryError(f"{where} must be a canonical relative path")
    rel = PurePosixPath(value)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise RegistryError(f"{where} escapes its authority root: {value!r}")
    return rel


def _safe_file(root: Path, rel: str, where: str) -> Path:
    relative = _safe_rel(rel, where)
    root = root.resolve(strict=True)
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(candidate) from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise RegistryError(f"{where} is not a regular non-symlink file: {rel}")
    return resolved


def _verify_blob(path: Path, expected: str, where: str) -> None:
    actual = git_blob_file(path)
    if actual != expected:
        raise RegistryError(f"{where} Git blob drift: expected {expected}, got {actual}")


def _as_dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RegistryError(f"{where} must be an object")
    return value


def _as_text(value: Any, where: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise RegistryError(f"{where} must be a non-empty exact string")
    return value


def _as_sha256(value: Any, where: str) -> str:
    value = _as_text(value, where)
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise RegistryError(f"{where} must be lowercase SHA-256")
    return value


def _entry(
    *,
    identity: str,
    source: str,
    status: str,
    kind: str | None = None,
    family: str | None = None,
    source_id: str | None = None,
    entry: str | None = None,
    entry_sha256: str | None = None,
    blocker: str | None = None,
    intended_kind: str | None = None,
    intended_family: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": identity, "source": source, "status": status}
    for key, value in (
        ("kind", kind), ("family", family), ("source_id", source_id),
        ("entry", entry), ("entry_sha256", entry_sha256), ("blocker", blocker),
        ("intended_kind", intended_kind), ("intended_family", intended_family),
    ):
        if value is not None:
            row[key] = value
    if metadata:
        row["metadata"] = metadata
    return row


def _panel_row(row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] == "resolved":
        return {
            "id": row["id"],
            "kind": row["kind"],
            "family": row["family"],
            "source_id": row["source_id"],
            "status": "resolved",
        }
    note = row.get("blocker", "source unavailable")
    return {
        "id": row["id"],
        "kind": "unknown",
        "family": None,
        "source_id": None,
        "status": "unresolved",
        "note": note,
    }


def _reference_entries(v4_root: Path) -> list[dict[str, Any]]:
    manifest_path = v4_root / REFERENCE_REL
    raw = _as_dict(load_json(manifest_path), "reference registry")
    if raw.get("schema") != REF_REGISTRY_SCHEMA:
        raise RegistryError("reference registry schema changed")
    policies = _as_dict(raw.get("policies"), "reference registry policies")
    kg_root = v4_root.parents[2].resolve(strict=True)
    out: list[dict[str, Any]] = []
    for policy_id in sorted(policies):
        policy = _as_dict(policies[policy_id], f"policy {policy_id}")
        root_rel = _as_text(policy.get("root"), f"policy {policy_id}.root")
        entry_rel = _as_text(policy.get("entry"), f"policy {policy_id}.entry")
        files = _as_dict(policy.get("files"), f"policy {policy_id}.files")
        expected_entry = _as_sha256(files.get(entry_rel), f"policy {policy_id} entry hash")
        intended_family = f"reference:{policy_id}"
        identity = f"reference-{policy_id.replace('_', '-')}"
        custody = str(policy.get("custody_at_receipt", ""))
        missing: list[str] = []
        policy_root = kg_root.joinpath(*_safe_rel(root_rel, f"policy {policy_id}.root").parts)
        try:
            policy_root.resolve(strict=True).relative_to(kg_root)
        except (OSError, ValueError):
            missing.append(f"root:{root_rel}")
        for rel, expected_raw in sorted(files.items()):
            expected = _as_sha256(expected_raw, f"policy {policy_id}.files[{rel}]")
            try:
                path = _safe_file(policy_root, rel, f"policy {policy_id}.files[{rel}]")
            except FileNotFoundError:
                missing.append(rel)
                continue
            actual = sha256_file(path)
            if actual != expected:
                raise RegistryError(
                    f"policy {policy_id} source digest drift for {rel}: expected {expected}, got {actual}"
                )
        notices = policy.get("notices", {})
        if type(notices) is not dict:
            raise RegistryError(f"policy {policy_id}.notices must be an object")
        for rel, expected_raw in sorted(notices.items()):
            expected = _as_sha256(expected_raw, f"policy {policy_id}.notices[{rel}]")
            try:
                path = _safe_file(kg_root, rel, f"policy {policy_id}.notices[{rel}]")
            except FileNotFoundError:
                missing.append(f"notice:{rel}")
                continue
            actual = sha256_file(path)
            if actual != expected:
                raise RegistryError(
                    f"policy {policy_id} notice digest drift for {rel}: expected {expected}, got {actual}"
                )
        if "not_recovered" in custody or missing:
            reason = custody or ("missing exact files: " + ", ".join(missing))
            out.append(_entry(
                identity=identity,
                source="reference-policy-bank",
                status="unresolved",
                blocker=reason,
                intended_kind="real_policy",
                intended_family=intended_family,
                metadata={"registry_policy": policy_id, "declared_entry_sha256": expected_entry},
            ))
            continue
        entry_path = _safe_file(policy_root, entry_rel, f"policy {policy_id}.entry")
        out.append(_entry(
            identity=identity,
            source="reference-policy-bank",
            status="resolved",
            kind="real_policy",
            family=intended_family,
            source_id=f"sha256:{expected_entry}",
            entry=entry_path.relative_to(kg_root).as_posix(),
            entry_sha256=expected_entry,
            metadata={"registry_policy": policy_id, "license": policy.get("license"), "entry_root": "kaggriculture"},
        ))
    return out


def _reforge_entries(
    v4_root: Path,
    bank_root: Path | None,
    caller_manifest_sha256: str | None,
) -> list[dict[str, Any]]:
    validation = _as_dict(load_json(v4_root / REFORGE_VALIDATION_REL), "REFORGE validation")
    material = _as_dict(validation.get("materialization"), "REFORGE materialization")
    expected_manifest = _as_sha256(material.get("reforge_manifest_sha256"), "REFORGE frozen manifest")
    entries_raw = material.get("entries")
    families_raw = _as_dict(material.get("families"), "REFORGE families")
    if type(entries_raw) is not list or not entries_raw:
        raise RegistryError("REFORGE validation has no entries")
    expected_entries = [_as_text(v, "REFORGE entry") for v in entries_raw]
    family_of: dict[str, str] = {}
    for family, members_raw in families_raw.items():
        family = _as_text(family, "REFORGE family")
        if type(members_raw) is not list or not members_raw:
            raise RegistryError(f"REFORGE family {family} has no members")
        for identity_raw in members_raw:
            identity = _as_text(identity_raw, f"REFORGE family {family} member")
            if identity in family_of:
                raise RegistryError(f"REFORGE entry appears in two families: {identity}")
            family_of[identity] = family
    if set(family_of) != set(expected_entries):
        raise RegistryError("REFORGE family membership does not match entry set")

    def unresolved(identity: str, reason: str) -> dict[str, Any]:
        return _entry(
            identity=f"reforge-{identity}",
            source="reference-policy-bank/reforge",
            status="unresolved",
            blocker=reason,
            intended_kind="real_policy",
            intended_family=f"reference:{family_of[identity]}",
            metadata={"generated_identity": identity, "published_manifest_sha256": expected_manifest},
        )

    if bank_root is None:
        return [unresolved(i, "REFORGE runtime materialization required") for i in expected_entries]
    if caller_manifest_sha256 is None:
        raise RegistryError("--reforge-bank-root requires --reforge-manifest-sha256")
    caller_manifest_sha256 = _as_sha256(caller_manifest_sha256, "caller REFORGE manifest SHA-256")
    if caller_manifest_sha256 != expected_manifest:
        raise RegistryError("caller REFORGE manifest does not match published validated materialization")
    bank_root = bank_root.resolve(strict=True)
    manifest_path = _safe_file(bank_root, "REFORGE-BANK.json", "REFORGE-BANK.json")
    if sha256_file(manifest_path) != caller_manifest_sha256:
        raise RegistryError("REFORGE-BANK.json bytes do not match caller-frozen hash")
    manifest = _as_dict(load_json(manifest_path), "REFORGE runtime manifest")
    if manifest.get("schema") != REFORGE_SCHEMA:
        raise RegistryError("REFORGE runtime schema changed")
    files = _as_dict(manifest.get("files"), "REFORGE runtime files")
    for rel, expected_raw in sorted(files.items()):
        expected = _as_sha256(expected_raw, f"REFORGE file {rel}")
        path = _safe_file(bank_root, rel, f"REFORGE file {rel}")
        actual = sha256_file(path)
        if actual != expected:
            raise RegistryError(f"REFORGE runtime file drift: {rel}")
    manifest_entries = _as_dict(manifest.get("entries"), "REFORGE runtime entries")
    if set(manifest_entries) != set(expected_entries):
        raise RegistryError("REFORGE runtime entry set changed")
    out: list[dict[str, Any]] = []
    for identity in expected_entries:
        row = _as_dict(manifest_entries[identity], f"REFORGE entry {identity}")
        if row.get("family") != family_of[identity]:
            raise RegistryError(f"REFORGE family changed: {identity}")
        declared = _safe_rel(_as_text(row.get("entry"), f"REFORGE entry {identity}.entry"), "REFORGE entry")
        if len(declared.parts) != 2 or declared.parts[0] != "bank":
            raise RegistryError(f"REFORGE entry path shape changed: {declared}")
        entry_path = _safe_file(bank_root, declared.name, f"REFORGE generated entry {identity}")
        digest = sha256_file(entry_path)
        out.append(_entry(
            identity=f"reforge-{identity}",
            source="reference-policy-bank/reforge",
            status="resolved",
            kind="real_policy",
            family=f"reference:{family_of[identity]}",
            source_id=f"sha256:{digest}",
            entry=declared.as_posix(),
            entry_sha256=digest,
            metadata={"generated_identity": identity, "runtime_manifest_sha256": caller_manifest_sha256, "entry_root": "reforge-bank-parent"},
        ))
    return out


def _orchard_entries(v4_root: Path) -> list[dict[str, Any]]:
    manifest_path = v4_root / ORCHARD_REL
    raw = _as_dict(load_json(manifest_path), "ORCHARD opponent manifest")
    if raw.get("schema") != ORCHARD_SCHEMA:
        raise RegistryError("ORCHARD opponent schema changed")
    module_rel = _as_text(raw.get("module"), "ORCHARD module")
    expected = _as_sha256(raw.get("module_sha256"), "ORCHARD module SHA-256")
    module = _safe_file(manifest_path.parent, module_rel, "ORCHARD module")
    actual = sha256_file(module)
    if actual != expected:
        raise RegistryError(f"ORCHARD module digest drift: expected {expected}, got {actual}")
    profiles = _as_dict(raw.get("profiles"), "ORCHARD profiles")
    family = "synthetic:" + _as_text(raw.get("family"), "ORCHARD family")
    out: list[dict[str, Any]] = []
    for profile, function_raw in sorted(profiles.items()):
        function = _as_text(function_raw, f"ORCHARD profile {profile}")
        profile_id = _as_text(profile, "ORCHARD profile name")
        out.append(_entry(
            identity=f"reactive-{profile_id}",
            source="opponent-challengers",
            status="resolved",
            kind="archetype",
            family=family,
            source_id=f"sha256:{expected}",
            entry=module.relative_to(v4_root).as_posix() + f"::{function}",
            entry_sha256=expected,
            metadata={"profile": profile_id, "classification": raw.get("classification"), "entry_root": "v4"},
        ))
    return out


def _pressure_entries(v4_root: Path) -> list[dict[str, Any]]:
    module = _safe_file(v4_root, PRESSURE_REL.as_posix(), "market-pressure source")
    digest = sha256_file(module)
    return [_entry(
        identity="wheat-pressure-stress",
        source="market-pressure",
        status="resolved",
        kind="archetype",
        family="stress:wheat-pressure",
        source_id=f"sha256:{digest}",
        entry=PRESSURE_REL.as_posix() + "::agent",
        entry_sha256=digest,
        metadata={"purpose": "external-demand WHEAT pressure stress opponent", "entry_root": "v4"},
    )]


def _load_spectrum_validator(path: Path) -> Callable[[Any], dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("titan_v4_spectrum_panel_diversity", path)
    if spec is None or spec.loader is None:
        raise RegistryError("cannot import SPECTRUM validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - external authority import failure
        raise RegistryError(f"cannot import SPECTRUM validator: {exc}") from exc
    validate = getattr(module, "validate_panel", None)
    if not callable(validate):
        raise RegistryError("SPECTRUM validator missing validate_panel")
    return validate


def build_registry(
    v4_root: Path,
    *,
    reforge_bank_root: Path | None = None,
    reforge_manifest_sha256: str | None = None,
    pins: dict[str, str] | None = None,
    validate_panel: Callable[[Any], Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    v4_root = v4_root.resolve(strict=True)
    pins = dict(DEFAULT_PINS if pins is None else pins)
    required_pins = set(DEFAULT_PINS)
    if set(pins) != required_pins:
        raise RegistryError("source pin set changed")
    authority_paths = {
        "reference_manifest": v4_root / REFERENCE_REL,
        "reforge_validation": v4_root / REFORGE_VALIDATION_REL,
        "reforge_generator": v4_root / REFORGE_GENERATOR_REL,
        "orchard_manifest": v4_root / ORCHARD_REL,
        "market_pressure": v4_root / PRESSURE_REL,
        "spectrum_validator": v4_root / SPECTRUM_REL,
    }
    for name, path in authority_paths.items():
        if not path.is_file() or path.is_symlink():
            raise RegistryError(f"missing authority source: {name}")
        _verify_blob(path, pins[name], name)

    entries = (
        _reference_entries(v4_root)
        + _reforge_entries(v4_root, reforge_bank_root, reforge_manifest_sha256)
        + _orchard_entries(v4_root)
        + _pressure_entries(v4_root)
    )
    entries.sort(key=lambda r: r["id"])
    ids = [r["id"] for r in entries]
    if len(ids) != len(set(ids)):
        raise RegistryError("duplicate opponent identity after composition")
    panel = {
        "schema": PANEL_SCHEMA,
        "expected_labels": len(entries),
        "source": "ASTRA-GAUNTLETBRIDGE current-V4 source registry",
        "notes": (
            "Identity-only SPECTRUM panel. Execution paths and digests live in the paired "
            "titan.gauntlet.opponent-registry.v1 output; unresolved rows are never substituted."
        ),
        "opponents": [_panel_row(r) for r in entries],
    }
    validator = validate_panel or _load_spectrum_validator(authority_paths["spectrum_validator"])
    try:
        validator(panel)
    except Exception as exc:
        raise RegistryError(f"SPECTRUM rejected generated panel: {exc}") from exc

    blockers = [
        {"id": r["id"], "reason": r.get("blocker", "unresolved")}
        for r in entries if r["status"] != "resolved"
    ]
    registry = {
        "schema": REGISTRY_SCHEMA,
        "panel_schema": PANEL_SCHEMA,
        "authority_git_blobs": dict(sorted(pins.items())),
        "entries": entries,
        "resolved_labels": len(entries) - len(blockers),
        "unresolved_labels": len(blockers),
        "blockers": blockers,
        "ownership": {
            "orchestration": "Riot/existing gauntlet owner",
            "scheduling": "SPECTRUM/family_schedule",
            "admission": "SEALCHAIN",
            "this_tool": "source authentication + identity/entry registry only",
        },
        "side_effects": {
            "runs_games": False,
            "changes_gameplay": False,
            "changes_defaults": False,
            "changes_archive": False,
            "submits_kaggle": False,
        },
    }
    return registry, panel


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-root", type=Path, required=True)
    parser.add_argument("--registry-out", type=Path, required=True)
    parser.add_argument("--panel-out", type=Path, required=True)
    parser.add_argument("--reforge-bank-root", type=Path)
    parser.add_argument("--reforge-manifest-sha256")
    parser.add_argument("--require-resolved", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.reforge_bank_root) != bool(args.reforge_manifest_sha256):
        parser.error("--reforge-bank-root and --reforge-manifest-sha256 must be supplied together")
    try:
        registry, panel = build_registry(
            args.v4_root,
            reforge_bank_root=args.reforge_bank_root,
            reforge_manifest_sha256=args.reforge_manifest_sha256,
        )
        _write_json(args.registry_out, registry)
        _write_json(args.panel_out, panel)
    except (OSError, RegistryError, ValueError) as exc:
        print(f"GAUNTLETBRIDGE BLOCKED: {exc}", file=sys.stderr)
        return 2
    summary = {
        "status": "PASS" if not registry["blockers"] else "PARTIAL",
        "resolved": registry["resolved_labels"],
        "unresolved": registry["unresolved_labels"],
        "registry_sha256": sha256_file(args.registry_out),
        "panel_sha256": sha256_file(args.panel_out),
    }
    print(json.dumps(summary, sort_keys=True))
    if args.require_resolved and registry["blockers"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
