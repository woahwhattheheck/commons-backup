#!/usr/bin/env python3
"""Run the open-door scanner with syntax-aware negative-assertion handling.

The unchanged scanner implementation lives beside this wrapper.  This module
re-exports its public surface, then narrows only the exemption for regression
assertions: executable Python tails on the same logical statement remain
visible to every existing line and window rule.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import os
import re
from pathlib import Path
import textwrap
import tokenize
import types
import sys


def _load_core():
    sibling = Path(__file__).with_name("open_door_guard_core.py")
    source = sibling if sibling.is_file() else Path(os.environ.get("OPEN_DOOR_GUARD_CORE", ""))
    if not source.is_file():
        raise ImportError("open_door_guard_core.py must accompany the scanner")
    spec = importlib.util.spec_from_file_location("open_door_guard_core", source)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load open_door_guard_core.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_core = _load_core()
# The existing workflow matrix copies this wrapper into an isolated Git fixture.
# Its child inherits this explicit source pointer; normal repository execution
# finds the sibling without consulting the environment.
os.environ["OPEN_DOOR_GUARD_CORE"] = str(Path(_core.__file__).resolve())
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value
SKIP_FILES.add("open_door_guard_core.py")


def _legacy_fstring_code(token_text: str) -> str:
    """Keep only executable interpolation from a pre-3.12 STRING token."""
    try:
        expression = ast.parse(token_text, mode="eval").body
    except (SyntaxError, ValueError):
        return " "
    if not isinstance(expression, ast.JoinedStr):
        return " "
    values = []
    for node in ast.walk(expression):
        if isinstance(node, ast.FormattedValue):
            try:
                values.append(ast.unparse(node.value))
            except (AttributeError, TypeError, ValueError):
                return token_text
    return " ".join(values) or " "


def _code_without_literals(text: str) -> str:
    """Return available Python code tokens with strings/comments blanked.

    Python 3.12+ exposes f-string literal segments separately, while older
    tokenizers expose the whole f-string as STRING. In both cases retain only
    executable interpolation, never quoted denial text. A partial added line
    can end before its unchanged continuation; keep tokens emitted before that
    expected EOF so an executable gate identifier cannot inherit an exemption.
    """
    literal_types = {tokenize.COMMENT}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        token_type = getattr(tokenize, name, None)
        if token_type is not None:
            literal_types.add(token_type)
    tokens = []
    generator = tokenize.generate_tokens(io.StringIO(text).readline)
    try:
        for token in generator:
            if token.type == tokenize.STRING:
                replacement = _legacy_fstring_code(token.string)
                token = tokenize.TokenInfo(
                    token.type, replacement, token.start, token.end, token.line
                )
            elif token.type in literal_types:
                token = tokenize.TokenInfo(token.type, " ", token.start, token.end, token.line)
            tokens.append(token)
    except (IndentationError, tokenize.TokenError):
        pass
    return tokenize.untokenize(tokens)


def _negative_assertion_statement(statement: ast.stmt, source: str) -> bool:
    """Return whether one parsed statement is only a negative assertion.

    Admission identifiers used as executable code are never hidden merely
    because the surrounding statement is an assertion. Literal quotation in a
    negative regression remains exempt.
    """
    if any(isinstance(node, ast.NamedExpr) for node in ast.walk(statement)):
        return False
    shape = isinstance(statement, ast.Assert) or (
        isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
    )
    if not shape:
        return False
    try:
        code = _code_without_literals(source)
    except (IndentationError, tokenize.TokenError):
        return False
    return not any(rule.pattern.search(code) for rule in LINE_RULES)


def _top_level_semicolon(text: str) -> bool:
    """Detect a second simple statement without treating quoted semicolons as code."""
    depth = 0
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type != tokenize.OP:
                continue
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}" and depth:
                depth -= 1
            elif token.string == ";" and depth == 0:
                return True
    except (IndentationError, tokenize.TokenError):
        pass
    return False


def _negative_assertion_indexes(path: str, lines: Sequence[AddedLine]) -> set[int]:
    """Find added source lines occupied solely by a negative assertion.

    Non-Python languages retain the existing line heuristic. Python is parsed
    so a semicolon, boolean expression, or second statement cannot hide
    executable admission logic behind an assertion prefix. A truncated first
    line from an otherwise unchanged multiline assertion remains exempt.
    """
    if not path.lower().endswith(".py"):
        return {index for index, line in enumerate(lines) if _negative_assertion(line.text)}

    hidden: set[int] = set()
    for start, line in enumerate(lines):
        stripped = line.text.lstrip()
        plain_assert = stripped.startswith("assert") and (
            len(stripped) == len("assert")
            or stripped[len("assert")].isspace()
            or stripped[len("assert")] == "("
        )
        if start in hidden or not (_negative_assertion(line.text) or plain_assert):
            continue
        source: list[str] = []
        parsed = False
        previous_line = line.line_number - 1
        for end in range(start, min(len(lines), start + 32)):
            current = lines[end]
            if current.line_number != previous_line + 1:
                break
            previous_line = current.line_number
            source.append(current.text)
            joined = "\n".join(source)
            try:
                module = ast.parse(textwrap.dedent(joined))
            except SyntaxError:
                continue
            parsed = True
            if (len(module.body) == 1
                    and _negative_assertion(joined)
                    and _negative_assertion_statement(module.body[0], joined)):
                hidden.update(range(start, end + 1))
            break
        if not parsed:
            joined = "\n".join(source)
            if (_negative_assertion(joined)
                    and not _top_level_semicolon(joined)):
                code = _code_without_literals(joined)
                if not any(rule.pattern.search(code) for rule in LINE_RULES):
                    hidden.update(range(start, start + len(source)))
    return hidden


# Preserve the existing directive/prohibition implementation byte-for-byte,
# but remove its old blanket assertion-prefix shortcut. Assertion suppression
# is now decided once, with path and neighboring-line context, above.
_directive_globals = dict(_core._directive_or_prohibition.__globals__)
_directive_globals["_negative_assertion"] = lambda text: False
_directive_or_prohibition = types.FunctionType(
    _core._directive_or_prohibition.__code__,
    _directive_globals,
    _core._directive_or_prohibition.__name__,
    _core._directive_or_prohibition.__defaults__,
    _core._directive_or_prohibition.__closure__,
)


def _window_rule_matches(rule: Rule, path: str, window: str) -> bool:
    """Match structural window rules without confusing argparse configuration.

    ``argparse.add_argument(..., action=...)`` uses ``action`` as a parser
    behavior keyword, not as an Action Pad field.  Mask only that keyword
    before the structural enum scan; actual ``--action`` options and
    action/verb schema fields remain visible to the existing rule.
    """
    candidate = window
    if rule.name == "verb-enum" and path.lower().endswith(".py"):
        candidate = re.sub(
            r"(\badd_argument\s*\([^)]{0,240}?)\baction\s*=",
            r"\1argparse_action=",
            candidate,
            flags=re.IGNORECASE,
        )
    return bool(rule.pattern.search(candidate))


def _production_lims_human_release_exception(
    path: str, line_index: int, path_lines: Sequence[AddedLine]
) -> bool:
    """Recognize product-local human-release safety, not Commons admission.

    Production-LIMS harnesses intentionally fail closed when code attempts an
    automatic report/certificate/dossier release.  Exempt only a permission
    exception whose nearby added source proves that exact release context.
    Authentication/authorization or Commons/Action-Pad context always wins and
    remains rejectable.
    """
    normalized = normalize_path(path).lower()
    if not normalized.startswith("revenue/production-lims/") or not normalized.endswith(".py"):
        return False

    line = path_lines[line_index]
    start = max(0, line_index - 5)
    end = min(len(path_lines), line_index + 6)
    neighbors = [
        item.text.strip()
        for item in path_lines[start:end]
        if abs(item.line_number - line.line_number) <= 10
    ]
    context = " ".join(neighbors)

    release_context = re.search(
        r"\b(?:automatic[_ ]release|auto[_ ]release|release|human[-_ ]qa|"
        r"human[-_ ]review|named[-_ ]human|named[-_ ]reviewer|staged[-_ ]report|"
        r"staged[-_ ]dossier|certificate)\b",
        context,
        re.IGNORECASE,
    )
    admission_context = re.search(
        r"\b(?:action\s+pad|commons|post_to_action_pad|admission|"
        r"authentication|authorization|actor(?:_id)?|identity|claim|seat)\b",
        context,
        re.IGNORECASE,
    )
    return bool(release_context) and not bool(admission_context)


def scan_added(lines: Iterable[AddedLine]) -> list[Violation]:
    by_path: dict[str, list[AddedLine]] = {}
    for line in lines:
        if active_path(line.path):
            by_path.setdefault(normalize_path(line.path), []).append(line)

    found: dict[tuple[str, int, str], Violation] = {}
    for path, path_lines in by_path.items():
        negative_assertion_indexes = _negative_assertion_indexes(path, path_lines)
        for line_index, line in enumerate(path_lines):
            if line_index in negative_assertion_indexes:
                continue
            for rule in LINE_RULES:
                if rule.name in HARD_LINE_RULES and rule.pattern.search(line.text):
                    if (rule.name == "permission-exception"
                            and _production_lims_human_release_exception(
                                path, line_index, path_lines
                            )):
                        continue
                    item = Violation(path, line.line_number, rule.name, rule.explanation, line.text.strip())
                    found[(path, line.line_number, rule.name)] = item
            if _directive_or_prohibition(line.text):
                continue
            for rule in LINE_RULES:
                if rule.name in HARD_LINE_RULES:
                    continue
                contexts = (_admission_contexts(path, line.text)
                            if rule.name == "admission-phrase" else [line.text])
                if any(rule.pattern.search(context) for context in contexts):
                    item = Violation(path, line.line_number, rule.name, rule.explanation, line.text.strip())
                    found[(path, line.line_number, rule.name)] = item

        for index, line in enumerate(path_lines):
            indexed_window = list(enumerate(path_lines[index:index + 8], index))
            window_lines = [item for _, item in indexed_window]
            if not window_lines or window_lines[-1].line_number - line.line_number > 12:
                continue
            window_lines = [
                item for item_index, item in indexed_window
                if item_index not in negative_assertion_indexes
            ]
            window = " ".join(item.text.strip() for item in window_lines)
            if not window or _directive_or_prohibition(window):
                continue
            for rule in WINDOW_RULES:
                if _window_rule_matches(rule, path, window):
                    item = Violation(path, line.line_number, rule.name, rule.explanation, window[:240])
                    found[(path, line.line_number, rule.name)] = item
    return sorted(found.values(), key=lambda item: (item.path, item.line_number, item.rule))


def scan_diff(diff_text: str) -> list[Violation]:
    return scan_added(added_lines(diff_text))


_core.SKIP_FILES = SKIP_FILES
_core._directive_or_prohibition = _directive_or_prohibition
_core.scan_added = scan_added
_core.scan_diff = scan_diff


def main(argv: Sequence[str] | None = None) -> int:
    return _core.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
