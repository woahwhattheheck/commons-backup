import assert from "node:assert/strict";
import {
  answerOffline, buildContextPacket, canonicalJson, modelInstruction,
  normalizeTranscript, transcriptSha256, validateContextPacket,
} from "../web/core.js";
import { demoEpisode } from "../web/demo_episode.js";

const cues = normalizeTranscript(demoEpisode.cues);
assert.equal(cues.length, 15);
assert.match(await transcriptSha256(cues), /^[0-9a-f]{64}$/);

const beforeTwist = await buildContextPacket(cues, 310000, "CATCH_UP");
await validateContextPacket(beforeTwist);
assert.ok(beforeTwist.context.every((cue) => cue.endMs <= 310000));
assert.equal(beforeTwist.context.some((cue) => cue.id === "c14"), false, "future twist cue must not cross boundary");
assert.equal(JSON.stringify(beforeTwist).includes("signal came from probe seven"), false, "future twist text must not leak");
assert.equal(answerOffline(beforeTwist).includes("signal came from probe seven"), false, "offline answer must not leak future twist");
assert.match(modelInstruction(beforeTwist), /Never infer or reveal events after/);

const afterTwist = await buildContextPacket(cues, 335000, "WHY");
await validateContextPacket(afterTwist);
assert.equal(afterTwist.context.at(-1).id, "c14");
assert.ok(answerOffline(afterTwist).includes("probe seven"));

const atCueStart = await buildContextPacket(cues, 320000, "WHO");
assert.equal(atCueStart.context.some((cue) => cue.id === "c14"), false, "started-but-not-finished cue is future");

const tampered = structuredClone(beforeTwist);
tampered.context[0].text = "The ending is revealed here.";
await assert.rejects(() => validateContextPacket(tampered), /digest mismatch/);

const futureResealed = structuredClone(beforeTwist);
futureResealed.context[futureResealed.context.length - 1] = { id: "forged", startMs: 309000, endMs: 311000, speaker: "Attacker", text: "future" };
futureResealed.maxCueEndMs = 311000;
const signed = {
  version: futureResealed.version,
  positionMs: futureResealed.positionMs,
  questionKind: futureResealed.questionKind,
  transcriptSha256: futureResealed.transcriptSha256,
  context: futureResealed.context,
};
const raw = new TextEncoder().encode(canonicalJson(signed));
const hash = await crypto.subtle.digest("SHA-256", raw);
futureResealed.contextSha256 = [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
await assert.rejects(() => validateContextPacket(futureResealed), /future cue/);

assert.throws(() => normalizeTranscript([
  { id: "x", startMs: 0, endMs: 1000, speaker: "A", text: "ok" },
  { id: "x", startMs: 1000, endMs: 2000, speaker: "B", text: "duplicate" },
]), /duplicate cue id/);

console.log("SpoilerShield core: 10 spoiler-boundary/integrity checks PASS");
