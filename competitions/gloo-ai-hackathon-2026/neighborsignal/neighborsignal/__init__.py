"""NeighborSignal: fail-closed community-care coordination for Gloo AI Hackathon 2026."""

from .core import POLICY_VERSION, compile_plan, compile_plan_historical, verify_receipt

__all__ = ["POLICY_VERSION", "compile_plan", "compile_plan_historical", "verify_receipt"]
