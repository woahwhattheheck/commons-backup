"""Redacted relational inventory for connected accounts and service access.

The module consumes reference metadata and configuration signals only. Canonical
resource-ledger surfaces remain resource declarations, separate from provider
account identity. It never reads credential values or attempts account mutations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

_SAFE_FIELDS = (
    "name", "label", "account_name", "account_id", "account_ref", "candidate_account_ref", "provider", "service",
    "service_name", "identity_state", "identity_status", "capability", "capability_name", "resource_id", "resource_type",
    "kind", "status", "state", "source", "scope_name", "quota_name", "unit",
    "limit", "remaining", "used", "reset_at", "updated_at", "expires_at",
    "credential_ref", "vault_ref", "keyring_ref", "connector", "connector_name",
    "credential_id", "reference_id", "ref_id", "credential_name", "credential_type",
    "credential_refs", "target", "pointer", "type", "format", "encoding", "text_encoding",
    "scope", "scopes", "workspace", "workspace_id", "host", "repository", "repo",
    "source_id", "source_locator", "operation", "endpoint", "available", "enabled", "peer_access", "metadata",
    "complete", "listing_complete", "reader", "tools", "unread_regions", "source_role", "configuration_state",
)
_CONFIG_FILES = {".mcp.json", "mcp.json", "connectors.json", "services.json", "package.json",
                 "pyproject.toml", "config.json", "manifest.json", "commons.json"}
_SECRET_KEY = re.compile(r"(?i)(token|secret|password|credential_value|private.?key|api.?key|authorization|cookie)")
_SECRET_VALUE = re.compile(r"(?i)(?:\b(?:sk|ghp|gho|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,}\b|\bBearer\s+[A-Za-z0-9._~+/-]{8,}|-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----|\b(?:password|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[:=]\s*[\"']?[^\s\"',;]{6,})")


def _label(value: Any, limit: int = 180) -> str | None:
    if isinstance(value, (str, int, float, bool)):
        text = re.sub(r"\s+", " ", str(value)).strip()
        if text and not _SECRET_VALUE.search(text):
            return text[:limit]
    return None


def _stable(kind: str, *parts: Any) -> str:
    seed = "\x1f".join([kind, *(str(p or "") for p in parts)])
    return kind + ":" + hashlib.sha256(seed.encode("utf-8", "replace")).hexdigest()[:20]


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if value.get("schema") == "commons-resource-ledger/v2" and isinstance(value.get("surfaces"), list):
            return [{**surface, "_resource_ledger_surface": True,
                     "_resource_ledger_source_id": value.get("source_id"),
                     "_resource_ledger_surface_index": index}
                    for index, surface in enumerate(value["surfaces"])
                    if isinstance(surface, Mapping)]
        rows: list[Mapping[str, Any]] = []
        for key in ("items", "resources", "accounts", "services", "connectors", "credentials", "references",
                    "records", "sources", "capabilities", "quotas", "inventory", "rows", "providers"):
            child = value.get(key)
            if isinstance(child, list):
                rows.extend(v for v in child if isinstance(v, Mapping))
            elif isinstance(child, Mapping):
                rows.extend({"label": label, **row} for label, row in child.items() if isinstance(row, Mapping))
        if rows:
            if any(key in value for key in ("account_ref", "account_id", "service", "provider", "source_id", "credential_ref")):
                rows.insert(0, value)
            return rows
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [v for v in value if isinstance(v, Mapping)]
    return []


def _path_values(value: Any) -> list[str | os.PathLike[str]]:
    if value is None:
        return []
    if isinstance(value, (str, os.PathLike)):
        return [value]
    if isinstance(value, Mapping):
        value = value.get("path", value.get("root", value.get("value", ())))
        return _path_values(value)
    if isinstance(value, Iterable):
        return [item for item in value if isinstance(item, (str, os.PathLike))]
    return []


def _record(entity_type: str, entity_id: str, name: str | None, status: str | None,
            attributes: Mapping[str, Any] | None = None, relations: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"entity_type": entity_type, "entity_id": entity_id, "name": name,
            "status": status, "attributes": dict(attributes or {}), "relations": relations or []}


def _attrs(row: Mapping[str, Any], omit: set[str] | None = None) -> dict[str, Any]:
    omit = omit or set()
    result: dict[str, Any] = {}
    for field in _SAFE_FIELDS:
        if field in omit or field not in row or _SECRET_KEY.search(field):
            continue
        val = row[field]
        # Only preserve scalar metadata. Never serialize arbitrary nested provider data.
        if isinstance(val, (str, int, float, bool)) or val is None:
            safe = _label(val)
            if safe is not None:
                result[field] = safe
        elif field in {"credential_refs", "tools", "unread_regions", "scopes"} and isinstance(val, (list, tuple)):
            safe_values = [_label(item, 500) for item in val]
            result[field] = [item for item in safe_values if item is not None]
        elif field == "reader" and isinstance(val, Mapping):
            reader = {}
            for key in ("road", "method", "methods", "endpoint", "pagination", "types", "full_content"):
                item = val.get(key)
                if isinstance(item, (str, int, float, bool)):
                    safe = _label(item, 500)
                    if safe is not None:
                        reader[key] = safe
                elif key in {"methods", "types"} and isinstance(item, (list, tuple)):
                    reader[key] = [safe for child in item if (safe := _label(child, 300)) is not None]
            if reader:
                result[field] = reader
        elif field == "metadata" and isinstance(val, Mapping):
            nested = {}
            for key in ("provider_login", "provider_account_id", "workspace_id", "user_id", "bot_id",
                        "host", "identity_state", "account_status", "service_status", "available", "enabled"):
                safe = _label(val.get(key), 300)
                if safe is not None:
                    nested[key] = safe
            if nested:
                result[field] = nested
    return result


def _provider(row: Mapping[str, Any]) -> str:
    for key in ("provider", "service", "service_name", "connector", "connector_name", "source"):
        val = _label(row.get(key), 120)
        if val:
            return val.lower()
    refs = row.get("credential_refs") if isinstance(row.get("credential_refs"), (list, tuple)) else []
    refs = list(refs) + [row.get(key) for key in ("credential_ref", "vault_ref", "keyring_ref") if row.get(key)]
    for reference in refs:
        if not isinstance(reference, str):
            continue
        parts = [part for part in re.split(r"[/:]", reference.strip("/:")) if part]
        if parts and parts[0].lower() in {"vault", "cloud", "environment", "account", "credentials"}:
            parts = parts[1:]
        if parts:
            label = _label(parts[0], 120)
            if label:
                return label.lower()
    if str(row.get("type", "")).lower() in {"windows_credential", "keyring", "secure_reference"}:
        target = str(row.get("target") or row.get("pointer") or row.get("label") or "").lower()
        if target.startswith(("commons:", "shared:", "vault:")):
            return "shared-vault"
    for field in ("label", "target", "pointer"):
        raw = row.get(field)
        if not isinstance(raw, str) or not raw:
            continue
        parts = [part for part in re.split(r"[/:@]", raw.strip("/:@")) if part]
        parts = [part for part in parts if part.lower() not in {"vault", "credentials", "credential", "keyring", "account", "accounts", "token", "secret", "windows_credential"}]
        if parts:
            label = _label(parts[0], 120)
            if label and not re.fullmatch(r"[0-9a-f-]{24,}", label, re.I):
                return label.lower()
    return "unknown"


def _inventory_records(inputs: Iterable[Mapping[str, Any]], source: str, default_type: str) -> list[dict[str, Any]]:
    result = []
    for row in inputs:
        if row.get("_resource_ledger_surface") is True:
            name = _label(row.get("name") or row.get("resource_id"))
            if not name:
                continue
            attributes = _attrs(row, {"source"})
            attributes.update(source="resource_ledger", resource_id=name,
                              source_locator="ground/RESOURCE_LEDGER.json#/surfaces/" + str(row["_resource_ledger_surface_index"]))
            for target, value in (
                ("source_id", row.get("_resource_ledger_source_id")),
                ("resource_type", row.get("kind")),
                ("declared_stage", row.get("stage")),
                ("declared_condition", row.get("condition")),
                ("declared_capacity", row.get("capacity")),
                ("holder", row.get("holder")),
                ("evidence_ts", row.get("evidence_ts")),
                ("last_used_at", row.get("last_used_at")),
                ("provenance", row.get("source")),
            ):
                safe = _label(value, 2000)
                if safe is not None:
                    attributes[target] = safe
            # A resource declaration is not an authenticated provider account.
            # Preserve every surface without interpreting provenance as a login.
            result.append(_record("resource", _stable("resource", "commons-resource-ledger", name),
                                  name, "recorded", attributes))
            continue
        provider = _provider(row)
        account_name = _label(row.get("account_name") or row.get("account") or row.get("owner") or row.get("candidate_account_ref") or row.get("account_ref") or provider)
        account_ref = _label(row.get("account_id") or row.get("account_ref") or account_name)
        service_name = _label(row.get("service_name") or row.get("service") or row.get("connector_name") or row.get("connector") or row.get("provider") or row.get("source") or provider)
        service_id = _stable("service", provider, service_name)
        nested_metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        identity_state = row.get("identity_state") or nested_metadata.get("identity_state")
        identity_verified = identity_state in {"provider_observed", "authenticated", "verified"} or row.get("provider_identity_verified") is True
        identity_status = "provider_observed" if identity_verified else "pending_recovery"
        if provider == "unknown" or account_ref in {None, "unknown", "unknown:unresolved-account"}:
            identity_status = "pending_recovery"
        credential_refs = row.get("credential_refs") if isinstance(row.get("credential_refs"), (list, tuple)) else []
        credential_refs = list(credential_refs)
        for field in ("credential_ref", "vault_ref", "keyring_ref"):
            value = row.get(field)
            if isinstance(value, str) and value not in credential_refs:
                credential_refs.append(value)
        if source == "secure_reference" and not credential_refs:
            value = row.get("target") or row.get("pointer") or row.get("label") or row.get("reference_id")
            if isinstance(value, str):
                credential_refs.append(value)
        # Before an account-specific reader verifies identity, each distinct
        # secure reference remains its own unresolved evidence entity. Two refs
        # for the same provider are never merged into one account by provider name.
        if credential_refs and not identity_verified:
            account_targets = [("account-evidence:" + _stable("reference", provider, ref),
                                _label(row.get("candidate_account_ref")) or account_name, ref)
                               for ref in sorted(set(str(value) for value in credential_refs))]
        else:
            account_targets = [(_stable("account", provider, account_ref), account_name, None)]
        account_ids = []
        for evidence_account_id, evidence_name, evidence_ref in account_targets:
            account_ids.append(evidence_account_id)
            attrs = {"provider": provider, "source": source, **_attrs(row, {"secret", "token", "password"})}
            if evidence_ref is not None:
                attrs["credential_refs"] = [evidence_ref]
                attrs["identity_state"] = "unresolved_reference_evidence"
            result.append(_record("account", evidence_account_id, evidence_name, "pending_recovery" if evidence_ref else identity_status, attrs))
        source_status = _label(row.get("service_status") or row.get("status"))
        pending_statuses = {"pending_recovery", "reader_binding_pending", "pending_backfill", "account_mapping_pending"}
        if source_status not in pending_statuses:
            if source_status == "configured":
                pass
            elif source_status == "provider_observed":
                source_status = "reader_binding_pending"
            else:
                source_status = "reader_binding_pending" if provider != "unknown" else "pending_recovery"
        result.append(_record("service", service_id, service_name, source_status,
                              {"provider": provider, "source": source, **_attrs(row, {"credential_ref", "credential_refs", "vault_ref", "keyring_ref", "password", "token", "secret"})},
                              [{"relation": "connected_account", "entity_type": "account", "entity_id": account_id} for account_id in account_ids]))

        capability = _label(row.get("capability_name") or row.get("capability") or row.get("operation") or row.get("scope"))
        if capability:
            capability_id = _stable("capability", service_id, capability)
            capability_status = _label(row.get("capability_status") or row.get("status"))
            if row.get("complete") is False or row.get("status") in {"pending_recovery", "reader_binding_pending", "pending_backfill", "account_mapping_pending"}:
                capability_status = "pending_recovery"
            capability_attrs = {"available": _label(row.get("available")), "enabled": _label(row.get("enabled")),
                                "peer_access": _label(row.get("peer_access")), "source": source,
                                **_attrs(row, {"credential_ref", "credential_refs", "vault_ref", "keyring_ref", "password", "token", "secret"})}
            result.append(_record("capability", capability_id, capability,
                                  capability_status, capability_attrs,
                                  [{"relation": "provided_by", "entity_type": "service", "entity_id": service_id}]))

        quota_keys = ("quota_name", "limit", "remaining", "used", "unit", "reset_at")
        quota_attrs = {key: _label(row.get(key)) for key in quota_keys if _label(row.get(key)) is not None}
        if quota_attrs:
            quota_id = _stable("quota", service_id, quota_attrs.get("quota_name", "default"), quota_attrs.get("unit"))
            result.append(_record("quota", quota_id, quota_attrs.get("quota_name") or "quota", "observed", quota_attrs,
                                  [{"relation": "applies_to", "entity_type": "service", "entity_id": service_id}]))
    return result


def _configuration_signals(roots: Iterable[str | os.PathLike[str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    coverage = {"files_scanned": 0, "signals_found": 0, "unread_reasons": []}
    for root in roots:
        path = Path(root).expanduser()
        try:
            candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
            for file in candidates:
                if file.name.lower() not in _CONFIG_FILES:
                    continue
                try:
                    raw = file.read_text(encoding="utf-8")
                    data = json.loads(raw) if file.suffix.lower() == ".json" or file.name.lower() in {".mcp.json", "mcp.json"} else None
                    coverage["files_scanned"] += 1
                    if not isinstance(data, Mapping):
                        continue
                    services = data.get("mcpServers") or data.get("services") or data.get("connectors") or {}
                    if isinstance(services, Mapping):
                        for service_name, config in services.items():
                            name = _label(service_name)
                            if not name:
                                continue
                            service_id = _stable("service", "repo-config", name)
                            account_id = _stable("account", "repo-config", name)
                            # Record only presence and non-secret structural signals; command/args/env are omitted.
                            attrs = {"source": "repo_config", "config_file": file.name, "configuration_state": "configured"}
                            if isinstance(config, Mapping):
                                for key in ("enabled", "type", "transport", "url"):
                                    val = _label(config.get(key), 160)
                                    if val:
                                        attrs[key] = val
                                if any(_SECRET_KEY.search(str(key)) for key in config.keys()):
                                    attrs["credential_signal"] = "configured_reference_or_secret_field_present"
                            records.append(_record("account", account_id, name + " account unresolved", "pending_recovery",
                                                   {"provider": "unknown", "source": "repo_config", "identity_state": "unresolved", "credential_signal": attrs.get("credential_signal")}))
                            records.append(_record("service", service_id, name, "reader_binding_pending", attrs,
                                                   [{"relation": "connected_account", "entity_type": "account", "entity_id": account_id}]))
                            coverage["signals_found"] += 1
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, PermissionError) as exc:
                    coverage["unread_reasons"].append({"source": file.name, "reason": type(exc).__name__})
        except OSError as exc:
            coverage["unread_reasons"].append({"source": str(path.name), "reason": type(exc).__name__})
    return records, coverage


def build_account_inventory(*, secure_references: Iterable[Mapping[str, Any]] = (),
                            resource_ledger: Iterable[Mapping[str, Any]] = (),
                            connector_records: Iterable[Mapping[str, Any]] = (),
                            service_records: Iterable[Mapping[str, Any]] = (),
                            repo_config_roots: Iterable[str | os.PathLike[str]] = ()) -> dict[str, Any]:
    """Return redacted account/service/capability/quota entities and relations.

    ``secure_references`` must contain metadata such as vault reference labels;
    the adapter discards secret-like keys and never resolves the references.
    """
    records: list[dict[str, Any]] = []
    inputs = (("secure_reference", secure_references), ("resource_ledger", resource_ledger),
              ("connector", connector_records), ("service", service_records))
    coverage: dict[str, Any] = {"source_counts": {}, "repo_config": {}}
    for source, rows in inputs:
        normalized = _rows(rows)
        coverage["source_counts"][source] = len(normalized)
        records.extend(_inventory_records(normalized, source, source))
    config_records, config_coverage = _configuration_signals(repo_config_roots)
    records.extend(config_records)
    coverage["repo_config"] = config_coverage
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        # Merge duplicate entity observations without losing provenance or relations.
        current = unique.get(record["entity_id"])
        if current is None:
            unique[record["entity_id"]] = record
            continue
        current["attributes"].update(record["attributes"])
        current["relations"] = list({(r["relation"], r["entity_type"], r["entity_id"]): r
                                      for r in current["relations"] + record["relations"]}.values())
        if current["status"] in (None, "unknown") and record["status"]:
            current["status"] = record["status"]
    result = list(unique.values())
    coverage["entities"] = len(result)
    coverage["relations"] = sum(len(item["relations"]) for item in result)
    coverage["credential_values_read"] = 0
    coverage["universe_complete"] = False
    coverage["coverage_status"] = "partial_evidence_inventory"
    coverage["pending_accounts"] = sum(record["entity_type"] == "account" and record.get("status") in {"pending_recovery", "unknown", "unresolved"} for record in result)
    coverage["pending_services"] = sum(record["entity_type"] == "service" and record.get("status") in {"pending_recovery", "reader_binding_pending", "pending_backfill", "account_mapping_pending"} for record in result)
    coverage["pending_capabilities"] = sum(record["entity_type"] == "capability" and record.get("status") in {"pending_recovery", "reader_binding_pending", "pending_backfill", "account_mapping_pending"} for record in result)
    coverage["recovery_scope"] = {
        "status": "pending_recovery", "complete": False,
        "observed_source_counts": dict(coverage["source_counts"]),
        "observed_repo_config_files": config_coverage.get("files_scanned", 0),
        "observed_repo_config_signals": config_coverage.get("signals_found", 0),
        "pending_account_entities": coverage["pending_accounts"],
        "pending_service_entities": coverage["pending_services"],
        "pending_capability_entities": coverage["pending_capabilities"],
        "unread_regions": [
            "provider accounts and services without evidence in supplied secure references, resource ledgers, connectors, or scanned configuration roots",
            "provider identity and reader binding for service/account evidence without an account reference",
            "account-level capabilities and quotas not represented in supplied metadata",
        ],
    }
    return {"records": result, "coverage": coverage}


def collect_account_inventory(inputs: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Accept runner payload envelopes and direct inventory sources.

    Expected envelope shape is ``{"source": "resource-ledger", "data": ...}``.
    Only recognized scalar metadata fields survive normalization; nested payloads
    and secret-like fields are discarded by the inventory builder.
    """
    buckets: dict[str, list[Mapping[str, Any]]] = {
        "secure_references": [], "resource_ledger": [],
        "connector_records": [], "service_records": [],
    }
    roots: list[str | os.PathLike[str]] = _path_values(kwargs.pop("repo_config_roots", ()))
    for key in buckets:
        values = kwargs.pop(key, ()) or ()
        buckets[key].extend(_rows(values))

    envelopes = _rows(inputs)
    # A direct inventory object may carry several parallel source collections.
    if isinstance(inputs, Mapping) and any(key in inputs for key in (*buckets.keys(), "repo_config_roots", "references", "sources", "coverage")):
        buckets["secure_references"].extend(_rows(inputs.get("secure_references", inputs.get("references", ()))))
        buckets["resource_ledger"].extend(_rows(inputs.get("resource_ledger", inputs.get("resources", ()))))
        buckets["connector_records"].extend(_rows(inputs.get("connector_records", inputs.get("connectors", ()))))
        buckets["service_records"].extend(_rows(inputs.get("service_records", inputs.get("services", ()))))
        buckets["service_records"].extend(_rows(inputs.get("accounts", ())))
        buckets["service_records"].extend(_rows(inputs.get("sources", ())))
        roots.extend(_path_values(inputs.get("repo_config_roots", ())))
        envelopes = []

    for envelope in envelopes:
        source = str(envelope.get("source", "")).lower().replace("_", "-")
        if any(key in envelope for key in ("data", "payload", "records")):
            data = envelope.get("data", envelope.get("payload", envelope.get("records", ())))
        else:
            data = envelope
        if "repo-config" in source or "config-root" in source:
            if isinstance(data, (str, os.PathLike)):
                roots.append(data)
            elif isinstance(data, Iterable) and not isinstance(data, (bytes, Mapping)):
                roots.extend(item for item in data if isinstance(item, (str, os.PathLike)))
            continue
        records = _rows(data)
        if any(token in source for token in ("vault", "credential", "keyring", "secret-ref", "configured-reference", "credential-source")):
            buckets["secure_references"].extend(records)
        elif any(token in source for token in ("resource", "ledger", "inventory")):
            buckets["resource_ledger"].extend(records)
        elif any(token in source for token in ("connector", "mcp")):
            buckets["connector_records"].extend(records)
        elif any(token in source for token in ("service", "account", "provider")):
            buckets["service_records"].extend(records)
        elif records:
            # Unlabeled payloads are service records, while their own metadata
            # still determines the provider/account relationships.
            buckets["service_records"].extend(records)

    return build_account_inventory(**buckets, repo_config_roots=roots)
