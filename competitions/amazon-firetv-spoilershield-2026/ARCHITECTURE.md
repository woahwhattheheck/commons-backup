# SpoilerShield architecture

## Product

SpoilerShield is a TV-native context companion for the moments when somebody asks “who is that?”, “why does this matter?”, or “catch me up.” The hard product requirement is **no future-scene leakage**. The viewer's playhead is therefore a trust boundary, not merely prompt text.

## Data path

1. A transcript generation is normalized on-device.
2. `buildContextPacket` admits only cues with `cue.endMs <= positionMs`. A cue that has started but has not completed is excluded.
3. The packet binds the transcript SHA-256, exact completed cue bytes, question mode, position, maximum admitted end time, and a canonical context SHA-256.
4. The app validates its own packet before any provider call.
5. With no endpoint configured, the deterministic local provider answers from the bounded packet.
6. With an HTTPS endpoint configured, the Lambda backend independently verifies packet integrity and all timestamp bounds, optionally pins an allowed transcript generation, and then calls Bedrock.
7. Backend failure does not widen authority: the app falls back to the local provider over the already-bounded packet.

## Why the AI provider is downstream of policy

The model never decides what counts as “already seen.” It receives only evidence the local spoiler gate admitted. The optional Bedrock system message also bans outside plot/franchise/web knowledge, but prompt discipline is defense-in-depth; the mechanical context filter is the primary boundary.

## Fire TV shape

The client is dependency-free HTML5/CSS/ES modules. Fire TV supports HTML5 web apps, and Amazon's Web App Tester can load either a hosted app or a packaged ZIP. The UI is deliberately 10-foot readable and uses ordinary focusable buttons so D-pad/Enter work without a touch dependency.

## Privacy and cost

The bundled demo is synthetic. No account, viewing history, microphone, camera, guest data, or PII is required. AWS is optional; offline mode is a complete deterministic demo. Deployment/spend is never implied by the source carrier.
