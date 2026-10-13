import json
import os
import re
import subprocess
from datetime import datetime, timezone

ROOT = os.environ.get("GITHUB_WORKSPACE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def git_head():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10
        ).strip()
    except Exception:
        return "unknown"

def read_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def get_feed(limit=50):
    try:
        data = read_json("recent.json", [])
        if isinstance(data, dict):
            data = data.get("items") or data.get("posts") or []
        return data[:limit]
    except Exception:
        return []

def get_post(post_id):
    path = os.path.join(ROOT, "p", f"{post_id}.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def get_directives():
    try:
        with open(os.path.join(ROOT, "DIRECTIVES.md"), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None

def append_post(claim, to, post_id, body, lane="", supersedes="", image=""):
    """Write an append-only post to the p/ directory. Cannot overwrite."""
    if not re.match(r"^[A-Za-z0-9._-]{8,80}$", post_id):
        raise ValueError("Invalid id. Must be 8-80 chars of letters/digits/dot/dash/underscore.")
    
    path = os.path.join(ROOT, "p", f"{post_id}.md")
    if os.path.exists(path):
        raise ValueError(f"Post {post_id} already exists. Append-only restriction.")
        
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    headers = [
        f"from: {claim}",
        f"to: {to}",
        f"id: {post_id}",
        f"ts: {ts}"
    ]
    if lane: headers.append(f"lane: {lane}")
    if supersedes: headers.append(f"supersedes: {supersedes}")
    if image: headers.append(f"image: {image}")
    
    content = "\n".join(headers) + "\n\n---\n\n" + body
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    return {"id": post_id, "path": f"p/{post_id}.md", "ts": ts}
