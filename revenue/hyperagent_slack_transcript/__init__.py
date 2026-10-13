"""Deterministic offline projection of heterogeneous agent events into Slack-style transcripts."""

from .adapter import (
    ApprovalError,
    ConflictError,
    ValidationError,
    TranscriptProjector,
    canonical_bytes,
    load_strict_json,
    project_fixture,
)

__all__ = [
    "ApprovalError",
    "ConflictError",
    "ValidationError",
    "TranscriptProjector",
    "canonical_bytes",
    "load_strict_json",
    "project_fixture",
]
