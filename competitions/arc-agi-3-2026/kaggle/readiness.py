"""Fail-closed competition runtime/readiness gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Mapping

from .profile import ProfileReceipt


@dataclass(frozen=True)
class RuntimeLimits:
    wall_seconds: float
    memory_mib: float | None
    max_fraction: float = 0.80

    def __post_init__(self) -> None:
        if not math.isfinite(self.wall_seconds) or self.wall_seconds <= 0:
            raise ValueError("wall_seconds must be finite positive")
        if self.memory_mib is not None and (not math.isfinite(self.memory_mib) or self.memory_mib <= 0):
            raise ValueError("memory_mib must be finite positive when known")
        if not math.isfinite(self.max_fraction) or not 0 < self.max_fraction < 1:
            raise ValueError("max_fraction must be in (0,1)")


def evaluate_readiness(*, manifest: Mapping[str, object], profile: ProfileReceipt, limits: RuntimeLimits) -> dict[str, object]:
    blockers: list[str] = []
    findings = manifest.get("network_or_secret_findings")
    if not isinstance(findings, list) or findings:
        blockers.append("OFFLINE_OR_SECRET_SCAN_NOT_CLEAN")
    if profile.returncode != 0 or profile.timed_out:
        blockers.append("SMOKE_PROFILE_FAILED")
    if profile.wall_seconds > limits.wall_seconds * limits.max_fraction:
        blockers.append("WALL_TIME_MARGIN_INSUFFICIENT")
    if limits.memory_mib is None:
        blockers.append("DECLARED_MEMORY_LIMIT_UNKNOWN")
    elif profile.peak_rss_mib > limits.memory_mib * limits.max_fraction:
        blockers.append("MEMORY_MARGIN_INSUFFICIENT")
    return {
        "schema": "arc3-sage-kaggle-readiness/v1",
        "state": "READY_FOR_ACCOUNT_SIDE_SUBMISSION_STEPS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "limits": asdict(limits),
        "profile": asdict(profile),
        "source_manifest_sha256": manifest.get("manifest_sha256"),
        "authority": {"kaggle_submit": False, "leaderboard_claim": False, "external_network": False},
    }
