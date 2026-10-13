"""Build the V3 candidate package from the canonical export plus this directory.

    python build_v3.py            write dist/titan-v3.tar.gz, dist/titan-v3.sha256, FILES.json
                                  and refresh the archive fields in V3-MANIFEST.json
    python build_v3.py --check    rebuild in memory and verify the manifest still matches
    python build_v3.py --tree D   materialise the full package into directory D (a shard
                                  runs --candidate D/main.py directly)
    --canonical PATH              use another canonical archive (must match base.sha256)

Recipe: extract ../../exports/titan-current.tar.gz (SHA-256 pinned in V3-MANIFEST.json
under base.sha256), copy overlay/ over it (the lane modules and the check), then run
apply_v3.apply() which edits titan_runtime.py, scheduler.py, frozen_selected.py,
TITAN-CONFIG.json and TITAN-RELEASE.md with exact-anchor replacements.  Fixed tar
metadata makes the archive a pure function of (canonical, overlay, apply_v3).  dist/
is a build product and is not committed; a shard verifies each materialised file
against FILES.json.
"""
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import apply_v3  # noqa: E402

OVERLAY = HERE / "overlay"
DIST = HERE / "dist"
MANIFEST = HERE / "V3-MANIFEST.json"
CANON = HERE.parent.parent / "exports" / "titan-current.tar.gz"


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def overlay_files():
    return {p.relative_to(OVERLAY).as_posix(): p.read_bytes()
            for p in sorted(OVERLAY.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def package_files(canon_path=None):
    m = manifest()
    archive = Path(canon_path or CANON)
    data = archive.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == m["base"]["sha256"], "canonical archive %s is %s, manifest pins %s" % (archive, digest, m["base"]["sha256"])
    work = Path(tempfile.mkdtemp(prefix="titan-v3-"))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name[2:] if member.name.startswith("./") else member.name
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
        for name, blob in overlay_files().items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
        apply_v3.apply(str(work))
        files = {}
        for path in sorted(p for p in work.rglob("*") if p.is_file()):
            files[path.relative_to(work).as_posix()] = path.read_bytes()
        return files
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build_bytes(files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name in sorted(files):
            blob = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(blob))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def file_shas(files):
    return {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(files)}


def source_shas():
    shas = file_shas(overlay_files())
    shas["apply_v3.py"] = hashlib.sha256((HERE / "apply_v3.py").read_bytes()).hexdigest()
    return shas


def main(argv):
    canon = Path(argv[argv.index("--canonical") + 1]) if "--canonical" in argv else None
    files = package_files(canon)
    blob = build_bytes(files)
    digest = hashlib.sha256(blob).hexdigest()
    shas = file_shas(files)
    if "--tree" in argv:
        target = Path(argv[argv.index("--tree") + 1])
        for name, data in files.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print("V3 TREE", target, len(files), "files", digest)
        return
    m = manifest()
    if "--check" in argv:
        assert m["archive"]["sha256"] == digest, "V3-MANIFEST.json archive.sha256 %s != rebuilt %s" % (m["archive"]["sha256"], digest)
        assert m["archive"]["files"] == len(files), "V3-MANIFEST.json archive.files drifted"
        assert m["overlay"] == source_shas(), "V3-MANIFEST.json overlay hashes drifted"
        recorded = json.loads((HERE / "FILES.json").read_text(encoding="utf-8"))
        assert recorded == shas, "FILES.json drifted"
        print("V3 CHECK OK", digest, len(files), "files", len(blob), "bytes")
        return
    DIST.mkdir(exist_ok=True)
    (DIST / "titan-v3.tar.gz").write_bytes(blob)
    (DIST / "titan-v3.sha256").write_text("%s  titan-v3.tar.gz\n" % digest)
    (HERE / "FILES.json").write_text(json.dumps(shas, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    m["archive"] = {"path": "dist/titan-v3.tar.gz (build product, not committed)", "sha256": digest,
                    "bytes": len(blob), "files": len(files)}
    m["overlay"] = source_shas()
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    print("V3 BUILD", digest, len(files), "files", len(blob), "bytes")


if __name__ == "__main__":
    main(sys.argv[1:])
