#!/usr/bin/env python3
"""Run a Gradle wrapper using the cloud environment's existing HTTP proxies."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import errno
import fcntl
import ipaddress
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


FORKED_PROXY_INIT = r"""
// Only endpoint/bypass settings and an explicit trust-store path are inherited.
// No credentials or property values are logged.
def inheritProxyDefaults = { fork ->
    fork.doFirst {
        def explicit = fork.systemProperties.keySet().collect { it.toString() } as Set
        // Include lazy argument providers at execution time, when their inputs
        // are ready, so a task-specific endpoint is never mixed with a default.
        fork.allJvmArgs.each { argument ->
            if (argument.startsWith('-D')) {
                explicit.add(argument.substring(2).split('=', 2)[0])
            }
        }
        ['http', 'https'].each { protocol ->
            def endpoint = [protocol + '.proxyHost', protocol + '.proxyPort']
            if (!endpoint.any { explicit.contains(it) }) {
                endpoint.each { key ->
                    def value = System.getProperty(key)
                    if (value != null) {
                        fork.systemProperty(key, value)
                    }
                }
            }
        }
        ['http.nonProxyHosts', 'javax.net.ssl.trustStore'].each { key ->
            if (!explicit.contains(key)) {
                def value = System.getProperty(key)
                if (value != null) {
                    fork.systemProperty(key, value)
                }
            }
        }
    }
}
gradle.beforeProject { project ->
    project.tasks.withType(org.gradle.api.tasks.testing.Test).configureEach(inheritProxyDefaults)
    project.tasks.withType(org.gradle.api.tasks.JavaExec).configureEach(inheritProxyDefaults)
}
"""


def proxy_properties(environment: dict[str, str]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for protocol in ("http", "https"):
        value = environment.get(f"{protocol}_proxy") or environment.get(f"{protocol.upper()}_PROXY")
        if not value:
            continue
        try:
            proxy = urlsplit(value if "://" in value else f"http://{value}")
            port = proxy.port if proxy.port is not None else 80
        except ValueError:
            raise ValueError(f"{protocol.upper()}_PROXY is not a valid proxy URL") from None
        if proxy.scheme != "http":
            raise ValueError(f"{protocol.upper()}_PROXY must name an HTTP forward proxy for the JVM")
        if proxy.username is not None or proxy.password is not None:
            raise ValueError(f"{protocol.upper()}_PROXY contains credentials; configure the JVM's existing proxy authenticator instead")
        if not proxy.hostname or proxy.path not in ("", "/") or proxy.query or proxy.fragment:
            raise ValueError(f"{protocol.upper()}_PROXY is not a host-and-port proxy URL")
        if port == 0:
            raise ValueError(f"{protocol.upper()}_PROXY must use a nonzero port")
        properties[f"{protocol}.proxyHost"] = proxy.hostname
        properties[f"{protocol}.proxyPort"] = str(port)

    bypass = environment.get("no_proxy") or environment.get("NO_PROXY")
    if properties and bypass:
        hosts: list[str] = ["localhost", "127.*", "[::1]"]
        for entry in bypass.split(","):
            host = entry.strip()
            if not host:
                continue
            if "/" in host:
                try:
                    network = ipaddress.ip_network(host, strict=False)
                except ValueError:
                    raise ValueError("NO_PROXY contains an invalid IP network") from None
                if network.version == 6 and network.num_addresses != 1:
                    raise ValueError("NO_PROXY contains an IPv6 subnet; supply explicit JVM nonProxyHosts for its address spellings")
                if network.version == 4 and network.num_addresses > 1:
                    # Split only to the next whole octet: /12 becomes sixteen
                    # address prefixes, never millions of individual addresses.
                    prefix = max(8, ((network.prefixlen + 7) // 8) * 8)
                    blocks = network.subnets(new_prefix=prefix) if prefix > network.prefixlen else (network,)
                    for block in blocks:
                        parts = str(block.network_address).split(".")
                        hosts.append(".".join(parts[:prefix // 8]) + (".*" if prefix < 32 else ""))
                    continue
                host = str(network.network_address)
            if host.startswith("."):
                hosts.extend((host[1:], f"*{host}"))
            elif host.startswith("*."):
                hosts.extend((host[2:], host))
            else:
                try:
                    address = ipaddress.ip_address(host.strip("[]"))
                except ValueError:
                    if ":" in host:
                        raise ValueError("NO_PROXY contains a port-specific rule the JVM cannot represent; use explicit JVM nonProxyHosts")
                    if "*" not in host:
                        hosts.append(f"*.{host}")
                else:
                    if address.version == 6:
                        host = f"[{address}]"
                hosts.append(host)
        properties["http.nonProxyHosts"] = "|".join(dict.fromkeys(hosts))
    return properties


def explicit_properties(environment: dict[str, str], project: Path, arguments: list[str]) -> set[str]:
    """Keep existing JVM settings, including project/user Gradle properties."""
    keys: set[str] = set()
    option_text = " ".join(environment.get(name, "") for name in
                           ("GRADLE_OPTS", "JAVA_OPTS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"))
    keys.update(re.findall(r"(?:^|\s)[\"']?-D([^\s=]+)=", option_text))
    keys.update(argument[2:].split("=", 1)[0] for argument in arguments if argument.startswith("-D"))
    user_home = Path(environment.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    for path in (project / "gradle.properties", user_home / "gradle.properties"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            keys.update(re.findall(r"(?m)^\s*systemProp\.([^\s:=]+)\s*[:=]", text))
    return keys


class AdmissionUnavailable(Exception):
    """A cooperating build or the available disk space prevents this launch."""


def acquire_build_lock(path: Path) -> int:
    # O_NONBLOCK also keeps an unexpected FIFO from blocking before fstat.
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("--build-lock must name a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise AdmissionUnavailable(
                    f"build lock is busy ({path}); retry after the cooperating build finishes"
                ) from None
            raise
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def storage_paths(environment: dict[str, str], project: Path, arguments: list[str]) -> tuple[Path, Path]:
    """Resolve common Gradle directory options relative to the launcher cwd."""
    directories: dict[str, str] = {}
    home_property = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            break
        property_argument = argument
        if argument == "-D" and index + 1 < len(arguments):
            index += 1
            property_argument = "-D" + arguments[index]
        if property_argument.startswith("-Dgradle.user.home="):
            home_property = property_argument.split("=", 1)[1]
        for short, long, name in (("-g", "--gradle-user-home", "home"), ("-p", "--project-dir", "project")):
            value = None
            if argument in (short, long, long[1:]):
                index += 1
                if index >= len(arguments) or arguments[index].startswith("-"):
                    raise ValueError(f"{long} requires a directory")
                value = arguments[index]
            elif argument.startswith(long + "="):
                value = argument.split("=", 1)[1]
            elif argument.startswith(short) and not argument.startswith("--"):
                attached = argument[len(short):]
                if not attached.startswith(("=", "/", ".")):
                    raise ValueError("--min-free-disk-mib requires long Gradle options or separated -g/-p values instead of ambiguous attached options")
                value = attached.removeprefix("=")
            if value is not None:
                if not value or name in directories:
                    raise ValueError(f"{long} requires one nonempty directory value")
                directories[name] = value
                break
        index += 1
    if "home" not in directories and home_property is None:
        option_text = " ".join(environment.get(name, "") for name in
                               ("GRADLE_OPTS", "JAVA_OPTS", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"))
        if re.search(r"""(?:^|\s)["']?-D(?:gradle\.user\.home|user\.home)(?:=|\s|$)""", option_text):
            raise ValueError("--min-free-disk-mib requires forwarded --gradle-user-home when JVM options override the home")
    home = directories.get("home", home_property if home_property is not None else
                           environment.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    paths = (Path(directories.get("project", str(project))), Path(home))
    return tuple((path if path.is_absolute() else project / path).resolve() for path in paths)


def check_free_disk(project: Path, user_home: Path, minimum_mib: int) -> None:
    for label, path in (("project", project), ("Gradle user home", user_home)):
        existing = path
        while not existing.exists():
            existing = existing.parent
        if not existing.is_dir():
            raise ValueError(f"{label} or its nearest existing parent is not a directory")
        free = shutil.disk_usage(existing).free
        if free < minimum_mib * 1024 * 1024:
            raise AdmissionUnavailable(
                f"{label} has {free // (1024 * 1024)} MiB free at {existing}; "
                f"requires {minimum_mib} MiB; free space or select another build/cache location and retry"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Gradle project directory (default: current directory)")
    parser.add_argument("--refresh-env-proxy", action="store_true", help="Replace inherited GRADLE_OPTS proxy endpoint flags with this invocation's environment")
    parser.add_argument("--forked-jvms", action="store_true", help="Supply missing Test/JavaExec proxy defaults through a temporary Gradle init script")
    parser.add_argument("--build-lock", type=Path, help="Try a shared cooperative POSIX lock without waiting; retain its file after release")
    parser.add_argument("--min-free-disk-mib", type=int, help="Require this nonnegative free-space floor on the selected project and Gradle user home")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Wrapper arguments after --")
    args = parser.parse_args()
    if args.min_free_disk_mib is not None and args.min_free_disk_mib < 0:
        parser.error("--min-free-disk-mib must be a nonnegative integer")
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    project = args.project.resolve()
    wrapper = project / "gradlew"
    environment = os.environ.copy()
    lock_descriptor = None
    try:
        if not wrapper.is_file():
            raise ValueError("The selected project does not contain a Gradle wrapper")
        if args.refresh_env_proxy:
            refresh_keys = {
                f"{protocol}.{part}"
                for protocol in ("http", "https")
                if environment.get(f"{protocol}_proxy") or environment.get(f"{protocol.upper()}_PROXY")
                for part in ("proxyHost", "proxyPort")
            }
            try:
                inherited = shlex.split(environment.get("GRADLE_OPTS", ""))
            except ValueError:
                raise ValueError("GRADLE_OPTS contains unmatched quoting") from None
            environment["GRADLE_OPTS"] = shlex.join(
                option for option in inherited
                if not (option.startswith("-D") and option[2:].split("=", 1)[0] in refresh_keys)
            )
        explicit = explicit_properties(environment, project, arguments)
        proxy_environment = environment.copy()
        # An explicit host/port pair belongs to the caller; do not mix it with
        # half of an environment proxy endpoint.
        for protocol in ("http", "https"):
            if any(f"{protocol}.{part}" in explicit for part in ("proxyHost", "proxyPort")):
                proxy_environment.pop(f"{protocol}_proxy", None)
                proxy_environment.pop(f"{protocol.upper()}_PROXY", None)
        if "http.nonProxyHosts" in explicit:
            proxy_environment.pop("no_proxy", None)
            proxy_environment.pop("NO_PROXY", None)
        properties = proxy_properties(proxy_environment)
        options = [f"-D{key}={value}" for key, value in properties.items()]
        # The launcher needs these before a distribution exists. CLI properties
        # also reach the Gradle daemon; caller-supplied options stay last.
        environment["GRADLE_OPTS"] = " ".join(filter(None, (shlex.join(options), environment.get("GRADLE_OPTS", ""))))
        if args.build_lock is not None:
            lock_descriptor = acquire_build_lock(args.build_lock)
        if args.min_free_disk_mib is not None:
            check_free_disk(*storage_paths(environment, project, arguments), args.min_free_disk_mib)
        print(f"Gradle environment proxy: {len(properties)} JVM properties applied; existing explicit settings preserved", file=sys.stderr, flush=True)
        with ExitStack() as temporary:
            init_options: list[str] = []
            if args.forked_jvms:
                directory = temporary.enter_context(tempfile.TemporaryDirectory(prefix="gradle-env-proxy-"))
                init_script = Path(directory) / "forked-proxy.gradle"
                init_script.write_text(FORKED_PROXY_INIT, encoding="utf-8")
                init_options = ["--init-script", str(init_script)]
            command = [str(wrapper), *options, *init_options, *arguments]
            result = subprocess.run(command, cwd=project, env=environment, check=False)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except AdmissionUnavailable as error:
        print(f"Gradle environment proxy: {error}", file=sys.stderr)
        return 75
    except (OSError, ValueError) as error:
        # Do not include proxy URLs or environment values in failure messages.
        if isinstance(error, OSError):
            print(f"Gradle environment proxy: process or file operation failed ({error.__class__.__name__}, errno={error.errno})", file=sys.stderr)
        else:
            print(f"Gradle environment proxy: {error}", file=sys.stderr)
        return 2
    finally:
        if lock_descriptor is not None:
            # Close releases flock. Never unlink: peers must keep using one inode.
            os.close(lock_descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
