#!/usr/bin/env python3
"""Readback verifier for a cast-3845 evidence manifest.

Usage:
    python3 verify-manifest.py manifest.json --video capture.mp4

Recomputes the video SHA-256 and byte size, revalidates required fields
against manifest-schema.json rules, and prints PASS/FAIL per check.
Exit 0 only if every check passes. A CAPTURED manifest with a STUB video
(or any hash mismatch) fails.

Self-test: python3 verify-manifest.py --self-test
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "make_manifest", os.path.join(THIS_DIR, "make-manifest.py")
)
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)


def verify(manifest_path, video_path):
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))

    try:
        with open(manifest_path) as f:
            m = json.load(f)
    except Exception as e:
        check("manifest parses as JSON", False, str(e))
        return checks
    check("manifest parses as JSON", True)

    errs = mm.validate(m)
    check("schema-field validation", not errs, "; ".join(errs) if errs else f"{len(m)} top-level keys")

    vid = (m.get("capture") or {}).get("video", {})
    check("video block present", bool(vid.get("sha256") and vid.get("bytes")))

    if video_path:
        if not os.path.isfile(video_path):
            check("video file exists", False, video_path)
        else:
            check("video file exists", True, video_path)
            h = mm.sha256_file(video_path)
            check("video sha256 matches manifest", h == vid.get("sha256"), h[:16] + "...")
            b = os.path.getsize(video_path)
            check("video byte size matches manifest", b == vid.get("bytes"), str(b))

    status = m.get("status")
    check("status is explicit", status in ("CAPTURED", "STUB-NO-HARDWARE"), str(status))
    if status == "CAPTURED":
        recv = m.get("receiver", {})
        check("receiver not simulated (CAPTURED)", recv.get("simulated", False) is False)
        steps = m.get("steps", [])
        fails = [s for s in steps if s.get("status") == "fail"]
        check("no failed capture steps", not fails, f"{len(fails)} failed" if fails else f"{len(steps)} steps")

    return checks


def run_self_test():
    print("verify self-test: building stub manifest then verifying it")
    with tempfile.TemporaryDirectory() as td:
        video = os.path.join(td, "v.mp4")
        with open(video, "wb") as f:
            f.write(b"\x11" * 2048)
        specj = {
            "build_order": "CAST-3845-REAL-RECEIVER-VIDEO-20261002-01",
            "pr": {
                "number": 3845, "repo": "microg/GmsCore",
                "url": "https://github.com/microg/GmsCore/pull/3845",
                "head_sha": "4b21ddf1e3201e049007de4b128ec9e19ad90897",
                "maintainer_comment": {
                    "id": 5947015322,
                    "url": "https://github.com/microg/GmsCore/pull/3845#issuecomment-5947015322",
                    "requirement_quote": "proof video required",
                },
            },
            "apk": {"source": "local-build", "package_name": "org.microg.gms", "sha256": "ab" * 32},
            "receiver": {"kind": "physical", "model": "SELFTEST", "runtime": "SELFTEST", "firmware": "SELFTEST"},
            "capture": {"started_at": "2026-10-02T13:00:00+00:00", "ended_at": "2026-10-02T13:02:00+00:00", "timezone": "UTC"},
            "steps": [{"seq": 1, "name": "s", "expected": "e", "observed": "o", "status": "skipped"}],
            "privacy": {"faces_visible": False, "credentials_visible": False},
        }
        sp = os.path.join(td, "spec.json")
        mp = os.path.join(td, "manifest.json")
        with open(sp, "w") as f:
            json.dump(specj, f)
        mm.build(sp, video, mp, stub=True)

        # good verify must pass
        checks = verify(mp, video)
        bad = [c for c in checks if not c[1]]
        assert not bad, f"expected all PASS, got failures: {bad}"

        # tampered video must fail
        with open(video, "ab") as f:
            f.write(b"\x22")
        checks2 = verify(mp, video)
        assert any((not ok) for (_, ok, _) in checks2), "tampered video must fail verification"

    print("verify self-test: PASS (good manifest passes; tampered video fails)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", nargs="?")
    ap.add_argument("--video")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return run_self_test()
    if not a.manifest:
        ap.error("manifest path required (or --self-test)")
    checks = verify(a.manifest, a.video)
    allok = True
    for name, ok, detail in checks:
        print(("PASS " if ok else "FAIL ") + name + (f" [{detail}]" if detail else ""))
        allok = allok and ok
    print("RESULT: " + ("ALL PASS" if allok else "FAILURES PRESENT"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
