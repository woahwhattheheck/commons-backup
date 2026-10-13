# Gradle through an existing cloud proxy

Use `gradle_env_proxy.py` when a cloud VM can fetch with curl or Git but the
Gradle wrapper's Java downloader fails with `Network is unreachable`. Java does
not automatically consume the shell's `HTTP_PROXY` / `HTTPS_PROXY` settings.
The helper translates those existing settings into JVM properties for the
wrapper launcher and the Gradle daemon, then runs the real project wrapper in
a POSIX cloud environment with Python 3.9 or newer.

```sh
python3 /path/to/commons/host/gradle_env_proxy.py --refresh-env-proxy --project /path/to/GmsCore -- --version
GRADLE_MICROG_VERSION_WITHOUT_GIT=1 python3 /path/to/commons/host/gradle_env_proxy.py --refresh-env-proxy --project /path/to/GmsCore -- :play-services-droidguard-core:assembleDebug
```

Cloud proxy endpoints can change between tool invocations. Read the environment
on every invocation; do not copy a proxy host or port from a prior command.
`--refresh-env-proxy` removes only inherited `GRADLE_OPTS` proxy host/port flags
for protocols configured in the current environment, then rebuilds those flags
from that environment. Other JVM options remain. Explicit wrapper arguments,
other JVM option variables and `gradle.properties` still take precedence. Omit
the flag when intentionally keeping proxy endpoint flags in `GRADLE_OPTS`.

Add `--forked-jvms` when a Gradle `Test` or `JavaExec` task performs its own
network requests, such as Robolectric downloading its Android runtime. These
forked JVMs do not automatically inherit the Gradle process's proxy properties.
The flag installs a temporary init script for this invocation and removes it
when the wrapper finishes. It supplies the effective HTTP/HTTPS host, port and
bypass properties immediately before those tasks run, along with an explicitly
configured `javax.net.ssl.trustStore` path so a fork can use the same existing
trust roots. Existing task properties and JVM argument providers win; an
explicit task host or port preserves that whole endpoint. Explicit Gradle CLI
settings remain the inherited defaults. Credentials, trust-store passwords and
unrelated JVM properties are never copied or logged. No project build file or
JDK trust store is changed. Without the flag, forked tasks are unchanged.

Use `--no-configuration-cache` with this execution-time opt-in; compatibility
with a cached task graph is not established. The helper preserves the caller's
cache selection:

```sh
python3 /path/to/commons/host/gradle_env_proxy.py --refresh-env-proxy --forked-jvms --project /path/to/GmsCore -- --no-configuration-cache :play-services-wearable-core:testDebugUnitTest
```

Run the tasks required by the active bounty on its exact current source. Keep
the existing issue claim, integration branch and upstream submission owner.
This helper supplies network configuration; it does not provide Android SDK
packages, a JDK compiler, a device, attestation, or bounty acceptance.

For a D8 duplicate-class failure involving `.rsync-tmp` entries in generated
Wear JARs, use the separate [generated JAR repair](GRADLE_RSYNC_JARS.md).
That guide also records the [runnable Wear source and combined command](GRADLE_RSYNC_JARS.md#runnable-wear-source-and-combined-command), including the immutable successful
source pin and the moving integration branch.

## Behavior

- Uses lowercase proxy variables first, then uppercase equivalents. Each
  protocol keeps its own endpoint. An HTTP forward proxy also handles HTTPS
  destinations through the JVM's normal CONNECT behavior.
- Preserves explicit proxy properties from wrapper arguments, existing JVM
  option variables, and the project's/user's `gradle.properties`. If a caller
  supplies a proxy host or port, the helper leaves that endpoint alone.
- Translates `NO_PROXY` hostnames, domain suffixes, wildcard domains and literal
  IP addresses to `http.nonProxyHosts` (the JVM property also used for HTTPS).
  IPv4 CIDRs become bounded address-prefix lists: `172.16.0.0/12` becomes
  `172.16.*` through `172.31.*`. This is JVM hostname matching, not a DNS
  resolution rule. Loopback bypass remains. IPv6 subnets and port-specific
  bypasses produce a clear error before the wrapper runs. Explicit
  `-Dhttp.nonProxyHosts=...` takes precedence over automatic translation.
- Preserves other wrapper arguments and JVM options, returns the wrapper's exit
  code, and reports missing wrappers or invalid configuration with exit 2.
- Does not print proxy URLs or values, write credentials or project settings,
  change network policy, install software outside the wrapper's normal behavior,
  dispatch hosted CI, or schedule work. Authenticated proxy URLs must use an
  existing JVM authenticator rather than putting credentials in command options.

## Optional build admission

On a POSIX filesystem shared by cooperating builders, use one agreed lock path
and a free-space floor before starting another wrapper. Both options are
disabled by default; the normal proxy invocation remains available.

```sh
export GRADLE_USER_HOME="$PWD/.gradle-user-home"
python3 /path/to/commons/host/gradle_env_proxy.py \
  --refresh-env-proxy --project /path/to/GmsCore \
  --build-lock /workspace/scratch/android-build.lock \
  --min-free-disk-mib 2048 -- \
  --no-daemon --max-workers=2 '-Dorg.gradle.jvmargs=-Xmx1g' \
  :play-services-droidguard-core:assembleDebug
```

Choose the floor for the task; 2048 MiB is an example, not a measured build
requirement. Keep the writable Gradle home private to that build. Reuse installed
JDK/SDK/distribution files without sharing another active build's writable
daemon or journal cache. If the downloaded JDK needs this environment's system
Java truststore, preserve its existing truststore JVM setting; do not disable TLS.

- `--build-lock PATH` opens a regular file without following its symlink leaf
  and tries an exclusive, nonblocking POSIX `flock`. Its parent must already
  exist. The launcher retains the lock until the wrapper returns, then closes
  the descriptor. It never truncates or unlinks the lock file: cooperating
  callers must keep using the same file/inode. Paths and permissions must be
  suitable for the participating processes.
- `--min-free-disk-mib N` accepts a nonnegative integer and checks available
  bytes on the selected project and writable Gradle-home filesystems before
  launch, while holding the requested build lock. For a directory that does
  not exist yet, it checks the nearest existing parent without creating it.
  The default home is `GRADLE_USER_HOME`, otherwise `~/.gradle`.
- Forwarded `--project-dir` / `-p` and `--gradle-user-home` / `-g` select
  the checked roots. Use separate values or long `--option=value` forms;
  short `-g=value`, `-p=value` and attached absolute or `./` paths are
  also supported. Ambiguous attached short options require long or separated
  forms when the floor is enabled. Repeated or empty directory selections
  are configuration errors. Relative paths resolve against `--project`,
  independently of a forwarded `-p`.
- An explicit `-g` takes precedence over forwarded
  `-Dgradle.user.home=...`, which takes precedence over the environment.
  If JVM option environments override `gradle.user.home` or `user.home`,
  select the home explicitly with either of those forwarded options.
  Custom wrapper-embedded settings, project-cache/output directories,
  init scripts and other filesystem consumers are outside this check.
- An occupied lock or insufficient disk returns **75** with a retry reason,
  before launching the wrapper. Other configuration/file errors return **2**.
  Once launched, the wrapper's exit status is preserved.

The lock coordinates only callers sharing the same POSIX lock inode; separate
filesystem views and noncooperating builds are not serialized. The disk floor
is a launch-time observation, not reserved capacity or a guarantee that space
will remain available. This adds no waiting queue or scheduler.

References: [Python `fcntl.flock`](https://docs.python.org/3/library/fcntl.html#fcntl.flock)
and [Python `shutil.disk_usage`](https://docs.python.org/3/library/shutil.html#shutil.disk_usage).

## Observed cloud use

On 2026-10-04, the exact GmsCore wrapper at
`3f10ba2b9ef6aa7a7806cf0547d70932bb4d3965` failed before downloading Gradle 8.13
with `java.net.SocketException: Network is unreachable`. curl reached that
distribution URL through the environment proxy. Applying the same environment
proxy as JVM settings completed the real Gradle distribution download and
`--version` with exit 0 on OpenJDK 17.0.20/Linux. This is a working wrapper
download and launch, not an Android application build or a device result.
The real project also completed Gradle `help` with dependency configuration and
exit 0 in 71 seconds using the same configured proxy. The helper's automatic
environment path and explicit-setting preservation were then exercised against
that installed wrapper; no test suite or hosted workflow was dispatched.

Reference: [Gradle networking](https://docs.gradle.org/current/userguide/networking.html)
and [JDK 17 networking properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html).
