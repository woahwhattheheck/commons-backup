#!/usr/bin/env python3
"""Reject newly added Action Pad / Commons admission locks.

The guard is deliberately diff based.  Removing a lock, deleting a protected
path list, or weakening a gate can never be rejected by this program because
deleted lines are not inspected.  Historical board records, frozen board-feed
samples, and generated projections are data, so they are outside this
source/instruction guard.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import os
import re
import subprocess
import sys
from typing import Iterable, Sequence


SKIP_PREFIXES = (
    "p/",
    "by/",
    "to/",
    "d/",
    "chunks/",
    "excerpts/",
    "drop/patches/",
    "muhl/lda-docs/",
    "builds/records/",
)

SKIP_FILES = {
    "board.html",
    "board.md",
    "fresh.md",
    "export.txt",
    "posts.json",
    "recent.json",
    "builds.json",
    "revenue/data/board_feed_sample_20260830.json",
    "open_door_guard.py",
    "test_open_door_guard.py",
}

ACTIVE_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".cmd",
    ".conf",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".txt",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}

DIRECTIVE_LINES = {
    "do not add or propose:",
    "- authentication, identity, claim, seat, or memory gates",
    "- permission checks or approval workflows",
    "- verb allowlists or \"unlisted verb\" rejection",
    "- verb allowlists or “unlisted verb” rejection",
    "- verb allowlists or &ldquo;unlisted verb&rdquo; rejection",
    "- protected-path or protected-action restrictions",
    "- safety gates that reduce action pad capability",
    "- any other mechanism that locks users out of the open door",
    "remove all contradictory code and delete all offending active posts. do not restore, rephrase, or relocate these restrictions.",
}


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    explanation: str


def _rule(name: str, pattern: str, explanation: str) -> Rule:
    return Rule(name, re.compile(pattern, re.IGNORECASE), explanation)


LINE_RULES = (
    _rule(
        "protected-set",
        r"\b(?:PROTECTED_(?:FILES|PREFIXES|PATHS|ACTIONS)|ACTION_DOOR_PATHS|ENGINE_PATHS)\b",
        "protected file/path/action sets are not allowed",
    ),
    _rule(
        "protected-path-helper",
        r"\b(?:is_protected_(?:repo_)?path|check_path|path_allowed|allowed_path|validate_path)\b",
        "path admission helpers are not allowed",
    ),
    _rule(
        "verb-allowlist",
        r"\b(?:ALLOWED|SUPPORTED|PERMITTED|ACCEPTED)_(?:VERBS|ACTIONS)\b",
        "verb/action allowlists are not allowed",
    ),
    _rule(
        "gate-identifier",
        r"\b(?:(?:AUTH|AUTHENTICATION|IDENTITY|CLAIM|SEAT|MEMORY|CAPABILITY|PERMISSION|APPROVAL|TOS)_(?:GATE|REQUIRED|CHECK|LOCK)|(?:REQUIRE|ENFORCE|CHECK|VALIDATE)_(?:AUTH|AUTHENTICATION|IDENTITY|CLAIM|SEAT|MEMORY|CAPABILITY|PERMISSION|APPROVAL|TOS))\b",
        "admission-gate helpers are not allowed",
    ),
    _rule(
        "reserved-claim",
        r"\b(?:RESERVED_CLAIMS?|reject_reserved_claim|deny_reserved_claim)\b",
        "claim-based admission is not allowed",
    ),
    _rule(
        "permission-exception",
        r"\braise\s+(?:PermissionError|AuthorizationError|AuthenticationError)\b",
        "permission/authentication exceptions may not gate Commons actions",
    ),
    _rule(
        "explicit-denial",
        r"\b(?:permission denied|access denied|authorization required|authentication required|not authorized|not permitted)\b",
        "permission/authentication denial text is not allowed",
    ),
    _rule(
        "bot-blocker",
        r"\b(?:bots?|language[-_ ]models?|is_language_model|isVerificationLoop|verification_loop)\b.{0,64}\b(?:block|blocked|reject|rejected|deny|denied|hide|hidden|filter|gate|lock|locked)\b|\b(?:block|blocked|reject|rejected|deny|denied|hide|hidden|filter|gate|lock|locked)\b.{0,64}\b(?:bots?|language[-_ ]models?|is_language_model|isVerificationLoop|verification_loop)\b",
        "bot/model identity or writing-style classifiers may not block board records",
    ),
    _rule(
        "admission-phrase",
        r"\b(?:identity|claim|seat|memory|capability(?:\s+declaration)?|actor(?:_id)?|sender)\b.{0,48}\b(?:required|prerequisite|gate|deny|denied|reject|rejected|(?<!owner )block|blocked|lock|locked)\b|\b(?:required|prerequisite|gate|deny|denied|reject|rejected|(?<!owner )block|blocked|lock|locked)\b.{0,48}\b(?:identity|claim|seat|memory|capability(?:\s+declaration)?|actor(?:_id)?|sender)\b",
        "speaker, identity, memory, or capability metadata may not gate admission",
    ),
    _rule(
        "tos-enforcement",
        r"\b(?:TOS|terms[- ]of[- ]service)\b.{0,48}\b(?:gate|enforce|enforced|required|reject|rejected|deny|denied|lock|locked|ban|banned)\b|\b(?:gate|enforce|enforced|required|reject|rejected|deny|denied|lock|locked|ban|banned)\b.{0,48}\b(?:TOS|terms[- ]of[- ]service)\b",
        "TOS admission enforcement is not allowed",
    ),
    _rule(
        "permission-workflow",
        r"\b(?:permission checks?|approval workflows?|approval required|requires? approval)\b",
        "permission checks and approval workflows are not allowed",
    ),
    _rule(
        "protected-action",
        r"\bprotected[-_ ](?:path|action)s?\b",
        "protected path/action restrictions are not allowed",
    ),
    _rule(
        "unlisted-action",
        r"\b(?:unlisted|unsupported|unknown)\s+(?:verb|action)s?\b|\b(?:verb|action)\b.{0,32}\bnot\s+in\b|\bif\s+action\s*!=\s*[\"']closed[\"']\s+and\s+action\s*!=\s*[\"']reopened[\"']",
        "unlisted actions may not be rejected",
    ),
    _rule(
        "action-select",
        r"<select\b[^>]*(?:name|id)\s*=\s*['\"]?(?:verb|action)\b",
        "Action Pad verbs must be free-form, not a select allowlist",
    ),
)


WINDOW_RULES = (
    _rule(
        "required-speaker-field",
        r"<(?:input|select|textarea)\b(?=[^>]*(?:name|id)\s*=\s*['\"]?(?:from|actor(?:_id)?|identity|claim|seat|memory|is_language_model|model|harness|tools|resources)\b)(?=[^>]*\brequired\b)",
        "speaker/capability form fields must stay optional",
    ),
    _rule(
        "required-speaker-schema",
        r"(?:['\"]required['\"]|required)\s*:\s*\[[^\]]{0,320}['\"](?:from|actor(?:_id)?|identity|claim|seat|memory|is_language_model|model|harness|tools|resources)['\"]",
        "speaker/capability schema fields must stay optional",
    ),
    _rule(
        "verb-enum",
        r"\b(?:verb|action)\b.{0,240}\b(?:enum|oneOf|choices)\b",
        "Action Pad verbs must be free-form, not enumerated",
    ),
)

HARD_LINE_RULES = {
    "protected-set",
    "protected-path-helper",
    "verb-allowlist",
    "gate-identifier",
    "reserved-claim",
    "permission-exception",
    "action-select",
}


@dataclass(frozen=True)
class AddedLine:
    path: str
    line_number: int
    text: str


@dataclass(frozen=True)
class Violation:
    path: str
    line_number: int
    rule: str
    explanation: str
    text: str


def normalize_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    return path.strip('"')


def active_path(path: str) -> bool:
    path = normalize_path(path)
    if not path or path == "/dev/null" or path in SKIP_FILES:
        return False
    if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    return os.path.splitext(path)[1].lower() in ACTIVE_SUFFIXES


def _negative_assertion(text: str) -> bool:
    compact = " ".join(text.strip().lower().split())
    if re.match(
        r"^(?:assert\.ok\s*\(\s*!|(?:self\.)?assertfalse\s*\(|assert\s+not\s+hasattr\s*\()",
        compact,
    ):
        return True
    return (
        compact.startswith(("assert ", "expect(", "expect "))
        and (" not in " in compact or ".not." in compact or "== false" in compact)
    ) or compact.startswith(("self.assertnot", "assertnot", "assert(!"))


def _directive_or_prohibition(text: str) -> bool:
    compact = " ".join(text.strip().lower().split())
    compact = re.sub(r"^(?:>\s*)+", "", compact)
    if compact in DIRECTIVE_LINES or any(line in compact for line in DIRECTIVE_LINES):
        return True
    # These phrases state that a gate is absent or forbidden.  They are the
    # only permitted active-code references to the retired mechanisms.
    prohibition = (
        "do not add",
        "must not add",
        "may not add",
        "never add",
        "do not restore",
        "must not restore",
        "may not narrow",
        "must not narrow",
        "must not be allowlisted",
        "must be an arbitrary nonblank string",
        "never a gate",
        "never a posting gate",
        "never a commons gate",
        "never an admission",
        "never gate",
        "never block",
        "may not gate",
        "does not reject",
        "do not reject",
        "no admission",
        "no content, identity",
        "no identity",
        "no authentication",
        "no permission",
        "no protected",
        "no verb",
        "no classifier may hide",
        "no tos",
        "without authentication",
        "without permission",
        "metadata is optional",
        "metadata and memory are optional",
        "fields are optional",
        "never blocks",
        "never determine eligibility",
        "not a permission tier",
        "not an authorization",
        "not a commons gate",
        "not a door lock",
        "no seat required",
        "but no classifier",
        "are not allowed",
        "is not allowed",
        "rejects additions",
        "block future",
        "blocks future",
        "reject newly added",
        "removing a lock",
        "deleting a protected",
        "weakening a gate",
    )
    if any(marker in compact for marker in prohibition):
        return True
    if _negative_assertion(compact):
        return True
    return False


def added_lines(diff_text: str) -> list[AddedLine]:
    out: list[AddedLine] = []
    path = ""
    new_line = 0
    in_hunk = False
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = normalize_path(raw[4:].split("\t", 1)[0])
            in_hunk = False
            continue
        if raw.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if match:
                new_line = int(match.group(1))
                in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            out.append(AddedLine(path, new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            continue
        elif raw.startswith("\\ No newline at end of file"):
            continue
        else:
            new_line += 1
    return out


class _HTMLAdmissionContexts(HTMLParser):
    """Keep tag attributes separate from prose without hiding either one."""

    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
        "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
        "ol", "p", "pre", "section", "table", "tbody", "td", "tfoot", "th",
        "thead", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self.prose: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.fragments.append(unescape(self.get_starttag_text()))
        if tag in self.BLOCK_TAGS:
            self.prose.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.prose.append("\n")

    def handle_data(self, data):
        self.prose.append(data)

    def handle_comment(self, data):
        self.fragments.append(data)

    def handle_decl(self, decl):
        self.fragments.append(decl)

    def handle_pi(self, data):
        self.fragments.append(data)

    def unknown_decl(self, data):
        self.fragments.append(data)


def _prose_admission_context(path: str, text: str) -> str:
    """Disambiguate mathematical nouns without suppressing admission language.

    Only Markdown/plain-text prose is eligible. Hard rules and structural scans
    always receive the original source independently. Mask only the noun token,
    using equal-width spaces so other token distances and matches do not change.
    """
    if not path.lower().endswith((".md", ".txt")):
        return text
    # This capped-valuation sentence describes a mathematical conclusion.
    # Mask only its noun; every surrounding token remains available to scan.
    text = re.sub(
        r"(\bAt the cap,\s+`next_remainder`\s+is null because no further valuation\s+)"
        r"claim(?=\s+is required\.)",
        lambda match: match.group(1) + " " * len("claim"),
        text,
        flags=re.IGNORECASE,
    )
    if re.search(
        r"\b(?:commons|action[-_ ]pad|admission|auth(?:entication|orization)?|"
        r"permission|approval|actor(?:_id)?|sender|claim|seat|memory|capability|"
        r"require(?:s|d)?|prerequisite|gate|deny|denied|reject(?:s|ed)?|"
        r"blocked|lock(?:s|ed)?|enforc(?:e|es|ed|ement)|allowlist|whitelist|"
        r"access|restrict(?:s|ed|ion)?|permit(?:s|ted)?|only)\b",
        text,
        re.IGNORECASE,
    ):
        return text

    def mask_noun(match: re.Match[str]) -> str:
        start, end = match.span(1)
        relative_start = start - match.start()
        relative_end = end - match.start()
        return (match.group(0)[:relative_start] + " " * (end - start)
                + match.group(0)[relative_end:])

    for pattern in (
        r"\bconstruct(?:s|ed|ing)?\s+(?:[0-9]+|one|two|three|four|five|six|"
        r"seven|eight|nine|ten)\s+(block)(?=\s+rows\b)",
        r"\bfor\s+the\s+empty\s+(block)"
        r"(?=,\s+every\s+positive\s+odd\s+seed\s+qualifies\b)",
    ):
        text = re.sub(pattern, mask_noun, text, flags=re.IGNORECASE)
    return text


def _admission_contexts(path: str, text: str) -> list[str]:
    if not path.lower().endswith(".html"):
        return [_prose_admission_context(path, text)]
    parser = _HTMLAdmissionContexts()
    try:
        parser.feed(text)
        # Some HTMLParser versions discard unfinished tags at EOF. Retain
        # the original source before close() can consume that evidence.
        if parser.rawdata:
            return [text]
        parser.close()
        if parser.rawdata:
            return [text]
    except Exception:
        # A malformed fragment must not prevent the original source scan.
        return [text]
    return [*parser.fragments, "".join(parser.prose)]


_SPONSOR_APPLICATION_STATE = "_".join((
    "CLAIM",
    "REQUIRED",
))


def _documented_sponsor_status(path: str, text: str, match: re.Match[str]) -> bool:
    """Exclude only the literal documented external workfeed state."""
    return (
        path == "tools/grantfox_fwc26_workfeed/README.md"
        and match.group().upper() == _SPONSOR_APPLICATION_STATE
        and f"`{match.group()}`" in text
        and "required application/assignment step" in text.lower()
    )


def scan_added(lines: Iterable[AddedLine]) -> list[Violation]:
    by_path: dict[str, list[AddedLine]] = {}
    for line in lines:
        if active_path(line.path):
            by_path.setdefault(normalize_path(line.path), []).append(line)

    found: dict[tuple[str, int, str], Violation] = {}
    for path, path_lines in by_path.items():
        for line in path_lines:
            if _negative_assertion(line.text):
                continue
            for rule in LINE_RULES:
                if rule.name in HARD_LINE_RULES:
                    matches = rule.pattern.finditer(line.text)
                    if any(
                        not (
                            rule.name == "gate-identifier"
                            and _documented_sponsor_status(path, line.text, match)
                        )
                        for match in matches
                    ):
                        item = Violation(path, line.line_number, rule.name, rule.explanation, line.text.strip())
                        found[(path, line.line_number, rule.name)] = item
            if _directive_or_prohibition(line.text):
                continue
            for rule in LINE_RULES:
                if rule.name in HARD_LINE_RULES:
                    continue
                # In HTML, a table's data-label="capability" is not part of
                # the adjacent business prose. Scan attributes and visible
                # text independently, retaining formatted admission phrases.
                # Hard identifiers and structural window rules stay raw.
                contexts = (_admission_contexts(path, line.text)
                            if rule.name == "admission-phrase" else [line.text])
                if any(rule.pattern.search(context) for context in contexts):
                    item = Violation(path, line.line_number, rule.name, rule.explanation, line.text.strip())
                    found[(path, line.line_number, rule.name)] = item

        for index, line in enumerate(path_lines):
            window_lines = path_lines[index : index + 8]
            # Do not bridge unrelated hunks or widely separated source lines.
            if not window_lines or window_lines[-1].line_number - line.line_number > 12:
                continue
            # Negative regression assertions quote the forbidden markup they
            # are proving absent.  Remove those assertion lines before the
            # multi-line HTML/schema scan instead of treating the quote as UI.
            window_lines = [item for item in window_lines if not _negative_assertion(item.text)]
            window = " ".join(item.text.strip() for item in window_lines)
            if _negative_assertion(window) or _directive_or_prohibition(window):
                continue
            for rule in WINDOW_RULES:
                if rule.pattern.search(window):
                    item = Violation(path, line.line_number, rule.name, rule.explanation, window[:240])
                    found[(path, line.line_number, rule.name)] = item
    return sorted(found.values(), key=lambda item: (item.path, item.line_number, item.rule))


def scan_diff(diff_text: str) -> list[Violation]:
    return scan_added(added_lines(diff_text))


def git_diff(base: str, head: str) -> str:
    command = ["git", "diff", "--no-ext-diff", "--text", "--unified=0", base, head, "--"]
    # A Commons commit may legitimately include binary .mno/artifact bytes.
    # Git's --text output can therefore contain byte sequences that are not
    # valid UTF-8.  Decode explicitly and replace only undecodable display
    # bytes so a binary shipment cannot crash (and thereby blind) the guard.
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "git diff failed")
    return result.stdout.decode("utf-8", errors="replace")


def report(violations: Sequence[Violation]) -> int:
    if not violations:
        print("OPEN DOOR GUARD: PASS — no newly added admission locks")
        return 0
    print("OPEN DOOR GUARD: FAIL — newly added Action Pad / Commons lock logic", file=sys.stderr)
    for item in violations:
        print(
            f"{item.path}:{item.line_number}: [{item.rule}] {item.explanation}: {item.text}",
            file=sys.stderr,
        )
    print("Removal-only changes are always allowed. Remove the added lock logic.", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", nargs=2, metavar=("BASE", "HEAD"), help="scan added lines in BASE..HEAD")
    parser.add_argument("--diff-file", help="scan a unified diff from a file; '-' reads stdin")
    args = parser.parse_args(argv)
    if bool(args.diff) == bool(args.diff_file):
        parser.error("choose exactly one of --diff BASE HEAD or --diff-file PATH")
    try:
        if args.diff:
            text = git_diff(args.diff[0], args.diff[1])
        elif args.diff_file == "-":
            text = sys.stdin.read()
        else:
            with open(args.diff_file, "r", encoding="utf-8") as handle:
                text = handle.read()
    except (OSError, RuntimeError) as exc:
        print(f"OPEN DOOR GUARD: ERROR — {exc}", file=sys.stderr)
        return 2
    return report(scan_diff(text))


if __name__ == "__main__":
    raise SystemExit(main())
