#!/usr/bin/env python3
"""Offline-only ASR starter for the official Lost in Transcription runtime.

Package an open-weight Hugging Face speech-to-text checkpoint under ./model/.
No network access or hosted inference is used.
"""
from __future__ import annotations

import csv
from pathlib import Path

import librosa
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor


DATA_DIR = Path("/code_execution/data")
CLIPS_DIR = DATA_DIR / "clips"
SUBMISSION_FORMAT = DATA_DIR / "submission_format.csv"
SUBMISSION_PATH = Path("/code_execution/submission/submission.csv")
MODEL_DIR = Path(__file__).resolve().parent / "model"
SAMPLE_RATE = 16_000


def _load_model():
    if not MODEL_DIR.is_dir():
        raise RuntimeError(
            "Missing ./model directory. Bundle a competition-permitted open-weight "
            "speech-to-text checkpoint in the submission ZIP."
        )
    processor = AutoProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        MODEL_DIR,
        local_files_only=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    return processor, model, device


def transcribe(audio_path: Path, processor, model, device) -> str:
    audio, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
    features = processor(
        audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="pt",
    )
    model_inputs = {
        key: value.to(device)
        for key, value in features.items()
        if isinstance(value, torch.Tensor)
    }
    with torch.inference_mode():
        generated = model.generate(**model_inputs)
    text = processor.batch_decode(generated, skip_special_tokens=True)[0]
    return " ".join(text.split())


def main() -> None:
    with SUBMISSION_FORMAT.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "audio_filename" not in rows[0]:
        raise RuntimeError("submission_format.csv must contain audio_filename")

    processor, model, device = _load_model()
    output = []
    for row in rows:
        filename = row["audio_filename"]
        output.append(
            {
                "audio_filename": filename,
                "transcript": transcribe(CLIPS_DIR / filename, processor, model, device),
            }
        )

    SUBMISSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUBMISSION_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["audio_filename", "transcript"])
        writer.writeheader()
        writer.writerows(output)
    print(f"Wrote {len(output)} predictions to {SUBMISSION_PATH}")


if __name__ == "__main__":
    main()
