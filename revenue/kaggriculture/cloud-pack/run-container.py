"""Run the package regression in an existing local Docker image; never pull one."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Already available image with Python 3.11 or newer")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--spec", required=True, help="Path relative to --repo")
    parser.add_argument("--opponent", required=True, help="Standalone Python path relative to --repo, optionally ::function")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=6100003)
    parser.add_argument("--python", default="python")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    engine = args.engine_dir.resolve(strict=True)
    bundle = args.bundle.resolve(strict=True)
    output = args.output.resolve()
    source, sep, function = args.opponent.partition("::")
    spec = (repo / args.spec).resolve(strict=True).relative_to(repo)
    opponent = (repo / source).resolve(strict=True).relative_to(repo)
    rival = "/repo/" + str(opponent) + ("::" + function if sep else "")
    # Docker --mount's comma syntax cannot represent a comma in a host path.
    if any("," in str(path) for path in (repo, engine, bundle, output)):
        raise ValueError("Use cloud paths without commas for Docker bind mounts")
    if output.exists():
        raise FileExistsError(f"Use a new result directory: {output}")
    command = ["docker", "run", "--pull=never", "--rm", "--init", "--network=none",
        "--cpus=1.6", "--memory=6656m", "--memory-swap=6656m", "--pids-limit=256",
        "--read-only", "--tmpfs", "/tmp:rw,size=1073741824,mode=1777",
        "--user", f"{os.getuid()}:{os.getgid()}", "--workdir", "/repo",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--mount", f"type=bind,src={repo},dst=/repo,readonly",
        "--mount", f"type=bind,src={engine},dst=/engine,readonly",
        "--mount", f"type=bind,src={bundle},dst=/bundle,readonly",
        "--mount", f"type=bind,src={output},dst=/results",
        "--entrypoint", args.python, args.image,
        "-B", "/repo/revenue/kaggriculture/cloud-pack/pack.py", "check",
        "--bundle", "/bundle", "--spec", "/repo/" + str(spec),
        "--engine-dir", "/engine", "--opponent", rival,
        "--output", "/results/run", "--seed", str(args.seed)]
    invocation = {"command": command, "requested_cpu_quota": 1.6,
        "requested_memory_bytes": 6656 * 1024**2, "network": "none",
        "tmpfs_bytes": 1024**3, "hosted_runtime": False,
        "disk_note": "The report bind mount has its host filesystem capacity; an official 8-GiB disk quota is not emulated.",
        "scope": "CPU/RAM quotas cover this entire regression container, including both players and the interpreter."}
    if args.dry_run:
        print(json.dumps(invocation, indent=2))
        return 0
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is unavailable in this runner; use the existing Claude Linux VM")
    image = subprocess.run(["docker", "image", "inspect", args.image, "--format",
        '{"id":{{json .Id}},"repo_digests":{{json .RepoDigests}}}'],
        check=True, text=True, capture_output=True)
    invocation["image"] = json.loads(image.stdout)
    # Run precisely the inspected image, even if a mutable tag changes meanwhile.
    command[command.index("--entrypoint") + 2] = invocation["image"]["id"]
    output.mkdir(parents=True)
    (output / "container.json").write_text(json.dumps(invocation, indent=2) + "\n")
    with (output / "container.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    invocation["exit_code"] = result.returncode
    (output / "container.json").write_text(json.dumps(invocation, indent=2) + "\n")
    print(json.dumps({"exit_code": result.returncode, "results": str(output)}, indent=2))
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
