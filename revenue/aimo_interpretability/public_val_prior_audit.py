"""Leakage audit for the 28-row public AIMO validation sample.

Counts were transcribed from the official `aimo-interp/val-sample` viewer on
2026-09-13. They are evidence about the *public sample*, not a competition
submission feature. In particular, `stability_probe.py` never imports this
module and never maps model identifiers to labels.
"""

from __future__ import annotations

from dataclasses import dataclass

SOURCE = "https://huggingface.co/datasets/aimo-interp/val-sample/viewer"


@dataclass(frozen=True)
class LabelCount:
    robust: int
    non_robust: int

    @property
    def total(self) -> int:
        return self.robust + self.non_robust


PUBLIC_MODEL_COUNTS: dict[str, LabelCount] = {
    "lukealonso/GLM-5.1-NVFP4:low": LabelCount(robust=4, non_robust=0),
    "gpt-5.2-2025-12-11:low": LabelCount(robust=3, non_robust=0),
    "huikang-gpt-oss-120b-aimo3:low": LabelCount(robust=1, non_robust=2),
    "Qwen/Qwen3.5-397B-A17B-FP8:low": LabelCount(robust=1, non_robust=6),
    "gpt-oss-120b:low": LabelCount(robust=0, non_robust=7),
    "qwen3-8b:low": LabelCount(robust=0, non_robust=1),
    "gemini-3.1-pro-preview:low": LabelCount(robust=0, non_robust=3),
}


def total_rows() -> int:
    return sum(count.total for count in PUBLIC_MODEL_COUNTS.values())


def constant_false_correct() -> int:
    return sum(count.non_robust for count in PUBLIC_MODEL_COUNTS.values())


def resubstitution_model_prior_correct() -> int:
    """Majority label per model, fitted and scored on the same public rows."""
    return sum(max(count.robust, count.non_robust) for count in PUBLIC_MODEL_COUNTS.values())


def leave_one_model_out_prior_correct() -> int:
    """Score an identity lookup when every held-out model id is unseen.

    With no evidence for a new identity, the conservative fallback is False.
    This is exactly the relevant stress test for the competition-phase model ids,
    which differ from the public sample aliases/checkpoints.
    """
    return constant_false_correct()


def report() -> dict[str, object]:
    total = total_rows()
    constant = constant_false_correct()
    resub = resubstitution_model_prior_correct()
    lomo = leave_one_model_out_prior_correct()
    return {
        "source": SOURCE,
        "rows": total,
        "robust_rows": total - constant,
        "non_robust_rows": constant,
        "constant_false": {"correct": constant, "accuracy": constant / total},
        "model_id_prior_resubstitution": {"correct": resub, "accuracy": resub / total},
        "model_id_prior_leave_one_model_out": {"correct": lomo, "accuracy": lomo / total},
    }


if __name__ == "__main__":
    import json

    print(json.dumps(report(), indent=2, sort_keys=True))
