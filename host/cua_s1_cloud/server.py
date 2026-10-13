"""HTTP choice-scoring service using the official CUA-S1-FORMS checkpoint.

This service performs inference only. It never receives browser credentials or
performs UI actions. A container host can keep it available without the owner
laptop or a Codex session.
"""

from __future__ import annotations

import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.request import urlopen


REVISION = "f54adbf447f4ca6ec259f529ee3f2e3e09f8cc71"
FILES = {
    "cua-s1-forms.safetensors": "05954c1caf51c2fb6c13ea4acbfc88a2e7653dea192252bb51dc89e76a356ddc",
    "cua-s1-forms.json": "62d31e2f9a001a8e9b6f8534c5194d07ebdd3f9d62ef1ac281906622992650ca",
}
MAX_BODY = 65536


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_checkpoint(directory: Path) -> Path:
    """Fetch two pinned official files and verify exact expected bytes."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        destination = directory / name
        if destination.exists() and _sha256(destination) == expected:
            continue
        url = f"https://huggingface.co/cua-ai/cua-s1-forms/resolve/{REVISION}/{name}"
        temporary = destination.with_suffix(destination.suffix + ".download")
        with urlopen(url, timeout=60) as remote, temporary.open("wb") as output:
            for block in iter(lambda: remote.read(1024 * 1024), b""):
                output.write(block)
        if _sha256(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"checkpoint hash mismatch: {name}")
        temporary.replace(destination)
    return directory / "cua-s1-forms.safetensors"


class Scorer:
    def __init__(self, checkpoint: Path):
        from cua_s1.model import load_checkpoint, select_device

        self.model, self.collator, self.config = load_checkpoint(checkpoint, select_device("cpu"))
        self.lock = Lock()

    def score(self, request: dict) -> dict:
        from cua_s1.model import ChoiceExample
        import torch

        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        context = request.get("context")
        options = request.get("options")
        if not isinstance(context, str) or not context.strip():
            raise ValueError("context must be a nonempty string")
        if not isinstance(options, list) or not 2 <= len(options) <= 32 or any(
            not isinstance(option, str) or not option.strip() for option in options
        ) or len(set(options)) != len(options):
            raise ValueError("options must be 2 to 32 distinct nonempty strings")
        if len(context.encode("utf-8")) > 4096 or any(len(x.encode("utf-8")) > 1024 for x in options):
            raise ValueError("context or option exceeds request size limit")
        with self.lock, torch.inference_mode():
            batch = self.collator([ChoiceExample(context, tuple(options), 0)])
            probabilities = self.model(batch).softmax(dim=-1)[0, :len(options)].tolist()
        choices = [{"index": i, "option": x, "probability": p}
                   for i, (x, p) in enumerate(zip(options, probabilities))]
        return {"model": "cua-ai/cua-s1-forms", "revision": REVISION,
                "selected_index": max(choices, key=lambda choice: choice["probability"])["index"],
                "choices": choices, "device": "cpu", "executed": False,
                "context_tokens": self.config["context_tokens"],
                "option_tokens": self.config["option_tokens"]}


def handler_for(scorer: Scorer):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict):
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"ok": True, "model": "cua-ai/cua-s1-forms", "revision": REVISION})
            else:
                self._json(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/score":
                return self._json(404, {"error": "not_found"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size < 1 or size > MAX_BODY:
                    return self._json(413, {"error": "body_size_invalid"})
                request = json.loads(self.rfile.read(size))
                return self._json(200, scorer.score(request))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": "invalid_request", "message": str(exc)})

    return Handler


def main() -> None:
    checkpoint = ensure_checkpoint(Path(os.environ.get("CUA_S1_MODEL_DIR", "/models")))
    scorer = Scorer(checkpoint)
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), handler_for(scorer)).serve_forever()


if __name__ == "__main__":
    main()
