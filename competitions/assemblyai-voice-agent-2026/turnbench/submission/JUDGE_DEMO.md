# TurnBench — judge/demo script

1. **Open with the failure:** “Voice agents can regress without crashing. A small endpointing or barge-in change can make a release feel broken even when every service is technically up.”
2. **Show the contract:** open the shipped synthetic scenario and point out latency, semantic-interruption and required-tool-call expectations.
3. **Run the good fixture:** evaluate the known-good synthetic trace and show the content-addressed PASS receipt. Say explicitly: “This proves deterministic evaluator behavior on a synthetic fixture; it is not a live-provider claim.”
4. **Make one controlled failure:** use a shipped hostile/failing fixture or change a synthetic trace so a required tool-call witness/latency contract fails. Re-run and show the stable HOLD/failure reasons.
5. **Show the privacy boundary:** explain that the capture adapter drops credentials, session/resume tokens and raw audio; only contract-relevant trace material remains.
6. **Show the live architecture boundary:** browser → backend temporary-token endpoint → AssemblyAI Voice Agent WebSocket → minimized capture → TurnBench receipt. The API key stays server-side.
7. **Close with the product wedge:** “The same receipt becomes a release gate in CI and a regression-audit deliverable for teams shipping voice agents.”

## Claims to avoid during the demo
Do not say the synthetic fixtures are a live AssemblyAI benchmark. Do not say the project is registered, deployed, submitted, judged, ranked, prize-winning, paid, or revenue-generating unless separate current evidence proves that fact.
