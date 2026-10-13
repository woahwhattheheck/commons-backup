#!/usr/bin/env python3
"""Fail closed when a retired product reappears on an active Commons surface."""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

SCHEMA = "commons.product-lifecycle.v1"
STATES = frozenset({"ACTIVE", "RETIRING", "RETIRED"})
WORKFLOW_PATH = Path(".github/workflows/capability-entrypoints.yml")
ACTIVE_STATIC_PATHS = (
    Path("host/payment_capability.py"),
    Path("revenue/outcome_commerce/catalog.json"),
)
# Root HTML that projects historical board receipts rather than a customer
# storefront. Retirement must not rewrite append-only board evidence.
HISTORICAL_ROOT_HTML = frozenset({"board.html"})
STRUCTURED_ACTIVE_JSON_PATHS = frozenset(
    {Path("revenue/outcome_commerce/catalog.json")}
)
ACTIVE_JSON_MAX_BYTES = 8_000_000
ACTIVE_JSON_MAX_NODES = 100_000
ACTIVE_JSON_MAX_TEXT_BYTES = 4_000_000
REQUIRED_WORKFLOW_EVENTS = ("push", "pull_request")
REQUIRED_WORKFLOW_STATIC_PATHS = frozenset(
    {
        WORKFLOW_PATH.as_posix(),
        "host/product_lifecycle_guard.py",
        "revenue/product_lifecycle/**",
        "*.html",
        *(path.as_posix() for path in ACTIVE_STATIC_PATHS),
    }
)
URL_RE = re.compile(r"(?:(?:https?):)?//[^\s\"'<>]+", re.IGNORECASE)
PRODUCT_KEYS = frozenset(
    {
        "id",
        "state",
        "checkout_urls",
        "catalog_sources",
        "effective_at",
        "provenance",
        "note",
    }
)


class LifecycleError(ValueError):
    """The lifecycle registry or one of its identities is invalid."""


@dataclass(frozen=True)
class Product:
    id: str
    state: str
    checkout_urls: tuple[str, ...]
    catalog_sources: tuple[str, ...]
    effective_at: str | None
    provenance: str | None
    note: str | None


@dataclass(frozen=True)
class Violation:
    product_id: str
    path: str
    kind: str
    identity: str


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LifecycleError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise LifecycleError("registry must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=lambda _raw: (_ for _ in ()).throw(
                LifecycleError("floating-point values are forbidden")
            ),
            parse_constant=lambda raw_value: (_ for _ in ()).throw(
                LifecycleError(f"non-finite JSON value forbidden: {raw_value}")
            ),
        )
    except LifecycleError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LifecycleError(f"invalid registry JSON: {exc}") from exc


def load_active_json_bytes(raw: bytes, label: str) -> Any:
    """Decode one active JSON surface with consumer-equivalent string semantics."""
    if len(raw) > ACTIVE_JSON_MAX_BYTES:
        raise LifecycleError(
            f"active JSON exceeds {ACTIVE_JSON_MAX_BYTES} bytes: {label}"
        )
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise LifecycleError(f"active JSON must be UTF-8: {label}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda raw_value: (_ for _ in ()).throw(
                LifecycleError(
                    f"non-finite active JSON value forbidden in {label}: {raw_value}"
                )
            ),
        )
    except LifecycleError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LifecycleError(f"invalid active JSON {label}: {exc}") from exc


def _bounded_json_strings(value: Any, label: str) -> tuple[str, ...]:
    """Return decoded JSON keys/string leaves under explicit work bounds."""
    stack: list[Any] = [value]
    strings: list[str] = []
    nodes = 0
    text_bytes = 0
    while stack:
        current = stack.pop()
        nodes += 1
        if nodes > ACTIVE_JSON_MAX_NODES:
            raise LifecycleError(
                f"active JSON node budget exceeded in {label}: {ACTIVE_JSON_MAX_NODES}"
            )
        if type(current) is dict:
            if nodes + (2 * len(current)) > ACTIVE_JSON_MAX_NODES:
                raise LifecycleError(
                    f"active JSON node budget exceeded in {label}: {ACTIVE_JSON_MAX_NODES}"
                )
            for key, child in reversed(tuple(current.items())):
                stack.append(child)
                stack.append(key)
            continue
        if type(current) is list:
            if nodes + len(current) > ACTIVE_JSON_MAX_NODES:
                raise LifecycleError(
                    f"active JSON node budget exceeded in {label}: {ACTIVE_JSON_MAX_NODES}"
                )
            stack.extend(reversed(current))
            continue
        if type(current) is str:
            try:
                encoded = current.encode("utf-8", "strict")
            except UnicodeEncodeError as exc:
                raise LifecycleError(
                    f"active JSON contains non-UTF-8 string in {label}"
                ) from exc
            text_bytes += len(encoded)
            if text_bytes > ACTIVE_JSON_MAX_TEXT_BYTES:
                raise LifecycleError(
                    f"active JSON text budget exceeded in {label}: "
                    f"{ACTIVE_JSON_MAX_TEXT_BYTES}"
                )
            strings.append(current)
            continue
        if current is None or type(current) in (bool, int):
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise LifecycleError(f"active JSON non-finite number in {label}")
            continue
        raise LifecycleError(
            f"active JSON contains unsupported value type in {label}: "
            f"{type(current).__name__}"
        )
    return tuple(strings)


def _plain_str(value: Any, field: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str or not value.strip():
        raise LifecycleError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise LifecycleError(f"{field} must not have surrounding whitespace")
    return value


def _normalized_host(parsed: Any, raw: str) -> str:
    try:
        port = parsed.port
    except ValueError as exc:
        raise LifecycleError(f"invalid checkout URL: {raw}") from exc
    if parsed.username is not None or parsed.password is not None:
        raise LifecycleError(f"checkout URL must not contain credentials: {raw}")
    if port not in (None, 443, 80):
        raise LifecycleError(f"checkout URL must not use a non-default port: {raw}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise LifecycleError(f"checkout URL missing host: {raw}")
    return host


def _normalized_path(parsed: Any, raw: str) -> str:
    path = unquote(parsed.path)
    if not path or path == "/":
        raise LifecycleError(f"checkout URL missing checkout path: {raw}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path):
        raise LifecycleError(f"checkout URL contains control characters: {raw}")
    while len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def canonical_checkout_identity(value: str) -> str:
    """Strict canonical identity for registry-controlled checkout URLs."""
    raw = _plain_str(value, "checkout URL")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise LifecycleError(f"invalid checkout URL: {raw}") from exc
    if parsed.scheme.lower() != "https":
        raise LifecycleError(f"checkout URL must use https: {raw}")
    if parsed.query or parsed.fragment:
        raise LifecycleError(f"checkout URL must not contain query/fragment: {raw}")
    host = _normalized_host(parsed, raw)
    if parsed.port == 80:
        raise LifecycleError(f"checkout URL must not use HTTP port 80: {raw}")
    path = _normalized_path(parsed, raw)
    return f"https://{host}{path}"


def canonical_active_checkout_identity(value: str) -> str:
    """Browser-facing identity used for active-surface alias detection.

    Query and fragment do not change the protected checkout identity. Protocol-
    relative and HTTP spellings are normalized to the registry's HTTPS identity
    so a stale storefront cannot evade a tombstone by changing only URL syntax.
    """
    raw = _plain_str(value, "active checkout URL")
    absolute = "https:" + raw if raw.startswith("//") else raw
    try:
        parsed = urlsplit(absolute)
    except ValueError as exc:
        raise LifecycleError(f"invalid active checkout URL: {raw}") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise LifecycleError(f"active checkout URL must be HTTP(S): {raw}")
    host = _normalized_host(parsed, raw)
    path = _normalized_path(parsed, raw)
    return f"https://{host}{path}"


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise LifecycleError(f"{field} must be an array")
    out: list[str] = []
    for index, item in enumerate(value):
        parsed = _plain_str(item, f"{field}[{index}]")
        if not isinstance(parsed, str):
            raise LifecycleError(f"{field}[{index}] must be a string")
        out.append(parsed)
    return tuple(out)


def validate_registry(doc: Any) -> tuple[Product, ...]:
    if type(doc) is not dict:
        raise LifecycleError("registry root must be an object")
    if set(doc) != {"schema", "products"}:
        raise LifecycleError("registry root keys must be exactly schema, products")
    if doc["schema"] != SCHEMA:
        raise LifecycleError(f"unsupported lifecycle schema: {doc['schema']!r}")
    if type(doc["products"]) is not list:
        raise LifecycleError("products must be an array")

    products: list[Product] = []
    ids: set[str] = set()
    checkout_owners: dict[str, str] = {}
    source_owners: dict[str, str] = {}

    for index, raw_product in enumerate(doc["products"]):
        if type(raw_product) is not dict:
            raise LifecycleError(f"products[{index}] must be an object")
        unknown = set(raw_product) - PRODUCT_KEYS
        required = {"id", "state", "checkout_urls", "catalog_sources"}
        missing = required - set(raw_product)
        if unknown:
            raise LifecycleError(
                f"products[{index}] has unknown keys: {', '.join(sorted(unknown))}"
            )
        if missing:
            raise LifecycleError(
                f"products[{index}] missing keys: {', '.join(sorted(missing))}"
            )
        product_id = _plain_str(raw_product["id"], f"products[{index}].id")
        state = _plain_str(raw_product["state"], f"products[{index}].state")
        if not isinstance(product_id, str) or not isinstance(state, str):
            raise LifecycleError(f"products[{index}] id/state must be strings")
        if product_id in ids:
            raise LifecycleError(f"duplicate product id: {product_id}")
        ids.add(product_id)
        if state not in STATES:
            raise LifecycleError(f"invalid lifecycle state for {product_id}: {state}")

        checkout_urls = _string_list(
            raw_product["checkout_urls"], f"products[{index}].checkout_urls"
        )
        catalog_sources = _string_list(
            raw_product["catalog_sources"], f"products[{index}].catalog_sources"
        )
        canonical_urls: list[str] = []
        local_urls: set[str] = set()
        for url in checkout_urls:
            canonical = canonical_checkout_identity(url)
            if canonical in local_urls:
                raise LifecycleError(
                    f"duplicate checkout identity within {product_id}: {canonical}"
                )
            local_urls.add(canonical)
            prior = checkout_owners.get(canonical)
            if prior is not None:
                raise LifecycleError(
                    f"checkout identity shared by {prior} and {product_id}: {canonical}"
                )
            checkout_owners[canonical] = product_id
            canonical_urls.append(canonical)

        seen_sources: set[str] = set()
        for source in catalog_sources:
            if source.startswith("/") or "\\" in source or ".." in Path(source).parts:
                raise LifecycleError(
                    f"catalog source must be a normalized repository-relative path: {source}"
                )
            if source in seen_sources:
                raise LifecycleError(
                    f"duplicate catalog source within {product_id}: {source}"
                )
            seen_sources.add(source)
            prior = source_owners.get(source)
            if prior is not None:
                raise LifecycleError(
                    f"catalog source shared by {prior} and {product_id}: {source}"
                )
            source_owners[source] = product_id

        effective_at = _plain_str(
            raw_product.get("effective_at"),
            f"products[{index}].effective_at",
            allow_none=True,
        )
        provenance = _plain_str(
            raw_product.get("provenance"),
            f"products[{index}].provenance",
            allow_none=True,
        )
        note = _plain_str(
            raw_product.get("note"),
            f"products[{index}].note",
            allow_none=True,
        )
        if state == "RETIRED" and effective_at is None:
            raise LifecycleError(f"RETIRED product {product_id} requires effective_at")

        products.append(
            Product(
                id=product_id,
                state=state,
                checkout_urls=tuple(canonical_urls),
                catalog_sources=catalog_sources,
                effective_at=effective_at,
                provenance=provenance,
                note=note,
            )
        )
    return tuple(products)


def load_registry(path: Path) -> tuple[Product, ...]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LifecycleError(f"cannot read lifecycle registry: {path}") from exc
    return validate_registry(load_json_bytes(raw))


def enforce_retired_monotonicity(
    base_products: Iterable[Product], candidate_products: Iterable[Product]
) -> None:
    """A candidate may not erase or weaken a tombstone already RETIRED in base."""
    base = {product.id: product for product in base_products}
    candidate = {product.id: product for product in candidate_products}
    for product_id, old in sorted(base.items()):
        if old.state != "RETIRED":
            continue
        new = candidate.get(product_id)
        if new is None:
            raise LifecycleError(f"retired product removed from lifecycle registry: {product_id}")
        if new.state != "RETIRED":
            raise LifecycleError(
                f"retired product downgraded from RETIRED: {product_id} -> {new.state}"
            )
        lost_urls = sorted(set(old.checkout_urls) - set(new.checkout_urls))
        if lost_urls:
            raise LifecycleError(
                f"retired checkout identities removed from {product_id}: {', '.join(lost_urls)}"
            )
        lost_sources = sorted(set(old.catalog_sources) - set(new.catalog_sources))
        if lost_sources:
            raise LifecycleError(
                f"retired catalog sources removed from {product_id}: {', '.join(lost_sources)}"
            )


def active_surface_paths(repo_root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for candidate in repo_root.glob("*.html"):
        if candidate.is_file() and candidate.name not in HISTORICAL_ROOT_HTML:
            paths.add(candidate)
    for rel in ACTIVE_STATIC_PATHS:
        candidate = repo_root / rel
        if candidate.is_file():
            paths.add(candidate)
    return tuple(sorted(paths, key=lambda p: p.as_posix()))


def _active_url_identities(text: str) -> tuple[set[str], tuple[str, ...]]:
    identities: set[str] = set()
    malformed: list[str] = []
    for match in URL_RE.finditer(html.unescape(text)):
        token = match.group(0).rstrip(".,);]")
        try:
            identities.add(canonical_active_checkout_identity(token))
        except LifecycleError:
            malformed.append(token)
    return identities, tuple(malformed)


def _checkout_hosts(products: Iterable[Product]) -> set[str]:
    hosts: set[str] = set()
    for product in products:
        for checkout in product.checkout_urls:
            hosts.add(urlsplit(checkout).hostname or "")
    return hosts


def _malformed_mentions_retired_host(token: str, retired_hosts: set[str]) -> bool:
    folded = token.casefold()
    return any(host and host.casefold() in folded for host in retired_hosts)


_WORKFLOW_EVENT_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")
_WORKFLOW_PATHS_RE = re.compile(
    r"^    paths:\s*(?:(?:&([A-Za-z0-9_-]+))|(?:\*([A-Za-z0-9_-]+)))?"
    r"\s*(?:#.*)?$"
)
_WORKFLOW_PATH_ITEM_RE = re.compile(
    r"^      -\s+'((?:[^']|'')*)'\s*(?:#.*)?$"
)


def _workflow_event_paths(text: str) -> dict[str, tuple[str, ...]]:
    """Parse the intentionally constrained `on.<event>.paths` workflow subset.

    Fail closed on representation changes rather than accepting path-looking text
    from comments, heredocs, unrelated lists, or other YAML locations.
    """
    lines = text.splitlines()
    on_rows = [
        index
        for index, line in enumerate(lines)
        if line.rstrip() == "on:" and line == line.lstrip(" ")
    ]
    if len(on_rows) != 1:
        raise LifecycleError("lifecycle workflow must contain exactly one top-level on:")
    start = on_rows[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise LifecycleError("tabs are forbidden in lifecycle workflow indentation")
        if len(line) - len(line.lstrip(" ")) == 0:
            end = index
            break

    sections: dict[str, tuple[int, int]] = {}
    index = start
    while index < end:
        line = lines[index]
        match = _WORKFLOW_EVENT_RE.fullmatch(line)
        if match:
            event = match.group(1)
            if event in sections:
                raise LifecycleError(f"duplicate lifecycle workflow event: {event}")
            section_end = end
            probe = index + 1
            while probe < end:
                candidate = lines[probe]
                if candidate.strip() and not candidate.lstrip().startswith("#"):
                    indent = len(candidate) - len(candidate.lstrip(" "))
                    if indent <= 2:
                        section_end = probe
                        break
                probe += 1
            sections[event] = (index + 1, section_end)
            index = section_end
            continue
        index += 1

    anchors: dict[str, tuple[str, ...]] = {}
    specs: dict[str, tuple[str, str | tuple[str, ...]]] = {}
    for event, (section_start, section_end) in sections.items():
        found: tuple[str, str | tuple[str, ...]] | None = None
        row = section_start
        while row < section_end:
            line = lines[row]
            if line.strip() and not line.lstrip().startswith("#"):
                indent = len(line) - len(line.lstrip(" "))
                if indent == 4 and line.lstrip().startswith("paths-ignore:"):
                    raise LifecycleError(
                        f"lifecycle workflow paths-ignore is forbidden for event: {event}"
                    )
                if indent == 4 and line.lstrip().startswith("paths:"):
                    if found is not None:
                        raise LifecycleError(
                            f"duplicate lifecycle workflow paths key for event: {event}"
                        )
                    match = _WORKFLOW_PATHS_RE.fullmatch(line)
                    if match is None:
                        raise LifecycleError(
                            f"unsupported lifecycle workflow paths syntax for event: {event}"
                        )
                    anchor_name, alias_name = match.groups()
                    if alias_name is not None:
                        found = ("alias", alias_name)
                    else:
                        values: list[str] = []
                        probe = row + 1
                        while probe < section_end:
                            item_line = lines[probe]
                            if not item_line.strip() or item_line.lstrip().startswith("#"):
                                probe += 1
                                continue
                            item_indent = len(item_line) - len(item_line.lstrip(" "))
                            if item_indent <= 4:
                                break
                            item_match = _WORKFLOW_PATH_ITEM_RE.fullmatch(item_line)
                            if item_match is None:
                                raise LifecycleError(
                                    f"unsupported lifecycle workflow path item for event: "
                                    f"{event}"
                                )
                            value = item_match.group(1).replace("''", "'")
                            if value.startswith("!"):
                                raise LifecycleError(
                                    f"negative lifecycle workflow path filter is forbidden "
                                    f"for event {event}: {value}"
                                )
                            values.append(value)
                            probe += 1
                        if not values:
                            raise LifecycleError(
                                f"lifecycle workflow paths list is empty for event: {event}"
                            )
                        direct = tuple(values)
                        found = ("direct", direct)
                        if anchor_name is not None:
                            if anchor_name in anchors:
                                raise LifecycleError(
                                    f"duplicate lifecycle workflow anchor: {anchor_name}"
                                )
                            anchors[anchor_name] = direct
            row += 1
        if found is not None:
            specs[event] = found

    resolved: dict[str, tuple[str, ...]] = {}
    for event in REQUIRED_WORKFLOW_EVENTS:
        spec = specs.get(event)
        if spec is None:
            raise LifecycleError(
                f"lifecycle workflow missing on.{event}.paths"
            )
        kind, payload = spec
        if kind == "alias":
            if type(payload) is not str:
                raise LifecycleError(
                    f"invalid lifecycle workflow alias payload for event: {event}"
                )
            direct = anchors.get(payload)
            if direct is None:
                raise LifecycleError(
                    f"lifecycle workflow unresolved paths alias for {event}: {payload}"
                )
            resolved[event] = direct
        else:
            if type(payload) is not tuple:
                raise LifecycleError(
                    f"invalid lifecycle workflow paths payload for event: {event}"
                )
            resolved[event] = payload
    return resolved


def validate_workflow_source_coverage(repo_root: Path, products: Iterable[Product]) -> None:
    workflow = repo_root / WORKFLOW_PATH
    try:
        text = workflow.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise LifecycleError(f"cannot read lifecycle workflow coverage: {workflow}") from exc

    event_paths = _workflow_event_paths(text)
    required = set(REQUIRED_WORKFLOW_STATIC_PATHS)
    for product in products:
        required.update(product.catalog_sources)

    for event in REQUIRED_WORKFLOW_EVENTS:
        available = set(event_paths[event])
        missing = sorted(required - available)
        if missing:
            raise LifecycleError(
                f"lifecycle workflow on.{event}.paths missing required trigger(s): "
                f"{', '.join(missing)}"
            )


def scan_active_surfaces(
    repo_root: Path, products: Iterable[Product]
) -> tuple[Violation, ...]:
    retired = tuple(product for product in products if product.state == "RETIRED")
    if not retired:
        return ()
    violations: list[Violation] = []
    retired_hosts = _checkout_hosts(retired)
    for path in active_surface_paths(repo_root):
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8", "strict")
        except (OSError, UnicodeDecodeError) as exc:
            raise LifecycleError(f"cannot read active surface: {path}") from exc
        rel_path = path.relative_to(repo_root)
        rel = rel_path.as_posix()
        views: list[str] = [text]
        if rel_path in STRUCTURED_ACTIVE_JSON_PATHS:
            doc = load_active_json_bytes(raw, rel)
            views.extend(_bounded_json_strings(doc, rel))

        found_urls: set[str] = set()
        malformed_urls: list[str] = []
        for view in views:
            view_urls, view_malformed = _active_url_identities(view)
            found_urls.update(view_urls)
            malformed_urls.extend(view_malformed)

        for token in malformed_urls:
            if _malformed_mentions_retired_host(token, retired_hosts):
                violations.append(
                    Violation("*", rel, "ambiguous_checkout_url", token)
                )
        for product in retired:
            for checkout in product.checkout_urls:
                if checkout in found_urls:
                    violations.append(
                        Violation(product.id, rel, "checkout_url", checkout)
                    )
            for source in product.catalog_sources:
                if any(source in view for view in views):
                    violations.append(
                        Violation(product.id, rel, "catalog_source_reference", source)
                    )

    for product in retired:
        for source in product.catalog_sources:
            source_path = repo_root / source
            if source_path.exists():
                if not source_path.is_file():
                    raise LifecycleError(
                        f"retired catalog source path is not a regular file: {source}"
                    )
                violations.append(
                    Violation(product.id, source, "catalog_source_present", source)
                )
    return tuple(
        sorted(
            set(violations),
            key=lambda row: (row.product_id, row.path, row.kind, row.identity),
        )
    )


def check_repo(
    repo_root: Path,
    registry_path: Path | None = None,
    base_registry_path: Path | None = None,
) -> tuple[Violation, ...]:
    registry = registry_path or repo_root / "revenue/product_lifecycle/registry.json"
    products = load_registry(registry)
    validate_workflow_source_coverage(repo_root, products)
    if base_registry_path is not None:
        base_products = load_registry(base_registry_path)
        enforce_retired_monotonicity(base_products, products)
    return scan_active_surfaces(repo_root, products)


def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--registry")
    parser.add_argument("--base-registry")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    registry = Path(args.registry).resolve() if args.registry else None
    base_registry = Path(args.base_registry).resolve() if args.base_registry else None
    try:
        violations = check_repo(repo_root, registry, base_registry)
    except LifecycleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    if violations:
        print(
            json.dumps(
                {
                    "ok": False,
                    "violations": [
                        {
                            "product_id": row.product_id,
                            "path": row.path,
                            "kind": row.kind,
                            "identity": row.identity,
                        }
                        for row in violations
                    ],
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps({"ok": True, "violations": []}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
