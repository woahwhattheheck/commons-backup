"""Callable wrapper for the byte-preserved Barnyard Economist V7 policy."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "upstream" / "main.py"
EXPECTED_SHA256 = "997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6"


def _load_fresh() -> Callable[[Any], Any]:
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Barnyard V7 source drift: {digest}")
    namespace = {
        "__name__": "_titan_w13_barnyard_v7_policy",
        "__file__": str(SOURCE),
        "__package__": None,
    }
    exec(compile(data, str(SOURCE), "exec"), namespace)
    fn = namespace.get("agent") or namespace.get("_kaggle_submission_entrypoint")
    if not callable(fn):
        raise RuntimeError("Barnyard V7 source exposes no callable agent")
    return fn


def make_agent() -> Callable[[Any, Any], Any]:
    """Return a fresh policy instance for one actor/game."""
    policy = _load_fresh()

    def wrapped(observation: Any, configuration: Any = None) -> Any:
        del configuration
        return policy(observation)

    return wrapped


agent = make_agent()
