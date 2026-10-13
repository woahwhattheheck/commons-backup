# HomeOps Relay — Alexa+ MCP for the Amazon Build, Ship, Shape Hackathon

HomeOps Relay turns a spoken household problem into an evidence-linked maintenance case, deterministic diagnostic plan, quote comparison, and **owner-gated** action proposal. It is designed for the Alexa+ track as a self-hosted Model Context Protocol server using **MCP protocol version `2025-11-25` over Streamable HTTP**.

The differentiator is not another single-turn home-maintenance chatbot. HomeOps Relay maintains a tamper-evident state chain across sessions/workflows and separates three things agents often blur together: *what the household observed*, *what a provider claimed*, and *what an owner actually authorized*. Contacting a provider, scheduling, purchasing, warranty filing, payment, or any other real-world side effect is permanently outside this demo server; the MCP surface can create and review proposals, not execute them.

## Competition fit

Captured from the current Amazon/Devpost first-party pages on 2026-09-17:

- Submission deadline: **2026-10-23 12:00 PM Pacific**.
- Alexa+ accepts a working Agent Skill or a **self-hosted MCP server implementing spec `2025-11-25` or later over Streamable HTTP**.
- Public source, working demo, and a public English demo video under three minutes are required at submission.
- Alexa+ track cash prizes are **$25,000 / $15,000 / $4,000**; a qualifying primary-track project can also compete for the **$5,000 Open Source** mini challenge.
- Judging emphasizes technical implementation, design, potential impact, and quality of the idea.

Authoritative sources are pinned in [`RULES_SNAPSHOT.md`](RULES_SNAPSHOT.md). Nothing in this repository is a registration, submission, eligibility, award, or payment claim.

## Architecture

```text
Alexa+ / MCP client
       |
       | JSON-RPC 2.0 over POST /mcp
       v
+----------------------+      +--------------------------+
| Streamable HTTP MCP  | ---> | HomeOps deterministic    |
| protocol 2025-11-25  |      | event / receipt ledger   |
+----------------------+      +--------------------------+
                                        |
             +--------------------------+--------------------------+
             |                          |                          |
        issue intake               quote intake              plan + action
      observations only       caller-supplied/unverified      proposals only
                                                                   |
                                                        PENDING_OWNER_REVIEW
                                                                   |
                                                        APPROVED_NOT_EXECUTED
```

The hash chain is replayable: each event binds its sequence, semantic kind, exact payload, and predecessor receipt. `HomeOpsLedger.verify_events()` reconstructs the state and fails on mutation, reordering, unknown semantics, duplicate IDs, non-integer money, or invalid transitions.

## MCP tools

| Tool | Purpose | External effect |
| --- | --- | --- |
| `homeops.intake_issue` | Capture issue, severity, area, detail, evidence refs | none |
| `homeops.record_quote` | Record caller-supplied provider quote in integer minor units | none |
| `homeops.propose_plan` | Create deterministic diagnostic + quote comparison plan | none |
| `homeops.request_action` | Create provider/schedule/purchase/warranty proposal | none |
| `homeops.record_owner_decision` | Record approval/rejection evidence | **still none** |
| `homeops.snapshot` | Return state + tamper-evident receipt | none |

## Run locally

Requires Python 3.10+ and the standard library only.

```bash
cd competitions/amazon_build_ship_shape_2026/homeops_relay
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python -m homeops_relay.demo
python -m homeops_relay.mcp_server
```

The server binds `127.0.0.1:8000` by default. Its MCP endpoint is `http://127.0.0.1:8000/mcp`; health is `/healthz`. It implements the `2025-11-25` handshake lifecycle: successful `initialize` returns a cryptographically random `MCP-Session-Id`; the client sends `notifications/initialized`; subsequent calls require both that session ID and `MCP-Protocol-Version: 2025-11-25`. POST transport requests must advertise both `application/json` and `text/event-stream` in `Accept`, as required by Streamable HTTP. This implementation chooses JSON responses and intentionally returns 405 to the optional GET/SSE listener.

For an intentional remote deployment, set `HOMEOPS_HOST=0.0.0.0` together with `HOMEOPS_ALLOW_REMOTE_BIND=1`, terminate TLS/authentication in a trusted production reverse proxy, and explicitly set `HOMEOPS_ALLOWED_ORIGINS` for browser origins. The handler rejects non-local `Origin` headers by default, caps request bodies, rejects duplicate JSON keys/non-finite numbers, rate-limits tool calls per session, and serializes append-only ledger mutation across concurrent HTTP workers.

## Demo story

`python -m homeops_relay.demo` runs an entirely synthetic kitchen-leak flow:

1. record a leak observation and evidence references;
2. record two synthetic quotes;
3. produce an evidence-linked plan;
4. request a provider-contact action without executing it;
5. export a deterministic snapshot and verify the full event chain.

The submission storyboard in [`DEVPOST_SUBMISSION.md`](DEVPOST_SUBMISSION.md) turns the same flow into a voice-first <3 minute demo without inventing Alexa runtime evidence before an actual deployment exists.

## Truth / authority ceiling

- No provider contact, booking, purchase, payment, claim filing, account mutation, or home-system control is implemented.
- A recorded quote is explicitly `CALLER_SUPPLIED_UNVERIFIED`.
- `APPROVE` means `APPROVED_NOT_EXECUTED`; it does not authorize or prove an external side effect.
- MCP transport hardening is part of the product: lifecycle/session checks, protocol-version pinning, Origin validation, request limits, per-session tool-call limiting, and deterministic JSON-only responses.
- No AWS/Alexa/Devpost credential is stored here.
- Final entrant identity, eligibility, Devpost registration, live Alexa+ integration, deployment, video, and submission remain separate owner/account actions.

## License

This project is part of the public `woahwhattheheck/commons` repository, which is licensed under Apache-2.0 at the repository root.
