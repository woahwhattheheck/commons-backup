"""Decode immutable measurement evidence and export complete actor action traces."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read(bundle: Path = HERE / "evidence.json.gz.b64",
         manifest: Path = HERE / "EVIDENCE-MANIFEST.json") -> dict[str, Any]:
    pins = json.loads(manifest.read_text(encoding="utf-8"))
    compressed = base64.b64decode("".join(bundle.read_text(encoding="ascii").split()), validate=True)
    if len(compressed) != pins["compressed_bytes"] or hashlib.sha256(compressed).hexdigest() != pins["compressed_sha256"]:
        raise ValueError("Compressed evidence digest or size differs")
    raw = gzip.decompress(compressed)
    if len(raw) != pins["uncompressed_bytes"] or hashlib.sha256(raw).hexdigest() != pins["uncompressed_sha256"]:
        raise ValueError("Decoded evidence digest or size differs")
    data = json.loads(raw)
    if data["schema"] != "titan.cok-activation-evidence.v1":
        raise ValueError("Unexpected evidence schema")
    for case in data["cases"]:
        for position in (0, 1):
            rows = actions(data, case, position)
            actual = hashlib.sha256(b"".join(encoded(row) + b"\n" for row in rows)).hexdigest()
            if actual != case["action_log_sha256_by_seat"][position]:
                raise ValueError("Reconstructed action trace differs")
    for filename, content in data["measurement_source"].items():
        if hashlib.sha256(content.encode()).hexdigest() != pins["source_files"][filename]:
            raise ValueError("Historical measurement source differs")
    return data


def actions(data: dict[str, Any], case: dict[str, Any], position: int) -> list[dict[str, Any]]:
    if position not in (0, 1):
        raise ValueError("Player position must be 0 or 1")
    stream = data["streams"][case["stream_by_seat"][position]]
    orders = data["orders"]
    return [{"step": step, "action": {"farmer": orders[row[0]],
              "hands": [orders[i] for i in row[1]], "market": [orders[i] for i in row[2]]}}
            for step, row in enumerate(stream)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = read()
    args.output.mkdir(parents=True, exist_ok=False)
    for case in data["cases"]:
        root = args.output / f"seed-{case['seed']}-cok-{case['candidate_seat']}"
        root.mkdir()
        for position in (0, 1):
            (root / f"player-{position}.jsonl").write_bytes(b"".join(encoded(row) + b"\n" for row in actions(data, case, position)))
        (root / "frames.json").write_text(json.dumps(case["frames"], indent=2) + "\n", encoding="utf-8")
    (args.output / "GAMES.json").write_text(json.dumps(data["original_games"], indent=2) + "\n", encoding="utf-8")
    historical = args.output / "historical-measurement-source"
    historical.mkdir()
    for name, content in data["measurement_source"].items():
        (historical / name).write_text(content, encoding="utf-8")
    print(json.dumps({"games": len(data["cases"]), "complete_actor_traces": 4,
                      "original_own_observation_checkpoints": 18}))


if __name__ == "__main__":
    main()
