"""Exact research tools for Zhi-Wei Sun's OEIS A303656 conjecture."""

from .oracle import A303656Witness, find_witness, sum_two_squares

__all__ = ["A303656Witness", "find_witness", "sum_two_squares"]
