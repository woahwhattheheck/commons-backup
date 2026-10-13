from __future__ import annotations
import argparse, json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from core import TRACKS, TrackPrior, TranscriptEvidence, canonical_json


def build(input_path: Path, output_path: Path) -> dict:
    rows: list[TranscriptEvidence] = []
    raw = input_path.read_bytes()
    for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            rows.append(TranscriptEvidence(**item))
        except Exception as exc:
            raise ValueError(f"invalid evidence line {lineno}: {exc}") from exc
    priors = {track: asdict(TrackPrior.fit(track, rows)) for track in sorted(TRACKS)}
    payload = {"schema_version": 1, "input_sha256": sha256(raw).hexdigest(), "priors": priors}
    output_path.write_text(canonical_json(payload), encoding="utf-8")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    build(args.input, args.output)

if __name__ == "__main__": main()
