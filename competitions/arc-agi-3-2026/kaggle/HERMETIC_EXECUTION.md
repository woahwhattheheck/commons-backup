# ARC3 SAGE hermetic offline execution gate

This is an additive successor to the existing `kaggle/package.py`, `profile.py`, and `readiness.py` carrier. It does **not** replace those tools. The packager answers “which source bytes should go into an offline notebook bundle?”; this gate answers “can those exact bytes execute without undeclared packages, inherited credentials, network/process escape, or ambiguous per-run resource evidence?”

## External rule boundary

The ARC Prize 2026 ARC-AGI-3 Kaggle overview currently states that competition submissions must run through Notebooks, CPU and GPU notebook runtime is limited to **9 hours**, and internet access must be disabled. Revalidate the controlling competition page before using the `32400`-second default in a release decision. The public competition page inspected for this change did not provide a memory ceiling, so this code does not invent one.

A `HERMETIC_RUNTIME_CONFORMANT` receipt is **not** a Kaggle-submission, score, rank, prize, or platform-readiness claim. The existing `readiness.py` may still block account-side readiness when the platform memory limit is unknown. Every execution receipt carries explicit false authority for Kaggle submission, leaderboard claims, and prize claims.

Official source inspected 2026-09-13: `https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3/overview`.

## What it proves

`hermetic.py` consumes the existing packager layout:

```text
bundle/
  source_manifest.json
  src/
    ... manifest-bound Python source ...
```

Before execution it:

1. verifies the source manifest self-hash and requires the earlier offline/secret findings to be clean;
2. opens every manifest source as a regular non-symlink file and verifies exact bytes + SHA-256;
3. requires the `src/` inventory to equal the manifest inventory, so extra `.py`, `.so`, `.pth`, or other files cannot silently alter imports;
4. parses every verified Python file and classifies imports as local, Python standard library, or undeclared third-party;
5. rejects dynamic import capability and `ctypes`, which could bypass the Python audit-hook boundary;
6. launches a fresh `python -I -S` interpreter, so user and global site-packages are not dependency fallbacks;
7. supplies a minimal environment rather than inheriting tokens, proxy settings, `PYTHONPATH`, `HOME`, or cloud credentials;
8. installs an audit hook before the entrypoint and denies socket creation/connect/bind/name resolution plus subprocess, spawn, exec, and fork escape events;
9. captures stdout/stderr through bounded drains, terminates the process group on timeout/output overflow, and never invokes a shell;
10. samples Linux `/proc` process-tree RSS per execution rather than reusing cumulative `RUSAGE_CHILDREN.ru_maxrss` from earlier children;
11. re-verifies source bytes after execution to detect mutation; and
12. emits a hash-bound receipt whose execution identity covers claim-critical state while wall/RSS remain explicitly measured evidence.

On non-Linux hosts, RSS authority becomes unavailable instead of being guessed. If a real memory ceiling is later supplied to `ExecutionPolicy`, unavailable or over-margin memory evidence blocks the receipt.

## Operator path

Build the bundle with the already-landed packager, then close dependencies:

```bash
cd competitions/arc-agi-3-2026
python -m kaggle.hermetic_cli closure /tmp/sage-bundle > /tmp/closure.json
```

Run the packaged benchmark with a local smoke timeout. The competition runtime field remains a distinct policy ceiling; do not substitute a short smoke timeout for the full provider-runtime claim:

```bash
python -m kaggle.hermetic_cli run /tmp/sage-bundle \
  --entrypoint benchmark.py \
  --timeout 300 \
  --competition-runtime 32400 \
  --margin 0.80 > /tmp/hermetic-receipt.json
```

If and only if a controlling platform source provides a current memory ceiling, add for example `--memory-mib <actual-limit>`. Do not infer a limit from local RAM.

Verify a stored receipt without rerunning the workload:

```bash
python -m kaggle.hermetic_cli verify /tmp/hermetic-receipt.json
```

Exit code `0` means the selected local hermetic contract passed. Exit code `2` means blocked. Neither code authorizes account-side Kaggle actions.

## Receipt semantics

The deterministic `execution_identity_sha256` binds:

- manifest SHA-256;
- dependency-closure SHA-256;
- entrypoint and policy;
- return code and timeout/output-limit state;
- full output byte counts and output digests (captured output is bounded; overflow itself blocks);
- source-unchanged result;
- blocker set and conformance state.

Wall time and peak RSS are retained as measured evidence rather than hidden inside a supposedly reproducible hash. `verify_receipt()` rejects authority escalation, malformed state, state/blocker inconsistency, and identity tampering.

## Threat-boundary limits

This is an offline execution guard for the dependency-free Python carrier, not an OS container or a malicious-code sandbox. It deliberately rejects `ctypes` and dynamic imports rather than claiming to safely host arbitrary native code. Kaggle/provider isolation, competition-account state, hardware quotas, hidden games, and scoring remain external authority.
