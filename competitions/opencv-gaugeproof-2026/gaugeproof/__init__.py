"""GaugeProof: evidence-first visual gauge inspection."""

from .core import (
    Calibration,
    FrameReading,
    InspectionDecision,
    analyze_frame,
    inspect_sequence,
)
from .receipt import compile_receipt, verify_receipt

__all__ = [
    "Calibration",
    "FrameReading",
    "InspectionDecision",
    "analyze_frame",
    "inspect_sequence",
    "compile_receipt",
    "verify_receipt",
]
