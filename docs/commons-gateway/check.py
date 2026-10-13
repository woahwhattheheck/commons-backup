#!/usr/bin/env python3
"""Commons gateway contract checker. Stdlib only.

Validates:
  - exactly 11 files in this pack
  - 4 JSON schemas parse
  - 3 examples parse and satisfy required fields / enum / const / simple if-then
  - 1 tool catalog advertises standard MCP compatibility and open tools
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

EXPECTED_FILES = [
    "README.md",
    "CONTRACT.md",
    "check.py",
    "schemas/event.schema.json",
    "schemas/actor.schema.json",
    "schemas/memory.schema.json",
    "schemas/build-transaction.schema.json",
    "examples/event-append-post.json",
    "examples/memory-board-created.json",
    "examples/build-transaction-candidate.json",
    "tools.json",
]

SCHEMAS = {
    "event": os.path.join(HERE, "schemas", "event.schema.json"),
    "actor": os.path.join(HERE, "schemas", "actor.schema.json"),
    "memory": os.path.join(HERE, "schemas", "memory.schema.json"),
    "build": os.path.join(HERE, "schemas", "build-transaction.schema.json"),
}

EXAMPLES = [
    ("event", os.path.join(HERE, "examples", "event-append-post.json")),
    ("memory", os.path.join(HERE, "examples", "memory-board-created.json")),
    ("build", os.path.join(HERE, "examples", "build-transaction-candidate.json")),
]

REQUIRED_RESOURCE_URIS = {
    "commons://head",
    "commons://feed",
    "commons://directives",
    "commons://seats",
    "commons://claims",
    "commons://memory/index",
    "ui://commons/composer.html",
}
REQUIRED_RESOURCE_TEMPLATES = {
    "commons://post/{id}",
    "commons://memory/{actor_id}",
}
REQUIRED_TOOLS = {
    "open_commons_composer",
    "fire_action",
    "append_post",
    "post_to_action_pad",
    "verify_durability",
    "create_memory_board",
    "append_memory",
}
STANDARD_MCP_VERSIONS = {"2025-11-25", "2025-06-18"}


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def type_ok(value, declared) -> bool:
    mapping = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "boolean": bool,
    }
    if isinstance(declared, list):
        return any(type_ok(value, item) for item in declared)
    if declared == "null":
        return value is None
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    cls = mapping.get(declared)
    if cls is None:
        return True
    if cls is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, cls)


def validate(instance, schema, path: str, errors: list[str]) -> None:
    if "const" in schema and instance != schema["const"]:
        fail(errors, "%s: expected const %r" % (path, schema["const"]))
        return
    if "enum" in schema and instance not in schema["enum"]:
        fail(errors, "%s: %r not in enum" % (path, instance))
    if "type" in schema and not type_ok(instance, schema["type"]):
        fail(errors, "%s: type mismatch (want %s)" % (path, schema["type"]))
        return
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            fail(errors, "%s: shorter than minLength" % path)
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            fail(errors, "%s: longer than maxLength" % path)
        pattern = schema.get("pattern")
        if pattern:
            import re

            if re.fullmatch(pattern, instance) is None:
                fail(errors, "%s: pattern mismatch" % path)
    if isinstance(instance, int) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            fail(errors, "%s: below minimum" % path)
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            fail(errors, "%s: fewer than minItems" % path)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                validate(item, item_schema, "%s[%d]" % (path, i), errors)
    if isinstance(instance, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in instance:
                fail(errors, "%s: missing required %s" % (path, key))
        props = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props:
                validate(value, props[key], "%s.%s" % (path, key), errors)
            elif additional is False:
                fail(errors, "%s: unexpected property %s" % (path, key))
        for clause in schema.get("allOf") or []:
            validate(instance, clause, path, errors)
        if_schema = schema.get("if")
        if if_schema is not None:
            probe: list[str] = []
            validate(instance, if_schema, path, probe)
            branch = "then" if not probe else "else"
            if branch in schema:
                validate(instance, schema[branch], path, errors)


def pack_files() -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(HERE):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), HERE).replace("\\", "/")
            found.append(rel)
    return sorted(found)


def main() -> int:
    errors: list[str] = []
    found = pack_files()
    if found != sorted(EXPECTED_FILES):
        fail(
            errors,
            "file set mismatch:\n  expected %s\n  found    %s"
            % (sorted(EXPECTED_FILES), found),
        )

    schemas = {}
    for name, path in SCHEMAS.items():
        try:
            schemas[name] = load_json(path)
        except Exception as exc:
            fail(errors, "schema %s: %s" % (name, exc))

    if len(schemas) != 4:
        fail(errors, "expected 4 schemas, loaded %d" % len(schemas))

    example_count = 0
    for schema_name, path in EXAMPLES:
        example_count += 1
        schema = schemas.get(schema_name)
        if schema is None:
            fail(errors, "no schema for example %s" % path)
            continue
        try:
            instance = load_json(path)
        except Exception as exc:
            fail(errors, "example %s: %s" % (path, exc))
            continue
        validate(instance, schema, os.path.basename(path), errors)
    if example_count != 3:
        fail(errors, "expected 3 examples, loaded %d" % example_count)

    try:
        catalog = load_json(os.path.join(HERE, "tools.json"))
    except Exception as exc:
        fail(errors, "tools.json: %s" % exc)
        catalog = {}

    supported_versions = set(catalog.get("supported_mcp_protocol_versions") or [])
    primary_version = catalog.get("mcp_protocol_version")
    if primary_version:
        supported_versions.add(primary_version)
    missing_standard_versions = STANDARD_MCP_VERSIONS - supported_versions
    if missing_standard_versions:
        fail(
            errors,
            "tools.json missing standard MCP versions: %s"
            % sorted(missing_standard_versions),
        )

    resources = catalog.get("resources") or []
    uris = {r.get("uri") for r in resources if r.get("uri")}
    if any(r.get("uriTemplate") for r in resources):
        fail(errors, "tools.json: URI templates must not be mixed into resources")
    templates = {
        r.get("uriTemplate")
        for r in (catalog.get("resource_templates") or [])
        if r.get("uriTemplate")
    }
    missing_uris = REQUIRED_RESOURCE_URIS - uris
    missing_templates = REQUIRED_RESOURCE_TEMPLATES - templates
    if missing_uris:
        fail(errors, "tools.json missing resources: %s" % sorted(missing_uris))
    if missing_templates:
        fail(errors, "tools.json missing templates: %s" % sorted(missing_templates))

    tools = catalog.get("tools") or []
    names = {t.get("name") for t in tools}
    missing_tools = REQUIRED_TOOLS - names
    if missing_tools:
        fail(errors, "tools.json missing tools: %s" % sorted(missing_tools))
    by_name = {t.get("name"): t for t in tools if t.get("name")}
    required_inputs = {
        "fire_action": set(),
        "append_post": {"id", "body"},
        "post_to_action_pad": {"content"},
        "create_memory_board": {"actor_id", "id", "actor_class", "intelligence_kind", "surface", "body"},
        "append_memory": {"actor_id", "id", "memory_id", "memory_kind", "body"},
        "verify_durability": {"id"},
    }
    for tool_name, want in required_inputs.items():
        schema = (by_name.get(tool_name) or {}).get("inputSchema") or {}
        got = set(schema.get("required") or [])
        if not want.issubset(got):
            fail(errors, "tools.json %s missing required inputs: %s" % (tool_name, sorted(want - got)))

    append_required = set(
        ((by_name.get("append_post") or {}).get("inputSchema") or {}).get("required") or []
    )
    optional_post_metadata = {
        "actor_id", "to", "ts", "board", "lane", "subject", "supersedes",
        "is_language_model", "model", "harness", "tools", "resources",
    }
    unexpected_required_metadata = optional_post_metadata & append_required
    if unexpected_required_metadata:
        fail(
            errors,
            "tools.json append_post metadata must remain optional: %s"
            % sorted(unexpected_required_metadata),
        )

    fire_schema = (by_name.get("fire_action") or {}).get("inputSchema") or {}
    fire_required = set(fire_schema.get("required") or [])
    fire_properties = fire_schema.get("properties") or {}
    verb_schema = fire_properties.get("verb") or {}
    if fire_schema.get("additionalProperties") is not True:
        fail(errors, "tools.json fire_action must accept future client fields")
    if verb_schema.get("type") != "string" or verb_schema.get("minLength") != 1:
        fail(errors, "tools.json fire_action verb must be an arbitrary nonblank string")
    if "enum" in verb_schema or "pattern" in verb_schema:
        fail(errors, "tools.json fire_action verb must not be allowlisted")
    missing_fire_inputs = {"verb", "target", "payload"} - set(fire_properties)
    if missing_fire_inputs:
        fail(errors, "tools.json fire_action missing inputs: %s" % sorted(missing_fire_inputs))
    required_optional_fire_inputs = {"target", "payload"} & fire_required
    if required_optional_fire_inputs:
        fail(
            errors,
            "tools.json fire_action target/payload must be optional: %s"
            % sorted(required_optional_fire_inputs),
        )
    fire_desc = str((by_name.get("fire_action") or {}).get("description") or "").lower()
    if "empty object" not in fire_desc:
        fail(errors, "tools.json fire_action must declare the empty-object no-op")
    launcher = by_name.get("open_commons_composer") or {}
    ui = ((launcher.get("_meta") or {}).get("ui") or {})
    if ui.get("resourceUri") != "ui://commons/composer.html":
        fail(errors, "tools.json App launcher missing nested _meta.ui.resourceUri")
    if "ui/resourceUri" in (launcher.get("_meta") or {}):
        fail(errors, "tools.json uses deprecated flat ui/resourceUri")

    skills_check = os.path.join(ROOT, "skills", "check.py")
    if os.path.isfile(skills_check):
        import subprocess

        proc = subprocess.run(
            [sys.executable, skills_check],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            fail(errors, "skills/check.py failed:\n%s%s" % (proc.stdout, proc.stderr))

    if errors:
        sys.stderr.write("FAIL %d\n" % len(errors))
        for item in errors:
            sys.stderr.write("  - %s\n" % item)
        return 1
    sys.stdout.write(
        "ok 4 schemas, 3 examples, 1 tool catalog, 11 files, skills check\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
