# SpoilerShield threat model

| Threat | Control | Test/evidence |
|---|---|---|
| Future subtitle enters prompt | Admit only cues with `endMs <= positionMs` | `core.test.mjs` future-twist and started-but-unfinished checks |
| Packet text changed after gating | Canonical context SHA-256 | JS + Python digest-tamper tests |
| Attacker reseals a packet containing a future cue | Timestamp policy is re-evaluated independently of digest | JS resealed-future + Python resealed-future tests |
| Caller prompt asks model to ignore policy | Backend discards caller `instruction`; server generates its own system instruction | Python hostile instruction test |
| Wrong transcript generation routed to fixed demo backend | Optional `ALLOWED_TRANSCRIPT_SHA256` pin | Python generation-pin test |
| Bedrock/network unavailable | Deterministic local fallback; no policy widening | Client fallback path |
| Model uses outside plot knowledge | Mechanical context minimization + explicit server instruction; if insufficient, abstain | Architecture contract; device demo should include an insufficiency case |
| Duplicate/malformed cue IDs | Strict bounded schema + unique IDs + monotone chronology | JS/Python validation |
| Cached sensitive context | Backend returns `Cache-Control: no-store`; demo contains no PII | Python handler test |

## Non-claims

This code does not prove Fire TV/Vega simulator execution, Appstore acceptance, AWS deployment, hackathon registration/submission, judging score, prize, payment, or revenue. Those states require external evidence.
