from __future__ import annotations
import hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "managed-clipping-project-v1"
DEFAULT_FPS = 30.0


class ManagedClippingError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ManagedClippingError(f"required executable not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise ManagedClippingError(f"command failed ({cmd[0]}): {detail}") from exc


def probe_source(source: Path) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_file():
        raise ManagedClippingError(f"source does not exist: {source}")
    proc = _run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)
    ])
    raw = json.loads(proc.stdout)
    video = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ManagedClippingError("source has no video stream")
    duration = raw.get("format", {}).get("duration") or video.get("duration")
    if duration is None:
        raise ManagedClippingError("source duration unavailable")
    duration_ms = int(round(float(duration) * 1000))
    if duration_ms <= 0:
        raise ManagedClippingError("source duration must be positive")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ManagedClippingError("source dimensions unavailable")
    return {
        "path": str(source),
        "filename": source.name,
        "size": source.stat().st_size,
        "sha256": _sha256(source),
        "duration_ms": duration_ms,
        "width": width,
        "height": height,
    }


def _validate_project(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema") != SCHEMA:
        raise ManagedClippingError(f"unsupported project schema: {data.get('schema')!r}")
    if not isinstance(data.get("moments"), list):
        raise ManagedClippingError("project moments must be a list")
    return data


def load_project(path: Path) -> dict[str, Any]:
    return _validate_project(json.loads(path.read_text(encoding="utf-8")))


def save_project(path: Path, data: dict[str, Any]) -> None:
    _validate_project(data)
    data["updated_at"] = _utc_now()
    _json_dump(path, data)


def verify_source(project: dict[str, Any]) -> Path:
    source = Path(project["source"]["path"])
    if not source.is_file():
        raise ManagedClippingError(f"source missing: {source}")
    expected = project["source"]
    if source.stat().st_size != expected["size"] or _sha256(source) != expected["sha256"]:
        raise ManagedClippingError("source synchronization failure: bytes differ from project fingerprint")
    return source

