import { answerOffline, buildContextPacket, formatClock, modelInstruction, validateContextPacket } from "./core.js";
import { demoEpisode } from "./demo_episode.js";

const state = { positionMs: 0, selectedKind: "CATCH_UP" };
const byId = (id) => document.getElementById(id);
const position = byId("position");
const progress = byId("progress");
const answer = byId("answer");
const mode = byId("mode");
const evidence = byId("evidence");
byId("episode-title").textContent = demoEpisode.title;

function renderPosition() {
  position.textContent = `${formatClock(state.positionMs)} / ${formatClock(demoEpisode.durationMs)}`;
  progress.value = state.positionMs;
  progress.max = demoEpisode.durationMs;
}

function seek(deltaMs) {
  state.positionMs = Math.max(0, Math.min(demoEpisode.durationMs, state.positionMs + deltaMs));
  renderPosition();
  answer.textContent = "Ask a spoiler-safe question about what you have completed so far.";
  evidence.textContent = "";
}

async function ask(kind) {
  state.selectedKind = kind;
  const packet = await buildContextPacket(demoEpisode.cues, state.positionMs, kind);
  await validateContextPacket(packet);
  evidence.textContent = `${packet.context.length} completed cues • max evidence ${formatClock(packet.maxCueEndMs)} • ${packet.contextSha256.slice(0, 12)}…`;
  const endpoint = (window.SPOILERSHIELD_CONFIG?.endpoint ?? "").trim();
  if (!endpoint) {
    mode.textContent = "OFFLINE DEMO";
    answer.textContent = answerOffline(packet);
    return;
  }
  mode.textContent = "AWS BEDROCK PATH";
  answer.textContent = "Thinking only over completed-scene evidence…";
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...packet, instruction: modelInstruction(packet) }),
    });
    if (!response.ok) throw new Error(`backend ${response.status}`);
    const body = await response.json();
    answer.textContent = body.answer;
    mode.textContent = body.mode === "bedrock" ? "AWS BEDROCK" : "BACKEND OFFLINE";
  } catch (error) {
    mode.textContent = "SAFE FALLBACK";
    answer.textContent = `${answerOffline(packet)} (Cloud path unavailable; future-scene policy remains local.)`;
  }
}

byId("back").addEventListener("click", () => seek(-30000));
byId("forward").addEventListener("click", () => seek(30000));
for (const button of document.querySelectorAll("[data-kind]")) {
  button.addEventListener("click", () => ask(button.dataset.kind));
}

// Fire TV remotes surface standard key events in HTML5 apps. Media keys are additive;
// ordinary D-pad focus/Enter behavior remains native browser behavior.
window.addEventListener("keydown", (event) => {
  if (event.key === "MediaRewind" || event.key === "j") seek(-30000);
  if (event.key === "MediaFastForward" || event.key === "l") seek(30000);
  if (event.key === "1") ask("WHO");
  if (event.key === "2") ask("WHY");
  if (event.key === "3") ask("CATCH_UP");
});

renderPosition();
