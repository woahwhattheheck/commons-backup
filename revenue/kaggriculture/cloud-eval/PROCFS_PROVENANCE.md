# Procfs sampling diagnostics

`Actor.report()` includes the additive scalar `procfs_sample_status`. Existing resource values, `resource_sample`, `final_resource_sample`, worker actions, deadlines and cleanup retain their prior behavior. `play()` and the CLI serialize this field through their existing actor-report path.

| Status | Meaning |
| --- | --- |
| `not_attempted` | Teardown has not recorded a procfs sampling outcome. |
| `not_applicable:non_linux` | The evaluator took its existing non-Linux branch without reading procfs. |
| `skipped:pid_view_mismatch` | The existing self-PID compatibility check detected different PID views. No numeric child procfs path was read. |
| `error:self_stat:<type>` | Reading or parsing `/proc/self/stat` failed. |
| `error:child_status:<type>` | Reading child status or parsing its RSS field failed. |
| `error:child_stat:<type>` | Reading or parsing child CPU statistics failed. An earlier RSS sample may already have contributed. |
| `sampled` | The existing procfs CPU sampling path completed. RSS is sampled only when the status contains `VmHWM`. |

`<type>` is the exception class name, not its message or a filesystem path. This diagnostic does not assert that sampled values exceeded existing maxima. An error does not erase a resource contribution made before the error. Final `wait4` usage may still update CPU/RSS after a procfs failure. Read the existing `final_resource_sample` field separately.

The PID check is the compatibility check introduced by RENEW in PR10479, not a universal proof of namespace identity. This change records its disposition without changing the check. Existing saved reports and historical resource measurements are not rewritten; absence of the new field means the report did not record this diagnostic.

Focused coverage: `python3 -B test_procfs_provenance.py` from this directory. It uses real worker processes with controlled procfs inputs and the real report writer, not official games. The non-Linux test selects that branch on Linux and is not native non-Linux validation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
