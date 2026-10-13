"""Codabench entrypoint for the AIMO Interpretability answer-stability probe."""

from stability_probe import predict_robustness


def are_robust(model_id: str, problems: list[str]) -> list[bool]:
    return predict_robustness(model_id, problems)
