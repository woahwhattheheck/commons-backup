"""Reproduce stored full-engine results without rerunning timed native agents."""
import argparse
import base64
import copy
import hashlib
import json
import lzma
from pathlib import Path
import zlib

import sale_window as sw
import run_native as native


def unpack(path):
    path = Path(path)
    wrapper = json.loads(path.read_text())
    if wrapper.get("schema") == "titan.sale-window-evidence-parts.v1":
        pieces = []
        for name in wrapper["parts"]:
            part = path.parent / name
            native.require(part.resolve().parent == path.resolve().parent, "unsafe evidence part path")
            pieces.append(part.read_bytes())
        packed = b"".join(pieces)
        native.require(len(packed) == wrapper["bytes"], "packed evidence length mismatch")
        native.require(hashlib.sha256(packed).hexdigest() == wrapper["sha256"], "packed evidence hash mismatch")
        wrapper = json.loads(packed)
    if wrapper.get("encoding") != "base64(lzma(UTF-8 JSON))":
        raise ValueError("unsupported evidence encoding")
    raw = lzma.decompress(base64.b64decode(wrapper["data"], validate=True))
    native.require(len(raw) == wrapper["uncompressed_bytes"], "evidence length mismatch")
    native.require(hashlib.sha256(raw).hexdigest() == wrapper["sha256"], "evidence hash mismatch")
    return json.loads(raw)


def verify(evidence, reference):
    results = []
    tapes = []
    for stored in evidence["captures"]:
        engine, Struct = sw.load_engine(reference)
        game = stored["native"]
        initial = sw.initialize(engine, Struct, game["seed"])
        encoded = stored["trace"]
        if encoded["encoding"] == "JSON":
            tape = encoded["data"]
        elif encoded["encoding"] == "swap_seats_of_capture":
            origin = encoded["data"]
            native.require(type(origin) is int and 0 <= origin < len(tapes), "invalid trace derivation")
            tape = [[pair[1], pair[0]] for pair in tapes[origin]]
        else:
            raise ValueError("unsupported trace encoding")
        raw = json.dumps(tape, sort_keys=True, separators=(",", ":")).encode()
        tapes.append(tape)
        native.require(hashlib.sha256(raw).hexdigest() == encoded["sha256"], "trace hash mismatch")
        native.require(len(raw) == encoded["uncompressed_bytes"], "trace length mismatch")
        tape = json.loads(raw)
        native.require(sw.digest(tape) == game["tape_sha256"], "action tape drift")
        baseline, census, outcomes = native.audit(engine, initial, tape, game["seat"])
        native.require(native.summarize(baseline) == stored["baseline"], "baseline replay drift")
        native.require(census == stored["census"], "engagement census drift")
        native.require(outcomes == stored["open_loop_interventions"], "timing intervention drift")
        for field in ("state_sha256", "env_sha256", "tape_sha256"):
            native.require(baseline[field] == game[field], "native capture mismatch: " + field)
        executed = sum(row["status"] == "EXECUTED_OPEN_LOOP" for row in outcomes)
        results.append({"seat": game["seat"], "seed": game["seed"], "exact": True,
                        "interventions": executed, "engine_turns": (1 + 2 * executed) * len(tape)})
    native.require(sorted(r["seat"] for r in results) == [0, 1], "both seats required")
    return {"schema": "titan.sale-window-evidence-replay.v1", "results": results,
            "engine_turns": sum(r["engine_turns"] for r in results),
            "native_agent_calls": 0,
            "scope": "exact stored open-loop results; no adaptive-policy or donor acceptance"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path(__file__).with_name("HARVESTCLOCK-EVIDENCE.json"))
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(unpack(args.evidence), args.reference), indent=2))
