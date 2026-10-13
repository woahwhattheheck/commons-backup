# CALL-E competition submission packet — RouteScout

Operation: `CALL-E-ROUTESCOUT-ZCKM6V2-20260913`

## Product sentence

RouteScout makes one approval-gated CALL-E call to a published procurement/vendor-support business line, asks only for the permitted official route for an already-identified process inquiry, and returns a fail-closed routing receipt without pitching, negotiating, or bypassing procurement.

## Judging angle

**Most Practical:** many legitimate business/procurement inquiries die in generic inboxes or unclear vendor-support routes. RouteScout uses the phone only for channel discovery and hands control back to the human/system after the route is proven.

**Safety/governance:** one recipient, exact-byte approval, deterministic idempotency, first-party-source requirement, no marketing/leadgen, no private-contact harvesting, explicit DNC state, no automatic retry, and zero authority to send the follow-up.

## Software status

- [x] deterministic offline preview
- [x] strict input schema / duplicate-key rejection
- [x] marketing and lead-generation purpose rejection
- [x] exact inquiry SHA + approval token + idempotency key
- [x] CALL-E Developer API request using official origin only
- [x] one-recipient live request
- [x] GET-only resume path
- [x] fail-closed terminal-result reconciliation
- [x] deterministic demo fixtures
- [x] focused local test suite
- [x] upstream-ready `skills/routescout/` tree
- [ ] real CALL-E account email retained by operator
- [ ] real `CALLE_API_KEY` available at runtime
- [ ] at least one authorized real CALL-E call completed and retained
- [ ] public demo video under 3 minutes
- [ ] upstream PR URL to `CALLE-AI/awesome-phone-call-agents`
- [ ] Devpost submission created and final fields entered

Unchecked external items are **HOLD**, not implied by source code.

## Suggested real demo

Use a business number you are explicitly authorized to call or a consenting test organization. Do not use the fictional `+1 555...` fixture for a real call.

1. Show `sample_inquiry.json` replaced with an authorized published business number and first-party source URL.
2. Run `preview`; point out the masked number, one-call side effect, approval token, and fixed authority ceiling.
3. Run the exact approved inquiry live with CALL-E.
4. Show CALL-E terminal status and evidence.
5. Run `reconcile`; show `ROUTE_FOUND`, `NO_ROUTE`, `DO_NOT_CONTACT`, or `HUMAN_REQUIRED`.
6. Show that editing one byte of the inquiry invalidates the confirmation token.
7. Close with the key distinction: RouteScout discovers the permitted route; it does not send the pitch or bypass the process.

## Sub-three-minute narration

**0:00–0:25** — “Procurement and vendor-process inquiries often get stuck because the official routing path is unclear. RouteScout calls one published organizational number to discover the permitted business channel — and nothing more.”

**0:25–0:55** — Show the input and preview. “The operator must approve exact bytes. Change the organization, phone, source, inquiry type, or purpose and the token changes. Marketing and lead-generation categories are rejected.”

**0:55–1:45** — Run one real CALL-E call. “The AI discloses itself, confirms the organization, asks one routing question, and is forbidden to pitch, negotiate, collect private contact details, or bypass procurement.”

**1:45–2:25** — Show terminal result and reconcile. “A completed call is not route proof. RouteScout needs consent, an explicit routing answer, a business channel, permission, and a verbatim route. DNC dominates everything.”

**2:25–2:50** — Show resume/idempotency and authority ceiling. “If the network fails after dispatch, the same inquiry keeps the same idempotency key; the resume command only polls. The receipt cannot send follow-up, claim acceptance, or claim revenue.”

**2:50–3:00** — “RouteScout turns one frustrating phone tree into a safe, structured next step.”

## External facts to paste only after verification

- CALL-E account email: `HOLD`
- Real call id: `HOLD`
- Upstream PR: `HOLD`
- Demo video: `HOLD`
- Devpost URL: `HOLD`
