# Remove transient synchronization duplicates from generated Wear JARs

Use `remove_rsync_jar_duplicates.py` when D8 reports a duplicate class and one
archive entry includes a `.rsync-tmp` path component. The utility accepts named
generated JARs as positional arguments. It removes a temporary entry only when
its canonical counterpart exists and has identical bytes. An unmatched or
different entry stops that archive's repair before replacement. Retained entry
bytes are checked before the corrected archive replaces the original atomically.
Archive comments, retained entry timestamps and compression methods, entry order,
and file mode are preserved.

The companion `wear_rsync_jar_cleanup.init.gradle` targets only these producers:

- `:play-services-base:bundleLibRuntimeToJarDebug`
- `:play-services-base:bundleLibCompileToJarDebug`

It runs the sanitizer in `doLast`, after each producer finishes writing its
generated `classes.jar`. Pre-clean existing affected archives once before
launching Gradle, since `doLast` does not run for an up-to-date task. Keep
`--no-build-cache` to avoid restoring an archive without running the hook, and
`--no-configuration-cache` for this execution-time init script.

## Runnable Wear source and combined command

For [microg/GmsCore#2843](https://github.com/microg/GmsCore/issues/2843), the
executable combined source is in `woahwhattheheck/GmsCore` on
[`bounty/wear2843-cloud-source-20261004-998e`](https://github.com/woahwhattheheck/GmsCore/tree/bounty/wear2843-cloud-source-20261004-998e).
The `bounty/wear2843-validation-source-20261003` branch carries patch packets
and handoff files; use the combined source branch for the runnable feature tree.

The completed run with **81 core tests + 3 API tests passing**, instrumentation
Java compilation, and an assembled APK belongs to immutable source
[`73793ddc4e084017a7098aade07703c40ab825bd`](https://github.com/woahwhattheheck/GmsCore/commit/73793ddc4e084017a7098aade07703c40ab825bd),
tree `8a3f7d563ff882ec1f57e04cbde3ae044f0ee308`. Pin that commit when reproducing
that result. The branch continues to move. Its successful successor after fork
PR #6 was source
[`360d6a9942e1e038fa7d3d4261c2d4651d17d02f`](https://github.com/woahwhattheheck/GmsCore/commit/360d6a9942e1e038fa7d3d4261c2d4651d17d02f),
tree `4d33a513c609a691bde089c794d4021bd82e13e7`. That warm run completed in
3m 59s: all 81 core tests reran and passed; the 3 API test results and
instrumentation Java compilation were reused as up to date; APK assembly
succeeded. Use your isolated cloud checkout of the chosen source and record
its commit/tree before each run.

Retain the existing Java, Android SDK and Gradle environment. Set these checkout
paths and run from a POSIX shell with Python 3.9 or newer:

```sh
set -e
export GRADLE_MICROG_VERSION_WITHOUT_GIT=1
COMMONS_ROOT=/abs/commons
GMSCORE_ROOT=/abs/GmsCore
JAR_SANITIZER="$COMMONS_ROOT/host/remove_rsync_jar_duplicates.py"

git -C "$GMSCORE_ROOT" rev-parse HEAD 'HEAD^{tree}'

python3 "$JAR_SANITIZER" \
  "$GMSCORE_ROOT/play-services-base/build/intermediates/runtime_library_classes_jar/debug/bundleLibRuntimeToJarDebug/classes.jar" \
  "$GMSCORE_ROOT/play-services-base/build/intermediates/compile_library_classes_jar/debug/bundleLibCompileToJarDebug/classes.jar"

python3 "$COMMONS_ROOT/host/gradle_env_proxy.py" \
  --project "$GMSCORE_ROOT" --forked-jvms --refresh-env-proxy -- \
  --no-daemon --no-build-cache --no-configuration-cache --max-workers=1 \
  '-Dorg.gradle.jvmargs=-Xmx1536m -XX:+UseSerialGC --add-exports=jdk.compiler/com.sun.tools.javac.main=ALL-UNNAMED' \
  -Pkotlin.compiler.execution.strategy=in-process \
  "-Dcommons.rsyncJarSanitizer=$JAR_SANITIZER" \
  --init-script "$COMMONS_ROOT/host/wear_rsync_jar_cleanup.init.gradle" \
  :play-services-wearable-core:testDebugUnitTest \
  :play-services-wearable:testDebugUnitTest \
  :play-services-wearable-core:compileDebugAndroidTestJavaWithJavac \
  :play-services-core:assembleVtmDefaultDebug
```

The pre-clean command assumes both named archives already exist, as in the
observed incremental-build failure. On a fresh build, omit that command and
retain the init script. Supply the sanitizer's absolute path through
`commons.rsyncJarSanitizer`; Python runs as a child of the selected Gradle task
and a repair failure fails that task. An archive with no temporary entries is
left unchanged. Each archive is handled separately; a later failure does not
undo successful repairs of earlier arguments.

This repairs generated build artifacts without changing project source or
clearing caches. The hook was exercised with AGP 8.13.2 and Gradle 8.13; its two
task names and `output` property describe that observed Wear build. For another
producer, inspect its actual output contract before adapting the selection.
For proxy or forked-test-JVM configuration, see [Gradle through an existing
cloud proxy](GRADLE_ENV_PROXY.md).
