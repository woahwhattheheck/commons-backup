#!/usr/bin/env python3
"""Run the existing Commons and Deathstar services in one cloud workspace.

State lives outside either checkout. This launcher uses the inherited provider
sessions and proxy settings; it never copies credentials or starts model jobs.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

COMMONS = Path(__file__).resolve().parents[1]
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RUNTIME_IMAGE = "commons-swarm-host-runtime:1"
RUNTIME_LABEL = "commons.swarm.cloud.runtime"


def commons_root(args):
    return (args.commons or COMMONS).resolve()


def launcher_python():
    # python and python3 can name the same installed interpreter. Keep wrappers
    # stable across those normal invocation aliases.
    stable = Path(sys.executable).with_name("python")
    return str(stable) if stable.exists() and stable.samefile(sys.executable) else sys.executable


def read_json(url):
    with LOCAL_HTTP.open(url, timeout=35) as response:
        return json.load(response)


def locations(args):
    workspace = args.workspace.resolve()
    state = (args.state or workspace / "shared/swarm").resolve()
    deathstar = (args.deathstar or workspace / "deathstar").resolve()
    return workspace, state, deathstar


def service_specs(args):
    workspace, state, deathstar = locations(args)
    commons = commons_root(args)
    python = launcher_python()
    return [
        {"name": "equipment", "cwd": commons, "url": "http://127.0.0.1:8878",
         "command": [python, "-B", "-m", "integrations.gemini_slack.peer_tool_gateway",
                     "--port", "8878", "--event-log", str(state / "equipment/events.jsonl"),
                     "--call-db", str(state / "equipment/calls.sqlite3"),
                     "--equipment-config", str(state / "equipment/equipment.json")]},
        {"name": "command-center", "cwd": commons, "url": "http://127.0.0.1:8890",
         "command": [python, "-B", "-m", "integrations.command_center.server",
                     "--port", "8890", "--gateway", "http://127.0.0.1:8878",
                     "--state-dir", str(state / "command-center")]},
        {"name": "deathstar", "cwd": deathstar, "url": "http://127.0.0.1:18540",
         "command": [python, "-B", "-m", "deathstar", "serve", "--data",
                     str(state / "deathstar"), "--host", "127.0.0.1", "--port", "18540",
                     "--bind-commons", "--commons-root", str(commons),
                     "--command-center-state", str(state / "command-center"),
                     "--carrier-workspace-root", str(state / "jobs")]},
    ]


def service_status(args):
    rows = []
    for spec in service_specs(args):
        row = {"name": spec["name"], "url": spec["url"]}
        try:
            health = read_json(spec["url"] + "/health")
            fields = ("ok", "service", "version", "tool_count", "resource_count", "storage",
                      "upstream_ok", "upstream_error", "commons_mcp", "slack_carrier")
            row.update(ok=health.get("ok") is True,
                       health={key: health[key] for key in fields if key in health})
        except (OSError, ValueError, urllib.error.URLError) as exc:
            row.update(ok=False, error=type(exc).__name__)
            if isinstance(exc, urllib.error.HTTPError):
                row["http_status"] = exc.code
        rows.append(row)
    return {"ok": all(row["ok"] for row in rows), "services": rows}


def status(args):
    report = service_status(args)
    # Docker is optional for the existing foreground road and status itself.
    try:
        container = owned_container(args)
        report["lifecycle"] = lifecycle_status(container)
    except (OSError, RuntimeError) as exc:
        report["lifecycle"] = {"available": False, "error": str(exc)}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def write_new(path, content, executable=False, previous=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != content and existing != previous:
            raise RuntimeError("Preserving existing different file: " + str(path))
        if existing == content:
            return
        replacement = path.with_name(path.name + ".swarm-upgrade-" + str(os.getpid()))
        with replacement.open("x", encoding="utf-8") as stream:
            stream.write(content)
        replacement.chmod(path.stat().st_mode & 0o777)
        replacement.replace(path)
        return
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)
    if executable:
        path.chmod(0o755)


def initialize(args):
    workspace, state, deathstar = locations(args)
    commons = commons_root(args)
    for folder in ("equipment", "command-center", "deathstar", "logs", "jobs", "workers", "artifacts", "exports", "cache", "tmp", "toolchains"):
        (state / folder).mkdir(parents=True, exist_ok=True)
    (workspace / "bin").mkdir(parents=True, exist_ok=True)
    values = {
        "COMMONS_SWARM_URL": "http://127.0.0.1:8890",
        "COMMONS_COMMAND_CENTER_STATE": str(state / "command-center"),
        "COMMONS_WORKTREE_SOURCE": str(commons),
        "COMMONS_WORKTREE_ROOT": str(state / "workers"),
        "COMMONS_CARRIER_WORKSPACE_ROOT": str(state / "jobs"),
        "SWARM_STATE_ROOT": str(state),
    }
    activation = "# Source this file in each cloud worker shell.\n"
    activation += "".join("export " + key + "=" + shlex.quote(value) + "\n" for key, value in values.items())
    activation += "export PATH=" + shlex.quote(str(workspace / "bin")) + ':"$PATH"\n'
    previous_activation = activation
    activation += '''if [ -z "${SWARM_NODE24_BIN:-}" ] && command -v node >/dev/null 2>&1; then
  SWARM_NODE24_BIN=$(dirname "$(command -v node)")
  export SWARM_NODE24_BIN
fi
'''
    for toolchain in ("android.sh", "languages.sh"):
        path = shlex.quote(str(state / "toolchains" / toolchain))
        activation += "if [ -f " + path + " ]; then . " + path + "; fi\n"
    activation += 'if [ -n "${SWARM_NODE24_BIN:-}" ]; then export PATH="$SWARM_NODE24_BIN:$PATH"; fi\n'
    write_new(workspace / "activate-swarm.sh", activation, previous=previous_activation)
    python = shlex.quote(launcher_python())
    def wrapper(name, script, extra=""):
        text = "#!/bin/sh\nset -eu\n. " + shlex.quote(str(workspace / "activate-swarm.sh")) + "\n"
        text += "exec " + python + " -B " + shlex.quote(str(commons / script)) + extra + ' "$@"\n'
        write_new(workspace / "bin" / name, text, executable=True)
    wrapper("swarmctl", "host/swarmctl.py")
    wrapper("swarm-capacity", "host/worker_capacity.py")
    wrapper("swarm-workspace", "tools/runtime_artifact_bootstrap/workdir.py")
    wrapper("swarm-current", "host/cloud_current_worktree.py")
    wrapper("swarm-worker", "host/swarm_cloud_worker.py")
    wrapper("swarm-env", "host/swarm_cloud_environment.py", " --workspace " + shlex.quote(str(workspace)) + " --state " + shlex.quote(str(state)) + " --deathstar " + shlex.quote(str(deathstar)))
    mcp = "#!/bin/sh\nset -eu\n. " + shlex.quote(str(workspace / "activate-swarm.sh")) + "\n"
    mcp += "cd " + shlex.quote(str(deathstar)) + "\nexec " + python + " -B -m deathstar mcp --data " + shlex.quote(str(state / "deathstar"))
    mcp += " --bind-commons --commons-root " + shlex.quote(str(commons)) + " --command-center-state " + shlex.quote(str(state / "command-center"))
    mcp += " --carrier-workspace-root " + shlex.quote(str(state / "jobs")) + '\n'
    write_new(workspace / "bin/swarm-mcp", mcp, executable=True)
    write_new(workspace / "swarm-mcp.json", json.dumps({"mcpServers": {"deathstar": {
        "command": str(workspace / "bin/swarm-mcp"), "args": []}}}, indent=2) + "\n")
    instructions = """# Swarm cloud workspace

Read `/workspace/commons/RULES.md` in full before work; live owner messages win.
Use the actual connected GitHub and Slack tools. Discover their current schemas
at work boundaries. `commons` and `deathstar` are the existing swarm projects.

Source `/workspace/activate-swarm.sh` in each worker shell. Run `swarm-env status`
for service observations and `swarm-capacity --path /workspace --path /dev/shm`
for current capacity. Health is service state, not proof of every backend.

Keep private runtime state and artifacts under `/workspace/shared/swarm`.
Use distinct cloud worktrees under its `workers` directory for concurrent source
changes; use existing canonical `state/claims` operations for actual work.
`swarm-current open --mode worktree --source /workspace/commons --peer NAME`
opens the existing current-main worktree road. Never discard another worker's
changes, force-push, or invent another task ledger or peer-review stage.

Use stable operation IDs and reconcile uncertain provider effects before retry.
Run the real product on real input. Do not add or run test batteries.
Do not put secret values or private source responses in Git or shared messages.
Do not create owner-PC clones/caches, paid compute, model jobs or recurring tasks
merely by starting this environment. Existing direct service roads stay available.

The full operating guide is `commons/host/SWARM_CLOUD_ENVIRONMENT.md`.
"""
    if not (workspace / "AGENTS.md").exists():
        write_new(workspace / "AGENTS.md", instructions)
    print(json.dumps({"ok": True, "workspace": str(workspace), "state": str(state),
                      "activation": str(workspace / "activate-swarm.sh"), "bin": str(workspace / "bin")}))
    return 0


def docker_command(command, *, input_bytes=None, check=True):
    env = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    result = subprocess.run(["docker", "--host=unix:///var/run/docker.sock", *command],
                            env=env, input=input_bytes, capture_output=True, timeout=60)
    if check and result.returncode:
        # Docker inspect contains inherited credentials. Never forward its output.
        raise RuntimeError("Local Docker " + command[0] + " failed (exit " + str(result.returncode) + ")")
    return result


def runtime_identity(args):
    workspace, state, _ = locations(args)
    name = "commons-swarm-" + hashlib.sha256(str(state).encode()).hexdigest()[:12]
    labels = {RUNTIME_LABEL: "environment-v1", "commons.swarm.cloud.workspace": str(workspace),
              "commons.swarm.cloud.state": str(state)}
    return name, labels


def owned_container(args):
    name, labels = runtime_identity(args)
    docker_command(["info", "--format", "{{.ServerVersion}}"])
    # Listing establishes absence without interpreting a daemon failure as absence.
    listed = docker_command(["container", "ls", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.ID}}"])
    if not listed.stdout.strip():
        return None
    container = json.loads(docker_command(["container", "inspect", name]).stdout)[0]
    actual = container.get("Config", {}).get("Labels", {}) or {}
    if any(actual.get(key) != value for key, value in labels.items()):
        raise RuntimeError("Preserving unrelated container named " + name)
    return container


def lifecycle_status(container):
    if not container:
        return {"available": True, "managed": False, "running": False}
    observed = container["State"]
    return {"available": True, "managed": True, "name": container["Name"].lstrip("/"),
            "running": observed["Running"], "status": observed["Status"],
            "exit_code": observed["ExitCode"], "restart_count": container["RestartCount"],
            "restart_policy": container["HostConfig"]["RestartPolicy"]["Name"]}


def ensure_runtime_image():
    listed = docker_command(["image", "ls", "--filter", "reference=" + RUNTIME_IMAGE, "--format", "{{.ID}}"])
    if listed.stdout.strip():
        existing = json.loads(docker_command(["image", "inspect", RUNTIME_IMAGE]).stdout)[0]
        if (existing.get("Config", {}).get("Labels", {}) or {}).get(RUNTIME_LABEL) != "host-image-v1":
            raise RuntimeError("Preserving unrelated Docker image " + RUNTIME_IMAGE)
        return
    # No registry pull or copied source/credentials: executables use read-only
    # mounts of the toolchain already installed in this VM.
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        for name in ("usr", "opt", "etc", "home", "workspace", "tmp"):
            entry = tarfile.TarInfo(name)
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o1777 if name == "tmp" else 0o755
            stream.addfile(entry)
        for name, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"), ("lib", "usr/lib"), ("lib64", "usr/lib64")):
            entry = tarfile.TarInfo(name)
            entry.type = tarfile.SYMTYPE
            entry.linkname = target
            stream.addfile(entry)
    docker_command(["image", "import", "--change", "LABEL " + RUNTIME_LABEL + "=host-image-v1", "-", RUNTIME_IMAGE],
                   input_bytes=archive.getvalue())


def available_ports(args):
    for spec in service_specs(args):
        port = int(spec["url"].rsplit(":", 1)[1])
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError("Preserving existing listener on " + spec["url"] + "; inspect it before startup") from exc


def runtime_configuration(args):
    workspace, state, deathstar = locations(args)
    # Values go through inherited --env NAME entries, never command arguments,
    # files, image layers, status responses or logs.
    excluded = {"SHLVL", "_", "PWD", "OLDPWD", "TERM", "DOCKER_HOST", "DOCKER_CONTEXT",
                "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}
    inherited = {key: value for key, value in os.environ.items() if key not in excluded}
    mounts = {"/usr": True, "/opt": True, "/etc": True, str(Path.home()): False,
              str(workspace): False}
    for path in (state, deathstar, commons_root(args), Path(__file__).resolve().parent):
        if not any(path.is_relative_to(Path(root)) for root in mounts):
            mounts[str(path)] = path not in (state, deathstar, commons_root(args))
    # Existing configured file/profile selectors remain available, including
    # credential bindings outside the ordinary workspace and home paths.
    for key in ("CODEX_PROXY_CERT", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "PIP_CERT",
                "NODE_EXTRA_CA_CERTS", "OIC_MANIFEST_PATH", "AWS_CONFIG_FILE",
                "AWS_SHARED_CREDENTIALS_FILE", "GOOGLE_APPLICATION_CREDENTIALS",
                "AZURE_CONFIG_DIR", "CLOUDSDK_CONFIG", "SSH_AUTH_SOCK"):
        value = inherited.get(key, "")
        path = Path(value)
        if value and path.is_absolute() and path.exists() and not any(path.is_relative_to(Path(root)) for root in mounts):
            mounts[str(path)] = True
    if Path("/var/run/docker.sock").exists():
        mounts["/var/run/docker.sock"] = False
    command = [launcher_python(), "-B", str(Path(__file__).resolve()), "--workspace", str(workspace),
               "--state", str(state), "--deathstar", str(deathstar), "--commons", str(commons_root(args)), "serve"]
    fingerprint = hashlib.sha256(json.dumps({"environment": inherited, "mounts": mounts,
        "command": command, "launcher": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "uid": os.getuid(), "gid": os.getgid()}, sort_keys=True).encode()).hexdigest()
    return inherited, mounts, command, fingerprint


def up(args):
    initialize(args)
    workspace, state, deathstar = locations(args)
    if not (deathstar / "deathstar").is_dir():
        raise RuntimeError("Deathstar checkout is missing: " + str(deathstar))
    container = owned_container(args)
    inherited, mounts, command, fingerprint = runtime_configuration(args)
    name, labels = runtime_identity(args)
    if container and container["Config"]["Labels"].get("commons.swarm.cloud.configuration") != fingerprint:
        # Refresh session proxy/credential bindings only for this owned runtime.
        # Durable databases and artifacts are bind-mounted and never removed.
        docker_command(["container", "stop", "--time", "40", name])
        docker_command(["container", "rm", name])
        container = None
    if not container or not container["State"]["Running"]:
        available_ports(args)
        if container:
            docker_command(["container", "start", name])
        else:
            ensure_runtime_image()
            run = ["container", "run", "--detach", "--name", name, "--restart", "unless-stopped",
                   "--stop-timeout", "40", "--user", str(os.getuid()) + ":" + str(os.getgid()),
                   "--log-driver", "local", "--log-opt", "max-size=10m", "--log-opt", "max-file=3",
                   "--workdir", str(workspace), "--network", "host"]
            # Host networking preserves the existing loopback-only endpoints;
            # every remote request still uses the inherited managed proxy.
            for key, value in {**labels, "commons.swarm.cloud.configuration": fingerprint}.items():
                run += ["--label", key + "=" + value]
            for key in sorted(inherited):
                run += ["--env", key]
            for source, readonly in mounts.items():
                run += ["--mount", "type=bind,src=" + source + ",dst=" + source + (",readonly" if readonly else "")]
            for group in os.getgroups():
                run += ["--group-add", str(group)]
            proxy_hosts = set()
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                host = urllib.parse.urlsplit(inherited.get(key, "")).hostname
                if host and host not in proxy_hosts:
                    run += ["--add-host", host + ":" + socket.gethostbyname(host)]
                    proxy_hosts.add(host)
            docker_command([*run, RUNTIME_IMAGE, *command])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if all(port_responds(spec["url"]) for spec in service_specs(args)):
            return status(args)
        container = owned_container(args)
        if container and not container["State"]["Running"] and container["State"]["Status"] != "restarting":
            raise RuntimeError("Swarm runtime exited " + str(container["State"]["ExitCode"]) + "; read " + str(state / "logs"))
        time.sleep(0.5)
    raise RuntimeError("Swarm services did not bind within 30 seconds; read " + str(state / "logs"))


def port_responds(url):
    try:
        with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1])), timeout=0.3):
            return True
    except OSError:
        return False


def down(args):
    container = owned_container(args)
    if container and container["State"]["Running"]:
        docker_command(["container", "stop", "--time", "40", runtime_identity(args)[0]])
    print(json.dumps({"ok": True, "lifecycle": lifecycle_status(owned_container(args)),
                      "state_preserved": str(locations(args)[1])}, indent=2))
    return 0


def serve(args):
    initialize(args)
    workspace, state, deathstar = locations(args)
    if not (deathstar / "deathstar").is_dir():
        raise RuntimeError("Deathstar checkout is missing: " + str(deathstar))
    available_ports(args)
    env = os.environ.copy()
    env.update(COMMONS_COMMAND_CENTER_STATE=str(state / "command-center"),
               COMMONS_CARRIER_WORKSPACE_ROOT=str(state / "jobs"),
               COMMONS_SWARM_URL="http://127.0.0.1:8890", PYTHONUNBUFFERED="1",
               TMPDIR=str(state / "tmp"), XDG_CACHE_HOME=str(state / "cache"))
    children, logs = [], []
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        for spec in service_specs(args):
            log = (state / "logs" / (spec["name"] + ".log")).open("ab")
            logs.append(log)
            child = subprocess.Popen(spec["command"], cwd=spec["cwd"], env=env,
                                     stdout=log, stderr=subprocess.STDOUT)
            children.append((spec, child))
            print(json.dumps({"starting": spec["name"], "pid": child.pid, "url": spec["url"]}), flush=True)
            # Give the equipment process time to bind before Deathstar imports it.
            time.sleep(0.5)
        print(json.dumps({"supervising": True, "state": str(state)}), flush=True)
        while True:
            for spec, child in children:
                code = child.poll()
                if code is not None:
                    raise RuntimeError(spec["name"] + " exited " + str(code) + "; read " + str(state / "logs" / (spec["name"] + ".log")))
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        for _, child in children:
            if child.poll() is None:
                child.terminate()
        for _, child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--deathstar", type=Path)
    parser.add_argument("--commons", type=Path)
    parser.add_argument("command", choices=("init", "up", "down", "serve", "status"))
    args = parser.parse_args()
    try:
        action = {"init": initialize, "up": up, "down": down, "serve": serve, "status": status}[args.command]
        if args.command in ("up", "down"):
            state = locations(args)[1]
            state.mkdir(parents=True, exist_ok=True)
            # Multiple peers can request the same named runtime concurrently.
            # Serialize container mutations without a task ledger or work gate.
            with (state / "lifecycle.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                return action(args)
        return action(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
