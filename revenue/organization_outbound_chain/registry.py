"""Closed provider inventory and repository bypass scanner.

This registry is deliberately redundant with the typed provider boundary: CI checks
that every declared adapter and boundary exists, then rejects repository code that
reaches lower one-shot primitives or provider mutation surfaces outside the guarded
chain.  Host connector identities are also enumerated so runtime/operator policy can
bind the same closed set; repository CI cannot intercept an out-of-process connector
call that never enters repository code.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .provider_boundary import (
    ProviderBoundaryError,
    registered_boundary_generation,
    registered_boundary_types,
)


@dataclass(frozen=True)
class Adapter:
    provider: str
    module_path: str
    callable_name: str
    boundary_module_path: str
    boundary_class_name: str
    transport_method: str
    host_mutation_identities: tuple[str, ...]


ADAPTERS = (
    Adapter(
        "gmail",
        "revenue/organization_outbound_chain/adapters.py",
        "gmail_initial_outreach",
        "revenue/organization_outbound_chain/provider_boundary.py",
        "GmailBoundary",
        "gmail_send_message",
        (
            "mcp__Gmail__send_email",
            "mcp__Gmail__send_draft",
            "mcp__Gmail__forward_emails",
        ),
    ),
    Adapter(
        "slack_dm",
        "revenue/organization_outbound_chain/adapters.py",
        "slack_dm_initial_outreach",
        "revenue/organization_outbound_chain/provider_boundary.py",
        "SlackDmBoundary",
        "slack_send_dm",
        (
            "mcp__Slack__slack_send_message",
            "mcp__Slack__slack_schedule_message",
        ),
    ),
    Adapter(
        "discord",
        "revenue/organization_outbound_chain/adapters.py",
        "discord_initial_outreach",
        "revenue/organization_outbound_chain/provider_boundary.py",
        "DiscordBoundary",
        "discord_send_message",
        (
            "discord.Webhook.send",
            "discord.webhook.execute",
        ),
    ),
    Adapter(
        "webhook_mail",
        "revenue/organization_outbound_chain/adapters.py",
        "webhook_mail_initial_outreach",
        "revenue/organization_outbound_chain/provider_boundary.py",
        "WebhookMailBoundary",
        "webhook_mail_send",
        ("http.webhook_mail.post",),
    ),
)

_EXPECTED_PROVIDERS = ("gmail", "slack_dm", "discord", "webhook_mail")
_PROVIDER_METHODS = frozenset(item.transport_method for item in ADAPTERS)
_HOST_MUTATION_IDENTITIES = frozenset(
    identity for item in ADAPTERS for identity in item.host_mutation_identities
)

# Concrete SDK/API spellings that constitute provider-send surfaces if they appear
# in repository code outside the registered boundary implementation.
PROVIDER_MARKERS = (
    "smtplib.SMTP",
    ".sendmail(",
    "users().messages().send(",
    "chat_postMessage(",
    "slack_send_message(",
    "discord.Webhook",
    "hooks.slack.com/services/",
    "api.sendgrid.com/",
    "api.mailgun.net/",
    *tuple(sorted(_HOST_MUTATION_IDENTITIES)),
)

_LOW_LEVEL_TARGETS = {
    "revenue.initial_outreach_slot.execute_initial_outreach": "direct-initial-outreach",
    "revenue.initial_outreach_slot.slot.execute_initial_outreach": "direct-initial-outreach",
    "revenue.outbound_send_consumer.consume_once": "direct-terminal-consumer",
    "revenue.outbound_send_consumer.consume.consume_once": "direct-terminal-consumer",
    "integrations.grok_slack.bridge.slack_web_call": "direct-slack-web-api-helper",
}
_LOW_LEVEL_MODULES = {
    "revenue.initial_outreach_slot",
    "revenue.initial_outreach_slot.slot",
    "revenue.outbound_send_consumer",
    "revenue.outbound_send_consumer.consume",
    "integrations.grok_slack.bridge",
}
_LOW_LEVEL_PRIMITIVES = {
    "revenue/initial_outreach_slot/slot.py",
    "revenue/outbound_send_consumer/consume.py",
}
_CHAIN_FILES = {
    "revenue/organization_outbound_chain/chain.py",
    "revenue/organization_outbound_chain/adapters.py",
    "revenue/organization_outbound_chain/provider_boundary.py",
    "revenue/organization_outbound_chain/registry.py",
}
_PROVIDER_METHOD_ALLOWED = {
    "revenue/organization_outbound_chain/provider_boundary.py",
}
_MARKER_ALLOWED = {
    "revenue/organization_outbound_chain/provider_boundary.py",
    "revenue/organization_outbound_chain/registry.py",
}
_CODE_SUFFIXES = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".rb", ".go", ".rs", ".java", ".kt", ".kts", ".sh", ".ps1",
})

# These two integrations are inbound-triggered Commons peer bridges. Their Slack
# mutation is a reply to the originating internal workspace thread, not commercial
# customer/prospect outreach. Exemption requires BOTH the exact reviewed Git blob
# and a fail-closed internal-scope guard contract. Hash identity alone is insufficient.
_INTERNAL_PROVIDER_GUARD_MARKERS = (
    "class InternalSlackScope",
    "conversations_info(",
    "self.scope.require_channel(channel)",
    "\"is_ext_shared\"",
    "\"is_org_shared\"",
    "\"is_pending_ext_shared\"",
    "\"is_member\"",
    'payload.get("team_id") != team_id',
)
_INTERNAL_PROVIDER_MARKER_EXEMPTIONS = (
    (
        "integrations/gemini_slack/bridge.py",
        "85dcb65a61af0aa6b198b014ebb16217a83a4661",
        _INTERNAL_PROVIDER_GUARD_MARKERS,
    ),
    (
        "integrations/grok_slack/bridge.py",
        "123a179e3071c0b700ac76baa8bd52631c180696",
        _INTERNAL_PROVIDER_GUARD_MARKERS,
    ),
)

# If this interpreter cannot parse a Python generation, we still fail closed on
# revenue/outbound-sensitive lexical seams instead of treating SyntaxError itself
# as proof of a provider bypass.
_PARSE_INCOMPATIBLE_SENSITIVE_MARKERS = (
    "execute_initial_outreach",
    "consume_once",
    "gmail_send_message",
    "slack_send_dm",
    "discord_send_message",
    "webhook_mail_send",
)


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _is_test(path: str) -> bool:
    name = Path(path).name
    return (
        name.startswith("test_")
        or "/tests/" in f"/{path}"
        or name.endswith("_test.py")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
    )


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def _target_label(dotted: str | None) -> str | None:
    if not dotted:
        return None
    if dotted in _LOW_LEVEL_TARGETS:
        return _LOW_LEVEL_TARGETS[dotted]
    for target, label in _LOW_LEVEL_TARGETS.items():
        if dotted.endswith("." + target):
            return label
    return None


def _python_call_violations(
    tree: ast.AST,
    *,
    _provider_methods: frozenset[str] = _PROVIDER_METHODS,
) -> set[str]:
    """Resolve direct imports, aliases and simple rebinding of guarded callsites."""
    callable_aliases: dict[str, str] = {}
    module_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                module_aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                target = f"{module}.{alias.name}" if module else alias.name
                label = _target_label(target)
                if label:
                    callable_aliases[local] = label
                if target in _LOW_LEVEL_MODULES:
                    module_aliases[local] = target

    # Resolve one or more simple alias assignments, including:
    # f = consume_once; f = module.consume_once.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            names: list[str] = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node.target, ast.Name):
                names = [node.target.id]
            label = None
            if isinstance(value, ast.Name):
                label = callable_aliases.get(value.id)
            else:
                dotted = _dotted(value) if value is not None else None
                if dotted:
                    root, _, rest = dotted.partition(".")
                    if root in module_aliases:
                        dotted = module_aliases[root] + ("." + rest if rest else "")
                    label = _target_label(dotted)
            if label:
                for name in names:
                    if callable_aliases.get(name) != label:
                        callable_aliases[name] = label
                        changed = True

    violations: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            label = callable_aliases.get(fn.id)
            if label:
                violations.add(label)
        else:
            dotted = _dotted(fn)
            if dotted:
                root, _, rest = dotted.partition(".")
                if root in module_aliases:
                    dotted = module_aliases[root] + ("." + rest if rest else "")
                label = _target_label(dotted)
                if label:
                    violations.add(label)
            if isinstance(fn, ast.Attribute) and fn.attr in _provider_methods:
                violations.add(f"provider-transport-method:{fn.attr}")

        # Literal getattr(module, "consume_once") / getattr(..., provider_method)
        if (
            isinstance(fn, ast.Name)
            and fn.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            attr = node.args[1].value
            if attr == "execute_initial_outreach":
                violations.add("dynamic-initial-outreach")
            elif attr == "consume_once":
                violations.add("dynamic-terminal-consumer")
            elif attr == "slack_web_call":
                violations.add("dynamic-slack-web-api-helper")
            elif attr in _provider_methods:
                violations.add(f"dynamic-provider-transport-method:{attr}")
    return violations



def _ast_expr_key(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _dict_channel_expr(node: ast.AST | None) -> ast.AST | None:
    if not isinstance(node, ast.Dict):
        return None
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == "channel":
            return value
    return None


def _internal_slack_callsite_violations(tree: ast.AST) -> set[str]:
    """Require each exempt Slack mutation to have a same-channel guard first.

    The reviewed bridge blob remains an identity fence, but identity alone never
    exempts an entire file. Direct WebClient chat_postMessage calls and the raw
    slack_web_call("chat.postMessage", ...) helper are each paired with a prior
    require_channel() call in the same function and for the same channel
    expression.
    """

    guards: dict[int, list[tuple[int, str | None]]] = {}
    mutations: list[tuple[int, str, int, str | None, str]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[ast.AST] = []

        def _visit_function(self, node: ast.AST) -> None:
            self.stack.append(node)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

        def visit_Call(self, node: ast.Call) -> None:
            if self.stack:
                function = self.stack[-1]
                function_id = id(function)
                function_name = str(getattr(function, "name", "<function>"))

                if isinstance(node.func, ast.Attribute) and node.func.attr == "require_channel":
                    guard_expr = node.args[0] if node.args else None
                    guards.setdefault(function_id, []).append(
                        (node.lineno, _ast_expr_key(guard_expr))
                    )

                mutation_kind: str | None = None
                channel_expr: ast.AST | None = None
                if isinstance(node.func, ast.Attribute) and node.func.attr == "chat_postMessage":
                    mutation_kind = "webclient-chat-post"
                    for keyword in node.keywords:
                        if keyword.arg == "channel":
                            channel_expr = keyword.value
                            break
                else:
                    dotted = _dotted(node.func)
                    if (
                        dotted
                        and dotted.endswith("slack_web_call")
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == "chat.postMessage"
                    ):
                        mutation_kind = "raw-webapi-chat-post"
                        payload_expr: ast.AST | None = node.args[2] if len(node.args) >= 3 else None
                        if payload_expr is None:
                            for keyword in node.keywords:
                                if keyword.arg == "payload":
                                    payload_expr = keyword.value
                                    break
                        channel_expr = _dict_channel_expr(payload_expr)

                if mutation_kind is not None:
                    mutations.append(
                        (
                            function_id,
                            function_name,
                            node.lineno,
                            _ast_expr_key(channel_expr),
                            mutation_kind,
                        )
                    )
            self.generic_visit(node)

    Visitor().visit(tree)
    violations: set[str] = set()
    for function_id, function_name, line, channel_key, kind in mutations:
        if channel_key is None:
            violations.add(
                f"internal-provider-callsite-channel-unknown:{function_name}:{line}:{kind}"
            )
            continue
        guarded = any(
            guard_line < line and guard_key == channel_key
            for guard_line, guard_key in guards.get(function_id, ())
        )
        if not guarded:
            violations.add(
                f"internal-provider-callsite-unguarded:{function_name}:{line}:{kind}"
            )
    return violations

def _top_level_defs(tree: ast.AST) -> tuple[set[str], set[str]]:
    functions: set[str] = set()
    classes: set[str] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
    return functions, classes


def validate_registry(
    repository_root: str | Path,
    *,
    _trusted_adapters: tuple[Adapter, ...] = ADAPTERS,
    _expected_providers: tuple[str, ...] = _EXPECTED_PROVIDERS,
    _provider_methods: frozenset[str] = _PROVIDER_METHODS,
) -> list[str]:
    """Prove the first-load provider manifest and runtime generation are closed.

    Public ADAPTERS and provider-boundary ClassVars are compatibility views only.
    Ordinary post-import rebinding cannot redefine the generation used here; any
    visible drift is reported as a failure instead of becoming new authority.
    """
    root = Path(repository_root)
    violations: list[str] = []
    if ADAPTERS != _trusted_adapters:
        violations.append("registry:public-manifest-drift")

    providers = tuple(item.provider for item in _trusted_adapters)
    if providers != _expected_providers:
        violations.append("registry:provider-set-not-exact")
    if len(set(providers)) != len(providers):
        violations.append("registry:duplicate-provider")
    if len(_provider_methods) != len(_trusted_adapters):
        violations.append("registry:duplicate-transport-method")

    try:
        runtime_generation = registered_boundary_generation()
        runtime_types = registered_boundary_types()
    except ProviderBoundaryError:
        violations.append("registry:runtime-boundary-metadata-drift")
        return sorted(set(violations))

    runtime_by_name = {
        boundary_type.__name__: (
            boundary_type,
            provider,
            transport_method,
            tuple(host_identities),
        )
        for boundary_type, provider, transport_method, host_identities
        in runtime_generation
    }
    if len(runtime_by_name) != len(runtime_generation):
        violations.append("registry:duplicate-runtime-boundary-type")
    if tuple(entry[0] for entry in runtime_generation) != runtime_types:
        violations.append("registry:runtime-boundary-type-view-mismatch")
    if set(runtime_by_name) != {
        item.boundary_class_name for item in _trusted_adapters
    }:
        violations.append("registry:runtime-boundary-set-not-exact")

    for item in _trusted_adapters:
        runtime_entry = runtime_by_name.get(item.boundary_class_name)
        if runtime_entry is None:
            violations.append(f"registry:{item.provider}:runtime-boundary-missing")
        else:
            _boundary_type, provider, transport_method, host_identities = runtime_entry
            if provider != item.provider:
                violations.append(f"registry:{item.provider}:runtime-provider-mismatch")
            if transport_method != item.transport_method:
                violations.append(
                    f"registry:{item.provider}:runtime-transport-method-mismatch"
                )
            if host_identities != item.host_mutation_identities:
                violations.append(
                    f"registry:{item.provider}:runtime-host-identities-mismatch"
                )

        if not item.host_mutation_identities:
            violations.append(f"registry:{item.provider}:host-mutation-identities-empty")
        adapter_path = root / item.module_path
        boundary_path = root / item.boundary_module_path
        try:
            adapter_tree = ast.parse(adapter_path.read_text(encoding="utf-8"), filename=item.module_path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"registry:{item.provider}:adapter-unreadable:{type(exc).__name__}")
            continue
        try:
            boundary_tree = ast.parse(boundary_path.read_text(encoding="utf-8"), filename=item.boundary_module_path)
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"registry:{item.provider}:boundary-unreadable:{type(exc).__name__}")
            continue
        adapter_functions, _ = _top_level_defs(adapter_tree)
        _, boundary_classes = _top_level_defs(boundary_tree)
        boundary_methods = {
            node.name
            for node in ast.walk(boundary_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if item.callable_name not in adapter_functions:
            violations.append(f"registry:{item.provider}:adapter-callable-missing")
        if item.boundary_class_name not in boundary_classes:
            violations.append(f"registry:{item.provider}:boundary-class-missing")
        if item.transport_method not in boundary_methods:
            violations.append(f"registry:{item.provider}:transport-method-missing")

    return sorted(set(violations))


def _iter_code_files(
    root: Path,
    *,
    _code_suffixes: frozenset[str] = _CODE_SUFFIXES,
) -> Iterable[Path]:
    for file in root.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in _code_suffixes:
            continue
        parts = set(file.parts)
        if ".git" in parts or "node_modules" in parts or "__pycache__" in parts:
            continue
        yield file


_QUOTED_STRING = re.compile(
    r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""",
    re.DOTALL,
)


def _compact_provider_text(value: str) -> str:
    """Conservative lexical view defeating simple split-string construction.

    Keep alphanumerics, underscore, dots, and '(' so method-call markers such
    as ``.sendmail(`` do not collide with English ``send mail`` or identifiers
    such as ``sendmailbox``. Quotes, operators, whitespace, slashes, and other
    punctuation are stripped so ``'.' + 'sendmail('`` still reconstructs
    ``.sendmail(`` and host identities still reconstruct across concatenations.
    """
    return "".join(ch for ch in value if ch.isalnum() or ch in "_.(")


def _literal_stream(source: str) -> str:
    """Concatenate quoted literal payloads across supported source languages."""
    return "".join(match.group(0)[1:-1] for match in _QUOTED_STRING.finditer(source))


def _contains_provider_marker(source: str, marker: str) -> bool:
    if marker in source:
        return True
    compact_marker = _compact_provider_text(marker)
    if not compact_marker:
        return False
    if compact_marker in _compact_provider_text(source):
        return True
    return compact_marker in _compact_provider_text(_literal_stream(source))


def find_bypasses(
    repository_root: str | Path,
    *,
    validate_manifest: bool = True,
    _validate_registry=validate_registry,
    _iter_files=_iter_code_files,
    _python_scan=_python_call_violations,
    _marker_match=_contains_provider_marker,
    _internal_callsite_scan=_internal_slack_callsite_violations,
    _provider_markers: tuple[str, ...] = PROVIDER_MARKERS,
    _low_level_primitives: frozenset[str] = frozenset(_LOW_LEVEL_PRIMITIVES),
    _chain_files: frozenset[str] = frozenset(_CHAIN_FILES),
    _provider_method_allowed: frozenset[str] = frozenset(_PROVIDER_METHOD_ALLOWED),
    _marker_allowed: frozenset[str] = frozenset(_MARKER_ALLOWED),
    _internal_provider_marker_exemptions: tuple[
        tuple[str, str, tuple[str, ...]], ...
    ] = _INTERNAL_PROVIDER_MARKER_EXEMPTIONS,
    _parse_incompatible_sensitive_markers: tuple[str, ...] = _PARSE_INCOMPATIBLE_SENSITIVE_MARKERS,
) -> list[str]:
    """Return code paths that bypass the mandatory provider-bound composition.

    Python analysis resolves imports, aliases and simple callable rebinding instead
    of matching only literal function names.  All supported code extensions are also
    scanned for known concrete provider/host mutation identities.  Tests and the
    primitive implementations are not live callers.
    """
    root = Path(repository_root)
    violations: list[str] = []
    if validate_manifest:
        violations.extend(_validate_registry(root))

    for file in _iter_files(root):
        rel = file.relative_to(root).as_posix()
        if _is_test(rel) or rel in _low_level_primitives:
            continue
        try:
            raw = file.read_bytes()
            source = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            violations.append(f"{rel}:unscannable:{type(exc).__name__}")
            continue

        exact_internal_marker_exempt = False
        exemption_map = {
            path: (expected_sha, required_markers)
            for path, expected_sha, required_markers in _internal_provider_marker_exemptions
        }
        if rel in exemption_map:
            expected_sha, required_markers = exemption_map[rel]
            if _git_blob_sha(raw) != expected_sha:
                violations.append(f"{rel}:internal-provider-exemption-drift")
            elif not all(marker in source for marker in required_markers):
                violations.append(f"{rel}:internal-provider-exemption-guard-missing")
            else:
                exact_internal_marker_exempt = True

        if file.suffix.lower() == ".py":
            tree = None
            try:
                tree = ast.parse(source, filename=rel)
            except SyntaxError:
                # A newer-language source file is not automatically a provider
                # bypass on an older CI interpreter. It still receives lexical
                # provider scanning below, plus conservative low-level seam scans.
                for marker in _parse_incompatible_sensitive_markers:
                    if _marker_match(source, marker):
                        violations.append(
                            f"{rel}:parse-incompatible-sensitive-marker:{marker}"
                        )
            if tree is not None:
                if rel not in _chain_files:
                    for label in _python_scan(tree):
                        violations.append(f"{rel}:{label}")
                elif rel not in _provider_method_allowed:
                    for label in _python_scan(tree):
                        if label.startswith("provider-transport-method:") or label.startswith("dynamic-provider-transport-method:"):
                            violations.append(f"{rel}:{label}")
                # Raw Slack Web API sends are provider mutations everywhere,
                # not only inside the two reviewed internal bridge files. Running
                # this for every parsed Python file closes helper-import bypasses
                # such as slack_web_call("chat.postMessage", ...).
                for label in _internal_callsite_scan(tree):
                    violations.append(f"{rel}:{label}")

        if rel not in _marker_allowed:
            for marker in _provider_markers:
                # Exact bridge identity may exempt only the direct SDK marker,
                # and only after the AST callsite proof above has run. Other
                # provider markers in the same file are never blanket-exempt.
                if exact_internal_marker_exempt and marker == "chat_postMessage(":
                    continue
                if _marker_match(source, marker):
                    violations.append(f"{rel}:provider-marker:{marker}")

    return sorted(set(violations))


def registered_provider_names(
    _trusted_adapters: tuple[Adapter, ...] = ADAPTERS,
) -> tuple[str, ...]:
    return tuple(item.provider for item in _trusted_adapters)


def registered_host_mutation_identities(
    _trusted_identities: frozenset[str] = _HOST_MUTATION_IDENTITIES,
) -> tuple[str, ...]:
    return tuple(sorted(_trusted_identities))
