# FrontierOR Stage-1 Main-track preflight

Small offline guardrail for the published FrontierOR Main-track submission contract. It is intentionally not a solver, scorer, feasibility checker, or submission client.

Official references checked 2026-10-05:

- https://frontieror-challenge.com/docs/main/submission-flow
- https://frontieror-challenge.com/docs/main/submission-format
- https://frontieror-challenge.com/docs/main/example-code

## What it checks

preflight.py check rejects the structural failures that FrontierOR documents at upload:

- archive over 10 MiB;
- anything other than zip, tar, or tar.gz;
- more than 10,000 archive entries;
- unsafe paths (parent traversal, absolute paths, Windows backslashes);
- symbolic or hard links where the archive format exposes them;
- more than 256 MiB unpacked;
- no problem folder with a direct solve.py or solve;
- a problem folder containing both entry points.

It understands the documented optional single wrapper directory. --expected-slug can be repeated; missing problem solvers are warnings by default because FrontierOR permits acknowledged missing problems to score zero. Add --require-all when preparing an archive intended to cover every named problem.

    python competitions/frontieror-stage1-preflight/preflight.py check submission.zip
    python competitions/frontieror-stage1-preflight/preflight.py check submission.zip \
      --expected-slug barnhart2000 --require-all

## Local resource-envelope probe

The official sandbox runs one instance at a time with 2 vCPU, 4 GB RAM, no swap/network, a 1 GB /work, and currently a 60-second instance limit. The platform invokes the entry point with --problem, --instance, --output, and --time-limit.

probe exercises that public CLI contract and applies best-effort local CPU affinity, 4 GiB address-space, fd/process, and wall-time bounds:

    python competitions/frontieror-stage1-preflight/preflight.py probe submission.zip \
      --slug barnhart2000 \
      --instance ./instance.json \
      --time-limit 60

The probe also checks that the process exits successfully and writes one JSON object with numeric objective_value no larger than 16 MiB.

This is not equivalent to FrontierOR's sandbox: it does not enforce network isolation, a read-only solver directory, the 1 GB /work filesystem budget, solution-schema validity, feasibility, or objective correctness. Use the organizer's uv run frontieror test --docker for the authoritative public-instance environment check.

## Bounded self-test

The self-test covers eight cases: valid single-problem archive, valid wrapper, traversal rejection, dual-entrypoint rejection, missing-solver rejection, entry-count budget, unpacked-size budget, and link rejection.

    python competitions/frontieror-stage1-preflight/preflight.py self-test

Expected result: 8 / 8 with ok = true.

## Why this exists before Stage 1

Stage 1 starts 2026-11-01. The problem set is intentionally hidden until the stage opens, but the archive and sandbox contracts are already public. This lets solver work fail fast on packaging/resource mistakes without making any registration, team, submission, or leaderboard mutation and without embedding solver strategy in public infrastructure.
