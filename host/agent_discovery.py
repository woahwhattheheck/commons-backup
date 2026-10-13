#!/usr/bin/env python3
"""Build deterministic public agent-discovery surfaces from one registry.

Generation stages and syncs each complete file before replacement. A failed
write preserves that destination; earlier files may already be updated. After
recovering storage, run generate again and use check to confirm the full set.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agent-discovery.json"
OUTPUTS = (
    "agents.txt",
    "manifest.json",
    "agent.json",
    "agents.json",
    ".well-known/agent.json",
    ".well-known/agents.json",
    "continuity.json",
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_registry(path: Path = SOURCE) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("registry must be an object")
    return value


def _public_url(value: str) -> bool:
    if (
        not value
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127
               for character in value)
    ):
        return False
    try:
        parsed = urlparse(value)
        if parsed.scheme == "https":
            # ``urlparse`` accepts ``https:relative`` and a non-empty ``:port``
            # netloc. Discovery links need a real absolute authority. Reading
            # ``port`` also rejects malformed, non-numeric port declarations.
            parsed.port
            return bool(
                parsed.netloc
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
            )
        if parsed.scheme == "mailto":
            # ``mailto://host`` is not a mailbox URI. The recipient is the
            # scheme path and must not be written as a slash-prefixed URL path.
            return not parsed.netloc and bool(parsed.path) and not parsed.path.startswith("/")
    except ValueError:
        return False
    return False


def validate(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema") != "commons-agent-discovery/v1":
        errors.append("schema")
    identity = registry.get("identity")
    if (
        not isinstance(identity, dict)
        or not identity.get("name")
        or not identity.get("description")
        or not _public_url(str(identity.get("homepage") or ""))
        or not _public_url(str(identity.get("repository") or ""))
    ):
        errors.append("identity")
    for field in ("contact_methods", "capabilities"):
        rows = registry.get(field)
        if not isinstance(rows, list) or not rows:
            errors.append(field)
    contacts = registry.get("contact_methods")
    if not isinstance(contacts, list):
        contacts = []
    for row in contacts:
        if not isinstance(row, dict):
            errors.append("contact_methods.$.row")
            continue
        if not str(row.get("type") or "").strip():
            errors.append("contact_methods.$.type")
        if not _public_url(str(row.get("url") or "")):
            errors.append("contact_methods.$.url")
        if not isinstance(row.get("preferred"), bool):
            errors.append("contact_methods.$.preferred")
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        capabilities = []
    for index, row in enumerate(capabilities):
        if not isinstance(row, dict):
            errors.append("capabilities.%d.row" % index)
            continue
        if not str(row.get("id") or "").strip():
            errors.append("capabilities.%d.id" % index)
        if not str(row.get("description") or "").strip():
            errors.append("capabilities.%d.description" % index)
        entrypoints = row.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            errors.append("capabilities.%d.entrypoints" % index)
        elif any(not isinstance(item, str) or not item.strip() for item in entrypoints):
            errors.append("capabilities.%d.entrypoints" % index)
    runtime = registry.get("runtime_signals") or {}
    if not isinstance(runtime, dict):
        errors.append("runtime_signals")
        runtime = {}
    expected = {
        "discovery_state": "open",
        "runtime_access": "public",
        "source_of_truth": "git-head",
        "claims_require_receipts": True,
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            errors.append(f"runtime_signals.{key}")
    if not str(runtime.get("runtime_state") or "").strip():
        errors.append("runtime_signals.runtime_state")
    continuity = registry.get("continuity") or {}
    if not isinstance(continuity, dict):
        errors.append("continuity")
        continuity = {}
    if continuity.get("startup_order") != ["harnesses/catalog.json", "AGENTS.md", "START.md", "boards.html"]:
        errors.append("continuity.startup_order")
    for field in ("pulse", "recent", "receipts", "instruction"):
        value = continuity.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"continuity.{field}")
    interoperability = registry.get("interoperability")
    if not isinstance(interoperability, dict):
        errors.append("interoperability")
        interoperability = {}
    formats = interoperability.get("formats")
    if not isinstance(formats, list):
        errors.append("interoperability.formats")
        formats = []
    elif any(not isinstance(item, str) for item in formats):
        errors.append("interoperability.formats")
    for output in OUTPUTS:
        if output not in formats:
            errors.append(f"interoperability.formats:{output}")
    return sorted(set(errors))


def agent_card(registry: dict[str, Any]) -> dict[str, Any]:
    identity = registry["identity"]
    skills = [
        {
            "id": row["id"],
            "name": row["id"],
            "description": row["description"],
            "entrypoints": row["entrypoints"],
        }
        for row in registry["capabilities"]
    ]
    return {
        "schema": "commons-agent-card/v1",
        "name": identity["name"],
        "description": identity["description"],
        "url": identity["homepage"],
        "documentationUrl": identity["repository"],
        "provider": {"organization": "Commons", "url": identity["homepage"]},
        "defaultInputModes": ["text", "json"],
        "defaultOutputModes": ["text", "json", "git"],
        "skills": skills,
        "runtime_signals": registry["runtime_signals"],
        "contact_methods": registry["contact_methods"],
        "continuity": registry["continuity"],
    }


def render_agents_txt(registry: dict[str, Any]) -> str:
    identity = registry["identity"]
    lines = [
        "# agents.txt - Commons Agent Discovery",
        "# Deterministic projection of agent-discovery.json",
        "",
        "[Commons]",
        f"name: {identity['name']}",
        f"description: {identity['description']}",
        f"homepage: {identity['homepage']}",
        f"repository: {identity['repository']}",
        f"source_of_truth: {registry['runtime_signals']['source_of_truth']}",
        f"runtime_state: {registry['runtime_signals']['runtime_state']}",
        f"runtime_access: {registry['runtime_signals']['runtime_access']}",
        "",
        "[Capabilities]",
    ]
    for row in registry["capabilities"]:
        lines.append(f"capability: {row['id']} | {row['description']} | {','.join(row['entrypoints'])}")
    lines.extend(("", "[Contact Methods]"))
    for row in registry["contact_methods"]:
        lines.append(f"contact: {row['type']} | preferred={str(row['preferred']).lower()} | {row['url']}")
    lines.extend((
        "",
        "[Continuity]",
        "startup_order: " + ",".join(registry["continuity"]["startup_order"]),
        "pulse: " + registry["continuity"]["pulse"],
        "recent: " + registry["continuity"]["recent"],
        "receipts: " + registry["continuity"]["receipts"],
        "instruction: " + registry["continuity"]["instruction"],
        "",
    ))
    return "\n".join(lines)


def projections(registry: dict[str, Any]) -> dict[str, str]:
    errors = validate(registry)
    if errors:
        raise ValueError("INVALID " + " ".join(errors))
    card = agent_card(registry)
    directory = {
        "schema": "commons-agent-directory/v1",
        "agents": [card],
        "runtime_signals": registry["runtime_signals"],
        "continuity": registry["continuity"],
    }
    return {
        "agents.txt": render_agents_txt(registry),
        "manifest.json": canonical(registry),
        "agent.json": canonical(card),
        "agents.json": canonical(directory),
        ".well-known/agent.json": canonical(card),
        ".well-known/agents.json": canonical(directory),
        "continuity.json": canonical({
            "schema": "commons-continuity-capsule/v1",
            **registry["continuity"],
            "runtime_signals": registry["runtime_signals"],
        }),
    }


def _write_projection(path: Path, data: bytes) -> None:
    # Follow an existing output symlink as write_bytes did; replace its target.
    target = path.resolve()
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = 0o644
    descriptor, staging = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                           dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            remaining = memoryview(data)
            while remaining:
                written = stream.write(remaining)
                if not written:
                    raise OSError(errno.EIO, "Incomplete projection write")
                remaining = remaining[written:]
            stream.flush()
            os.chmod(staging, mode)
            os.fsync(stream.fileno())
        os.replace(staging, target)
    finally:
        Path(staging).unlink(missing_ok=True)


def generate(root: Path = ROOT) -> None:
    for relative, content in projections(load_registry(root / "agent-discovery.json")).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_projection(path, content.encode("utf-8"))


def check(root: Path = ROOT) -> list[str]:
    expected = projections(load_registry(root / "agent-discovery.json"))
    return [relative for relative, content in expected.items() if not (root / relative).is_file() or (root / relative).read_bytes() != content.encode("utf-8")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "generate", "check"), nargs="?", default="check")
    args = parser.parse_args()
    if args.command == "validate":
        errors = validate(load_registry())
        print("VALID" if not errors else "INVALID " + " ".join(errors))
        return 0 if not errors else 1
    if args.command == "generate":
        generate()
        print("GENERATED " + " ".join(OUTPUTS))
        return 0
    stale = check()
    print("CURRENT" if not stale else "STALE " + " ".join(stale))
    return 0 if not stale else 1


if __name__ == "__main__":
    raise SystemExit(main())
