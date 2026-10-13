from __future__ import annotations

from typing import Any

try:
    from .compiler import compile_result
    from .contract import ContractError, canonical_bytes
except ImportError:
    from compiler import compile_result
    from contract import ContractError, canonical_bytes


def verify_result(raw_scenario: Any, candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    try:
        expected = compile_result(raw_scenario)
    except (ContractError, ValueError, TypeError):
        return False
    return canonical_bytes(expected) == canonical_bytes(candidate)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DARPA DV026 market POC technical proof", "",
        f"- Scenario: `{result['scenario_id']}`",
        f"- Status: **{result['status']}**",
        f"- Scenario SHA-256: `{result['scenario_sha256']}`",
        "- External heterogeneous LLM panel executed: **NO** (interface/plan only)",
        "- New human-subject collection: **NO**",
        "- SBIR eligibility / submission authority: **NOT PROVEN**", "",
        "## Market results", "",
        "| Mechanism | Efficient surplus | Realized surplus | Efficiency (bp) | >90% |",
        "|---|---:|---:|---:|:---:|",
    ]
    for row in result["mechanisms"]:
        bps = row["allocative_efficiency"]["basis_points"]
        lines.append(
            f"| {row['mechanism']} | {row['efficient_surplus']} | {row['realized_surplus']} | "
            f"{bps if bps is not None else 'undefined'} | {'YES' if row['strictly_above_90_percent'] else 'NO'} |"
        )
    lines += ["", "## Blockers", ""]
    if result["blockers"]:
        lines.extend(f"- `{item}`" for item in result["blockers"])
    else:
        lines.append("- None inside the synthetic technical proof. Owner/entity/solicitation gates remain outside this artifact.")
    lines += [
        "", "## Truth boundary", "",
        "This proof exercises deterministic market mechanics, provenance, and exact economic scoring on synthetic data. "
        "It is not a DARPA submission, not a 10-LLM external run, not human-market validation, not SBIR eligibility evidence, "
        "and not an award/payment/revenue claim.", "",
        f"Result receipt SHA-256: `{result['receipt']['result_sha256']}`",
    ]
    return "\n".join(lines) + "\n"
