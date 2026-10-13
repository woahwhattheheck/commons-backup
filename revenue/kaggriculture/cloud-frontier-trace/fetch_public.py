"""Retrieve an explicitly selected public replay through the ordinary Kaggle road.

Public mode sends no credential. Configured mode delegates authentication to an
already-configured official CLI; this module never reads or prints its secrets.
The API returns a raw download, not necessarily a JSON response envelope.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

ENDPOINT = "https://api.kaggle.com/v1/competitions.CompetitionApiService/GetEpisodeReplay"
SDK_REF = "f983c97287bf274ebab506aac85eda6efebe3b32"
MAX_BYTES = 100_000_000


def fetch(episode_id, output, configured_cli=False):
    if episode_id <= 0:
        raise ValueError("Episode ID must be positive")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    record = {"episode_id": episode_id, "endpoint": ENDPOINT, "sdk_ref": SDK_REF,
              "transport": "configured_official_cli" if configured_cli else "public_post"}
    try:
        if configured_cli:
            executable = shutil.which("kaggle")
            if not executable:
                raise RuntimeError("Configured Kaggle CLI is unavailable in this runtime")
            with tempfile.TemporaryDirectory(prefix="kaggle-public-replay-") as temp:
                completed = subprocess.run([executable, "competitions", "replay", str(episode_id),
                    "-p", temp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if completed.returncode:
                    raise RuntimeError(f"Configured replay command exited {completed.returncode}; output not published")
                files = [p for p in Path(temp).rglob("*") if p.is_file()]
                if len(files) != 1:
                    raise RuntimeError("Expected one replay download from configured CLI")
                if files[0].stat().st_size > MAX_BYTES:
                    raise ValueError("Replay exceeds bounded transport size")
                body = files[0].read_bytes()
        else:
            request = urllib.request.Request(ENDPOINT,
                data=json.dumps({"episodeId": episode_id}).encode(),
                headers={"Content-Type": "application/json", "Accept": "*/*"}, method="POST")
            with urllib.request.urlopen(request, timeout=40) as response:
                record.update(http_status=response.status, content_type=response.headers.get("Content-Type"))
                body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Replay exceeds bounded transport size")
        path = output / f"episode-{episode_id}.raw"
        path.write_bytes(body)
        record.update(status="DOWNLOADED", bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), file=path.name)
    except urllib.error.HTTPError as exc:
        record.update(status="AUTH_REQUIRED" if exc.code in (401, 403) else "HTTP_ERROR", http_status=exc.code)
    except Exception as exc:
        record.update(status="UNAVAILABLE", reason=str(exc))
    (output / "fetch.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--configured-cli", action="store_true")
    args = parser.parse_args()
    result = fetch(args.episode_id, args.output, args.configured_cli)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "DOWNLOADED" else 2)
