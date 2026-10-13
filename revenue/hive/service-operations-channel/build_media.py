#!/usr/bin/env python3
"""Rebuild the first three Hive023 tutorial recordings from the landed Hive09 app.

Uses only synthetic data. It does not post media, contact customers, or mutate the
source application. Videos are frame captures of the landed UI backed by the exact
landed Store implementation; the real HTTP handler is smoke-tested separately.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

EXPECTED_WORKFLOW_BLOB = "da339d714fd610689dafaca5a2e47c57d772edce"
EXPECTED_INDEX_BLOB = "62f98f0bfd798d8b5abe74094337fea3af7c991a"


def git_blob(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def load_source(workflow_path: Path):
    spec = importlib.util.spec_from_file_location("hive09_workflow_for_tutorial", workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load landed workflow source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_source(source_dir: Path):
    workflow = source_dir / "workflow.py"
    index = source_dir / "index.html"
    actual = {"workflow_git_blob": git_blob(workflow), "index_git_blob": git_blob(index)}
    expected = {"workflow_git_blob": EXPECTED_WORKFLOW_BLOB, "index_git_blob": EXPECTED_INDEX_BLOB}
    if actual != expected:
        raise SystemExit(f"Source pin mismatch: expected {expected}, got {actual}")
    return workflow, actual


def post_json(page, path: str, value: dict):
    return page.evaluate(
        """async ([path,value]) => {
            const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)});
            const body = await r.json();
            if (!r.ok) throw new Error(JSON.stringify(body));
            return body;
        }""",
        [path, value],
    )


def get_json(page, path: str):
    return page.evaluate(
        """async path => { const r=await fetch(path); const body=await r.json(); if(!r.ok) throw new Error(JSON.stringify(body)); return body; }""",
        path,
    )


def route_store(route, request, store, workflow):
    """Build-only browser transport: exact UI -> exact landed Store methods."""
    from urllib.parse import urlsplit
    path = urlsplit(request.url).path
    try:
        if request.method == "OPTIONS":
            route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type, Idempotency-Key", "Access-Control-Allow-Methods": "GET,POST,OPTIONS"})
            return
        value = json.loads(request.post_data or "{}") if request.method == "POST" else None
        if request.method == "GET" and path in ("/api/state", "/api/export"):
            result, status = store.snapshot(), 200
        elif request.method == "GET" and path == "/api/config":
            result, status = store.settings(), 200
        elif request.method == "GET" and path == "/health":
            result, status = {"ok": True}, 200
        elif request.method == "POST" and path == "/api/intakes":
            result = store.intake(value); status = 201 if result["created"] else 200
        elif request.method == "POST" and path == "/api/config":
            result, status = store.configure(value), 200
        elif request.method == "POST" and path == "/api/process":
            result, status = store.process_one(ident=value.get("id")), 200
        elif request.method == "POST" and path == "/api/retry":
            result, status = store.retry(workflow.text(value.get("id"), "Delivery id", 160)), 200
        elif request.method == "POST" and path == "/api/tasks":
            result, status = store.complete_task(workflow.text(value.get("id"), "Task id", 120), value.get("done")), 200
        elif request.method == "POST" and path == "/api/receive":
            result, status = store.receive(request.headers.get("idempotency-key", ""), value), 200
        else:
            result, status = {"error": "Route not found."}, 404
    except workflow.Conflict as exc:
        result, status = {"error": str(exc)}, 409
    except (workflow.InputError, ValueError) as exc:
        result, status = {"error": str(exc)}, 400
    route.fulfill(status=status, content_type="application/json; charset=utf-8", headers={"Access-Control-Allow-Origin": "*"}, body=workflow.encoded(result))


def http_handler_smoke(workflow, root: Path):
    """Exercise the real landed Handler over loopback outside Chromium."""
    store = workflow.Store(root / "http-smoke.sqlite3")
    server = workflow.Server(("127.0.0.1", 0), store)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=3) as response:
            body = json.loads(response.read())
            return {"status": response.status, "body": body}
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def wait_ready(page):
    page.wait_for_function("document.querySelectorAll('#stats .stat').length === 4")


def snap(page, path: Path, scroll: int = 0):
    page.evaluate("y => window.scrollTo(0,y)", scroll)
    page.wait_for_timeout(250)
    page.screenshot(path=str(path), full_page=False)


def synthetic(ident: str, name: str, service: str = "Standard residential clean"):
    return {
        "id": ident,
        "payload": {
            "name": name,
            "email": f"{ident}@example.invalid",
            "phone": "555-0100",
            "address": "17 Sample Lane",
            "service": service,
            "preferred_date": "2026-09-15",
            "notes": "Synthetic training record — no customer data.",
        },
    }


def capture_episode(page, episode_id: str, work: Path):
    shots = work / "shots"
    shots.mkdir(parents=True, exist_ok=True)

    if episode_id == "01-intake-to-job":
        snap(page, shots / "0.png", 0)
        fields = {
            "id": "demo-episode-01",
            "name": "Maya Chen",
            "email": "demo-episode-01@example.invalid",
            "phone": "555-0101",
            "address": "17 Sample Lane",
            "service": "Move-out clean",
            "preferred_date": "2026-09-15",
            "notes": "Synthetic training record — no customer data.",
        }
        for name, value in fields.items():
            locator = page.locator(f"#intake [name='{name}']")
            locator.fill(value)
        snap(page, shots / "1.png", 280)
        page.locator("#intake button[type=submit]").click()
        page.wait_for_function("document.querySelector('#stats .stat b').textContent === '1'")
        snap(page, shots / "2.png", 0)
        snap(page, shots / "3.png", 310)

    elif episode_id == "02-tasks-to-completion":
        post_json(page, "/api/intakes", synthetic("demo-episode-02", "Jordan Reed", "Recurring clean"))
        page.evaluate("refresh()")
        wait_ready(page)
        snap(page, shots / "0.png", 290)
        boxes = page.locator("#jobs input[type=checkbox]")
        boxes.nth(0).click()
        page.wait_for_function("document.querySelector('#jobs .badge').textContent.includes('in progress')")
        snap(page, shots / "1.png", 290)
        boxes = page.locator("#jobs input[type=checkbox]")
        boxes.nth(1).click()
        snap(page, shots / "2.png", 290)
        boxes = page.locator("#jobs input[type=checkbox]")
        boxes.nth(2).click()
        page.wait_for_function("document.querySelector('#jobs .badge').textContent.includes('complete')")
        snap(page, shots / "3.png", 290)

    elif episode_id == "03-selected-delivery-retry":
        post_json(page, "/api/intakes", synthetic("demo-episode-03-a", "Avery Park", "Deep clean"))
        post_json(page, "/api/intakes", synthetic("demo-episode-03-b", "Riley Shah", "Move-out clean"))
        page.evaluate("refresh()")
        wait_ready(page)
        snap(page, shots / "0.png", 250)
        retries = page.get_by_role("button", name="Retry delivery")
        retries.nth(0).click()
        page.wait_for_function("document.querySelector('#message').textContent.includes('Selected delivery: delivered')")
        state = get_json(page, "/api/state")
        states = [row["state"] for row in state["outbox"]]
        if sorted(states) != ["delivered", "pending"]:
            raise AssertionError(f"selected retry did not isolate delivery: {states}")
        snap(page, shots / "1.png", 250)
        snap(page, shots / "2.png", 640)
        page.evaluate("window.scrollTo(0,0)")
        page.get_by_role("button", name="Deliver next notification").click()
        page.wait_for_function("document.querySelector('#message').textContent.includes('Delivery: delivered')")
        state = get_json(page, "/api/state")
        if [row["state"] for row in state["outbox"]].count("delivered") != 2:
            raise AssertionError("remaining event was not delivered")
        snap(page, shots / "3.png", 600)
    else:
        raise ValueError(episode_id)
    return [shots / f"{i}.png" for i in range(4)]


def encode_video(shots: list[Path], output: Path, fps: int, scene_seconds: int, encode: dict):
    frames = output.parent / (output.stem + "-frames")
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir()
    copies = fps * scene_seconds
    n = 0
    for shot in shots:
        for _ in range(copies):
            shutil.copyfile(shot, frames / f"{n:05d}.png")
            n += 1
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
        "-i", str(frames / "%05d.png"), "-vf", f"scale={encode['width']}:{encode['height']},fps={encode['fps']}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(encode["crf"]),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)
    ], check=True)
    shutil.rmtree(frames)


def fmt_time(seconds: int) -> str:
    return f"00:00:{seconds:02d}.000"


def write_vtt(path: Path, captions: list[str], scene_seconds: int):
    lines = ["WEBVTT", ""]
    for i, text in enumerate(captions):
        lines += [str(i + 1), f"{fmt_time(i*scene_seconds)} --> {fmt_time((i+1)*scene_seconds)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def thumbnail_svg(title: str) -> str:
    safe = (title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
<rect width="1280" height="720" fill="#173d35"/><rect x="70" y="70" width="1140" height="580" rx="28" fill="#f3f6f2"/>
<text x="120" y="190" font-family="system-ui,sans-serif" font-size="34" fill="#20644b">HIVE · SERVICE OPERATIONS</text>
<text x="120" y="330" font-family="system-ui,sans-serif" font-size="64" font-weight="700" fill="#18322c">{safe}</text>
<text x="120" y="520" font-family="system-ui,sans-serif" font-size="32" fill="#557065">Synthetic local demo · landed intake workflow</text>
</svg>\n'''


def ffprobe(path: Path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate:format=duration,size",
        "-of", "json", str(path)
    ], text=True)
    return json.loads(raw)


def validate_vtt(path: Path, duration: float):
    text = path.read_text(encoding="utf-8")
    ends = re.findall(r"-->\s*00:00:(\d\d)\.000", text)
    if not ends:
        raise AssertionError(f"no caption timings in {path}")
    if max(map(int, ends)) > duration + 0.05:
        raise AssertionError(f"caption extends past media in {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM_BIN") or shutil.which("chromium"))
    args = parser.parse_args()
    source_dir = args.repo_root / "revenue" / "hive" / "intake-crm-workflow"
    workflow_path, source_hashes = require_source(source_dir)
    if not args.chromium:
        raise SystemExit("Chromium not found; pass --chromium or CHROMIUM_BIN")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is required")

    specs = json.loads((Path(__file__).with_name("episode_specs.json")).read_text(encoding="utf-8"))
    out = args.out
    (out / "media").mkdir(parents=True, exist_ok=True)
    (out / "captions").mkdir(parents=True, exist_ok=True)
    (out / "thumbnails").mkdir(parents=True, exist_ok=True)
    workflow = load_source(workflow_path)

    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix="hive023-http-smoke-") as smoke:
        http_smoke = http_handler_smoke(workflow, Path(smoke))
    validation = {
        "source": source_hashes, "episodes": [], "http_handler_smoke": http_smoke,
        "capture_transport": "Chromium direct loopback navigation is administrator-blocked in this builder environment; capture loads exact landed index.html with a build-only <base> tag plus a deterministic crypto.randomUUID polyfill needed because about:blank is not a secure context, then routes the app's unchanged API fetches into the exact landed Store methods. The real landed HTTP Handler is exercised separately by http_handler_smoke."
    }
    index_bytes = (source_dir / "index.html").read_text(encoding="utf-8")
    capture_html = index_bytes.replace("<title>", '<base href="https://hive.invalid/">\n<title>', 1)
    capture_html = capture_html.replace("<script>\n'use strict';", "<script>if(!crypto.randomUUID){crypto.randomUUID=()=>\"00000000-0000-4000-8000-000000000001\"}</script>\n<script>\n'use strict';", 1)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.chromium, args=["--no-sandbox"])
        try:
            for episode in specs["episodes"]:
                with tempfile.TemporaryDirectory(prefix="hive023-") as temp:
                    temp_path = Path(temp)
                    store = workflow.Store(temp_path / "workspace.sqlite3")
                    context = browser.new_context(viewport={"width": specs["video"]["width"], "height": specs["video"]["height"]})
                    page = context.new_page()
                    page.route("https://hive.invalid/**", lambda route, request, store=store: route_store(route, request, store, workflow))
                    try:
                        page.set_content(capture_html, wait_until="load")
                        wait_ready(page)
                        shots = capture_episode(page, episode["id"], temp_path)
                    finally:
                        context.close()
                    video = out / "media" / f"{episode['id']}.mp4"
                    vtt = out / "captions" / f"{episode['id']}.vtt"
                    thumb = out / "thumbnails" / f"{episode['id']}.svg"
                    encode_video(shots, video, specs["video"]["fps"], specs["video"]["scene_seconds"], specs["encode"])
                    write_vtt(vtt, episode["captions"], specs["video"]["scene_seconds"])
                    thumb.write_text(thumbnail_svg(episode["title"]), encoding="utf-8")
                    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
                    info = ffprobe(video)
                    duration = float(info["format"]["duration"])
                    validate_vtt(vtt, duration)
                    validation["episodes"].append({
                        "id": episode["id"], "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                        "caption_sha256": hashlib.sha256(vtt.read_bytes()).hexdigest(),
                        "thumbnail_sha256": hashlib.sha256(thumb.read_bytes()).hexdigest(),
                        "ffprobe": info,
                    })
        finally:
            browser.close()
    validation["boundary"] = "synthetic local app execution only; no external posting, customer use, or provider action; no claim that Chromium navigated the production loopback HTTP route"
    (out / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
