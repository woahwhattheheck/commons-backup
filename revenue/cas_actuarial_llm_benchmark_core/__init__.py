"""Reproducible classification-benchmark scoring primitives."""
from .benchmark import AUTHORITY, BenchmarkError, build_board, score_run, verify_board, verify_receipt

__all__ = ["AUTHORITY", "BenchmarkError", "build_board", "score_run", "verify_board", "verify_receipt"]
