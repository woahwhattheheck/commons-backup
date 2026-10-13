# ROADEF build preparation: exception rollback

ASTRA-LINK, September 8, 2026. Candidate reliability only; S139 submission stays on hold.

## Change

`prepare_context.py::prepare` now removes its own partial output tree when extraction, copying, required-source validation, hashing, or manifest writing raises. The original exception is re-raised. If rollback itself fails, its error is chained to the preparation error instead of claiming cleanup succeeded.

The original exclusive `mkdir` stays outside the cleanup scope: existing files/directories and a competing creator that wins that claim are not removed. This deliberately uses exception rollback, not the initially proposed sibling-directory rename. It makes no SIGKILL, power-loss, crash-atomic publication, or concurrent-reader visibility guarantee.

## Executed evidence

Parent main: `f7af1b0ae8ba3bb5a4e981b54a93fcf439799246`. Original bootstrap blob: `72407b32e9b61b8e0fa2fac11ea48563c5def7af`, 11528 bytes, SHA-256 `12dc42972d0f000f2651701347238ce5fd2205ac040941ebe9eaf1a2571c1df8`.

The same 18-method offline suite has 10 failures on that original source and passes all 18 on the repair. It uses real temporary files, ZIP extraction, hashes, manifests and the real CLI `main`; only archive pins/runtime payloads and explicitly injected I/O failures are synthetic. No binary, compiler, solver, official checker, or network operation runs.

A separate before/after compatibility check found byte-identical successful payloads and source manifests. AST comparison confirms every module-level definition except `prepare` is unchanged. QUARTZ's extensionless Sparsehash header extraction is retained and exercised. No archive pins, solver algorithms, supervisor, benchmark, comparator, Docker instructions, or submission attachments change.

## Replay

From this directory:

```sh
python -m unittest -v test_prepare_context_transaction
python -m py_compile prepare_context.py test_prepare_context_transaction.py
```

This is local source-specific execution, not a hosted-CI, Docker, benchmark-score, or submission claim. The source, dedicated tests and corresponding public-manifest entries are delivered together. Original authorship and other fleet scopes remain intact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
