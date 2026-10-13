#!/usr/bin/env python3
"""Install and inspect pinned, reusable Android/JDK bytes in cloud storage.

Downloads use this process's HTTPS proxy and CA configuration. Package archives
are checked against official publisher metadata before extraction; existing
installs are preserved. Writable Gradle homes belong to individual workers.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile


PACKAGES = (
    {"name": "jdk17", "path": "jdk-17.0.20.1+1", "version": "17.0.20.1+1",
     "url": "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_linux_hotspot_17.0.20.1_1.tar.gz",
     "size": 193252603, "algorithm": "sha256", "digest": "3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e",
     "required": "bin/javac"},
    {"name": "jdk21", "path": "jdk-21.0.12.1+1", "version": "21.0.12.1+1",
     "url": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz",
     "size": 207473347, "algorithm": "sha256", "digest": "ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94",
     "required": "bin/javac"},
    {"name": "platform35", "path": "android-sdk/platforms/android-35", "version": "35-r2",
     "url": "https://dl.google.com/android/repository/platform-35_r02.zip",
     "size": 64273788, "algorithm": "sha1", "digest": "0bb560a90a7a2cbd0dd8348224d518b638fe7949",
     "required": "android.jar"},
    {"name": "platform34", "path": "android-sdk/platforms/android-34", "version": "34-r3",
     "url": "https://dl.google.com/android/repository/platform-34-ext7_r03.zip",
     "size": 63180081, "algorithm": "sha1", "digest": "1f2e9478d6a7601425ceaa553311dc43191f103d",
     "required": "android.jar"},
    {"name": "buildtools35", "path": "android-sdk/build-tools/35.0.0", "version": "35.0.0",
     "url": "https://dl.google.com/android/repository/build-tools_r35_linux.zip",
     "size": 61958799, "algorithm": "sha1", "digest": "2cfaa0bbb2336e9ec18ed3ecea84fa2e2af607bc",
     "required": "aapt2"},
    {"name": "buildtools34", "path": "android-sdk/build-tools/34.0.0", "version": "34.0.0",
     "url": "https://dl.google.com/android/repository/build-tools_r34-linux.zip",
     "size": 61224257, "algorithm": "sha1", "digest": "d6d58e0c6925a9e4d9a541e84cd1f405c2f9d2a9",
     "required": "aapt2"},
    {"name": "cmdline", "path": "android-sdk/cmdline-tools/23.0", "version": "23.0-build16111833",
     "url": "https://dl.google.com/android/repository/commandlinetools-linux-16111833_latest.zip",
     "size": 181052239, "algorithm": "sha1", "digest": "e025545c62a8e64c7559119566a569fb1dec5f60",
     "required": "bin/sdkmanager"},
    {"name": "platformtools", "path": "android-sdk/platform-tools", "version": "37.0.1",
     "url": "https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip",
     "size": 9054187, "algorithm": "sha1", "digest": "477254aa5f903c15cf51001717bdf347fb6b53e0",
     "required": "adb"},
    {"name": "gradle813", "path": "gradle-8.13", "version": "8.13",
     "url": "https://downloads.gradle.org/distributions/gradle-8.13-bin.zip",
     "size": 136983045, "algorithm": "sha256", "digest": "20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78",
     "required": "bin/gradle"},
    {"name": "gradle89", "path": "gradle-8.9", "version": "8.9",
     "url": "https://downloads.gradle.org/distributions/gradle-8.9-bin.zip",
     "size": 136114148, "algorithm": "sha256", "digest": "d725d707bfabd4dfdc958c624003b3c80accc03f7037b5122c4b1d0ef15cecab",
     "required": "bin/gradle"},
)


def hash_file(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.replace(path)


def download(root: Path, package: dict) -> Path:
    directory = root / "downloads"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / package["url"].rsplit("/", 1)[1]
    if archive.exists():
        if (archive.stat().st_size != package["size"] or
                hash_file(archive, package["algorithm"]) != package["digest"]):
            raise ValueError(f"Retained archive does not match publisher pin: {archive}")
        return archive
    partial = directory / (archive.name + ".partial")
    # A partial download is retained for diagnosis, never used as an install.
    # Use a fresh filename after an interrupted earlier attempt.
    if partial.exists():
        import uuid
        partial = directory / (archive.name + ".partial." + uuid.uuid4().hex)
    digest = hashlib.new(package["algorithm"])
    size = 0
    request = urllib.request.Request(package["url"], headers={"User-Agent": "commons-cloud-toolchains"})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("xb") as stream:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            stream.write(chunk)
            digest.update(chunk)
            size += len(chunk)
            if size > package["size"]:
                raise ValueError(f"Download exceeds publisher size: {package['name']}")
        stream.flush()
        os.fsync(stream.fileno())
    if size != package["size"] or digest.hexdigest() != package["digest"]:
        raise ValueError(f"Download fails publisher size/digest: {package['name']}")
    partial.rename(archive)
    return archive


def extract(archive: Path, stage: Path) -> Path:
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as stream:
            stream.extractall(stage, filter="data")
    else:
        with zipfile.ZipFile(archive) as stream:
            for member in stream.infolist():
                name = PurePosixPath(member.filename)
                mode = member.external_attr >> 16
                if name.is_absolute() or ".." in name.parts or (mode & 0o170000) == 0o120000:
                    raise ValueError("Unsafe package archive member")
                target = stage.joinpath(*name.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with stream.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod((mode & 0o777) or 0o644)
    roots = list(stage.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError("Package archive must contain one root directory")
    return roots[0]


def install_package(root: Path, package: dict) -> dict:
    target = root / package["path"]
    receipt = target / ".commons-toolchain.json"
    if target.exists() or target.is_symlink():
        required = target / package["required"]
        if not required.is_file() or not required.stat().st_size or not receipt.is_file():
            raise ValueError(f"Preserved existing install lacks matching provenance: {target}")
        old = json.loads(receipt.read_text())
        if old.get("package") != package:
            raise ValueError(f"Preserved existing install has different publisher pin: {target}")
        return {**old, "reused": True}
    archive = download(root, package)
    stage = Path(tempfile.mkdtemp(prefix=package["name"] + ".", dir=root / "staging"))
    extracted = extract(archive, stage)
    if not (extracted / package["required"]).is_file():
        raise ValueError(f"Package missing required runtime file: {package['name']}")
    if package["name"].startswith("jdk"):
        run = subprocess.run([str(extracted / "bin/javac"), "-version"], capture_output=True,
                             text=True, timeout=15)
        if run.returncode or package["version"].split("+")[0] not in run.stdout + run.stderr:
            raise ValueError(f"Extracted compiler version mismatch: {package['name']}")
    result = {"package": package, "root": str(target), "archive_sha256": hash_file(archive, "sha256")}
    write_json(extracted / ".commons-toolchain.json", result)
    target.parent.mkdir(parents=True, exist_ok=True)
    extracted.rename(target)
    stage.rmdir()
    return {**result, "reused": False}


def activate(root: Path) -> None:
    by_name = {p["name"]: p for p in PACKAGES}
    values = {"JAVA17_HOME": str(root / by_name["jdk17"]["path"]),
              "JAVA21_HOME": str(root / by_name["jdk21"]["path"]),
              "ANDROID_HOME": str(root / "android-sdk"),
              "ANDROID_SDK_ROOT": str(root / "android-sdk"),
              "GRADLE813_HOME": str(root / by_name["gradle813"]["path"]),
              "GRADLE89_HOME": str(root / by_name["gradle89"]["path"])}
    lines = ["# Shared immutable runtime bytes; worker Gradle caches stay separate."]
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in values.items())
    lines.extend([
        'export JAVA_HOME="$JAVA21_HOME"',
        'export PATH="$JAVA_HOME/bin:$GRADLE813_HOME/bin:$ANDROID_HOME/cmdline-tools/23.0/bin:$ANDROID_HOME/platform-tools:$PATH"',
        'if [ -r /etc/ssl/certs/java/cacerts ]; then',
        '  case " ${JAVA_TOOL_OPTIONS-} " in',
        '    *-Djavax.net.ssl.trustStore=*) ;;',
        '    *) export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+$JAVA_TOOL_OPTIONS }-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts" ;;',
        '  esac',
        'fi',
        '',
    ])
    activation = root / "android.sh"
    content = "\n".join(lines)
    if activation.exists() and activation.read_text() == content:
        return
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    temporary.chmod(0o600)
    temporary.replace(activation)


def inspect(root: Path) -> dict:
    packages = []
    for package in PACKAGES:
        target = root / package["path"]
        required = target / package["required"]
        present = required.is_file() and required.stat().st_size > 0
        receipt = target / ".commons-toolchain.json"
        provenance = receipt.is_file() and json.loads(receipt.read_text()).get("package") == package
        row = {"name": package["name"], "version": package["version"], "root": str(target),
               "present": present, "provenance_matches": provenance}
        if present and package["name"].startswith("jdk"):
            run = subprocess.run([str(target / "bin/javac"), "-version"], capture_output=True,
                                 text=True, timeout=15)
            compiler = (run.stdout + run.stderr).strip()
            row.update(exit_code=run.returncode, compiler=compiler,
                       version_matches=package["version"].split("+")[0] in compiler)
        packages.append(row)
    return {"schema": "commons.cloud_toolchains/v1", "root": str(root), "packages": packages,
            "ready": all(p["present"] and p["provenance_matches"] and
                         p.get("exit_code", 0) == 0 and p.get("version_matches", True) for p in packages)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "install"))
    parser.add_argument("--root", type=Path, default=Path("/workspace/shared/swarm/toolchains"))
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "install":
            if sys.platform != "linux" or os.uname().machine != "x86_64":
                raise ValueError("These publisher pins are Linux x86_64 binaries")
            root.mkdir(parents=True, exist_ok=True)
            (root / "staging").mkdir(exist_ok=True)
            with (root / ".android-install.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                packages = []
                for package in PACKAGES:
                    result = install_package(root, package)
                    packages.append(result)
                    print(json.dumps({"installed": package["name"], "version": package["version"],
                                      "reused": result["reused"]}), flush=True)
                activate(root)
                write_json(root / "android-provenance.json", {"packages": packages})
        result = inspect(root)
        print(json.dumps(result, indent=2))
        return 0 if result["ready"] else 1
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, subprocess.TimeoutExpired) as error:
        print(f"Android toolchain {args.command} failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
