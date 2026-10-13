"""Deterministic no-auth opportunity alias resolution facts."""
from __future__ import annotations

from typing import Any

from .aliases import alias_key
from .registry import compile_observation, compile_registry, read_current_registry
from .strict import RESULT_SCHEMA, IdentityAliasError, canonical_json, sha256_json


def resolve_against(observation: Any, registry: Any) -> dict[str, Any]:
    obs = compile_observation(observation)
    reg = compile_registry(registry)
    buyer = obs["buyer_organization_key"]
    index: dict[tuple[str, str], str] = {}
    for entry in reg["entries"]:
        if entry["buyer_organization_key"] == buyer:
            for alias in entry["aliases"]:
                index[alias_key(alias)] = entry["canonical_opportunity_key"]

    resolved: set[str] = set()
    unknown: list[dict[str, str]] = []
    for alias in obs["aliases"]:
        candidate = index.get(alias_key(alias))
        if candidate is None:
            unknown.append(alias)
        else:
            resolved.add(candidate)

    if len(resolved) > 1:
        state, canonical = "AMBIGUOUS_ALIAS_SET", None
    elif unknown:
        state, canonical = "UNRESOLVED_ALIAS", None
    elif len(resolved) == 1:
        state, canonical = "RESOLVED", next(iter(resolved))
    else:
        state, canonical = "UNRESOLVED_ALIAS", None

    result = {
        "schema": RESULT_SCHEMA,
        "state": state,
        "buyer_organization_key": buyer,
        "canonical_opportunity_key": canonical,
        "candidate_canonical_opportunity_keys": sorted(resolved),
        "unknown_aliases": sorted(unknown, key=alias_key),
        "normalized_aliases": obs["aliases"],
        "registry_generation": reg["generation"],
        "registry_sha256": sha256_json(reg),
        "alias_set_sha256": sha256_json(obs["aliases"]),
        "external_action_authorized": False,
        "buyer_contact_authorized": False,
        "provider_mutation_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    result["result_sha256"] = sha256_json(result)
    return result


def verify_result(observation: Any, registry: Any, result: Any) -> bool:
    if type(result) is not dict:
        return False
    try:
        return canonical_json(result) == canonical_json(resolve_against(observation, registry))
    except IdentityAliasError:
        return False


def resolve_current(observation: Any) -> dict[str, Any]:
    """Resolve against the repository-carried current registry; no path selector."""
    return resolve_against(observation, read_current_registry())


def verify_current(observation: Any, result: Any) -> bool:
    """Verify against the repository-carried current registry; no path selector."""
    try:
        return verify_result(observation, read_current_registry(), result)
    except IdentityAliasError:
        return False
