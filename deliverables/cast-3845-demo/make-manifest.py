#!/usr/bin/env python3
"""Build an evidence manifest for a PR #3845 real-receiver proof video.

Usage:
    python3 make-manifest.py --spec capture-spec.json --video capture.mp4 --out manifest.json

The spec JSON carries the human-entered fields (build_order, pr, apk, receiver,
capture metadata without video, steps, privacy, handoff). The tool hashes the
video, merges computed fields, validates required fields/patterns per
manifest-schema.json (stdlib-only), and writes the manifest.

Anti-fabrication: the tool NEVER invents a video. If --stub is passed, status is
forced to STUB-NO-HARDWARE. A spec claiming CAPTURED with --stub is rejected.

Self-test: python3 make-manifest.py --self-test  (uses only tmp synthetic data)
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
ORDER = re.compile(r"^CAST-3845-REAL-RECEIVER-VIDEO-[0-9]{8}-[0-9]{2}$")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(2)


def validate(m):
    errs = []

    def need(path, cond, why):
        if not cond:
            errs.append(f"{path}: {why}")

    need("build_order", ORDER.match(str(m.get("build_order", ""))), "must match ^CAST-3845-REAL-RECEIVER-VIDEO-YYYYMMDD-NN$")
    need("status", m.get("status") in ("CAPTURED", "STUB-NO-HARDWARE"), "must be CAPTURED or STUB-NO-HARDWARE")

    pr = m.get("pr", {})
    need("pr.number", pr.get("number") == 3845, "must be 3845")
    need("pr.repo", pr.get("repo") == "microg/GmsCore", "must be microg/GmsCore")
    need("pr.url", isinstance(pr.get("url"), str) and pr["url"].startswith("http"), "must be a URL")
    need("pr.head_sha", HEX40.match(str(pr.get("head_sha", ""))), "must be 40 hex chars")
    mc = pr.get("maintainer_comment", {})
    need("pr.maintainer_comment.id", isinstance(mc.get("id"), int), "must be an int")
    need("pr.maintainer_comment.url", isinstance(mc.get("url"), str) and mc["url"].startswith("http"), "must be a URL")
    need("pr.maintainer_comment.requirement_quote", isinstance(mc.get("requirement_quote"), str) and mc["requirement_quote"].strip(), "must be non-empty")

    apk = m.get("apk", {})
    need("apk.source", apk.get("source") in ("ci-artifact", "local-build"), "must be ci-artifact or local-build")
    need("apk.package_name", isinstance(apk.get("package_name"), str) and apk["package_name"].strip(), "must be non-empty")
    need("apk.sha256", HEX64.match(str(apk.get("sha256", ""))), "must be 64 hex chars")

    rc = m.get("receiver", {})
    need("receiver.kind", rc.get("kind") in ("physical", "cloud"), "must be physical or cloud")
    for k in ("model", "runtime", "firmware"):
        need("receiver." + k, isinstance(rc.get(k), str) and rc[k].strip(), "must be non-empty")
    need("receiver.simulated", rc.get("simulated", False) is False, "simulated receivers are never acceptable evidence")

    cap = m.get("capture", {})
    for k in ("started_at", "ended_at", "timezone"):
        need("capture." + k, isinstance(cap.get(k), str) and cap[k].strip(), "must be non-empty")
    vid = cap.get("video", {})
    need("capture.video.sha256", HEX64.match(str(vid.get("sha256", ""))), "must be 64 hex chars")
    need("capture.video.bytes", isinstance(vid.get("bytes"), int) and vid["bytes"] > 0, "must be positive int")
    need("capture.video.container", isinstance(vid.get("container"), str) and vid["container"].strip(), "must be non-empty")

    steps = m.get("steps", [])
    need("steps", isinstance(steps, list) and len(steps) >= 1, "must be a non-empty list")
    for i, s in enumerate(steps):
        for k in ("seq", "name", "expected", "observed", "status"):
            need(f"steps[{i}].{k}", s.get(k) not in (None, ""), "required")
        need(f"steps[{i}].status", s.get("status") in ("pass", "fail", "skipped"), "must be pass/fail/skipped")

    priv = m.get("privacy", {})
    need("privacy.faces_visible", priv.get("faces_visible") is False, "must be false")
    need("privacy.credentials_visible", priv.get("credentials_visible") is False, "must be false")

    return errs


def build(spec_path, video_path, out_path, stub):
    with open(spec_path) as f:
        spec = json.load(f)
    if not os.path.isfile(video_path):
        fail("video file not found: " + video_path)

    if stub and str(spec.get("status")) == "CAPTURED":
        fail("--stub cannot produce a CAPTURED manifest")

    vhash = sha256_file(video_path)
    vbytes = os.path.getsize(video_path)
    container = os.path.splitext(video_path)[1].lstrip(".").lower() or "unknown"

    m = dict(spec)
    m["status"] = "STUB-NO-HARDWARE" if stub else spec.get("status", "CAPTURED")
    cap = dict(spec.get("capture", {}))
    cap["video"] = {
        "sha256": vhash,
        "bytes": vbytes,
        "container": container,
        "duration_s": spec.get("capture", {}).get("video", {}).get("duration_s", 0),
    }
    m["capture"] = cap

    errs = validate(m)
    if errs:
        for e in errs:
            print("VALIDATION: " + e, file=sys.stderr)
        sys.exit(3)

    with open(out_path, "w") as f:
        json.dump(m, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes) status={m['status']} video_sha256={vhash}")


def self_test():
    """Exercise builder + validator on synthetic tmp data only. No real capture implied."""
    print("self-test: building synthetic STUB-NO-HARDWARE manifest in tmpdir")
    with tempfile.TemporaryDirectory() as td:
        video = os.path.join(td, "selftest-video.mp4")
        with open(video, "wb") as f:
            f.write(b"\x00" * 1024)  # synthetic bytes; NOT a real capture
        spec = {
            "build_order": "CAST-3845-REAL-RECEIVER-VIDEO-20261002-01",
            "pr": {
                "number": 3845,
                "repo": "microg/GmsCore",
                "url": "https://github.com/microg/GmsCore/pull/3845",
                "head_sha": "4b21ddf1e3201e049007de4b128ec9e19ad90897",
                "maintainer_comment": {
                    "id": 5947015322,
                    "url": "https://github.com/microg/GmsCore/pull/3845#issuecomment-5947015322",
                    "requirement_quote": "I'm not reviewing any PR unless there is a proof video that this is working.",
                },
            },
            "apk": {"source": "ci-artifact", "package_name": "com.google.android.gms", "sha256": "00" * 32},
            "receiver": {"kind": "physical", "model": "SELFTEST", "runtime": "SELFTEST", "firmware": "SELFTEST"},
            "capture": {"started_at": "2026-10-02T13:00:00+00:00", "ended_at": "2026-10-02T13:05:00+00:00", "timezone": "UTC"},
            "steps": [{"seq": 1, "name": "selftest", "expected": "e", "observed": "o", "status": "pass"}],
            "privacy": {"faces_visible": False, "credentials_visible": False},
        }
        spec_path = os.path.join(td, "spec.json")
        out_path = os.path.join(td, "manifest.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f)

        # 1. stub forced even when spec says CAPTURED-with-stub is rejected
        bad = dict(spec, status="CAPTURED")
        bad_path = os.path.join(td, "bad.json")
        with open(bad_path, "w") as f:
            json.dump(bad, f)
        rc = os.system(f"python3 {os.path.abspath(__file__)} --spec {bad_path} --video {video} --out {td}/x.json --stub >/dev/null 2>&1")
        assert rc != 0, "stub+CAPTURED must be rejected"

        # 2. normal stub build succeeds and validates
        build(spec_path, video, out_path, stub=True)
        with open(out_path) as f:
            m = json.load(f)
        assert m["status"] == "STUB-NO-HARDWARE"
        assert m["capture"]["video"]["sha256"] == sha256_file(video)
        assert m["capture"]["video"]["bytes"] == 1024

        # 3. corrupt spec rejected (missing head_sha)
        broken = json.loads(json.dumps(spec))
        del broken["pr"]["head_sha"]
        broken_path = os.path.join(td, "broken.json")
        with open(broken_path, "w") as f:
            json.dump(broken, f)
        rc = os.system(f"python3 {os.path.abspath(__file__)} --spec {broken_path} --video {video} --out {td}/y.json --stub >/dev/null 2>&1")
        assert rc != 0, "missing head_sha must be rejected"

        # 4. simulated receiver rejected
        sim = json.loads(json.dumps(spec))
        sim["receiver"]["simulated"] = True
        sim_path = os.path.join(td, "sim.json")
        with open(sim_path, "w") as f:
            json.dump(sim, f)
        rc = os.system(f"python3 {os.path.abspath(__file__)} --spec {sim_path} --video {video} --out {td}/z.json --stub >/dev/null 2>&1")
        assert rc != 0, "simulated receiver must be rejected"

    print("self-test: PASS (4/4)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--video")
    ap.add_argument("--out")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not (a.spec and a.video and a.out):
        ap.error("--spec, --video and --out are required (or --self-test)")
    build(a.spec, a.video, a.out, a.stub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
