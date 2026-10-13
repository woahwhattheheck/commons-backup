"""Offline Lost in Transcription submission entrypoint.

The official runtime executes main.py from the root of submission.zip.
This scaffold never downloads a model at inference time. Put a compatible
Hugging Face ASR model under ./model/ before packing. If no model is present,
it emits empty transcripts as a deterministic plumbing baseline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

# The competition runtime has no general internet access. Make that contract
# explicit so a misconfigured local run fails closed instead of fetching assets.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import polars as pl

DATA_DIR = Path("/code_execution/data")
SUBMISSION_FORMAT_CSV = DATA_DIR / "submission_format.csv"
CLIPS_DIR = DATA_DIR / "clips"
SUBMISSION_PATH = Path("/code_execution/submission/submission.csv")
MODEL_DIR = Path(__file__).resolve().parent / "model"


def _empty_transcriber(_: Path) -> str:
    return ""


def _load_local_transformers_transcriber() -> Callable[[Path], str]:
    """Load a vendored Hugging Face ASR model without network access."""
    if not (MODEL_DIR / "config.json").is_file():
        return _empty_transcriber

    import torch
    from transformers import pipeline

    device = 0 if torch.cuda.is_available() else -1
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    asr = pipeline(
        "automatic-speech-recognition",
        model=str(MODEL_DIR),
        tokenizer=str(MODEL_DIR),
        feature_extractor=str(MODEL_DIR),
        device=device,
        torch_dtype=dtype,
        model_kwargs={"local_files_only": True},
    )

    def transcribe(audio_path: Path) -> str:
        result = asr(str(audio_path))
        if isinstance(result, dict):
            text = result.get("text", "")
        else:
            text = str(result)
        return text.strip()

    return transcribe


def main() -> None:
    submission = pl.read_csv(SUBMISSION_FORMAT_CSV)
    if "audio_filename" not in submission.columns:
        raise ValueError("submission_format.csv must contain audio_filename")
    if submission["audio_filename"].n_unique() != submission.height:
        raise ValueError("submission_format.csv contains duplicate audio_filename values")

    transcribe = _load_local_transformers_transcriber()
    predictions: list[str] = []
    for filename in submission["audio_filename"].to_list():
        audio_path = CLIPS_DIR / str(filename)
        if not audio_path.is_file():
            raise FileNotFoundError(f"missing clip: {audio_path}")
        predictions.append(transcribe(audio_path))

    output = submission.with_columns(pl.Series("transcript", predictions))
    SUBMISSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.write_csv(SUBMISSION_PATH)
    print(f"Wrote {output.height} predictions to {SUBMISSION_PATH}")


if __name__ == "__main__":
    main()
