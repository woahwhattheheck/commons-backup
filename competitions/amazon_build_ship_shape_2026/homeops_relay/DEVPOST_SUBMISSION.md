# HomeOps Relay — submission / demo packet

This is a **ready-to-fill** packet. It is not proof that the project has been joined to Devpost or submitted.

## One-line pitch

**HomeOps Relay gives Alexa+ an evidence-aware household maintenance memory: it captures what happened, compares repair options without laundering vendor claims into truth, and turns next steps into tamper-evident owner-gated action proposals.**

## Why it is not a basic MCP wrapper

A household problem evolves across hours or days: symptoms change, quotes arrive from different providers, and the high-risk step is often not answering a question but deciding what may happen next. HomeOps Relay provides an explicit state machine and cryptographic replay receipt instead of treating every voice turn as isolated chat context.

Core product properties:

- state persists semantically across tool calls;
- evidence, provider claims, and owner decisions are separate data classes;
- money is integer minor units, never float authority;
- quote ordering is deterministic but does not auto-select a provider;
- safety-first diagnostic plans are bounded and reviewable;
- vendor contact / scheduling / purchasing / warranty work is *proposed*, never silently executed;
- every mutation extends a replay-verifiable SHA-256 event chain.

## Suggested <3 minute demo

**0:00–0:20 — problem**  
“Alexa, there is water collecting under the kitchen sink when I run the faucet.” Show `homeops.intake_issue` creating an evidence-linked case.

**0:20–0:50 — memory + reasoning**  
Add one photo reference and two synthetic provider quotes. Ask for the plan. Show that water-specific safety/documentation steps are present and that both quotes remain marked caller-supplied/unverified.

**0:50–1:25 — agentic workflow without unsafe autonomy**  
Ask: “Contact the lower quote and get the earliest diagnostic slot.” Show `homeops.request_action` returning `PENDING_OWNER_REVIEW`, not sending anything. Explain that approval is a separate recorded event and still does not equal execution.

**1:25–1:55 — evidence receipt**  
Show `homeops.snapshot` and the current event receipt. Mutate one exported event in a terminal copy and run verification; show the hash mismatch.

**1:55–2:25 — Alexa+/MCP implementation**  
Show initialize negotiating `2025-11-25`, `tools/list`, and a live `POST /mcp` request. Mention Streamable HTTP and Origin validation.

**2:25–2:50 — impact**  
Explain the broader product: maintenance histories that survive across turns, compare options without losing provenance, and keep a human in control of expensive or safety-relevant actions.

**2:50–3:00 — close**  
“HomeOps Relay gives an ambient agent memory, provenance, and brakes — the three things a real household workflow needs after the first answer.”

## Final submission checklist

- [ ] Re-read current official rules and deadline.
- [ ] Devpost account has joined the correct hackathon under the intended entrant identity.
- [ ] Eligibility / team facts are truthful and complete.
- [ ] Deploy MCP endpoint publicly over HTTPS.
- [ ] Validate a real MCP client against the deployed endpoint and retain non-secret runtime evidence.
- [ ] If representing actual Alexa+ runtime, capture truthful live integration evidence; otherwise use only the rules-permitted simulation path and label it clearly.
- [ ] Public repository URL points to the exact submitted source and Apache-2.0 is visible at repo top level.
- [ ] Public English YouTube/Vimeo demo is <3 minutes.
- [ ] Description accurately distinguishes synthetic fixtures from live integration.
- [ ] Pre-existing/third-party assets, if any are later incorporated, are disclosed and license-compatible.
- [ ] Product feedback / friction log included if requested by the submission form.
- [ ] Submit exactly once, preserve provider receipt, and do not claim award/payment before organizer evidence.
