"""Buyer-safe Markdown projection for clarification packets."""
from __future__ import annotations
from typing import Any, Mapping

def _markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# DRAFT RFP clarification questions — OWNER REVIEW ONLY",
        "",
        f"- Status: **{packet['status']}**",
        f"- Solicitation pack: `{packet['pack_id']}`",
        f"- Evaluated at: `{packet['evaluated_at']}`",
        "- External action: **NOT AUTHORIZED**. A later send requires a fresh pursuit collision/DNR census and Muse single-writer arbitration.",
        "",
        "## Question deadline",
        "",
    ]
    deadline = packet["active_question_deadline"]
    if deadline is None:
        lines.append("No unique source-bound question deadline is active. Do not use this draft externally.")
    else:
        lines.append(f"- `{deadline['value']}` (UTC `{deadline['utc']}`)")
        lines.append(f"- Source: `{deadline['source_id']}` / section `{deadline['section_id']}` / `{deadline['source_sha256']}`")
    if packet["source_conflicts"]:
        lines += ["", "## Source conflicts — HOLD", ""]
        for conflict in packet["source_conflicts"]:
            lines.append(f"- `{conflict}`")
    lines += ["", "## Buyer-safe question draft", ""]
    if not packet["questions"]:
        lines.append("No question is projected. This may mean there are no unresolved buyer-safe questions, or the packet is on HOLD.")
    for index, row in enumerate(packet["questions"], 1):
        lines.append(f"### {index}. {row['question_class']} · priority {row['priority']}")
        lines.append("")
        lines.append(row["question_text"])
        lines.append("")
        lines.append("Source coordinates:")
        for coord in row["source_coordinates"]:
            lines.append(
                f"- gap `{coord['gap_id']}` · source `{coord['source_id']}` · section `{coord['section_id']}` · SHA `{coord['source_sha256']}`"
            )
        lines.append("")
    lines += [
        "## Authority ceiling",
        "",
        "This is a source-bound draft for owner review. It is not permission to contact a buyer, send email/DM, use a portal/form, submit a clarification, request Muse, submit a proposal, sign or price a contract, claim an award, request payment, or recognize revenue.",
        "",
        f"Packet SHA-256: `{packet['packet_sha256']}`",
        "",
    ]
    return "\n".join(lines)


