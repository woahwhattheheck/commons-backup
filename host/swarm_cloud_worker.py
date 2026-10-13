#!/usr/bin/env python3
"""Print a shell profile with this cloud worker's writable build directories.

Source activate-swarm.sh first, then eval the returned exports. Source work and
claims still use the existing swarm-current and swarmctl operations.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import sys


def profile(args):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.peer):
        raise ValueError("Use a worker directory name of 1–80 letters, digits, dots, underscores or hyphens.")
    state = Path(os.environ.get("SWARM_STATE_ROOT", "/workspace/shared/swarm")).resolve()
    root = state / "cache" / "workers" / args.peer
    # Mutable build state is outside source worktrees. Profiles are shell
    # environment, not a second coordination store.
    values = {"COMMONS_PEER": args.peer, "SWARM_WORKER_ROOT": str(root)}
    for name, relative in (("GRADLE_USER_HOME", "gradle"), ("CARGO_HOME", "cargo"),
                           ("GOPATH", "go"), ("GOCACHE", "cache/go-build"),
                           ("GOMODCACHE", "cache/go-mod"), ("npm_config_cache", "cache/npm"),
                           ("UV_CACHE_DIR", "cache/uv"), ("TMPDIR", "tmp"),
                           ("ANDROID_USER_HOME", "android"), ("XDG_CACHE_HOME", "cache")):
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        values[name] = str(directory)
    prefixes = []
    if args.java:
        home = os.environ.get("JAVA" + args.java + "_HOME")
        if not home or not (Path(home) / "bin/javac").is_file():
            raise ValueError("JDK " + args.java + " is not installed; run the Android toolchain provisioner.")
        values["JAVA_HOME"] = home
        prefixes.append(str(Path(home) / "bin"))
    if args.node == "18":
        home = os.environ.get("SWARM_NODE18_ROOT")
        if not home or not (Path(home) / "bin/node").is_file():
            raise ValueError("Node 18 is not installed; run the language toolchain provisioner.")
        prefixes.append(str(Path(home) / "bin"))
    elif args.node == "24":
        home = os.environ.get("SWARM_NODE24_BIN")
        if not home or not (Path(home) / "node").is_file():
            raise ValueError("The activation script has no installed Node 24 path.")
        prefixes.append(home)
    # Cargo executables may be shared; target output and mutable cache are owned
    # by this worker. RUSTUP_HOME continues selecting the shared compiler bytes.
    values["CARGO_TARGET_DIR"] = str(root / "cargo-target")
    if os.environ.get("SWARM_CARGO_HOME"):
        prefixes.append(str(Path(os.environ["SWARM_CARGO_HOME"]) / "bin"))
    if os.environ.get("GOROOT"):
        prefixes.append(str(Path(os.environ["GOROOT"]) / "bin"))
    for name, value in values.items():
        print("export " + name + "=" + shlex.quote(value))
    if prefixes:
        print("export PATH=" + shlex.quote(":".join(prefixes)) + ':"$PATH"')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("peer")
    parser.add_argument("--java", choices=("17", "21"))
    parser.add_argument("--node", choices=("18", "24"))
    args = parser.parse_args()
    try:
        profile(args)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
