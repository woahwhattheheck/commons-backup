from __future__ import annotations

import json
from typing import Any

from strands import Agent, tool

from core import build_packet, canonical_json, extract_requirements, verify_packet


@tool
def extract_rfp_obligations(rfp_text: str) -> str:
    """Extract mandatory RFP obligations into stable evidence-work IDs.

    Args:
        rfp_text: Plain-text or Markdown RFP content supplied by the user.
    """
    return canonical_json([r.__dict__ for r in extract_requirements(rfp_text)])


@tool
def compile_evidence_bound_packet(rfp_text: str, evidence_json: str, as_of: str) -> str:
    """Compile a deterministic bid/no-bid and response packet from RFP text plus evidence.

    Args:
        rfp_text: RFP content to analyze.
        evidence_json: JSON array of company evidence records.
        as_of: Evidence evaluation date in YYYY-MM-DD format.
    """
    evidence = json.loads(evidence_json)
    return canonical_json(build_packet(rfp_text, evidence, as_of=as_of))


@tool
def verify_evidence_bound_packet(packet_json: str) -> str:
    """Verify the canonical TenderProof receipt and authority boundary.

    Args:
        packet_json: JSON packet returned by compile_evidence_bound_packet.
    """
    packet: Any = json.loads(packet_json)
    return "VALID" if verify_packet(packet) else "INVALID"


SYSTEM_PROMPT = """You are TenderProof, a Professional Agent for public-sector and enterprise RFP response work.
Your job is to turn an RFP and a caller-provided evidence register into an evidence-bound working packet.
You MUST use the TenderProof tools for obligation extraction, compilation, and verification.
Never invent certifications, insurance, customers, experience, prices, security posture, legal authority, or submission status.
Never convert MISSING/BLOCKER requirements into affirmative claims. Preserve the packet's buyer_send_authorized=false and submission_authorized=false boundary.
End by reporting the machine decision, blocking/missing requirement IDs, and the next evidence actions. A human must approve any actual bid or buyer communication.
"""


def build_agent(*, model: Any = None) -> Agent:
    kwargs: dict[str, Any] = {
        "name": "tenderproof",
        "description": "Evidence-first RFP response agent that refuses unsupported commercial claims.",
        "tools": [extract_rfp_obligations, compile_evidence_bound_packet, verify_evidence_bound_packet],
        "system_prompt": SYSTEM_PROMPT,
    }
    if model is not None:
        kwargs["model"] = model
    return Agent(**kwargs)
