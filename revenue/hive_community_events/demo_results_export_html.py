#!/usr/bin/env python3
"""Create fictional Lantern standings through the real loopback API and print them to HTML."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from app import Store, make_handler


def run_demo(output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    requests = 0
    with tempfile.TemporaryDirectory(prefix="lantern-html-demo-") as scratch:
        database = Path(scratch) / "fictional.sqlite3"
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Store(database)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"

        def request(path, payload=None):
            nonlocal requests
            body = None if payload is None else json.dumps(payload).encode()
            req = Request(origin + path, data=body, headers={"Content-Type": "application/json"} if body else {})
            with urlopen(req, timeout=5) as response:
                requests += 1
                return json.load(response)

        try:
            now = time.time()
            event = request("/api/events", {"title": "Fictional weekly trivia — HTML demo", "room": "Sample community", "opens": now - 30, "ends": now + 3600,
                "questions": [{"prompt": "One plus one?", "choices": ["Two", "Three"], "correct": 0, "points": 100}, {"prompt": "Which is a fruit?", "choices": ["Apple", "Chair"], "correct": 0, "points": 200}]})["id"]
            prefix = f"/api/events/{event}"
            members = [request(prefix + "/join", {"name": name})["id"] for name in ("Arden (sample)", "Bela (sample)", "Cy (sample)", "Drew (sample)")]
            for member, choices in zip(members, ((0, 0), (0, 0), (0, 1), (1, 1))):
                for index, choice in enumerate(choices):
                    request(prefix + "/answers", {"member_id": member, "question": index, "choice": choice})
            retry = request(prefix + "/answers", {"member_id": members[0], "question": 0, "choice": 0})
            request(prefix + "/finish", {})
            reconnect = request(prefix + "/join", {"member_id": members[0]})
            state = request(prefix)
            subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("results_export_html.py")), "--db", str(database), "--event", event, "--output", str(output)], check=True, timeout=15)
            rendered = output.read_text(encoding="utf-8")
            checks = {
                "competition_ranks": [row["rank"] for row in state["leaderboard"]] == [1, 1, 3, 4],
                "answer_retry_replayed": retry["replayed"] is True,
                "reconnect_retains_member": reconnect["id"] == members[0],
                "reconnect_references_excluded": all(member not in rendered for member in members),
                "question_text_excluded": "One plus one?" not in rendered,
                "standings_present": all(row["name"] in rendered for row in state["leaderboard"]),
                "self_contained": "<script" not in rendered.lower() and "https://" not in rendered.lower() and "http://" not in rendered.lower(),
            }
            if not all(checks.values()):
                raise RuntimeError(f"Acceptance failed: {checks}")
            return {"fixture": "fictional; no customer data", "http_requests": requests, "checks": checks, "players": 4, "transport": "real loopback HTTP", "external_services_contacted": False}
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        receipt = run_demo(args.output)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Demo failed: {error}", file=sys.stderr); return 2
    print(json.dumps(receipt, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
