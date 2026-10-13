#!/usr/bin/env python3
"""Reproducible GSM8K evaluator for an OpenAI-compatible Spark-X2.5 endpoint."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

import requests
from datasets import load_dataset

DATASET_ID = "openai/gsm8k"
DATASET_CONFIG = "main"
DATASET_SPLIT = "test"
DEFAULT_MODEL_ID = "XHToken/Spark-X2.5-1.7B"
DEFAULT_SEED = 20260908

NUMBER_TOKEN = r"[-+]?\$?(?:\d[\d,]*)(?:\.\d+)?(?:/\d[\d,]*(?:\.\d+)?)?%?"
FINAL_RE = re.compile(rf"(?im)^\s*FINAL\s*:\s*({NUMBER_TOKEN})\s*[.!]?\s*$")
ANY_NUMBER_RE = re.compile(NUMBER_TOKEN)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except FileNotFoundError:
        return None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_capture(argv: list[str]) -> dict[str, Any]:
    if not shutil.which(argv[0]):
        return {"available": False}
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return {
            "available": True,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"available": True, "error": f"{type(exc).__name__}: {exc}"}


def environment_receipt() -> dict[str, Any]:
    packages = {
        name: package_version(name)
        for name in (
            "accelerate",
            "datasets",
            "huggingface_hub",
            "openai",
            "requests",
            "torch",
            "transformers",
            "vllm",
        )
    }
    return {
        "python": sys.version.split()[0],
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "packages": packages,
        "nvidia_smi": run_capture(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ]
        ),
        "vllm_version_command": run_capture(["vllm", "--version"]),
    }


def parse_numeric(token: str | None) -> Fraction | None:
    if not token:
        return None
    cleaned = token.strip().replace("$", "").replace(",", "").replace("%", "")
    try:
        if "/" in cleaned:
            num, den = cleaned.split("/", 1)
            denominator = Fraction(Decimal(den))
            if denominator == 0:
                return None
            return Fraction(Decimal(num)) / denominator
        return Fraction(Decimal(cleaned))
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def extract_gold(answer: str) -> tuple[str | None, Fraction | None]:
    marker = answer.rfind("####")
    candidate = answer[marker + 4 :].strip() if marker >= 0 else answer.strip()
    match = ANY_NUMBER_RE.search(candidate)
    if not match:
        return None, None
    token = match.group(0)
    return token, parse_numeric(token)


def extract_prediction(text: str) -> tuple[str | None, Fraction | None, str]:
    final_matches = FINAL_RE.findall(text)
    if final_matches:
        token = final_matches[-1]
        return token, parse_numeric(token), "final_label"

    all_numbers = ANY_NUMBER_RE.findall(text)
    if all_numbers:
        token = all_numbers[-1]
        return token, parse_numeric(token), "last_numeric_fallback"
    return None, None, "unparseable"


def prompt_for(question: str, mode: str) -> str:
    if mode == "direct":
        return (
            "Solve this grade-school math problem. "
            "Return only one line in the form `FINAL: <number>`.\n\n"
            f"Problem:\n{question}"
        )
    if mode == "reason":
        return (
            "Solve this grade-school math problem. "
            "Give a concise, checkable derivation. "
            "End with a separate line exactly in the form `FINAL: <number>`.\n\n"
            f"Problem:\n{question}"
        )
    raise ValueError(f"unknown prompt mode: {mode}")


def sanitize_revision(revision: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", revision).strip("-")[:40] or "rev"


def request_completion(
    *,
    base_url: str,
    served_model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    seed: int,
    timeout_seconds: int,
) -> tuple[dict[str, Any], float]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": served_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "seed": seed,
    }
    start = time.perf_counter()
    response = requests.post(url, json=body, timeout=timeout_seconds)
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    payload = response.json()
    return {"request": body, "response": payload}, elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:30000/v1")
    parser.add_argument("--served-model", default="spark25")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--dataset-revision", required=True)
    parser.add_argument("--prompt-mode", choices=("direct", "reason"), required=True)
    parser.add_argument("--sample-size", type=int, default=128)
    parser.add_argument("--sample-seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--generation-seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output-root", default="runs")
    args = parser.parse_args()

    if args.sample_size <= 0:
        parser.error("--sample-size must be positive")
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")
    if args.temperature < 0:
        parser.error("--temperature must be >= 0")
    if not (0 < args.top_p <= 1):
        parser.error("--top-p must be in (0, 1]")

    max_tokens = args.max_tokens

    dataset = load_dataset(
        DATASET_ID,
        DATASET_CONFIG,
        split=DATASET_SPLIT,
        revision=args.dataset_revision,
    )
    if args.sample_size > len(dataset):
        parser.error(f"--sample-size {args.sample_size} exceeds split size {len(dataset)}")

    sampler = random.Random(args.sample_seed)
    indices = sampler.sample(range(len(dataset)), args.sample_size)

    run_name = (
        f"{args.prompt_mode}-n{args.sample_size}-s{args.sample_seed}-"
        f"{sanitize_revision(args.model_revision)}"
    )
    run_dir = Path(args.output_root) / run_name
    if run_dir.exists():
        raise SystemExit(
            f"refusing to mix evidence with existing run directory: {run_dir}. "
            "Choose another --output-root or remove the directory deliberately."
        )
    run_dir.mkdir(parents=True)

    script_path = Path(__file__).resolve()
    requirements_path = script_path.with_name("requirements.txt")
    manifest = {
        "schema_version": 1,
        "started_at_utc": utc_now(),
        "model": {
            "id": args.model_id,
            "revision": args.model_revision,
            "served_name": args.served_model,
            "base_url": args.base_url,
        },
        "dataset": {
            "id": DATASET_ID,
            "config": DATASET_CONFIG,
            "split": DATASET_SPLIT,
            "revision": args.dataset_revision,
            "sample_size": args.sample_size,
            "sample_seed": args.sample_seed,
            "indices": indices,
        },
        "generation": {
            "prompt_mode": args.prompt_mode,
            "generation_seed": args.generation_seed,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "max_tokens": max_tokens,
            "timeout_seconds": args.timeout_seconds,
        },
        "harness": {
            "script_sha256": sha256_file(script_path),
            "requirements_sha256": sha256_file(requirements_path),
        },
        "environment": environment_receipt(),
        "privacy_note": (
            "No environment variables, tokens, hostname, cwd, or cache path are recorded."
        ),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    raw_path = run_dir / "raw.jsonl"
    correct = 0
    parsed = 0
    total_latency = 0.0
    prompt_token_total = 0
    completion_token_total = 0

    with raw_path.open("x", encoding="utf-8") as out:
        for ordinal, dataset_index in enumerate(indices):
            item = dataset[dataset_index]
            question = str(item["question"])
            gold_answer = str(item["answer"])
            gold_token, gold_value = extract_gold(gold_answer)
            if gold_value is None:
                raise RuntimeError(f"could not parse gold answer at dataset index {dataset_index}")

            prompt = prompt_for(question, args.prompt_mode)
            transaction, latency = request_completion(
                base_url=args.base_url,
                served_model=args.served_model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
                seed=args.generation_seed + ordinal,
                timeout_seconds=args.timeout_seconds,
            )
            response_payload = transaction["response"]
            choices = response_payload.get("choices") or []
            if not choices:
                raise RuntimeError(f"response contained no choices at dataset index {dataset_index}")
            assistant_text = str(choices[0].get("message", {}).get("content", ""))
            pred_token, pred_value, parse_source = extract_prediction(assistant_text)
            is_correct = pred_value is not None and pred_value == gold_value

            usage = response_payload.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)

            row = {
                "schema_version": 1,
                "ordinal": ordinal,
                "dataset_index": dataset_index,
                "question": question,
                "gold_answer_raw": gold_answer,
                "gold_token": gold_token,
                "gold_value": str(gold_value),
                "prompt_mode": args.prompt_mode,
                "prompt": prompt,
                "generation_seed": args.generation_seed + ordinal,
                "request": transaction["request"],
                "raw_response": response_payload,
                "assistant_text": assistant_text,
                "prediction_token": pred_token,
                "prediction_value": None if pred_value is None else str(pred_value),
                "parse_source": parse_source,
                "correct": is_correct,
                "latency_seconds": round(latency, 6),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                "assistant_text_sha256": sha256_bytes(assistant_text.encode("utf-8")),
            }
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            out.flush()

            correct += int(is_correct)
            parsed += int(pred_value is not None)
            total_latency += latency
            prompt_token_total += prompt_tokens
            completion_token_total += completion_tokens
            print(
                f"[{ordinal + 1:03d}/{args.sample_size}] "
                f"idx={dataset_index} correct={is_correct} parse={parse_source}",
                flush=True,
            )

    summary = {
        "schema_version": 1,
        "finished_at_utc": utc_now(),
        "n": args.sample_size,
        "correct": correct,
        "accuracy": correct / args.sample_size,
        "parsed": parsed,
        "unparseable": args.sample_size - parsed,
        "parse_rate": parsed / args.sample_size,
        "prompt_mode": args.prompt_mode,
        "latency_seconds_total": round(total_latency, 6),
        "latency_seconds_mean": round(total_latency / args.sample_size, 6),
        "prompt_tokens_total": prompt_token_total,
        "completion_tokens_total": completion_token_total,
        "raw_jsonl_sha256": sha256_file(raw_path),
        "scoring": (
            "Exact equality after transparent numeric normalization. "
            "Prefer the final `FINAL:` line; otherwise use the last numeric token and "
            "mark the row `last_numeric_fallback`. Unparseable outputs are wrong."
        ),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
