"""Public-data AIMO Interpretability runtime based on answer invariance.

The competition calls ``are_robust(model_id, problems)`` with only a model id and
problem texts. This module therefore avoids public model-id label lookups. It
asks the *current evaluated model* to solve each problem under three benign,
semantics-preserving wrappers and classifies a problem as robust when at least
two normalized final-answer signatures agree.

The inference runtime is loaded lazily so this file remains importable in tests
without torch/transformers installed. At most one model is retained in memory;
competition workers evaluate one model id at a time and the 120B checkpoint is
large enough that keeping multiple checkpoints would waste VRAM.
"""

from __future__ import annotations

from collections import Counter
import gc
import re
from typing import Callable, Iterable

MAX_NEW_TOKENS = 192
MAX_PROMPT_TOKENS = 4096

# These wrappers intentionally do not rewrite mathematical entities or numbers.
# They probe instruction/distractor sensitivity while keeping the exact problem
# text present in every call.
PROMPT_WRAPPERS: tuple[str, ...] = (
    "Solve the mathematical problem below. Return only the final answer, with no explanation.\n\n{problem}",
    "Independently verify the mathematical problem below, then return only the final answer. Do not explain your reasoning.\n\n{problem}",
    "Unrelated note: a day has 24 hours. Ignore that note. Solve the mathematical problem below and return only the final answer.\n\n{problem}",
)

_RUNTIME: dict[str, object] = {}


def _strip_outer_math(text: str) -> str:
    text = text.strip()
    pairs = (("$", "$"), ("\\(", "\\)"), ("\\[", "\\]"))
    changed = True
    while changed:
        changed = False
        for left, right in pairs:
            if text.startswith(left) and text.endswith(right) and len(text) >= len(left) + len(right):
                text = text[len(left) : -len(right)].strip()
                changed = True
    return text


def _last_boxed(text: str) -> str | None:
    """Return the final simple ``\\boxed{...}`` payload, if present.

    A small brace scanner is used rather than a regex so common nested LaTeX such
    as ``\\boxed{\\frac{1}{2}}`` is handled correctly.
    """
    marker = r"\boxed{"
    start = text.rfind(marker)
    if start < 0:
        return None
    i = start + len(marker)
    depth = 1
    payload_start = i
    while i < len(text):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[payload_start:i]
        i += 1
    return None


def answer_signature(response: str) -> str:
    """Extract a conservative comparable final-answer signature.

    Empty/obviously truncated outputs return ``""`` and therefore cannot vote a
    problem robust. The normalization deliberately avoids algebraic evaluation:
    different expressions are considered equal only when their textual final
    answers normalize to the same compact form.
    """
    if not isinstance(response, str):
        return ""
    text = response.strip()
    if not text:
        return ""

    boxed = _last_boxed(text)
    if boxed is not None:
        candidate = boxed
    else:
        # Prefer an explicit final/answer marker, taking the last one in case the
        # model revises itself. Otherwise use the final non-empty line.
        matches = list(
            re.finditer(
                r"(?im)^\s*(?:final\s+answer|answer)\s*[:=]\s*(.+?)\s*$",
                text,
            )
        )
        if matches:
            candidate = matches[-1].group(1)
        else:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                return ""
            candidate = lines[-1]

    candidate = candidate.strip().strip("`*_ ")
    candidate = re.sub(r"^(?:final\s+answer|answer)\s*[:=]\s*", "", candidate, flags=re.I)
    candidate = candidate.rstrip(".。").strip()
    candidate = _strip_outer_math(candidate)
    candidate = candidate.replace("−", "-").replace("–", "-").replace("—", "-")
    candidate = candidate.replace("\\,", "").replace("\\!", "")
    candidate = re.sub(r"\s+", "", candidate)
    candidate = candidate.lower()

    # A whole paragraph as the "last line" usually means generation was cut off
    # before a final answer. Refuse to turn that into a spurious agreement.
    if not candidate or len(candidate) > 160:
        return ""
    return candidate


def majority_signature(responses: Iterable[str]) -> str:
    signatures = [answer_signature(response) for response in responses]
    counts = Counter(signature for signature in signatures if signature)
    if not counts:
        return ""
    signature, count = counts.most_common(1)[0]
    return signature if count >= 2 else ""


def classify_from_responses(responses: Iterable[str]) -> bool:
    """Classify robustness from three independently wrapped model responses."""
    return bool(majority_signature(responses))


def build_prompts(problem: str) -> tuple[str, ...]:
    if not isinstance(problem, str):
        raise TypeError("problem must be a string")
    return tuple(wrapper.format(problem=problem) for wrapper in PROMPT_WRAPPERS)


def predict_with_generator(
    model_id: str,
    problems: list[str],
    generator: Callable[[str, str], str],
) -> list[bool]:
    """Pure orchestration seam used by the real runtime and focused tests."""
    if not isinstance(model_id, str) or not model_id.strip():
        return [False for _ in problems]

    predictions: list[bool] = []
    for problem in problems:
        if not isinstance(problem, str) or not problem.strip():
            predictions.append(False)
            continue
        responses: list[str] = []
        try:
            for prompt in build_prompts(problem):
                response = generator(model_id, prompt)
                responses.append(response if isinstance(response, str) else "")
        except Exception:
            # Competition scoring requires real bools. A per-problem inference
            # failure therefore degrades to the conservative non-robust class
            # instead of aborting the entire batch with invalid predictions.
            predictions.append(False)
            continue
        predictions.append(classify_from_responses(responses))
    return predictions


def _release_runtime() -> None:
    _RUNTIME.clear()
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _load_runtime(model_id: str):
    cached_id = _RUNTIME.get("model_id")
    if cached_id == model_id:
        return _RUNTIME["tokenizer"], _RUNTIME["model"]

    _release_runtime()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else (
        torch.float16 if torch.cuda.is_available() else torch.float32
    )
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=dtype,
        device_map="auto" if torch.cuda.is_available() else None,
        local_files_only=True,
    )
    if not torch.cuda.is_available():
        model.to("cpu")
    model.eval()
    _RUNTIME.update(model_id=model_id, tokenizer=tokenizer, model=model)
    return tokenizer, model


def _format_chat_prompt(tokenizer, prompt: str) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            pass
    return prompt


def generate_response(model_id: str, prompt: str) -> str:
    """Generate one deterministic answer using only the evaluator's local model."""
    import torch

    tokenizer, model = _load_runtime(model_id)
    rendered = _format_chat_prompt(tokenizer, prompt)
    encoded = tokenizer(
        rendered,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_PROMPT_TOKENS,
    )
    try:
        device = next(model.parameters()).device
    except StopIteration:
        device = torch.device("cpu")
    encoded = {name: value.to(device) for name, value in encoded.items()}
    input_length = int(encoded["input_ids"].shape[-1])
    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = tokenizer.eos_token_id

    with torch.inference_mode():
        output = model.generate(
            **encoded,
            do_sample=False,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=pad_token_id,
            use_cache=True,
        )
    generated = output[0, input_length:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def predict_robustness(model_id: str, problems: list[str]) -> list[bool]:
    return predict_with_generator(model_id, problems, generate_response)
