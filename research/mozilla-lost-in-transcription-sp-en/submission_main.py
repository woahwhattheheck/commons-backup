"""Competition-runtime entrypoint template for an offline faster-whisper ensemble.

Copy this file to main.py inside a submission package. Model weights and prior.json are
operator-supplied local assets; this repository intentionally does not redistribute them.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core import ConsensusConfig, Hypothesis, NgramPrior, choose_consensus  # noqa: E402

DATA_DIR = Path("/code_execution/data")
FORMAT = DATA_DIR / "submission_format.csv"
CLIPS = DATA_DIR / "clips"
OUTPUT = Path("/code_execution/submission/submission.csv")
CONFIG = SRC_DIR / "model_config.json"


def _inside_src(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(SRC_DIR)
    except ValueError as exc:
        raise ValueError(f"asset escapes submission root: {path}") from exc
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def _load_config() -> dict:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    models = raw.get("models")
    if not isinstance(models, list) or len(models) < 2:
        raise ValueError("model_config.json must declare at least two local models")
    for item in models:
        if item.get("kind") != "faster-whisper":
            raise ValueError("only the audited faster-whisper adapter is accepted")
        _inside_src(SRC_DIR / item["model_path"])
        rel = float(item.get("reliability", 1.0))
        if not math.isfinite(rel) or rel <= 0:
            raise ValueError("model reliability must be finite and > 0")
    return raw


def _transcribe(model, audio: Path, item: dict) -> Hypothesis:
    segments, _ = model.transcribe(
        str(audio),
        beam_size=int(item.get("beam_size", 5)),
        language=item.get("language"),
        vad_filter=bool(item.get("vad_filter", True)),
        condition_on_previous_text=False,
    )
    text_parts: list[str] = []
    weighted_lp = 0.0
    duration = 0.0
    for seg in segments:
        text_parts.append(seg.text.strip())
        seg_dur = max(0.001, float(seg.end) - float(seg.start))
        weighted_lp += float(seg.avg_logprob) * seg_dur
        duration += seg_dur
    text = " ".join(part for part in text_parts if part).strip()
    if not text:
        raise RuntimeError(f"empty ASR output from {item['name']}")
    avg_lp = weighted_lp / max(duration, 0.001)
    seq_lp = avg_lp * max(1, len(text.split()))
    return Hypothesis(text=text, source=str(item["name"]), acoustic_logprob=seq_lp, reliability=float(item.get("reliability", 1.0)))


def main() -> None:
    if os.environ.get("http_proxy") or os.environ.get("https_proxy"):
        raise RuntimeError("network proxy variables are forbidden in offline execution")
    config = _load_config()
    from faster_whisper import WhisperModel

    loaded = []
    for item in config["models"]:
        model_path = _inside_src(SRC_DIR / item["model_path"])
        loaded.append((item, WhisperModel(str(model_path), device=item.get("device", "cuda"), compute_type=item.get("compute_type", "float16"), local_files_only=True)))

    prior_path = SRC_DIR / "prior.json"
    prior = NgramPrior.from_json(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
    cc = ConsensusConfig(**config.get("consensus", {}))

    with FORMAT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "audio_filename" not in rows[0]:
        raise RuntimeError("invalid submission_format.csv")

    out_rows = []
    for row in rows:
        filename = row["audio_filename"]
        audio = (CLIPS / filename).resolve()
        try:
            audio.relative_to(CLIPS.resolve())
        except ValueError as exc:
            raise RuntimeError(f"audio path traversal: {filename}") from exc
        if not audio.is_file():
            raise FileNotFoundError(audio)
        hyps = [_transcribe(model, audio, item) for item, model in loaded]
        result = choose_consensus(hyps, prior=prior, config=cc)
        out_rows.append({"audio_filename": filename, "transcript": result.text})

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["audio_filename", "transcript"])
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"Wrote {len(out_rows)} predictions to {OUTPUT}")


if __name__ == "__main__":
    main()
