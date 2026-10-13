# Build, Ship, Shape — Fire TV submission packet

## Track

Fire TV — AI-enhanced viewing / family entertainment / multi-modal TV UX.

## One-line pitch

**SpoilerShield answers “who is that?”, “why does this matter?”, and “catch me up?” from only the scenes you have actually finished — never the ending.**

## Problem

Co-viewing breaks when someone joins late, misses dialogue, or cannot remember a character. Searching the web is slow on a TV and routinely reveals future plot. Generic assistants can also leak facts learned outside the viewer's current scene.

## Solution

SpoilerShield treats playback time as an evidence boundary. It constructs a cryptographically bound packet from completed transcript cues only, then answers locally or through an optional AWS Bedrock backend. A started-but-unfinished cue is not admissible. The model is downstream of policy rather than trusted to decide what is safe to reveal.

## Demo story (<3 min target)

1. Launch the packaged HTML5 app on Fire TV / Web App Tester or approved simulator.
2. At 5:10, ask **Catch me up**. Show the answer has no 5:20 probe-seven reveal.
3. Ask **Who is that?** with only the remote.
4. Advance to 5:35 and ask **Why does this matter?** The now-completed reveal becomes eligible.
5. Disable network and show the deterministic fallback still works.
6. Optional: re-enable the configured AWS endpoint and show the AWS BEDROCK badge, with the same evidence hash visible.

## Technical highlights

- Dependency-free Fire TV HTML5 client.
- 10-foot / D-pad-first interaction.
- Canonical transcript and context SHA-256 commitments.
- Mechanical `cue.endMs <= playhead` gate.
- Independent backend re-verification; caller prompt cannot override policy.
- Optional exact transcript-generation pin.
- AWS Bedrock runtime path with zero-temperature, context-only system instruction.
- Deterministic offline mode so judges can test without AWS credentials.
- Synthetic demo content: no copyrighted episode transcript needed.
- Hostile tests for future-cue resealing, digest tamper, generation transplant, and prompt override.

## Open-source / repository

Use the public `woahwhattheheck/commons` repository and its top-level open-source license. Submission link should point directly to `competitions/amazon-firetv-spoilershield-2026/` while preserving the repository root license visibility required by the rules.

## External gates before submission

- Join/register for the hackathon under the owner's account.
- Run and film on an actual Fire TV device or the Fire TV/Vega simulator.
- If claiming AWS Builder mini-challenge, actually deploy and visibly exercise the Bedrock path; source alone is not a runtime claim.
- Confirm the final public repo path and license are visible.
- Provide a <3 minute demo video and final Devpost description.

No registration, device run, submission, judging result, award, payment, or revenue is claimed by this source packet.
