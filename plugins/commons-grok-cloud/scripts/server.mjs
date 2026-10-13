#!/usr/bin/env node

import { createHash } from "node:crypto";
import { closeSync, fsyncSync, mkdirSync, openSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import process from "node:process";

const VERSION = "1.2.0";
const COMMONS_MCP = "https://commons-spark-mcp.vercel.app/mcp";
const SLACK_CHANNEL = "C0BRGMDQB6G";
const ID_RE = /^[A-Za-z0-9._-]{8,80}$/;
const GROK_URL_RE = /^https:\/\/grok\.com\/c\/[A-Za-z0-9_-]+(?:[/?#].*)?$/;

const ROUTES = Object.freeze({
  "grokcom-revenue": {
    executor: "chatgpt-cloud-browser",
    surface: "https://grok.com/",
    orchestrator_tool: "route_grokcom_revenue_work",
    durable_job_path: "wake_jobs/<task-id>.json",
    task_sources: ["slack", "commons-mcp", "action-ops", "user"],
    receipt: "grok.com/c/... URL plus exact prompt and result",
    direction: "bidirectional",
    grok_client_tool: "build_grok_commons_client",
  },
  "gemini-spark": {
    executor: "gemini-spark",
    surface: COMMONS_MCP,
    carrier: "carriers/gemini-spark.json",
  },
  commons: { executor: "streamable-http-mcp", surface: COMMONS_MCP },
  slack: { executor: "chatgpt-slack-connector", channel: SLACK_CHANNEL },
  "grokcom-slack": {
    executor: "grok_slack_bridge",
    surface: "http://127.0.0.1:8789/",
    slack_app_id: "A0BTJMFPTT6",
    channel: SLACK_CHANNEL,
    health: "127.0.0.1:8788",
    gemini_isolated: true,
    gemini_handoff: "127.0.0.1:8780",
    tool: "grok_slack_bridge",
    table_proof: "python integrations/grok_slack/bridge.py table-proof --json",
  },
  github: { executor: "chatgpt-github-connector", repository: "woahwhattheheck/commons" },
});

const AUTOMATION_PROMPT = [
  "Read new GROK TASK messages in Slack #commons (C0BRGMDQB6G).",
  "Send every event to Commons MCP route_grokcom_revenue_work at INTAKE.",
  "Skip completed or live-owned dedupe keys; execute only SEND_TO_GROKCOM packets.",
  "Use the commons-grok-cloud skill and the account's cloud browser to run the exact returned prompt once.",
  "Build the real grok.com artifact, feed it to GROKCOM_RESULT, and reply in the originating Slack thread and Commons.",
].join(" ");

function assertId(value) {
  const id = String(value ?? "").trim();
  if (!ID_RE.test(id)) throw new Error("task_id must be 8-80 Commons ID characters");
  return id;
}

function receiptId(taskId, suffix) {
  const id = assertId(taskId);
  const tail = `-grok-${suffix}`;
  if (id.length + tail.length <= 80) return id + tail;
  const digest = createHash("sha256").update(id).digest("hex").slice(0, 10);
  return `${id.slice(0, 80 - tail.length - 11)}-${digest}${tail}`;
}

function list(value) {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}


const CAPTURE_SCHEMA = "commons-grok-capture/v1";
const CAPTURE_DIR_NAME = ".commons-grok-captures";
const CAPTURE_INPUT_STATES = new Set([
  "OBSERVING", "PARTIAL", "COMPLETED", "FAILED", "PAGE_UNCONFIRMED",
  "CONNECTOR_UNAVAILABLE", "RECEIPT_EMITTED",
]);
const CAPTURE_ACTIVE_STATES = new Set(["CAPTURE_STARTED", "CAPTURING", "GROK_CONTINUE"]);
const SHA256_CAPTURE_RE = /^[0-9a-f]{64}$/;

function captureDigest(value) {
  const bytes = typeof value === "string" || Buffer.isBuffer(value)
    ? value
    : JSON.stringify(value, null, 2) + "\n";
  return createHash("sha256").update(bytes).digest("hex");
}

function exactText(value, field, { required = false, maximum = 1_000_000 } = {}) {
  if (value === undefined || value === null) value = "";
  if (typeof value !== "string") throw new Error(field + " must be a string");
  if (required && !value.trim()) throw new Error(field + " must not be empty");
  if (value.length > maximum) throw new Error(field + " exceeds " + maximum + " characters");
  return value;
}

function exactTextList(value, field) {
  if (!Array.isArray(value) || !value.length) throw new Error(field + " must be a non-empty string array");
  return value.map((item, index) => exactText(item, field + "[" + index + "]", { required: true }));
}

function plainObject(value, field) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(field + " must be an object");
  return value;
}

function jsonCopy(value, field) {
  try { return JSON.parse(JSON.stringify(value)); }
  catch (_) { throw new Error(field + " must be JSON-serializable"); }
}

function observedAt(value) {
  const text = exactText(value, "timestamp", { maximum: 128 }).trim();
  if (!text) return new Date().toISOString();
  if (Number.isNaN(Date.parse(text))) throw new Error("timestamp must be an ISO-8601 value");
  return text;
}

function captureRoot() {
  const configured = String(process.env.COMMONS_GROK_CAPTURE_DIR ?? "").trim();
  return resolve(configured || join(homedir(), CAPTURE_DIR_NAME));
}

function captureRunId(runKey) {
  return createHash("sha256").update(runKey).digest("hex").slice(0, 32);
}

function captureDirectory(runId) {
  return join(captureRoot(), runId);
}

function readLatestCaptureById(runId) {
  let names;
  try {
    names = readdirSync(captureDirectory(runId))
      .filter((name) => /^\d{8}\.json$/.test(name))
      .sort()
      .reverse();
  } catch (_) {
    return null;
  }
  for (const name of names) {
    try {
      const row = JSON.parse(readFileSync(join(captureDirectory(runId), name), "utf8"));
      if (row?.schema === CAPTURE_SCHEMA && row?.run_id === runId) return row;
    } catch (_) {
      // A torn newest snapshot never hides the preceding durable snapshot.
    }
  }
  return null;
}

function readCaptureByKey(runKey) {
  return readLatestCaptureById(captureRunId(runKey));
}

function readAllCaptures() {
  let entries;
  try { entries = readdirSync(captureRoot(), { withFileTypes: true }).sort((left, right) => left.name.localeCompare(right.name)); }
  catch (_) { return []; }
  return entries
    .filter((entry) => entry.isDirectory() && /^[0-9a-f]{32}$/.test(entry.name))
    .map((entry) => readLatestCaptureById(entry.name))
    .filter(Boolean);
}

function persistCapture(run) {
  const next = { ...jsonCopy(run, "capture"), revision: Number(run.revision || 0) + 1 };
  const directory = captureDirectory(next.run_id);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const bytes = Buffer.from(JSON.stringify(next, null, 2) + "\n", "utf8");
  const name = String(next.revision).padStart(8, "0") + ".json";
  const fd = openSync(join(directory, name), "wx", 0o600);
  try {
    writeFileSync(fd, bytes);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  return {
    capture: next,
    persistence: {
      schema: "commons-grok-capture-snapshot/v1",
      revision: next.revision,
      size_bytes: bytes.length,
      sha256: captureDigest(bytes),
      append_only: true,
      local_path_private: true,
    },
  };
}

function conversationFacts(value, field = "conversation_url") {
  const observed = exactText(value, field, { maximum: 2_000 }).trim();
  if (!observed) return { observed: "", canonical: "", rid: "" };
  const match = GROK_URL_RE.exec(observed);
  if (!match) throw new Error(field + " must be an actual https://grok.com/c/... URL");
  const rid = /^https:\/\/grok\.com\/c\/([A-Za-z0-9_-]+)/.exec(observed)?.[1] ?? "";
  return { observed, canonical: "https://grok.com/c/" + rid, rid };
}

function normalizeOrigin(value) {
  const row = plainObject(value, "origin");
  const origin = {
    task_id: exactText(row.task_id, "origin.task_id", { maximum: 256 }).trim(),
    session_id: exactText(row.session_id, "origin.session_id", { maximum: 256 }).trim(),
    thread_id: exactText(row.thread_id, "origin.thread_id", { maximum: 256 }).trim(),
    source: exactText(row.source || "user", "origin.source", { maximum: 128 }).trim(),
    event_id: exactText(row.event_id, "origin.event_id", { maximum: 256 }).trim(),
  };
  if (!origin.task_id && !origin.session_id) throw new Error("origin needs task_id or session_id");
  return origin;
}

function normalizeProvider(value, previous = {}) {
  if (value === undefined) return jsonCopy(previous, "provider");
  const row = plainObject(value, "provider");
  const provider = {
    model: exactText(row.model, "provider.model", { maximum: 256 }).trim(),
    mode: exactText(row.mode, "provider.mode", { maximum: 256 }).trim(),
  };
  if (row.source_count !== undefined) {
    if (typeof row.source_count === "boolean" || !Number.isInteger(row.source_count) || row.source_count < 0) {
      throw new Error("provider.source_count must be a non-negative integer");
    }
    provider.source_count = row.source_count;
  }
  if (row.token_evidence !== undefined) provider.token_evidence = jsonCopy(row.token_evidence, "provider.token_evidence");
  if (row.debit_evidence !== undefined) provider.debit_evidence = jsonCopy(row.debit_evidence, "provider.debit_evidence");
  return provider;
}

function normalizeArtifacts(value) {
  if (value === undefined) return null;
  if (!Array.isArray(value)) throw new Error("artifacts must be an array");
  return value.map((input, index) => {
    const row = plainObject(input, "artifacts[" + index + "]");
    const artifact = {
      path: exactText(row.path, "artifacts[" + index + "].path", { required: true, maximum: 4_000 }),
      provider_private: row.provider_private !== false,
      inspection_state: exactText(row.inspection_state || "UNINSPECTED", "artifact.inspection_state", { maximum: 128 }).trim(),
    };
    if (row.sha256 !== undefined && row.sha256 !== "") {
      const digest = exactText(row.sha256, "artifact.sha256", { maximum: 64 }).trim();
      if (!SHA256_CAPTURE_RE.test(digest)) throw new Error("artifact.sha256 must be exact lowercase sha256 when exposed");
      artifact.sha256 = digest;
    }
    if (row.size_bytes !== undefined) {
      if (typeof row.size_bytes === "boolean" || !Number.isInteger(row.size_bytes) || row.size_bytes < 0) {
        throw new Error("artifact.size_bytes must be a non-negative integer when exposed");
      }
      artifact.size_bytes = row.size_bytes;
    }
    return artifact;
  });
}

function mergeArtifacts(previous, incoming) {
  if (incoming === null) return jsonCopy(previous || [], "artifacts");
  const merged = new Map((previous || []).map((item) => [item.path, item]));
  for (const item of incoming) merged.set(item.path, item);
  return [...merged.values()];
}

function captureBoundary() {
  return {
    capture_only: true,
    prompt_submissions_by_capture: 0,
    prompt_resubmissions_by_capture: 0,
    extra_provider_tokens_by_capture: 0,
    provider_mutations_by_capture: 0,
    repository_mutations_by_capture: 0,
    excluded_browser_fields: ["cookies", "credentials", "browser_storage", "request_headers"],
  };
}

function duplicateCapture(kind, existing) {
  return {
    state: "DUPLICATE",
    dedupe: kind,
    prompt_action: "DO_NOT_SUBMIT",
    capture: existing,
    zero_token_boundary: existing.boundary,
  };
}

function findCaptureByConversation(canonicalUrl) {
  return canonicalUrl ? readAllCaptures().find((row) => row.conversation_url === canonicalUrl) ?? null : null;
}

export function startGrokCapture(args = {}) {
  const runKey = exactText(args.run_key, "run_key", { required: true, maximum: 512 }).trim();
  const existing = readCaptureByKey(runKey);
  if (existing) return duplicateCapture("RUN_KEY", existing);

  const prompts = exactTextList(args.exact_prompts, "exact_prompts");
  const parentKey = exactText(args.parent_run_key, "parent_run_key", { maximum: 512 }).trim();
  const parent = parentKey ? readCaptureByKey(parentKey) : null;
  if (parentKey && !parent) throw new Error("parent_run_key has no durable capture");
  if (parent && prompts.some((prompt) => parent.exact_prompts.includes(prompt))) {
    throw new Error("continuation prompt must be new; finished prompts are never replayed");
  }

  const conversation = conversationFacts(args.conversation_url || parent?.conversation_url || "");
  const urlMatch = findCaptureByConversation(conversation.canonical);
  if (urlMatch && !parent) return duplicateCapture("EXACT_URL", urlMatch);
  if (parent && conversation.canonical && parent.conversation_url && conversation.canonical !== parent.conversation_url) {
    throw new Error("continuation conversation must preserve parent conversation lineage");
  }

  const at = observedAt(args.started_at);
  const run = {
    schema: CAPTURE_SCHEMA,
    run_key: runKey,
    run_id: captureRunId(runKey),
    state: parent ? "GROK_CONTINUE" : "CAPTURE_STARTED",
    completion_state: "",
    origin: normalizeOrigin(args.origin),
    lineage: parent ? {
      parent_run_key: parent.run_key,
      parent_run_id: parent.run_id,
      parent_conversation_url: parent.conversation_url,
    } : null,
    conversation_url_observed: conversation.observed,
    conversation_url: conversation.canonical,
    conversation_rid: conversation.rid,
    exact_prompts: prompts,
    exact_final_result: "",
    partial_result: "",
    provider: normalizeProvider(args.provider),
    artifacts: normalizeArtifacts(args.artifacts) || [],
    failure: null,
    timestamps: { started_at: at, last_observed_at: at, completed_at: "" },
    boundary: captureBoundary(),
    delivery: { commons: "PENDING", slack: "PENDING", attempts: [] },
  };
  const persisted = persistCapture(run);
  return {
    state: persisted.capture.state,
    prompt_action: parent ? "SUBMIT_NEW_CONTINUATION_PROMPT_ONCE" : "SUBMIT_EXACT_PROMPT_ONCE",
    write_ahead_ack: true,
    ...persisted,
    zero_token_boundary: persisted.capture.boundary,
  };
}

function continuationPacket(run, prompt) {
  const continuationPrompt = exactText(prompt, "continuation_prompt", { maximum: 1_000_000 });
  if (!continuationPrompt.trim()) return null;
  if (run.exact_prompts.includes(continuationPrompt)) {
    throw new Error("continuation prompt must be new; finished prompts are never replayed");
  }
  const nextRunKey = "grok-continue-" + captureDigest({
    parent_run_key: run.run_key,
    conversation_url: run.conversation_url,
    prompt: continuationPrompt,
  }).slice(0, 32);
  return {
    state: "GROK_CONTINUE",
    action: "START_LINEAGE_LINKED_NEW_RUN",
    run_key: nextRunKey,
    parent_run_key: run.run_key,
    parent_conversation_url: run.conversation_url,
    exact_prompts: [continuationPrompt],
    prompt_action: "SUBMIT_NEW_PROMPT_ONCE_AFTER_WRITE_AHEAD_ACK",
  };
}

function buildCaptureDispatch(run) {
  const artifactBytes = JSON.stringify(run, null, 2) + "\n";
  const artifactBuffer = Buffer.from(artifactBytes, "utf8");
  const artifactPath = "artifacts/grok-captures/" + run.run_id + ".json";
  const artifactSha = captureDigest(artifactBuffer);
  const promptSha = captureDigest(run.exact_prompts.join("\n\u0000\n"));
  const resultSha = captureDigest(run.exact_final_result);
  const receiptIdValue = "grok-capture-" + run.run_id;
  const provider = JSON.stringify(run.provider);
  const artifacts = JSON.stringify(run.artifacts);
  const boundary = JSON.stringify(run.boundary);
  const body = [
    "GROK CAPTURE VERIFIED — " + run.run_key,
    "state: " + run.state,
    "conversation: " + run.conversation_url,
    "rid: " + run.conversation_rid,
    "origin: " + JSON.stringify(run.origin),
    "lineage: " + JSON.stringify(run.lineage),
    "exact_prompt_count: " + run.exact_prompts.length,
    "exact_prompts_sha256: " + promptSha,
    "exact_result_sha256: " + resultSha,
    "provider: " + provider,
    "artifacts: " + artifacts,
    "capture_artifact: " + artifactPath,
    "capture_artifact_size: " + artifactBuffer.length,
    "capture_artifact_sha256: " + artifactSha,
    "timestamps: " + JSON.stringify(run.timestamps),
    "zero_token_no_mutation_boundary: " + boundary,
    "Exact prompt/result bytes are in the SHA-pinned capture artifact; do not replay the finished prompt.",
  ].join("\n");
  return {
    state: "READY_TO_EMIT_AFTER_VERIFIED_COMPLETION",
    no_emit_before: "VERIFIED_COMPLETE",
    github_file: {
      repository: "woahwhattheheck/commons",
      path: artifactPath,
      content: artifactBytes,
      size_bytes: artifactBuffer.length,
      sha256: artifactSha,
    },
    commons_post: {
      id: receiptIdValue,
      to: "TOOLS",
      board: "TOOLS",
      subject: "automatic grok.com capture",
      body,
    },
    slack_receipt: {
      channel: SLACK_CHANNEL,
      thread_ts: run.origin.thread_id || "",
      dedupe_key: receiptIdValue,
      message: body,
    },
    delivery_order: [
      "WRITE_GITHUB_CAPTURE_ARTIFACT",
      "VERIFY_ARTIFACT_SHA_SIZE",
      "APPEND_COMMONS_POST",
      "VERIFY_COMMONS_DURABILITY",
      "SEND_SLACK_RECEIPT",
      "MARK_RECEIPT_EMITTED",
    ],
  };
}

export function captureGrokRun(args = {}) {
  const runKey = exactText(args.run_key, "run_key", { required: true, maximum: 512 }).trim();
  const prior = readCaptureByKey(runKey);
  if (!prior) throw new Error("run_key has no write-ahead capture");
  const inputState = exactText(args.state || "OBSERVING", "state", { maximum: 64 }).trim().toUpperCase();
  if (!CAPTURE_INPUT_STATES.has(inputState)) throw new Error("unsupported capture state: " + inputState);

  const run = jsonCopy(prior, "capture");
  const at = observedAt(args.observed_at);
  const conversation = conversationFacts(args.conversation_url || run.conversation_url || "");
  if (conversation.canonical) {
    const urlMatch = findCaptureByConversation(conversation.canonical);
    const lineageOwnsConversation = Boolean(
      run.lineage && conversation.canonical === run.lineage.parent_conversation_url
    );
    if (urlMatch && urlMatch.run_id !== run.run_id && !lineageOwnsConversation) {
      return duplicateCapture("EXACT_URL", urlMatch);
    }
    run.conversation_url_observed = conversation.observed;
    run.conversation_url = conversation.canonical;
    run.conversation_rid = conversation.rid;
  }
  run.provider = normalizeProvider(args.provider, run.provider);
  run.artifacts = mergeArtifacts(run.artifacts, normalizeArtifacts(args.artifacts));
  if (args.partial_result !== undefined) run.partial_result = exactText(args.partial_result, "partial_result");
  if (args.exact_final_result !== undefined) run.exact_final_result = exactText(args.exact_final_result, "exact_final_result");
  run.timestamps.last_observed_at = at;
  let continuation = null;

  if (inputState === "OBSERVING") {
    run.state = "CAPTURING";
  } else if (inputState === "PARTIAL") {
    run.state = "PARTIAL";
    run.completion_state = "PARTIAL";
    continuation = continuationPacket(run, args.continuation_prompt);
  } else if (inputState === "COMPLETED") {
    if (args.completion_verified !== true) throw new Error("COMPLETED requires completion_verified=true");
    if (!run.conversation_url) throw new Error("COMPLETED requires a confirmed grok.com/c/... page");
    if (!run.exact_final_result.trim()) throw new Error("COMPLETED requires exact_final_result");
    run.state = "VERIFIED_COMPLETE";
    run.completion_state = "COMPLETED";
    run.timestamps.completed_at = at;
  } else if (inputState === "PAGE_UNCONFIRMED") {
    run.state = "PAGE_UNCONFIRMED";
    run.completion_state = "PAGE_UNCONFIRMED";
    run.failure = {
      state: "PAGE_UNCONFIRMED",
      detail: exactText(args.failure_detail, "failure_detail", { maximum: 16_000 }),
      prompt_resubmission_allowed: false,
    };
    run.timestamps.completed_at = at;
  } else if (inputState === "FAILED") {
    run.state = "FAILED";
    run.completion_state = exactText(args.failure_state || "FAILED", "failure_state", { maximum: 128 }).trim().toUpperCase();
    run.failure = {
      state: run.completion_state,
      detail: exactText(args.failure_detail, "failure_detail", { maximum: 16_000 }),
      prompt_resubmission_allowed: false,
    };
    run.timestamps.completed_at = at;
  } else if (inputState === "CONNECTOR_UNAVAILABLE") {
    if (!["VERIFIED_COMPLETE", "RECEIPT_PENDING"].includes(run.state)) {
      throw new Error("connector failure may only follow verified completion");
    }
    run.state = "RECEIPT_PENDING";
    run.delivery.attempts.push({
      at,
      state: "CONNECTOR_UNAVAILABLE",
      connector: exactText(args.connector || "unknown", "connector", { maximum: 128 }).trim(),
      detail: exactText(args.failure_detail, "failure_detail", { maximum: 16_000 }),
    });
  } else if (inputState === "RECEIPT_EMITTED") {
    if (!["VERIFIED_COMPLETE", "RECEIPT_PENDING"].includes(run.state)) {
      throw new Error("receipt emission may only follow verified completion");
    }
    const delivery = plainObject(args.delivery, "delivery");
    if (delivery.commons !== "DURABLE_ON_MAIN" || delivery.slack !== "SENT") {
      throw new Error("receipt emission requires Commons durability and Slack SENT readback");
    }
    run.state = "RECEIPT_EMITTED";
    run.delivery = {
      commons: "DURABLE_ON_MAIN",
      slack: "SENT",
      attempts: run.delivery.attempts,
      evidence: jsonCopy(delivery.evidence || {}, "delivery.evidence"),
    };
  }

  const persisted = persistCapture(run);
  const response = {
    state: persisted.capture.state,
    ...persisted,
    zero_token_boundary: persisted.capture.boundary,
  };
  if (continuation) response.next_run = continuation;
  if (["VERIFIED_COMPLETE", "RECEIPT_PENDING"].includes(persisted.capture.state)) {
    response.dispatch = buildCaptureDispatch(persisted.capture);
  }
  return response;
}

function recoveryRow(run) {
  if (CAPTURE_ACTIVE_STATES.has(run.state)) {
    return {
      state: "INTERRUPTED_RECOVERABLE",
      prompt_action: "DO_NOT_RESUBMIT",
      recovery_action: "CAPTURE_OUTPUT_ONLY_FROM_EXISTING_CONVERSATION",
      capture: run,
      zero_token_boundary: run.boundary,
    };
  }
  if (["VERIFIED_COMPLETE", "RECEIPT_PENDING"].includes(run.state)) {
    return {
      state: "RECEIPT_PENDING",
      prompt_action: "DO_NOT_RESUBMIT",
      recovery_action: "EMIT_VERIFIED_RECEIPTS_WITHOUT_PROVIDER_CALL",
      capture: run,
      dispatch: buildCaptureDispatch(run),
      zero_token_boundary: run.boundary,
    };
  }
  return {
    state: run.state,
    prompt_action: "DO_NOT_RESUBMIT",
    recovery_action: "NONE",
    capture: run,
    zero_token_boundary: run.boundary,
  };
}

export function recoverGrokCapture(args = {}) {
  const runKey = exactText(args.run_key, "run_key", { maximum: 512 }).trim();
  const runs = runKey ? [readCaptureByKey(runKey)].filter(Boolean) : readAllCaptures();
  return {
    state: runs.length ? "RECOVERED" : "NO_CAPTURE",
    runs: runs.map(recoveryRow),
    dedupe: "EXACT_URL_AND_RUN_KEY",
    resubmit_finished_prompt: false,
  };
}

export function buildGrokCommonsClient(args = {}) {
  const taskId = args.task_id ? assertId(args.task_id) : "<stable-task-id>";
  const event = args.event && typeof args.event === "object" && !Array.isArray(args.event) ? args.event : {
    event_id: "<slack-event-id>",
    channel: SLACK_CHANNEL,
    message_ts: "<exact-message-ts>",
    thread_ts: "<exact-thread-ts>",
    author: "<author-id>",
    text: "<lossless-task-text>",
  };
  const intakeArguments = { stage: "INTAKE", mode: "AUTO", event };
  const forwardEnvelope = {
    schema: "commons-grok-forward-v1",
    task_id: taskId,
    tool: "route_grokcom_revenue_work",
    arguments: intakeArguments,
  };
  const grokPrompt = [
    "You are a bidirectional Commons peer, not only an execution target.",
    `Use the public Streamable HTTP MCP at ${COMMONS_MCP}; it has no auth, token, headers, identity gate, or allowlist.`,
    "List its tools, then call route_grokcom_revenue_work for Commons work and append_post/verify_durability for durable returns.",
    "Preserve the stable task ID, exact Slack timestamps, prompt/result bytes, current Git SHA, paths, checks, and the final grok.com/c/... URL.",
    "If this grok.com surface has no native remote-MCP field, emit the provided COMMONS_GROK_FORWARD envelope exactly; the connected cloud automation must forward it losslessly, return the MCP response here, and continue until the Commons receipt verifies.",
    "Do not create another queue, MCP core, login, credential, or approval step.",
  ].join(" ");
  return {
    schema: "commons-grok-client-v1",
    direction: "bidirectional",
    commons_mcp: COMMONS_MCP,
    transport: "streamable-http",
    auth: "none",
    config: { mcpServers: { commons: { type: "http", url: COMMONS_MCP } } },
    initialize: {
      jsonrpc: "2.0", id: 1, method: "initialize",
      params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "grok.com", version: "1" } },
    },
    tools_list: { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
    intake_call: { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "route_grokcom_revenue_work", arguments: intakeArguments } },
    forward_envelope: forwardEnvelope,
    grok_prompt: grokPrompt,
    return_tools: ["route_grokcom_revenue_work", "append_post", "verify_durability", "fire_action"],
  };
}

export function buildArtifact(args = {}) {
  const taskId = assertId(args.task_id);
  const conversationUrl = String(args.conversation_url ?? "").trim();
  if (!GROK_URL_RE.test(conversationUrl)) {
    throw new Error("conversation_url must be an actual https://grok.com/c/... URL");
  }
  const exactPrompt = String(args.exact_prompt ?? "");
  const result = String(args.result ?? "");
  const inspectedSha = String(args.inspected_sha ?? "").trim();
  if (!exactPrompt.trim() || !result.trim()) throw new Error("exact_prompt and result are required");
  if (!/^[0-9a-f]{7,40}$/i.test(inspectedSha)) throw new Error("inspected_sha must be a Git SHA");
  const state = String(args.state ?? "READY_FOR_INTEGRATION").trim();
  const event = args.event && typeof args.event === "object" && !Array.isArray(args.event) ? args.event : {};
  if (!Object.keys(event).length) throw new Error("original Slack event is needed to preserve the orchestrator task hash");
  const changedPaths = list(args.changed_paths);
  const checks = list(args.checks);
  const lines = [
    `GROK RESULT — ${taskId}`,
    `state: ${state}`,
    `conversation: ${conversationUrl}`,
    `inspected_sha: ${inspectedSha}`,
    args.model ? `model: ${String(args.model)}` : "",
    args.account ? `account: ${String(args.account)}` : "",
    args.usage ? `usage: ${String(args.usage)}` : "",
    changedPaths.length ? `changed_paths: ${changedPaths.join(", ")}` : "changed_paths: none",
    checks.length ? `checks: ${checks.join("; ")}` : "checks: not reported",
    "exact_prompt:",
    exactPrompt,
    "lossless_result:",
    result,
  ].filter(Boolean);
  const receiptBody = lines.join("\n");
  const artifact = {
    task_id: taskId,
    conversation_url: conversationUrl,
    exact_prompt: exactPrompt,
    lossless_result: result,
    inspected_sha: inspectedSha,
    model: args.model ? String(args.model) : "",
    account: args.account ? String(args.account) : "",
    usage: args.usage ? String(args.usage) : "",
    changed_paths: changedPaths,
    checks,
    state,
  };
  return {
    state,
    task_id: taskId,
    conversation_url: conversationUrl,
    artifact,
    orchestrator_tool: "route_grokcom_revenue_work",
    orchestrator_arguments: { stage: "GROKCOM_RESULT", event, artifact },
    commons_post: {
      id: receiptId(taskId, "result"),
      to: "TOOLS",
      board: "TOOLS",
      subject: "grok.com cloud execution",
      body: receiptBody,
    },
  };
}

export function classifyPreflight(args = {}) {
  if (!args.browser_bridge) return { state: "BROWSER_UNAVAILABLE", retry_same_session: false };
  if (!args.page_backend) return { state: "PAGE_BACKEND_UNAVAILABLE", retry_same_session: false };
  if (String(args.grok_page ?? "") === "login") return { state: "PROVIDER_SIGN_IN", retry_same_session: false };
  const url = String(args.conversation_url ?? "").trim();
  if (String(args.grok_page ?? "") !== "ready" || (url && !GROK_URL_RE.test(url))) {
    return { state: "PAGE_UNCONFIRMED", retry_same_session: false };
  }
  return { state: "READY", retry_same_session: true };
}

export function getBridge() {
  return {
    schema: "commons-grok-cloud-v1",
    commons_mcp: COMMONS_MCP,
    slack_channel: SLACK_CHANNEL,
    routes: ROUTES,
    automation_prompt: AUTOMATION_PROMPT,
    grok_client: buildGrokCommonsClient(),
    receipt_fields: [
      "run_key", "origin", "conversation_url", "conversation_rid", "exact_prompts", "exact_final_result",
      "artifacts", "provider", "timestamps", "lineage", "completion_state", "state", "boundary",
    ],
    capture_tools: ["start_grok_capture", "capture_grok_run", "recover_grok_capture"],
    continuation_state: "GROK_CONTINUE",
    failure_states: ["BROWSER_UNAVAILABLE", "PAGE_BACKEND_UNAVAILABLE", "PROVIDER_SIGN_IN", "PAGE_UNCONFIRMED", "CONNECTOR_UNAVAILABLE"],
  };
}

const TOOLS = [
  {
    name: "start_grok_capture",
    description: "Write the lossless run identity, origin, lineage, and exact prompt(s) before one intentional grok.com submission.",
    inputSchema: {
      type: "object",
      required: ["run_key", "origin", "exact_prompts"],
      properties: {
        run_key: { type: "string" }, origin: { type: "object", additionalProperties: true },
        exact_prompts: { type: "array", items: { type: "string" } },
        parent_run_key: { type: "string" }, conversation_url: { type: "string" },
        started_at: { type: "string" }, provider: { type: "object", additionalProperties: true },
        artifacts: { type: "array", items: { type: "object", additionalProperties: true } },
      },
      additionalProperties: false,
    },
  },
  {
    name: "capture_grok_run",
    description: "Append an observed partial, terminal, delivery-failure, or receipt state without submitting or replaying any prompt.",
    inputSchema: {
      type: "object",
      required: ["run_key", "state"],
      properties: {
        run_key: { type: "string" }, state: { type: "string" }, observed_at: { type: "string" },
        conversation_url: { type: "string" }, partial_result: { type: "string" },
        exact_final_result: { type: "string" }, completion_verified: { type: "boolean" },
        continuation_prompt: { type: "string" }, failure_state: { type: "string" },
        failure_detail: { type: "string" }, connector: { type: "string" },
        provider: { type: "object", additionalProperties: true },
        artifacts: { type: "array", items: { type: "object", additionalProperties: true } },
        delivery: { type: "object", additionalProperties: true },
      },
      additionalProperties: false,
    },
  },
  {
    name: "recover_grok_capture",
    description: "Recover durable run snapshots after interruption; capture output or emit pending receipts without prompt replay.",
    inputSchema: {
      type: "object",
      properties: { run_key: { type: "string" } },
      additionalProperties: false,
    },
  },
  {
    name: "build_grok_commons_client",
    description: "Build Grok's direct or losslessly forwarded Commons MCP client bundle so work can flow both ways.",
    inputSchema: {
      type: "object",
      properties: { task_id: { type: "string" }, event: { type: "object", additionalProperties: true } },
      additionalProperties: false,
    },
  },
  {
    name: "get_cloud_bridge",
    description: "Return the one-install Grok/Commons/Slack/Gemini cloud route and automation prompt.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "build_grok_artifact",
    description: "Turn a real cloud-browser Grok result into the canonical orchestrator artifact and Commons receipt.",
    inputSchema: {
      type: "object",
      required: ["task_id", "event", "conversation_url", "exact_prompt", "result", "inspected_sha"],
      properties: {
        task_id: { type: "string" }, event: { type: "object", additionalProperties: true },
        conversation_url: { type: "string" }, exact_prompt: { type: "string" },
        result: { type: "string" }, inspected_sha: { type: "string" }, model: { type: "string" },
        account: { type: "string" }, usage: { type: "string" }, state: { type: "string" },
        changed_paths: { type: "array", items: { type: "string" } }, checks: { type: "array", items: { type: "string" } },
      },
      additionalProperties: false,
    },
  },
  {
    name: "classify_grok_preflight",
    description: "Classify measured cloud browser and grok.com page readiness without repeated blind attempts.",
    inputSchema: {
      type: "object",
      properties: {
        browser_bridge: { type: "boolean" }, page_backend: { type: "boolean" }, grok_page: { type: "string" },
        conversation_url: { type: "string" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "grok_slack_bridge",
    description: "Callable Commons Grok Slack bridge: DPAPI vault, loopback 8789, #commons table-proof. Never returns token values. Gemini stays on 8780.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
];

function grokSlackBridge() {
  return {
    schema: "commons-grok-slack-handoff/v1",
    slack_app_id: "A0BTJMFPTT6",
    handoff_bind: "127.0.0.1:8789",
    gemini_handoff_bind: "127.0.0.1:8780",
    health_bind: "127.0.0.1:8788",
    slack_channel: SLACK_CHANNEL,
    implementation: "integrations/grok_slack/bridge.py",
    callable: [
      "python integrations/grok_slack/bridge.py health --json",
      "python integrations/grok_slack/bridge.py table-proof --json",
    ],
    vault: "current-user DPAPI (Windows) / user-bound ciphertext (POSIX); never plaintext; never deleted on unreadable",
    cross_process: true,
    secrets_printed: false,
    auth: "none",
    final_delivery_owner: "grok_slack_bridge",
    gemini_isolated: true,
  };
}

function toolResult(payload) {
  return { content: [{ type: "text", text: JSON.stringify(payload, null, 2) }], structuredContent: payload };
}

function callTool(name, args) {
  if (name === "start_grok_capture") return startGrokCapture(args);
  if (name === "capture_grok_run") return captureGrokRun(args);
  if (name === "recover_grok_capture") return recoverGrokCapture(args);
  if (name === "get_cloud_bridge") return getBridge();
  if (name === "build_grok_commons_client") return buildGrokCommonsClient(args);
  if (name === "build_grok_artifact") return buildArtifact(args);
  if (name === "classify_grok_preflight") return classifyPreflight(args);
  if (name === "grok_slack_bridge") return grokSlackBridge();
  throw new Error(`unknown tool: ${name}`);
}

function handle(message) {
  const id = message?.id;
  if (message?.method === "initialize") {
    return { jsonrpc: "2.0", id, result: { protocolVersion: "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "commons-grok-cloud", version: VERSION } } };
  }
  if (message?.method === "tools/list") return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
  if (message?.method === "tools/call") {
    try { return { jsonrpc: "2.0", id, result: toolResult(callTool(message.params?.name, message.params?.arguments ?? {})) }; }
    catch (error) { return { jsonrpc: "2.0", id, result: { isError: true, content: [{ type: "text", text: String(error.message || error) }] } }; }
  }
  if (message?.method === "ping") return { jsonrpc: "2.0", id, result: {} };
  if (id === undefined) return null;
  return { jsonrpc: "2.0", id, error: { code: -32601, message: "method not found" } };
}

function selfTest() {
  const result = buildArtifact({ task_id: "cloud-grok-test-20260828-01", event: { event_id: "Ev1", channel: SLACK_CHANNEL, message_ts: "1", text: "task" }, conversation_url: "https://grok.com/c/abc_123", exact_prompt: "p", result: "r", inspected_sha: "d778772" });
  if (result.state !== "READY_FOR_INTEGRATION" || result.orchestrator_arguments.stage !== "GROKCOM_RESULT") throw new Error("artifact fixture failed");
  if (classifyPreflight({}).state !== "BROWSER_UNAVAILABLE") throw new Error("browser fixture failed");
  if (classifyPreflight({ browser_bridge: true }).state !== "PAGE_BACKEND_UNAVAILABLE") throw new Error("backend fixture failed");
  if (classifyPreflight({ browser_bridge: true, page_backend: true, grok_page: "login" }).state !== "PROVIDER_SIGN_IN") throw new Error("sign-in fixture failed");
  if (classifyPreflight({ browser_bridge: true, page_backend: true, grok_page: "ready", conversation_url: "https://grok.com/c/abc" }).state !== "READY") throw new Error("ready fixture failed");
  if (!getBridge().automation_prompt.includes("GROK TASK")) throw new Error("automation fixture failed");
  const client = buildGrokCommonsClient({ task_id: "cloud-grok-test-20260828-01", event: { event_id: "Ev1", channel: SLACK_CHANNEL, message_ts: "1", text: "task" } });
  if (client.direction !== "bidirectional" || client.auth !== "none") throw new Error("Grok client direction fixture failed");
  if (client.forward_envelope.tool !== "route_grokcom_revenue_work") throw new Error("Grok forward fixture failed");
  if (!client.grok_prompt.includes("bidirectional Commons peer")) throw new Error("Grok prompt fixture failed");
  if (new Set(getBridge().receipt_fields).size !== getBridge().receipt_fields.length) throw new Error("duplicate receipt field");
  if (!getBridge().capture_tools.includes("start_grok_capture") || getBridge().continuation_state !== "GROK_CONTINUE") throw new Error("capture route fixture failed");
  if (!TOOLS.some((tool) => tool.name === "grok_slack_bridge")) throw new Error("grok slack tool missing");
  if (!getBridge().routes["grokcom-slack"] || getBridge().routes["grokcom-slack"].slack_app_id !== "A0BTJMFPTT6") throw new Error("grok slack route missing");
  if (callTool("grok_slack_bridge", {}).slack_app_id !== "A0BTJMFPTT6") throw new Error("grok slack tool fixture failed");
  if (callTool("grok_slack_bridge", {}).gemini_handoff_bind !== "127.0.0.1:8780") throw new Error("gemini isolation fixture failed");
  process.stdout.write("commons-grok-cloud self-test: PASS\n");
}

function runStdio() {
  let buffer = Buffer.alloc(0);
  process.stdin.on("data", (chunk) => { buffer = Buffer.concat([buffer, chunk]); drain(); });
  process.stdin.resume();

  function send(payload, mode) {
    if (!payload) return;
    const body = JSON.stringify(payload);
    if (mode === "content-length") process.stdout.write(`Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`);
    else process.stdout.write(body + "\n");
  }

  function drain() {
    while (buffer.length) {
      const text = buffer.toString("utf8");
      if (text.startsWith("Content-Length:")) {
        const headerEnd = text.indexOf("\r\n\r\n");
        if (headerEnd < 0) return;
        const match = /^Content-Length:\s*(\d+)/i.exec(text.slice(0, headerEnd));
        if (!match) throw new Error("invalid Content-Length frame");
        const headerBytes = Buffer.byteLength(text.slice(0, headerEnd + 4));
        const length = Number(match[1]);
        if (buffer.length < headerBytes + length) return;
        const body = buffer.subarray(headerBytes, headerBytes + length).toString("utf8");
        buffer = buffer.subarray(headerBytes + length);
        try { send(handle(JSON.parse(body)), "content-length"); }
        catch (error) { send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: String(error.message || error) } }, "content-length"); }
      } else {
        const newline = buffer.indexOf(10);
        if (newline < 0) return;
        const body = buffer.subarray(0, newline).toString("utf8").trim();
        buffer = buffer.subarray(newline + 1);
        if (!body) continue;
        try { send(handle(JSON.parse(body)), "jsonl"); }
        catch (error) { send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: String(error.message || error) } }, "jsonl"); }
      }
    }
  }
}

if (process.argv.includes("--self-test")) selfTest();
else if (process.argv.includes("--stdio")) runStdio();
else process.stdout.write(JSON.stringify(getBridge(), null, 2) + "\n");
