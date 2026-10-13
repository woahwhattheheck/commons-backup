"""Cross-document commercial-fact checker for UIOWA-132.

Compares proposal, fee schedule, staffing model, scope exhibit, and
option sheet against the pinned RFQ 18649 facts. Prime vs subcontract
role labels are preserved; the repairer must not collapse them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from typing import Any

try:
    from .canonical import CANONICAL, STALE_SEPTEMBER_22_TOKENS
except ImportError:
    from canonical import CANONICAL, STALE_SEPTEMBER_22_TOKENS

REQUIRED_DOCS = (
    "proposal",
    "fee_schedule",
    "staffing",
    "scope_exhibit",
    "option_sheet",
)

_FIELD = re.compile(
    r"^(deadline|currency|base_amount_usd|option_amount_usd|"
    r"milestone_split|kickoff_assumption|travel_treatment|"
    r"principal_role|specialist_role|kickoff_trigger|"
    r"draft_trigger|final_trigger|deliverable_kickoff|"
    r"deliverable_draft|deliverable_final):\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_MONEY = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\b")
_SPLIT = re.compile(r"\b(40)\s*/\s*(40)\s*/\s*(20)\b")
_DELIVERY_PAY = re.compile(
    r"\b(pay(?:ment|able)?|invoice|milestone)\b.{0,40}\bupon delivery\b"
    r"|\bupon delivery\b.{0,40}\b(pay(?:ment|able)?|invoice|milestone)\b",
    re.IGNORECASE,
)
_ACCEPTANCE_PAY = re.compile(
    r"\b(pay(?:ment|able)?|invoice|final milestone)\b.{0,48}\bacceptance\b",
    re.IGNORECASE,
)
_ROLE_COLLAPSE = re.compile(
    r"\bsubcontract(?:or|ing)?\b.{0,40}\bas (?:the )?prime\b"
    r"|\bprime\b.{0,40}\bas (?:a )?subcontract",
    re.IGNORECASE,
)


class FactsError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    code: str
    document: str
    detail: str


@dataclass
class DocumentFacts:
    name: str
    text: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def folded(self) -> str:
        return self.text.casefold()


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise FactsError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                FactsError(f"non-finite JSON number: {token}")
            ),
        )
    except FactsError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise FactsError(f"invalid JSON: {exc}") from exc


def parse_document(name: str, text: str) -> DocumentFacts:
    if type(name) is not str or type(text) is not str:
        raise FactsError("document name and text must be strings")
    fields = {}
    for match in _FIELD.finditer(text):
        key = match.group(1).casefold()
        fields[key] = match.group(2).strip().rstrip(".,;")
    return DocumentFacts(name=name, text=text, fields=fields)


def load_bundle(root: Path) -> dict[str, DocumentFacts]:
    root = Path(root)
    bundle = {}
    for name in REQUIRED_DOCS:
        path = root / f"{name}.md"
        if not path.is_file() or path.is_symlink():
            raise FactsError(f"missing regular file: {name}.md")
        bundle[name] = parse_document(name, path.read_text(encoding="utf-8"))
    extra = sorted(
        p.name
        for p in root.iterdir()
        if p.is_file() and p.name.endswith(".md") and p.stem not in REQUIRED_DOCS
    )
    if extra:
        raise FactsError(f"unexpected documents: {extra}")
    return bundle


def _int_field(value: str) -> int | None:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if cleaned.isdigit():
        return int(cleaned)
    return None


def _split_field(value: str) -> tuple[int, int, int] | None:
    parts = [p.strip() for p in value.replace("%", "").split("/")]
    if len(parts) != 3:
        return None
    try:
        nums = tuple(int(p) for p in parts)
    except ValueError:
        return None
    return nums  # type: ignore[return-value]


def _deadline_stale(text: str, fields: dict[str, str]) -> bool:
    folded = text.casefold()
    if any(token in folded for token in STALE_SEPTEMBER_22_TOKENS):
        return True
    declared = fields.get("deadline", "")
    if declared and declared not in {
        CANONICAL["deadline_date"],
        CANONICAL["deadline_local"],
        CANONICAL["deadline_iso"],
        "2026-09-22 15:00 America/Chicago",
        "September 22, 2026 3:00 PM CT",
    }:
        if "2026-09-22" not in declared and "september 22, 2026" not in declared.casefold():
            return "september 22" in declared.casefold() or "2026-09-22" in declared
        if "2025" in declared:
            return True
        if declared not in {
            CANONICAL["deadline_date"],
            CANONICAL["deadline_local"],
            CANONICAL["deadline_iso"],
            "2026-09-22 15:00 America/Chicago",
            "September 22, 2026 3:00 PM CT",
        }:
            # Vague "September 22" without year/time is stale residue.
            if declared.casefold() in {"september 22", "sep 22", "9/22"}:
                return True
    if re.search(r"\bseptember 22\b", folded) and "2026" not in folded:
        return True
    return False


def check_document(doc: DocumentFacts) -> list[Finding]:
    findings: list[Finding] = []
    fields = doc.fields
    folded = doc.folded

    if _deadline_stale(doc.text, fields):
        findings.append(
            Finding(
                "STALE_SEPTEMBER_22",
                doc.name,
                "document carries a stale or underspecified September 22 deadline",
            )
        )
    deadline = fields.get("deadline")
    if deadline and deadline not in {
        CANONICAL["deadline_date"],
        CANONICAL["deadline_local"],
        CANONICAL["deadline_iso"],
        "2026-09-22 15:00 America/Chicago",
        "September 22, 2026 3:00 PM CT",
    }:
        findings.append(
            Finding("DEADLINE_MISMATCH", doc.name, f"deadline {deadline!r} is not canonical")
        )

    currency = fields.get("currency")
    if currency and currency.upper() != CANONICAL["currency"]:
        findings.append(
            Finding("CURRENCY_MISMATCH", doc.name, f"currency {currency!r} is not USD")
        )

    base = _int_field(fields["base_amount_usd"]) if "base_amount_usd" in fields else None
    if base is None:
        amounts = [_int_field(m.group(1)) for m in _MONEY.finditer(doc.text)]
        amounts = [a for a in amounts if a is not None]
        mismatched = [a for a in amounts if a in {25000, 20000, 28000}]
        if mismatched and doc.name != "option_sheet":
            base = mismatched[0]
    if base is not None and base != CANONICAL["base_amount_usd"] and doc.name != "option_sheet":
        findings.append(
            Finding(
                "AMOUNT_MISMATCH",
                doc.name,
                f"base amount {base} does not match canonical {CANONICAL['base_amount_usd']}",
            )
        )
    if "base_amount_usd" in fields:
        parsed = _int_field(fields["base_amount_usd"])
        if parsed is not None and parsed != CANONICAL["base_amount_usd"] and doc.name != "option_sheet":
            if not any(f.code == "AMOUNT_MISMATCH" for f in findings):
                findings.append(
                    Finding(
                        "AMOUNT_MISMATCH",
                        doc.name,
                        f"base amount {parsed} does not match canonical {CANONICAL['base_amount_usd']}",
                    )
                )

    option = _int_field(fields["option_amount_usd"]) if "option_amount_usd" in fields else None
    if option is not None and option != CANONICAL["option_amount_usd"]:
        findings.append(
            Finding(
                "AMOUNT_MISMATCH",
                doc.name,
                f"option amount {option} does not match canonical {CANONICAL['option_amount_usd']}",
            )
        )

    if "milestone_split" in fields:
        split = _split_field(fields["milestone_split"])
        if split != CANONICAL["milestone_split"]:
            findings.append(
                Finding(
                    "MILESTONE_SPLIT_MISMATCH",
                    doc.name,
                    f"milestone split {fields['milestone_split']!r} is not 40/40/20",
                )
            )
    elif doc.name in {"proposal", "fee_schedule"} and not _SPLIT.search(doc.text):
        if "$24,000" in doc.text or "24000" in doc.text.replace(",", ""):
            findings.append(
                Finding(
                    "MILESTONE_SPLIT_MISMATCH",
                    doc.name,
                    "40/40/20 milestone split is missing from a commercial document",
                )
            )

    if fields.get("kickoff_assumption") and fields["kickoff_assumption"] != CANONICAL["kickoff_assumption"]:
        findings.append(
            Finding(
                "KICKOFF_ASSUMPTION_MISMATCH",
                doc.name,
                f"kickoff assumption {fields['kickoff_assumption']!r} is not after_award_no_travel",
            )
        )
    if fields.get("travel_treatment") and fields["travel_treatment"] != CANONICAL["travel_treatment"]:
        findings.append(
            Finding(
                "TRAVEL_TREATMENT_MISMATCH",
                doc.name,
                f"travel treatment {fields['travel_treatment']!r} is not excluded_from_base",
            )
        )

    principal = fields.get("principal_role")
    specialist = fields.get("specialist_role")
    if principal and principal.casefold() != "prime":
        findings.append(Finding("ROLE_LABEL_MISMATCH", doc.name, f"principal role {principal!r}"))
    if specialist and specialist.casefold() != "subcontract":
        findings.append(Finding("ROLE_LABEL_MISMATCH", doc.name, f"specialist role {specialist!r}"))
    if _ROLE_COLLAPSE.search(doc.text):
        findings.append(
            Finding(
                "ROLE_COLLAPSE",
                doc.name,
                "text collapses prime and subcontract identities",
            )
        )

    final_trigger = fields.get("final_trigger", "")
    if final_trigger.casefold() == "delivery" or (
        _DELIVERY_PAY.search(doc.text) and not _ACCEPTANCE_PAY.search(doc.text)
    ):
        findings.append(
            Finding(
                "DELIVERY_VS_ACCEPTANCE_TRIGGER",
                doc.name,
                "payment or final milestone is tied to delivery rather than acceptance",
            )
        )
    if fields.get("draft_trigger") and fields["draft_trigger"].casefold() not in {
        "draft_delivery",
        "draft delivery",
        "delivery",
    }:
        findings.append(
            Finding(
                "DELIVERABLE_LABEL_MISMATCH",
                doc.name,
                f"draft trigger {fields['draft_trigger']!r} is not a draft-delivery label",
            )
        )
    return findings


def facts_table(bundle: dict[str, DocumentFacts]) -> list[dict[str, str]]:
    rows = []
    for name in REQUIRED_DOCS:
        doc = bundle[name]
        rows.append(
            {
                "document": name,
                "deadline": doc.fields.get("deadline", ""),
                "currency": doc.fields.get("currency", ""),
                "base_amount_usd": doc.fields.get("base_amount_usd", ""),
                "option_amount_usd": doc.fields.get("option_amount_usd", ""),
                "milestone_split": doc.fields.get("milestone_split", ""),
                "kickoff_assumption": doc.fields.get("kickoff_assumption", ""),
                "travel_treatment": doc.fields.get("travel_treatment", ""),
                "principal_role": doc.fields.get("principal_role", ""),
                "specialist_role": doc.fields.get("specialist_role", ""),
                "final_trigger": doc.fields.get("final_trigger", ""),
            }
        )
    return rows


def check_bundle(bundle: dict[str, DocumentFacts]) -> dict[str, Any]:
    if set(bundle) != set(REQUIRED_DOCS):
        raise FactsError(f"bundle must contain exactly {REQUIRED_DOCS}")
    findings: list[Finding] = []
    for name in REQUIRED_DOCS:
        findings.extend(check_document(bundle[name]))
    codes = sorted({f.code for f in findings})
    return {
        "schema": CANONICAL["schema"],
        "rfq_id": CANONICAL["rfq_id"],
        "canonical": {
            "deadline_iso": CANONICAL["deadline_iso"],
            "currency": CANONICAL["currency"],
            "base_amount_usd": CANONICAL["base_amount_usd"],
            "option_amount_usd": CANONICAL["option_amount_usd"],
            "milestone_split": list(CANONICAL["milestone_split"]),
            "milestone_amounts_usd": list(CANONICAL["milestone_amounts_usd"]),
        },
        "facts_table": facts_table(bundle),
        "findings": [
            {"code": f.code, "document": f.document, "detail": f.detail} for f in findings
        ],
        "finding_codes": codes,
        "consistent": not findings,
        "authority": dict(CANONICAL["authority"]),
    }


def render_facts_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# UIOWA-132 commercial facts table",
        "",
        f"RFQ `{result['rfq_id']}` · consistent `{result['consistent']}`",
        "",
        "| document | deadline | currency | base | option | split | kickoff | travel | prime | subcontract | final trigger |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in result["facts_table"]:
        lines.append(
            "| {document} | {deadline} | {currency} | {base_amount_usd} | {option_amount_usd} | "
            "{milestone_split} | {kickoff_assumption} | {travel_treatment} | {principal_role} | "
            "{specialist_role} | {final_trigger} |".format(**row)
        )
    lines.extend(["", "## Findings", ""])
    if not result["findings"]:
        lines.append("No cross-document commercial mismatches.")
    else:
        for item in result["findings"]:
            lines.append(f"- `{item['code']}` · {item['document']}: {item['detail']}")
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "Checker output is internal draft reconciliation only. "
            "Buyer contact, submission, invoice, payment, revenue, and scheduling remain false.",
            "",
        ]
    )
    return "\n".join(lines)
