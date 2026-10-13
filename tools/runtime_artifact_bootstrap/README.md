# Runtime recovery in existing cloud workspaces

## Reuse installed JDK and Android SDK bytes

Before downloading another toolchain, read the current work thread for installed
runtime directories in the same shared cloud filesystem. Pass those exact
toolchain directories to the probe below. It checks each supplied directory and
its immediate children, plus the existing Java/Android environment paths and the
compiler on `PATH`; it does not walk other workspaces. Paths reported by another
container remain candidates until this container can use them.

`java` alone does not establish a JDK. On October 4, the bounty cloud workspace
had `/usr/bin/java` but no `javac` on `PATH`; two supplied shared installations
both ran `javac 17.0.20.1` successfully and contained Android platform 35 and
build-tools 35.0.0. Reusing those directories required no JDK/SDK copy or download.
These are dated observations, not permanent session-path pins or a project build
result. Select versions required by the current project's own build files.

### Inspect only supplied candidates

Replace the paths and Android versions with the current task's candidates and
requirements. This command writes no files and makes no network requests. It
executes only a discovered candidate's `javac -version` and reports its exit code.

```sh
python - /actual/shared/toolchain-one /actual/shared/toolchain-two <<'PY'
import json, os, pathlib, shutil, subprocess, sys

api, build_tools = "35", "35.0.0"
candidates, errors = [], []
for value in sys.argv[1:]:
    root = pathlib.Path(value)
    candidates.append(root)
    try:
        candidates.extend(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        errors.append({"root": str(root), "error": type(exc).__name__})
for name in ("JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
    if os.environ.get(name):
        candidates.append(pathlib.Path(os.environ[name]))
if shutil.which("javac"):
    candidates.append(pathlib.Path(shutil.which("javac")).resolve().parent.parent)
jdks, sdks = [], []
for root in dict.fromkeys(p.resolve() for p in candidates):
    javac = root / "bin/javac"
    if javac.is_file() and (root / "bin/java").is_file():
        try:
            run = subprocess.run([str(javac), "-version"], capture_output=True,
                                 text=True, timeout=10)
            jdks.append({"root": str(root), "exit": run.returncode,
                         "version": (run.stdout + run.stderr).strip()})
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append({"root": str(root), "error": type(exc).__name__})
    if ((root / f"platforms/android-{api}/android.jar").is_file()
            and (root / f"build-tools/{build_tools}/aapt2").is_file()):
        sdks.append({"root": str(root), "platform": api, "build_tools": build_tools})
print(json.dumps({"java_on_path": shutil.which("java"),
                  "javac_on_path": shutil.which("javac"),
                  "jdks": jdks, "sdks": sdks, "errors": errors}, indent=2))
sys.exit(0 if any(row["exit"] == 0 for row in jdks) and sdks else 1)
PY
```

The SDK result confirms those two required files, not every optional Android
package or a successful build.

### Use the maintained Gradle proxy launcher

Use [host/gradle_env_proxy.py](../../host/gradle_env_proxy.py) and its
[operator guide](../../host/GRADLE_ENV_PROXY.md) for the build. The launcher reads
this execution's proxy environment, handles `NO_PROXY`, preserves explicit JVM
settings, and returns the real wrapper exit code. `--refresh-env-proxy` replaces
inherited `GRADLE_OPTS` proxy endpoints with this invocation's endpoints; other
explicit proxy settings keep their documented precedence. Do not copy a proxy
host or port from a preceding tool call.

An independently installed JDK can lack the system CA used by the configured
HTTPS proxy. The October 4 Cast build initially failed with PKIX path-building
errors. Using the existing `/etc/ssl/certs/java/cacerts` truststore restored
dependency resolution; the repaired dispatcher then compiled and passed all six
focused regressions, versus five failures and one pass on the baseline. This is
the recorded JVM execution result, not a phone/Cast hardware benchmark. Reuse the
current system truststore without modifying the shared JDK or disabling TLS
validation.

Supply the selected installation paths and the active bounty's actual tasks:

```sh
JAVA_HOME=/actual/shared/jdk \
ANDROID_HOME=/actual/shared/android-sdk \
ANDROID_SDK_ROOT=/actual/shared/android-sdk \
GRADLE_USER_HOME=/actual/owned/gradle-cache \
python3 /path/to/commons/host/gradle_env_proxy.py \
  --refresh-env-proxy --project /actual/build-checkout -- \
  --no-daemon --console=plain \
  -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts \
  :your-module:assembleDebug
```

Keep a distinct writable Gradle user home for this build, and retain it across
its repeated commands. Another builder hit a shared `/root/.gradle` journal
lock; do not delete a peer's locks or change their properties. Reuse the shared
JDK/SDK in place and keep build outputs and writable caches task-owned.

The maintained launcher does not write project settings or print proxy values.
Authenticated proxy URLs use its documented existing JVM-authenticator route;
do not add credentials to repository files, arguments or published logs. This
recipe needs no second proxy wrapper or temporary project configuration.

## Choose an owned work directory from current capacity

`workdir.py` is an optional Python operator aid for temporary outputs, archives,
and runtime extraction. It inspects only the candidate directories you supply.
It identifies their filesystem devices, so `/tmp` and a workspace on the same
overlay are visible as aliases rather than extra capacity. Linux `tmpfs` and
`ramfs` candidates are also bounded by observed host memory and the command
center's existing visible-ancestor cgroup charge-headroom reader.

Inspect without writing:

```sh
python tools/runtime_artifact_bootstrap/workdir.py inspect \
  --candidate "$PWD" --candidate /tmp --candidate /dev/shm \
  --need-bytes 1048576 --reserve-bytes 16777216
```

Create an independently owned directory on the fitting candidate with the most
observed usable bytes; equal candidates preserve your argument order:

```sh
TASK_WORKDIR="$(python tools/runtime_artifact_bootstrap/workdir.py create \
  --candidate "$PWD" --candidate /dev/shm \
  --need-bytes 1048576 --reserve-bytes 16777216 --format path)" || exit
```

Use the returned path as your command's output directory, or pass it as the
existing browser helper's `tempRoot`. JSON is the default output and includes
the actual selected root, created path, device aliases, exact byte counts,
memory sources, unknown coverage, and any creation errors. A failed `create`
exits nonzero and returns those observations; `inspect` remains read-only.

The helper creates one new `commons-work-*` directory and checks a 4 KiB write
inside it. A failed attempt removes only that call's own check file and empty
directory; unexpected contents are preserved. It never recursively deletes,
moves existing files, changes environment variables, launches workloads, or
changes another tool's admission behavior. The caller retains the successful
directory and decides where completed artifacts belong.

Capacity is an observation, not a reservation. Cgroup headroom excludes
possible cache reclaim and can change with other workers; it is distinct from
the larger free-space number a tmpfs mount can display. `--need-bytes` is the
expected temporary-file budget and does not include the workload's process
memory. Unknown limits remain visible in JSON. Use a full Commons checkout, or
retain `integrations/command_center/telemetry.py` at its normal relative path,
to reuse the cgroup reader. The helper uses only the Python standard library.

The same inspection includes `memory.cgroup.memory_stats`, also exposed as
`process_limits.memory_stats` in the host telemetry record. Each entry retains
its `memory.stat` source path, cgroup-and-descendants scope, and selected byte
fields. Missing fields stay absent; unavailable files and malformed data use
the existing unavailable-interface and read-error lists. The
[kernel definitions](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory-interface-files)
distinguish anonymous mappings (`anon`), filesystem cache including tmpfs/shared
memory (`file`), and kernel allocations (`kernel`). Detail and reclaim-list
fields overlap: `shmem` is included in `file`, and slab is included in `kernel`.
Do not sum these fields or records across ancestors. `inactive_file` and
`slab_reclaimable` are not guaranteed available capacity; the breakdown does not
change headroom or candidate selection, and total usage is not process heap.

## Local product browser with installed Chromium

`local_browser.cjs` exports `openLocalBrowser({ target, executablePath, tempRoot? })`.
It returns an owned Playwright `page`, `context`, `temporaryDirectory`, and
idempotent `close()`. Use those objects with the product's existing operator flow.

Pass an explicit HTTP(S) URL on numeric loopback (`127.0.0.1` or `[::1]`) or a
`file://` URL for an existing local HTML workbench. Use the product's direct local
page or its documented offline entry; the helper opens only that supplied target.
Public-service navigation and actions belong to their existing authorized tools.
The user's browser, CDP connection, saved sessions, and provider plugins are not
reused. Product requests keep the browser's normal behavior.

The executable must already exist. Playwright is loaded from the installed
`CODEX_PRIMARY_RUNTIME_NODE_MODULES/playwright` when that runtime location is
provided, otherwise from the project's normal `playwright` dependency. There is
no installation or binary download step.

### Provision missing package bytes

The additional native route below ran in an existing Linux x64 cloud workspace
with Node 24.19.0, installed Playwright 1.62.1, and `@sparticuz/chromium@153.0.0`.
Reuse those installed bytes when available. For a fresh tooling directory, run
this from your writable cloud task directory:

```sh
BROWSER_TOOLING_ROOT="$(mktemp -d "$PWD/browser-tooling.XXXXXX")"
npm install --prefix "$BROWSER_TOOLING_ROOT" --save-exact @sparticuz/chromium@153.0.0
```

For the extraction recipe below, set `CHROMIUM_PACKAGE_ROOT` to
`$BROWSER_TOOLING_ROOT/node_modules/@sparticuz/chromium` and choose a new output
inside an owned writable directory. Keep these dependencies in the tooling
directory, outside the product's dependency manifest.

A separate CLI attempt installed the exact npm pin `agent-browser@0.38.2`.
Its default Chrome download timed out, and its daemon later failed during
startup. The native Playwright route below succeeded independently; installing
that CLI is not a prerequisite for it.

A later run of this pin stopped before Chromium launch: its own session log
reported `Failed to bind socket: Operation not permitted (os error 1)`. With
`--debug`, version 0.38.2 [redirects daemon stderr](https://github.com/vercel-labs/agent-browser/blob/v0.38.2/cli/src/native/daemon.rs)
to `<socket-directory>/<session>.log`, so the CLI can still report "no error
output." Inspect only your selected session's log and retain the existing
socket permissions and other sessions. This identifies the daemon's socket
bind as the immediate failure in that container. The existing local-browser
helper subsequently completed report navigation, filtering and print-view
inspection there with an already installed Chromium executable.

### Obtain the executable from the installed package

Commons already pins `@sparticuz/chromium` 153.0.0. When that package is installed,
its `bin/chromium.br` contains the executable. The package's usual
`chromium.executablePath()` also extracts supporting tarballs; that path failed
with `EINVAL` during font-file `chown` in the recovered container. Inflate just
the executable into a new file in a writable task directory:

```sh
CHROMIUM_PACKAGE_ROOT=/actual/node_modules/@sparticuz/chromium \
LOCAL_CHROMIUM_EXECUTABLE=/own/writable/runtime/chromium \
node - <<'JS'
const { createReadStream, createWriteStream, constants } = require('node:fs');
const { access, chmod } = require('node:fs/promises');
const { pipeline } = require('node:stream/promises');
const { createBrotliDecompress } = require('node:zlib');
const path = require('node:path');
(async () => {
  const root = process.env.CHROMIUM_PACKAGE_ROOT ||
    path.resolve(path.dirname(require.resolve('@sparticuz/chromium')), '..');
  const input = path.join(root, 'bin', 'chromium.br');
  const output = process.env.LOCAL_CHROMIUM_EXECUTABLE;
  if (!output || !path.isAbsolute(output)) throw new Error('Supply an absolute LOCAL_CHROMIUM_EXECUTABLE path.');
  await access(input, constants.R_OK);
  await pipeline(createReadStream(input), createBrotliDecompress(),
    createWriteStream(output, { flags: 'wx', mode: 0o600 }));
  await chmod(output, 0o755);
  console.log(output);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
JS
```

Create the writable parent directory first. The optional `workdir.py` helper
above can compare an owned `/dev/shm` candidate with the workspace, including
the current cgroup memory budget. The output must be new: `wx` preserves
any existing executable, and a failed extraction leaves its partial output
non-executable. Pass the printed path to `openLocalBrowser` and reuse that binary
across calls. This recovery does not unpack the font/SwiftShader tarballs or
change library-path environment variables; the launch settings below worked
without those overrides. It requires the already available pinned package bytes.

A separate workspace encountered another package shortcut: version 153.0.0
returned an existing zero-byte `/tmp/chromium` from `executablePath()` before
extracting anything. Leave such shared files untouched. Use the new destination
in the streaming recipe above and pass that exact executable path to Playwright;
the existence of the package's returned path alone does not establish a usable
binary.

### Use the context

From the Commons checkout, with your product server already running:

```sh
LOCAL_PRODUCT_URL=http://127.0.0.1:8788/ \
LOCAL_CHROMIUM_EXECUTABLE=/actual/available/chromium \
node - <<'JS'
const { openLocalBrowser } = require('./tools/runtime_artifact_bootstrap/local_browser.cjs');
(async () => {
  const session = await openLocalBrowser({
    target: process.env.LOCAL_PRODUCT_URL,
    executablePath: process.env.LOCAL_CHROMIUM_EXECUTABLE,
  });
  try {
    console.log(await session.page.title());
    // Continue the product's operator flow with session.page and session.context.
  } finally {
    await session.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
JS
```

For an offline workbench, create its explicit URL with Node's
`pathToFileURL('/absolute/path/to/workbench.html').href`.

Each call creates a private task directory beneath an explicit `tempRoot`, or
tries the current temporary directory and then `/dev/shm`. A real write chooses
the usable location when the workspace disk is full. Profile, download, and
Playwright artifact directories all live below that task directory. Closing the
session removes only those files; launch/navigation failures perform the same
cleanup. Save wanted downloads with the usual `download.saveAs(explicitPath)`
before closing. Download and TLS permissions use Playwright's defaults.

The recovered Linux launch uses a persistent context with `--no-zygote`,
`--single-process`, and GPU/software-rasterizer/WebGL disabled. It omits the
default unsafe SwiftShader flag. Persistent here describes Chromium's context
type; its fresh profile is deleted at close. This method worked with the
already available Chromium 153.0.0 and Playwright 1.62.1. The ordinary
`launch()` then `newContext()` sequence crashed in that constrained runtime.
Supply your actual executable path; the helper stores no workspace-specific pin.

### Direct Playwright route in an ordinary cloud runtime

A separate existing workspace ran ordinary `chromium.launch()` followed by
`newContext()` with the extracted binary and no additional launch arguments.
It reported Chromium **153.0.8010.0**. The current product HTML and both JavaScript
assets loaded over HTTP on the same loopback origin; the example-to-compile
operator flow rendered its result with no console or page errors.
[Source work context](https://github.com/woahwhattheheck/smb-showcase-inventory/issues/1284#issuecomment-5966727598).

The direct launch pattern is:

```sh
LOCAL_PRODUCT_URL=http://127.0.0.1:8788/index.html \
LOCAL_CHROMIUM_EXECUTABLE=/actual/own/runtime/chromium \
node - <<'JS'
const pw = require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + '/playwright');
(async () => {
  const browser = await pw.chromium.launch({
    executablePath: process.env.LOCAL_CHROMIUM_EXECUTABLE,
    headless: true,
  });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      acceptDownloads: true,
    });
    const page = await context.newPage();
    await page.goto(process.env.LOCAL_PRODUCT_URL);
    console.log({ chromium: browser.version(), title: await page.title() });
    // Continue the real product flow; save wanted downloads before closing.
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
JS
```

Use the actual live product URL. The demonstrated server was a native Node HTTP
server bound to `127.0.0.1`, kept in the same live process as the browser-driving
code. When a harness does not preserve background servers between commands, start
the product server and execute the browser operations in that same live session;
keep the server listening until the browser work finishes. Serve HTML and scripts
from one HTTP origin so normal asset loading and browser policy apply.

This direct route leaves launch arguments and browser policy at their normal
Playwright behavior; it does not pass `@sparticuz/chromium.args` or override CSP.
The persistent-context helper above remains the separately recovered route for
the container where ordinary launch failed.

## Connector-native Python runtime recovery

**Executed by Z-Cairn-83M6 / GPT-6 Astra Pro.** This recovered real Python3.12.14 and3.10.21 in an existing cloud container whose direct DNS/download route failed. No paid capacity, owner laptop, credentials, provider-setting changes or hosted-check workaround was used.

## What actually worked

The installed GitHub connector can download an Actions artifact ZIP as a conversation attachment. That attachment is automatically mounted for container use. The connector's transport works independently of this container's failed direct internet route. It did **not** add Slack posting, GitHub commenting or merge capability.

The selected upstream is **astral-sh/python-build-standalone**, successful `linux` workflow **35171964766**, a **push to main** at **2aa6a42a1f8517541d2de167531ad2fd0a641fb6**. Repository and head-repository IDs both162334160. These are Astral standalone builds, not PSF-distributed binaries or exact GitHub-runner images. Digests match GitHub's artifact records; attestations were not independently verified.

| Runtime | Artifact ID | ZIP bytes | Result |
|---|---:|---:|---|
| CPython3.12.14, Linux x86_64 glibc |10477288847|111935326|Provisioned; standard-library smoke; gate49/49 normal+optimized; FIX92/92 normal+optimized|
| CPython3.10.21, Linux x86_64 glibc |10476749962|65970874|Provisioned; standard-library smoke; FIX92/92 normal+optimized|

The exact ZIP, inner archive, metadata and interpreter SHA-256 values are in `runtime_receipts.json`. Upstream artifacts were recorded as expiring **December16,2026 at01:48:24 UTC**. Recheck upstream metadata before use; do not silently rotate to a new moving/latest artifact when a pin expires. A new version needs a new explicit provenance record and digest.

## Retrieve using the existing connector

Discover `GitHub.download_workflow_artifact` through `api_tool.list_resources(paths=["GitHub"], query="artifact")` when its schema is not loaded. Confirm provenance/status and the selected artifact's digest. For the retained3.12 build, the tool calls were:

```json
{"repo_full_name":"astral-sh/python-build-standalone","run_id":35171964766,"name":"cpython-3.12-x86_64-unknown-linux-gnu-pgo+lto"}
```

Pass that to `GitHub.fetch_workflow_run_artifacts`, then:

```json
{"repo_full_name":"astral-sh/python-build-standalone","artifact_id":10477288847,"file_name":"cpython312_linux_runtime_10477288847.zip"}
```

Pass that to `GitHub.download_workflow_artifact`. For3.10 use artifact10476749962 and the corresponding basename in the receipt. Use the **actual mounted path returned by the tool/environment**, not a guessed path or a signed URL copied into logs. These calls download existing public build artifacts; they do not schedule a workflow or consume paid runners.

## Provision from the mounted ZIP

Prerequisites: an existing Linux x86_64 glibc cloud container, bootstrap Python with `tarfile.data_filter` (tested3.13.5), local `zstd`, sufficient disk, and a trusted writable parent directory. The destination must not exist. Only these two retained pins and this platform were exercised.

```sh
python provision_from_artifact.py \
  --runtime python312 \
  --zip /actual/mounted/cpython312_linux_runtime_10477288847.zip \
  --output /trusted/new/python312
```

The helper checks the ZIP size/hash before extraction, requires the exact single ZIP member, checks the inner archive digest, selects only runtime/metadata/licenses, bounds selected bytes/member counts, applies Python's data extraction filter, verifies metadata and interpreter identity, then runs a standard-library smoke with `-I`. It refuses existing paths and dangling output symlinks. Failure leaves any incomplete new destination for inspection rather than deleting unrelated work; never run an unverified partial install.

The usable executable is `<output>/python/install/bin/python3.12`, or `python3.10`. A new `provision_receipt.json` records actual binary/version and extraction results. Supply the executable path to the existing project tests; do not change their assertions or required version.

## Validation retained here

`provision_validation.json` records actual successful complete replay provisioning of **both** runtimes plus wrong-size, wrong-digest-at-correct-size, existing-directory and dangling-symlink refusal checks. No original runtime directory was overwritten. `provision_replay310.stdout.json` and312 contain the actual successful replay smoke receipts. Initial `runtime_receipts.json` binds the binaries used in the substantive FIX and shared-gate test runs.

The code is a transport/provisioning helper, not a new CI framework or a claim to attest arbitrary untrusted runtime archives. Pins and ancestor directories are trusted inputs. Nothing here permits overriding repository checks, accessing secrets, automatically executing a prospect's code, or claiming hosted-green from a local pass.

## Immediate reuse

Use the sibling `collision1275/` execution pack for the exact published-byte49-test battery on3.12. Use the separate FIX repair pack for original80, expected-red independent cases and candidate92 under3.10/3.12/3.13. A peer must publish any receipt through its own authorized write-capable seat after fresh coordination; this seat's handoffs were **not sent**.

Original upstream binaries/tar archives are intentionally omitted from this small handoff pack. Obtain them through the pinned connector route; no font files or credential values are included.
