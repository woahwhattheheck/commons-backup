"""Readable views of results from the existing offline auditor, not a verifier."""
from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from .audit import SCHEMA, VERIFY_SCHEMA

_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+.!|>\-])")
_LIMITS = (
    "This is a view of the supplied capture's audit evidence, not endpoint "
    "identity, tool correctness, permission, or proof that an external action "
    "occurred. The command opens no endpoint and executes no captured tool. "
    "Keep the original capture and JSON receipt for exact verification; "
    "this Markdown document is not a verification input."
)


def _cell(value: Any) -> str:
    """Keep untrusted metadata within one literal Markdown table cell."""
    if value is None:
        return "not recorded"
    text = str(value)
    # Make line breaks, terminal controls, bidi/zero-width controls and lone
    # surrogates visible instead of permitting invisible layout changes.
    visible = "".join(
        f"\\u{ord(char):04x}"
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in text
    )
    return _MARKDOWN.sub(r"\\\1", html.escape(visible, quote=True))


def _table(headers: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return lines


def _audit(result: dict[str, Any]) -> list[str]:
    status = result["status"]
    if status not in ("PASS", "HOLD"):
        raise ValueError("unsupported audit status")
    lines = [
        "# MCP capture audit", "", f"**Capture audit: {status}.**", "",
        "PASS means the existing auditor found no listed capture-check failures. "
        "HOLD means review the recorded diagnostics; it is not a diagnosis of a live server.",
        "", "## Exact evidence identity", "",
    ]
    lines += _table(("Field", "Value"), (
        ("Audit schema", result["schema"]),
        ("Required protocol", result["required_protocol_version"]),
        ("Negotiated protocol", result["negotiated_protocol_version"]),
        ("Capture SHA-256", result["source_sha256"]),
        ("Capture bytes", result["source_bytes"]),
        ("Audit receipt SHA-256", result["receipt_sha256"]),
    ))
    counts = result["counts"]
    classified = sum(counts[key] for key in ("requests", "responses", "notifications"))
    lines += ["", "## Coverage and lifecycle", ""]
    lines += _table(("Measure", "Count"), (
        ("Nonempty records counted by auditor", result["event_count"]),
        ("Recorded evidence rows", len(result["evidence"])),
        ("Classified messages", classified),
        ("Client to server", counts["client_to_server"]),
        ("Server to client", counts["server_to_client"]),
        ("Requests", counts["requests"]),
        ("Responses", counts["responses"]),
        ("Notifications", counts["notifications"]),
    ))
    lines += ["", "Counts describe what the auditor processed, not a claim that a capture "
              "is complete. After a parsing or resource-limit failure, some records may "
              "have byte evidence only. Missing classifications are not successful checks.", ""]
    lifecycle = result["lifecycle"]
    lines += _table(("Lifecycle evidence", "Capture line"), (
        ("Initialize request", lifecycle["initialize_request_line"]),
        ("Initialize response", lifecycle["initialize_response_line"]),
        ("Initialized notification", lifecycle["initialized_notification_line"]),
    ))
    lines += ["", "## Diagnostics", ""]
    if result["reasons"]:
        lines += _table(("Scope / line", "Exact diagnostic code"), (
            (reason.get("line", "capture-wide"), reason["code"])
            for reason in result["reasons"]
        ))
    else:
        lines += ["No capture-check diagnostics were recorded."]
    lines += ["", "## Method counts", ""]
    if result["method_counts"]:
        lines += _table(("Method", "Count"), sorted(result["method_counts"].items()))
    else:
        lines += ["No method counts were recorded."]
    lines += ["", "## Event index", ""]
    if result["evidence"]:
        lines += _table(("Capture line", "Direction", "Kind", "Method / response association"), (
            (row["line"], row.get("direction"), row.get("kind", "not classified"),
             row.get("method", row.get("response_to_method")))
            for row in result["evidence"]
        ))
    else:
        lines += ["No event evidence rows were recorded."]
    lines += ["", "Every recorded evidence row is indexed above. Full line, payload and "
              "typed-ID hashes remain in the JSON receipt; this view does not replace them."]
    return lines


def _verification(result: dict[str, Any]) -> list[str]:
    if type(result["valid"]) is not bool:
        raise ValueError("verification valid must be a bool")
    verdict = "MATCH" if result["valid"] else "MISMATCH"
    lines = [
        "# MCP receipt verification", "", f"**Receipt verification: {verdict}.**", "",
        "MATCH means the saved JSON receipt exactly matches recomputation from "
        "these capture bytes. A matching receipt can describe a HOLD capture. "
        "This verification result does not contain the capture's PASS/HOLD status; "
        "run audit with --format markdown on the same capture to inspect it.",
        "", "## Exact evidence identity", "",
    ]
    lines += _table(("Field", "Value"), (
        ("Verification schema", result["schema"]),
        ("Capture SHA-256", result["source_sha256"]),
        ("Supplied JSON receipt file SHA-256", result["receipt_file_sha256"]),
        ("Verification SHA-256", result["verification_sha256"]),
    ))
    lines += ["", "## Verification diagnostics", ""]
    if result["reasons"]:
        lines += _table(("Exact diagnostic code",), ((reason,) for reason in result["reasons"]))
    else:
        lines += ["No receipt-mismatch diagnostics were recorded."]
    return lines


def render_markdown(result: dict[str, Any]) -> str:
    """Render a computed audit/verification result, without a trailing newline.

    Call audit_transcript/verify_receipt first. This display-only function does
    not authenticate arbitrary supplied result dictionaries or their hashes.
    It neither reads payloads nor accepts Markdown as a saved JSON receipt.
    """
    if type(result) is not dict:
        raise ValueError("report input must be an auditor result object")
    schema = result.get("schema")
    if schema == SCHEMA:
        lines = _audit(result)
    elif schema == VERIFY_SCHEMA:
        lines = _verification(result)
    else:
        raise ValueError("unsupported auditor result schema")
    lines += ["", "## Interpretation and handling", "", _LIMITS, "",
              "Request parameters, response results, error payloads and raw request IDs "
              "are not copied into this view. Method names and other retained metadata "
              "may still be sensitive; this is not an anonymization guarantee. "
              "Control characters are shown as Unicode escape text."]
    return "\n".join(lines)
