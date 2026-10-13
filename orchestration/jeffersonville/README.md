# Jeffersonville orchestration catalog

Status: **NOT_DEPLOYED**

This directory is a reference-only adapter and benchmark catalog. It records repository provenance, observed primitives, limitations, and possible compatibility roles. It is not a data-center design or runtime deployment and carries no Rust/Go rewrite intent.

## Open-door contract

The catalog has no auth, identity, permission, approval, allowlist, or admission gate. Descriptors explain compatibility; they do not accept or reject participants. Unknown capability fields remain valid and should be retained and described.

This openness does not turn catalog metadata into execution authority. Nothing here acquires dependencies, runs candidate code, changes an external system, or claims a deployment.

## Artifacts

- [`frameworks.json`](frameworks.json) is the evidence catalog, pinned to verified repository revisions.
- [`adapter.schema.json`](adapter.schema.json) is a permissive, descriptive compatibility schema. Its capability object accepts unknown fields.
- [`topology.json`](topology.json) groups candidates into reference-only adapter and benchmark tiers.
- [`probe.py`](probe.py) reads the adjacent JSON files and emits deterministic plans to standard output. It performs no candidate acquisition, installation, execution, or deployment.

Run the local plan emitter from the repository root:

```sh
python orchestration/jeffersonville/probe.py
```

## Evidence verdicts

| Candidate | Revision | License | Catalog verdict | Status |
|---|---:|---|---|---|
| [nbursa/inception-core](https://github.com/nbursa/inception-core) | `e8f4b13` | MIT | `REFERENCE_ONLY` | NOT_DEPLOYED |
| [NickSpyker/multi-agent-engine](https://github.com/NickSpyker/multi-agent-engine) | `ed540b8` | MIT OR Apache-2.0 | `BENCHMARK_SCAFFOLD_ONLY` | NOT_DEPLOYED |
| [liquidos-ai/AutoAgents](https://github.com/liquidos-ai/AutoAgents) | `6301004` | MIT OR Apache-2.0 | `PILOT_CANDIDATE_AFTER_PATCH` | NOT_DEPLOYED |
| [The-Swarm-Corporation/swarms-rs](https://github.com/The-Swarm-Corporation/swarms-rs) | `9d22ba9` | Apache-2.0 | `HOLD` | NOT_DEPLOYED |
| [InfinitiBit/graphbit](https://github.com/InfinitiBit/graphbit) | `f80c46e` | Apache-2.0 | `BENCHMARK_CANDIDATE` | NOT_DEPLOYED |
| [sayiir/sayiir](https://github.com/sayiir/sayiir) | `7d60cee` | MIT | `DURABILITY_ADAPTER_CANDIDATE` | NOT_DEPLOYED |
| [microsoft/agent-framework-go](https://github.com/microsoft/agent-framework-go) | `8c8544a` | MIT | `CONTROL_PLANE_ADAPTER_CANDIDATE` | NOT_DEPLOYED |
| [agenticdevops/aof](https://github.com/agenticdevops/aof) | `bf15701` | Apache-2.0 | `SCHEMA_AND_MCP_PATTERN_ONLY` | NOT_DEPLOYED |
| [tmetsch/rusty_agent](https://github.com/tmetsch/rusty_agent) | `f07e7df` | MIT | `ARCHIVE_REFERENCE_ONLY` | NOT_DEPLOYED |

Detailed positive and negative findings are in `frameworks.json`; this summary intentionally makes no performance, capacity, infrastructure, or economic claim.

## Attribution corrections

1. The Raft, BLAKE3, WebAssembly, capability-safe execution, and verifiable audit/replay claim family was not found in `nbursa/inception-core`. It aligns with [`scalarian/cathedral.fabric`](https://github.com/scalarian/cathedral.fabric) at `a98b290`, retained separately as `UNVERIFIED_LAB` and **NOT_DEPLOYED**.
2. The NoOps DSL, multi-language generation, NATS, and Kubernetes-generation claim family was not found in `agenticdevops/aof`. It aligns with [`raestrada/kumeo`](https://github.com/raestrada/kumeo) at `1b90d5d`, retained separately as `UNVERIFIED_REFERENCE` and **NOT_DEPLOYED**.

These are provenance corrections, not endorsements. Both candidates stay in the unverified reference tier.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

