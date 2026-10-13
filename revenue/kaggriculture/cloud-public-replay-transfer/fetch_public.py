"""Read public replay bodies once and preserve lossless, offline-verifiable inputs.

HTTP contract: native CompetitionApiService, retained T13 receipt at
16a2d4a7675c7e27b97bedc00f8073690bf7a763 and KESTREL 1788810125.388659.
The legacy EpisodeService probe returned HTTP400; no agent execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import urllib.error
import urllib.request

ENDPOINT = "https://api.kaggle.com/v1/competitions.CompetitionApiService/GetEpisodeReplay"
MAX_BYTES = 256_000_000
BATCH = (
    {"episode_id": 106567489, "cash_by_seat": [105675, 70683],
     "submission_by_seat": [56082977, 56081391], "own_seat": 1},
    {"episode_id": 106561613, "cash_by_seat": [79194, 78689],
     "submission_by_seat": [56038189, 56081391], "own_seat": 1},
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def episode_number(expected: dict) -> int:
    number = expected["episode_id"]
    if type(number) is not int or number <= 0:
        raise ValueError("episode number must be a positive integer")
    return number


def inspect_body(raw: bytes, expected: dict) -> dict:
    """Check the body, not its filename; never use replay features in an agent."""
    episode_number(expected)
    if len(raw) > MAX_BYTES:
        raise ValueError("response exceeds replay byte bound")
    value = json.loads(raw)
    envelope = []
    for _ in range(8):
        if isinstance(value, str):
            value = json.loads(value)
            envelope.append("json_string")
        elif isinstance(value, dict) and isinstance(value.get("steps"), list):
            break
        elif isinstance(value, dict):
            keys = [k for k in ("replay", "result", "episode", "Replay") if k in value]
            if len(keys) != 1:
                raise ValueError("unknown or ambiguous replay envelope")
            envelope.append(keys[0])
            value = value[keys[0]]
        else:
            raise ValueError("no replay object")
    if not isinstance(value, dict) or not isinstance(value.get("steps"), list):
        raise ValueError("replay envelope depth exceeded")
    if value.get("name") != "kaggriculture":
        raise ValueError("unexpected environment")
    info = value.get("info", {})
    if not isinstance(info, dict):
        raise ValueError("invalid replay metadata")
    embedded = info.get("EpisodeId")
    if embedded is not None and str(embedded) != str(expected["episode_id"]):
        raise ValueError("embedded episode identity differs")
    steps = value["steps"]
    if len(steps) != 720:
        raise ValueError("expected the complete 720-frame public episode")
    rows = steps[-1]
    if isinstance(rows, dict):
        rows = rows.get("state")
    if not isinstance(rows, list) or len(rows) != 2 or not all(isinstance(r, dict) for r in rows):
        raise ValueError("invalid terminal player rows")
    if [r.get("status") for r in rows] != ["DONE", "DONE"]:
        raise ValueError("episode not complete")
    cash = expected["cash_by_seat"]
    if [r.get("reward") for r in rows] != cash:
        raise ValueError("terminal rewards differ from public checkpoint")
    farm_sets = [r.get("observation", {}).get("farms") for r in rows]
    farm_sets = [farms for farms in farm_sets if farms is not None]
    if not farm_sets or any(not isinstance(farms, list) or len(farms) != 2 or
                           [f.get("money") for f in farms] != cash for farms in farm_sets):
        raise ValueError("terminal farm money differs from public checkpoint")
    return {"episode_id": expected["episode_id"], "embedded_episode_id": embedded,
            "identity_binding": "body_and_request" if embedded is not None else "request_and_checkpoint",
            "steps": len(steps),
            "statuses": [r["status"] for r in rows], "cash_by_seat": cash,
            "envelope": envelope, "raw_size_bytes": len(raw), "raw_sha256": sha256(raw)}


def retrieve_one(expected: dict, output: Path, opener=urllib.request.urlopen) -> dict:
    """One public request; an error is a result, not a retry instruction."""
    row = {"requested": expected, "status": "unavailable"}
    try:
        request = urllib.request.Request(
            ENDPOINT, data=json.dumps({"episodeId": expected["episode_id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Accept-Encoding": "identity"}, method="POST")
        with opener(request, timeout=45) as response:
            row["http_status"] = response.status
            raw = response.read(MAX_BYTES + 1)
        row["received_bytes"] = len(raw)
        row["response_sha256"] = sha256(raw)
        if row["http_status"] != 200:
            raise ValueError("non-success response")
        summary = inspect_body(raw, expected)
        compressed = gzip.compress(raw, mtime=0)
        name = str(episode_number(expected)) + ".raw.gz"
        with (output / name).open("xb") as stream:
            stream.write(compressed)
        row.update(status="delivered", body=summary, file=name,
                   file_size_bytes=len(compressed), file_sha256=sha256(compressed))
    except urllib.error.HTTPError as exc:
        row.update(error="HTTPError", http_status=exc.code)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        # No headers, cookies, body excerpts or raw exception payloads in logs.
        row["error"] = type(exc).__name__
    return row


def fetch_batch(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "titan.public-replay-fetch.v1", "endpoint": ENDPOINT,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "checkpoint_ts": "1788816519.316279",
                "source_commit": os.environ.get("GITHUB_SHA"),
                "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
                "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "script_sha256": sha256(Path(__file__).read_bytes()),
                "submission_binding": "Submission IDs are from the cited public checkpoint; Present body IDs and terminal state are independently checked; absent body IDs remain explicit.",
                "limits": "Public replay transport only; no gameplay, private source, policy evaluation, credentials or Kaggle writes.",
                "results": []}
    shutil.copyfile(__file__, output / "fetch_public.py")
    for expected in BATCH:
        manifest["results"].append(retrieve_one(expected, output))
        (output / "REPLAY-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def unpack(directory: Path, output: Path) -> dict:
    """Recover exact raw response bodies without importing or executing an agent."""
    manifest = json.loads((directory / "REPLAY-MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "titan.public-replay-fetch.v1":
        raise ValueError("unsupported replay manifest")
    recovered = []
    output.mkdir(parents=True, exist_ok=True)
    for row in manifest["results"]:
        if row["status"] != "delivered":
            continue
        expected = row["requested"]
        name = str(episode_number(expected)) + ".raw.gz"
        if row["file"] != name:
            raise ValueError("replay filename differs from episode")
        compressed = (directory / name).read_bytes()
        if len(compressed) != row["file_size_bytes"] or sha256(compressed) != row["file_sha256"]:
            raise ValueError("compressed replay differs from manifest")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        summary = inspect_body(raw, expected)
        if summary != row["body"]:
            raise ValueError("raw replay differs from manifest")
        target = output / (str(episode_number(expected)) + ".raw")
        if target.exists():
            if target.read_bytes() != raw:
                raise ValueError("existing raw output has different bytes")
        else:
            with target.open("xb") as stream:
                stream.write(raw)
        recovered.append(summary)
    return {"recovered": recovered, "unavailable": [r for r in manifest["results"] if r["status"] != "delivered"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument(
        "--output", type=Path,
        required=True,
    )
    unpack_parser = sub.add_parser("unpack")
    unpack_parser.add_argument(
        "--input", type=Path,
        required=True,
    )
    unpack_parser.add_argument(
        "--output", type=Path,
        required=True,
    )
    args = parser.parse_args()
    if args.command == "fetch":
        result = fetch_batch(args.output)
        print(json.dumps(result))
        return 0 if all(r["status"] == "delivered" for r in result["results"]) else 2
    result = unpack(args.input, args.output)
    print(json.dumps(result))
    return 0 if not result["unavailable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
