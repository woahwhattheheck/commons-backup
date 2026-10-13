"""No-inference validation of the actual packaged ARC runtime on cloud Linux."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

BANNED = re.compile(r"llama[._-]cpp|node-llama-cpp", re.I)


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.archive) as bundle:
        for info in bundle.infolist():
            destination = (root / info.filename).resolve()
            if not destination.is_relative_to(root):
                raise ValueError("Archive path escapes workspace")
        bundle.extractall(root)
    manifest = json.loads((root / "BUILD-MANIFEST.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Archive readback mismatch: " + name)
    report = root.parent / "dependency-plan.json"
    lock = root.parent / "requirements.resolved.txt"
    run(sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed",
        "--no-cache-dir", "--only-binary=:all:", "--report", str(report),
        "-r", str(root / "requirements.txt"))
    planned = json.loads(report.read_text())
    dependencies = [(item["metadata"]["name"], item["metadata"]["version"]) for item in planned["install"]]
    if any(BANNED.search(name.replace("_", "-")) for name, _ in dependencies):
        raise ValueError("Prohibited transitive dependency; install not performed")
    lock.write_text("".join(f"{name}=={version}\n" for name, version in sorted(dependencies)))
    run(sys.executable, "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:", "-r", str(lock))
    run(sys.executable, str(root / "main.py"), "--help", cwd=root)
    run(sys.executable, str(root / "main.py"), "/requirements", "--help", cwd=root)
    run(sys.executable, str(root / "main.py"), "--version", cwd=root)
    # Parse the exact platform invocation against real upstream argparse.
    code = (
        "import arc_cli; "
        "p=arc_cli.build_parser(); "
        "a=p.parse_args(['compile','/requirements','--output-dir','/workspace','--type','web']); "
        "assert a.requirement_path=='/requirements' and a.output_dir=='/workspace' and a.app_type=='web'; "
        "from arcbench_agent_runtime import AgentRuntime; "
        "print('actual upstream entrypoint and runtime SDK import passed')"
    )
    run(sys.executable, "-c", code, cwd=root)
    result = {"schema": "commons-gosim-preparation-validation-v1",
              "archive_sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
              "arc_revision": manifest["arc_revision"],
              "template_revision": manifest["template_revision"],
              "dependency_count": len(dependencies),
              "package_hash_readback": "passed", "real_cli_startup": "passed",
              "fixed_platform_cli_parse": "passed", "runtime_sdk_import": "passed",
              "model_calls": 0, "contest_tasks_run": 0,
              "platform_upload": "not_performed", "contest_score": None}
    (root.parent / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
