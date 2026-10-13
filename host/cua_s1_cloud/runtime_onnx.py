"""Small, source-faithful CUA-S1 ONNX inference runtime for Vercel Python."""

from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock

import numpy as np


MODEL_SHA256 = "3b1c10893356ebe2be80bbecd8c228ec0b324bd49fd16bf4b29a07dc9ae1db3e"
MODEL_PATH = Path(__file__).with_name("cua-s1-forms.onnx")
REVISION = "f54adbf447f4ca6ec259f529ee3f2e3e09f8cc71"
CONTEXT_TOKENS = 224
OPTION_TOKENS = 96
MAX_OPTIONS = 32
_session = None
_lock = Lock()


def collate(context: str, options: list[str]) -> dict[str, np.ndarray]:
    """Match cua_s1.model.ByteCollator's UTF-8 byte IDs and zero masks."""
    if not isinstance(context, str) or not context.strip():
        raise ValueError("context must be a nonempty string")
    if (not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS
            or any(not isinstance(value, str) or not value.strip() for value in options)
            or len(set(options)) != len(options)):
        raise ValueError("options must be 2 to 32 distinct nonempty strings")
    if len(context.encode("utf-8", errors="replace")) > 4096 or any(
        len(x.encode("utf-8", errors="replace")) > 1024 for x in options
    ):
        raise ValueError("context or option exceeds request size limit")
    context_ids = np.zeros((1, CONTEXT_TOKENS), dtype=np.int64)
    option_ids = np.zeros((1, MAX_OPTIONS, OPTION_TOKENS), dtype=np.int64)
    context_bytes = context.encode("utf-8", errors="replace")[:CONTEXT_TOKENS]
    context_ids[0, :len(context_bytes)] = np.frombuffer(context_bytes, dtype=np.uint8).astype(np.int64) + 1
    for i, value in enumerate(options):
        data = value.encode("utf-8", errors="replace")[:OPTION_TOKENS]
        option_ids[0, i, :len(data)] = np.frombuffer(data, dtype=np.uint8).astype(np.int64) + 1
    option_mask = np.zeros((1, MAX_OPTIONS), dtype=np.bool_)
    option_mask[0, :len(options)] = True
    return {"context_ids": context_ids, "context_mask": context_ids != 0,
            "option_ids": option_ids, "option_mask": option_mask,
            "option_token_mask": option_ids != 0}


def session():
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                import onnxruntime as ort

                if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
                    raise RuntimeError("pinned CUA-S1 ONNX artifact hash mismatch")
                _session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    return _session


def score(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    context, options = request.get("context"), request.get("options")
    batch = collate(context, options)
    logits = session().run(["logits"], batch)[0][0, :len(options)]
    centered = logits - logits.max()
    probabilities = np.exp(centered) / np.exp(centered).sum()
    choices = [{"index": i, "option": option, "probability": float(probability)}
               for i, (option, probability) in enumerate(zip(options, probabilities))]
    return {"model": "cua-ai/cua-s1-forms", "revision": REVISION,
            "artifact_sha256": MODEL_SHA256, "selected_index": int(np.argmax(probabilities)),
            "choices": choices, "device": "cpu-onnxruntime", "executed": False,
            "context_tokens": CONTEXT_TOKENS, "option_tokens": OPTION_TOKENS,
            "max_options": MAX_OPTIONS,
            "input_truncated": {
                "context": len(context.encode("utf-8", errors="replace")) > CONTEXT_TOKENS,
                "options": [len(option.encode("utf-8", errors="replace")) > OPTION_TOKENS for option in options],
            }}
