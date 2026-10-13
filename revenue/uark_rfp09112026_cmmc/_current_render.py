"""Truth-labeled renderers for the UArk current-authority carrier."""
from __future__ import annotations

from typing import Any, Callable


def _render(
    packet: dict[str, Any],
    verify_historical: Callable[[Any], bool],
    title: str,
    notice: str,
) -> str:
    verify_historical(packet)
    decision = packet["decision"]
    blockers = "\n".join(f"- {item}" for item in decision["blockers"]) or "- none"
    risks = "\n".join(f"- {item}" for item in decision["risks"]) or "- none"
    return (
        title + "\n\n"
        f"**Evaluated at:** `{packet['evaluated_at_utc']}`  \n"
        f"**Route:** `{decision['route_requested']}`  \n"
        f"**Status:** `{decision['status']}`  \n"
        f"**Submission ready:** `{str(decision['submission_ready']).lower()}`  \n\n"
        "## Blockers\n" + blockers + "\n\n"
        "## Risks / packet gaps\n" + risks + "\n\n"
        "## Authority boundary\n" + notice + "\n\n"
        "No buyer or partner contact, portal action, signature, price commitment, "
        "certification claim, protected-data handling, contract, award, payment, or "
        "revenue action is authorized.\n\n"
        f"Packet receipt: `{packet['packet_receipt_sha256']}`\n"
    )


def make_historical_renderer(
    verify_historical: Callable[[Any], bool],
) -> Callable[[dict[str, Any]], str]:
    def render_markdown_historical(packet: dict[str, Any]) -> str:
        return _render(
            packet,
            verify_historical,
            "# UArk RFP09112026 — HISTORICAL / INTEGRITY ONLY — NOT CURRENT",
            "Caller-supplied time; deterministic integrity replay only; this is not "
            "CURRENT authority.",
        )

    return render_markdown_historical


def make_current_renderer(
    verify_historical: Callable[[Any], bool],
) -> Callable[[dict[str, Any]], str]:
    def render_current(packet: dict[str, Any]) -> str:
        return _render(
            packet,
            verify_historical,
            "# UArk RFP09112026 — CURRENT qualification",
            "Compiled by this direct isolated process at process-owned UTC. A fresh "
            "direct isolated verification is still required at use; this is not a "
            "bearer credential.",
        )

    return render_current
