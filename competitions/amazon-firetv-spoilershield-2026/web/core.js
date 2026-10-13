export const PACKET_VERSION = "spoilershield/context-v1";
export const QUESTION_KINDS = Object.freeze(["WHO", "WHY", "CATCH_UP"]);

function assertInteger(name, value, min = 0, max = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new TypeError(`${name} must be an integer in [${min}, ${max}]`);
  }
}

function assertString(name, value, maxLength) {
  if (typeof value !== "string" || value.length === 0 || value.length > maxLength) {
    throw new TypeError(`${name} must be a non-empty string <= ${maxLength} chars`);
  }
  if (/\p{Cc}/u.test(value)) throw new TypeError(`${name} contains control characters`);
}

export function canonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new TypeError("canonical numbers must be safe integers");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  throw new TypeError(`unsupported canonical type: ${typeof value}`);
}

export async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function normalizeTranscript(rawCues) {
  if (!Array.isArray(rawCues) || rawCues.length === 0 || rawCues.length > 5000) {
    throw new TypeError("transcript must contain 1..5000 cues");
  }
  const seen = new Set();
  const cues = rawCues.map((raw, index) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new TypeError(`cue ${index} must be an object`);
    const cue = {
      id: raw.id,
      startMs: raw.startMs,
      endMs: raw.endMs,
      speaker: raw.speaker,
      text: raw.text,
    };
    assertString(`cue ${index}.id`, cue.id, 80);
    assertInteger(`cue ${index}.startMs`, cue.startMs, 0, 86_400_000);
    assertInteger(`cue ${index}.endMs`, cue.endMs, 1, 86_400_000);
    if (cue.endMs <= cue.startMs) throw new TypeError(`cue ${index} endMs must be > startMs`);
    assertString(`cue ${index}.speaker`, cue.speaker, 80);
    assertString(`cue ${index}.text`, cue.text, 600);
    if (seen.has(cue.id)) throw new TypeError(`duplicate cue id ${cue.id}`);
    seen.add(cue.id);
    return Object.freeze(cue);
  });
  for (let i = 1; i < cues.length; i += 1) {
    if (cues[i].startMs < cues[i - 1].startMs) throw new TypeError("transcript cues must be sorted by startMs");
  }
  return Object.freeze(cues);
}

export async function transcriptSha256(cues) {
  return sha256Hex(canonicalJson(cues.map((c) => ({
    id: c.id, startMs: c.startMs, endMs: c.endMs, speaker: c.speaker, text: c.text,
  }))));
}

export async function buildContextPacket(cues, positionMs, questionKind, options = {}) {
  assertInteger("positionMs", positionMs, 0, 86_400_000);
  if (!QUESTION_KINDS.includes(questionKind)) throw new TypeError("unsupported question kind");
  const maxCues = options.maxCues ?? 8;
  assertInteger("maxCues", maxCues, 1, 8);

  // The spoiler boundary is deliberately conservative: a subtitle/cue is usable only
  // after its END timestamp, never merely because it has started.
  const eligible = cues.filter((cue) => cue.endMs <= positionMs);
  const context = eligible.slice(-maxCues).map((cue) => ({
    id: cue.id,
    startMs: cue.startMs,
    endMs: cue.endMs,
    speaker: cue.speaker,
    text: cue.text,
  }));
  const transcriptSha = await transcriptSha256(cues);
  const signed = {
    version: PACKET_VERSION,
    positionMs,
    questionKind,
    transcriptSha256: transcriptSha,
    context,
  };
  return Object.freeze({
    ...signed,
    maxCueEndMs: context.length ? Math.max(...context.map((c) => c.endMs)) : 0,
    contextSha256: await sha256Hex(canonicalJson(signed)),
  });
}

export async function validateContextPacket(packet) {
  if (!packet || typeof packet !== "object" || Array.isArray(packet)) throw new TypeError("packet must be an object");
  if (packet.version !== PACKET_VERSION) throw new TypeError("unsupported packet version");
  assertInteger("positionMs", packet.positionMs, 0, 86_400_000);
  if (!QUESTION_KINDS.includes(packet.questionKind)) throw new TypeError("unsupported question kind");
  if (!/^[0-9a-f]{64}$/.test(packet.transcriptSha256 ?? "")) throw new TypeError("invalid transcriptSha256");
  if (!Array.isArray(packet.context) || packet.context.length > 8) throw new TypeError("invalid context length");
  const normalized = packet.context.length ? normalizeTranscript(packet.context) : Object.freeze([]);
  for (const cue of normalized) {
    if (cue.endMs > packet.positionMs) throw new Error("future cue crosses spoiler boundary");
  }
  const maxCueEndMs = normalized.length ? Math.max(...normalized.map((c) => c.endMs)) : 0;
  if (packet.maxCueEndMs !== maxCueEndMs) throw new Error("maxCueEndMs mismatch");
  const signed = {
    version: packet.version,
    positionMs: packet.positionMs,
    questionKind: packet.questionKind,
    transcriptSha256: packet.transcriptSha256,
    context: normalized.map((c) => ({ id: c.id, startMs: c.startMs, endMs: c.endMs, speaker: c.speaker, text: c.text })),
  };
  const expected = await sha256Hex(canonicalJson(signed));
  if (packet.contextSha256 !== expected) throw new Error("context digest mismatch");
  return true;
}

function last(context, n) {
  return context.slice(Math.max(0, context.length - n));
}

export function answerOffline(packet) {
  const context = packet.context ?? [];
  if (context.length === 0) return "Nothing completed yet — start the demo and ask again after the first line.";
  if (packet.questionKind === "WHO") {
    const cue = context[context.length - 1];
    return `${cue.speaker} is the most recent speaker you have actually reached. Last known context: “${cue.text}”`;
  }
  if (packet.questionKind === "WHY") {
    const recent = last(context, 3);
    return `Why this matters so far: ${recent.map((cue) => `${cue.speaker}: ${cue.text}`).join(" • ")}`;
  }
  const recent = last(context, 5);
  return `Catch-up through ${formatClock(packet.positionMs)}: ${recent.map((cue) => cue.text).join(" ")}`;
}

export function modelInstruction(packet) {
  return [
    "You are SpoilerShield, a television co-viewing context assistant.",
    "Use ONLY the supplied completed transcript cues.",
    `The viewer is at ${formatClock(packet.positionMs)}. Never infer or reveal events after that position.`,
    "Do not use franchise knowledge, training-memory plot knowledge, web knowledge, or future-scene hints.",
    "If the supplied context is insufficient, say so plainly.",
    `Question mode: ${packet.questionKind}. Keep the answer under 70 words and TV-readable.`,
  ].join("\n");
}

export function formatClock(ms) {
  assertInteger("ms", ms, 0, 86_400_000);
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
