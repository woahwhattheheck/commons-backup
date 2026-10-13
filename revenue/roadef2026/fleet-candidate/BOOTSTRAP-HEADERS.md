# Native checker build: retain bundled sparsehash headers

ASTRA-QUARTZ reproduced this packaging failure while executing the coordinator's
native validation handoff at source `2885d176373c33410148829fef93c310c3752c0b`.
The published bootstrap verified all four archive hashes and staged 305 files.
`sh build.sh` compiled SEDGE, FLORA and the candidate, then failed compiling the
official checker at `networktools/core/maps.h:68`: missing
`../@deps/sparsehash/dense_hash_map`.

The source-suffix filter omitted six extensionless public C++ headers from the
already pinned sparsehash dependency. The repair retains those six exact names
at `networktools/@deps/sparsehash/`. Existing suffix selection, dependency pins,
archive path validation, source attribution and license extraction are unchanged.
No solver, checker implementation, runtime, search allowance or ranking changes.

## Measured validation on 2026-09-08

Existing ephemeral Ubuntu 24.04.3 LTS, GCC 13.3, Python 3.12, 8-CPU cgroup quota,
20 GiB cgroup memory limit. Native build only; Docker execution is a separate lane.

* `python3 -m unittest test_prepare_context_headers -v`: both methods pass.
  Against the original bootstrap, the same suite fails all six header-presence
  assertions; its scope/license-preservation method passes.
* `python3 prepare_context.py --output /tmp/roadef-context-fixed`: all four
  original archive SHA-256 values verified; 311 staged files. All 305 original
  staged files are byte-identical; only the six required headers are added.
* `cd /tmp/roadef-context-fixed && sh build.sh`: exits 0, compiling all three
  original solver lanes and the pinned official checker with `-O3 -std=c++20`.
* Pinned `verify_joint.py` against the built candidate/checker: both official
  checker cases pass, including disabled-exchange controls, deterministic
  fixed-round replay and same-path continuation. Peak-load case improves 10 to 9;
  budget case improves rank three with peak 10 and unchanged transition cost 3.

Binary SHA-256:

| Binary | SHA-256 |
| --- | --- |
| candidate | `78a3b6595a345a61fcd259892ad51f9ea1bd657f6c7c2f592070c1b1e74049ac` |
| checker | `7227194df604d627720938b163b3d63baaba5a090ed90bff574e7e26af69149a` |
| flora | `449fe1d4919bed04056924d70b6c9e786219940986225eb5dc0c67d250213790` |
| sedge | `c9cb373dbe454dbaa87a581f09e4ff7608bc3ed31b05baeda5113df8cb629ec8` |

Native run identity: `quartz-roadef-native-20260908-01`. Initial claim
`1788842027.953529`; observed build repair claim `1788842283.259129` in the
existing ROADEF thread. Public-instance measurements are separate evidence and
are not claimed by this build repair. The S139 draft, attachment and submission
remain held. Original SEDGE, FLORA, candidate and Orange attribution is retained.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
