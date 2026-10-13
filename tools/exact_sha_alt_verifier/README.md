# Exact-SHA Alternate Verifier

Build demand: `EXACT-SHA-ALT-VERIFIER-NOSPEND-20260913`.

This is a **non-hosted evidence tool**, not a CI replacement. It fetches one exact commit into a fresh temporary Git checkout, detaches HEAD, requires a clean tree before and after the supplied commands, and writes a tamper-evident receipt.

The receipt always says:

- `verification_kind = "alternate_nonhosted"`
- `hosted_ci_green = false`
- `overrides_required_checks = false`
- `merge_authority = false`
- `credentials_inherited = false`
- `network_sandbox_claimed = false`

Use it only where project policy accepts equivalent/offline verification, or to diagnose work stuck behind unavailable hosted runners. It must not be used to bypass branch protection or a PR contract that explicitly requires hosted checks.

## Spec

```json
{
  "repo": "https://github.com/OWNER/REPO.git",
  "exact_sha": "0123456789abcdef0123456789abcdef01234567",
  "commands": [
    ["python3", "-m", "unittest", "-v", "test_module.py"],
    ["python3", "-m", "py_compile", "module.py"]
  ],
  "artifacts": ["reports/*.json"],
  "timeout_seconds": 900,
  "log_preview_bytes": 4096
}
```

Each command is an argv array. No shell is invoked. Network repository URLs are limited to `https`, `http`, and `file` transports; credential-bearing and scp-style URLs are rejected. The verifier also rejects obvious provider/network publication commands. It also launches commands with a small environment that does not inherit GitHub, cloud, package-registry, wallet, or other credential variables. This is **not an OS network sandbox**; supplied project commands must themselves be appropriate for offline/read-only verification.

## Run

```bash
python3 exact_sha_alt_verifier.py run spec.json --receipt receipt.json
python3 exact_sha_alt_verifier.py verify-receipt receipt.json
```

Exit codes for `run`: 0 passed, 1 verification failed, 2 invalid spec. `verify-receipt` returns 0 only when the canonical receipt hash matches.

Logs are streamed to temporary files so they are not accumulated in process memory. Receipts retain SHA-256 + byte count and only the configured bounded preview bytes. Artifact globs are relative, may not traverse parents, skip symlinks, are capped at 1000 files, and hash regular files by streaming.

Git cleanliness uses `git status --porcelain=v1 --untracked-files=all`; ignored build artifacts may therefore be hashed without invalidating the checkout, while tracked and ordinary untracked mutations fail closed.

## Tests

```bash
python3 -B -m unittest -v test_exact_sha_alt_verifier.py
python3 -m py_compile exact_sha_alt_verifier.py test_exact_sha_alt_verifier.py
```

The suite covers pre/post dirty-tree rejection, pre/post exact-head binding, detached checkout, command failure/exit/log propagation, bounded log previews with full-stream hashes, ignored artifact hashing, CLI receipt replay/tamper rejection, and provider-mutation/unsafe-repository guards.
