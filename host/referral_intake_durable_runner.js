#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const CORE_PATH = process.env.REFERRAL_INTAKE_CORE_PATH || path.resolve(__dirname, "..", "referral-intake-completeness.js");
const core = require(CORE_PATH);

const JOURNAL_SCHEMA = "commons-referral-intake-durable-journal-v1";
const RECEIPT_SCHEMA = "commons-referral-intake-durable-receipt-v1";
const VERIFY_SCHEMA = "commons-referral-intake-journal-verification-v1";
const INJECTED_CRASH_EXIT = 75;
const SHA256_RE = /^[0-9a-f]{64}$/;

class RunnerError extends Error {
  constructor(code, message, exitCode) {
    super(message);
    this.name = "RunnerError";
    this.code = code;
    this.exitCode = exitCode || 1;
  }
}

function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
  }
  const rendered = JSON.stringify(value);
  if (rendered === undefined) throw new RunnerError("NON_JSON_VALUE", "value is outside the JSON data model");
  return rendered;
}

function sha256Text(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function jsonClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function readJsonFile(filePath, label) {
  let stat;
  try {
    stat = fs.lstatSync(filePath);
  } catch (error) {
    if (error && error.code === "ENOENT") throw new RunnerError("FILE_NOT_FOUND", label + " file does not exist");
    throw new RunnerError("FILE_READ_FAILED", label + " file could not be inspected");
  }
  if (stat.isSymbolicLink()) throw new RunnerError("SYMLINK_REFUSED", label + " path must not be a symbolic link");
  if (!stat.isFile()) throw new RunnerError("NOT_A_FILE", label + " path must be a regular file");
  let raw;
  try {
    raw = fs.readFileSync(filePath);
  } catch (_error) {
    throw new RunnerError("FILE_READ_FAILED", label + " file could not be read");
  }
  let value;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch (_error) {
    throw new RunnerError("INVALID_JSON", label + " file is not valid JSON");
  }
  return { value, raw, fileSha256: sha256Bytes(raw) };
}

function assertSafeTarget(filePath, label) {
  try {
    const stat = fs.lstatSync(filePath);
    if (stat.isSymbolicLink()) throw new RunnerError("SYMLINK_REFUSED", label + " path must not be a symbolic link");
    if (!stat.isFile()) throw new RunnerError("NOT_A_FILE", label + " target must be a regular file");
  } catch (error) {
    if (error instanceof RunnerError) throw error;
    if (!error || error.code !== "ENOENT") throw new RunnerError("TARGET_INSPECTION_FAILED", label + " target could not be inspected");
  }
}

function atomicWriteJson(filePath, value, label) {
  const resolved = path.resolve(filePath);
  const dir = path.dirname(resolved);
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  } catch (_error) {
    throw new RunnerError("DIRECTORY_CREATE_FAILED", label + " directory could not be created");
  }
  assertSafeTarget(resolved, label);
  const data = Buffer.from(JSON.stringify(value, null, 2) + "\n", "utf8");
  const temp = path.join(dir, "." + path.basename(resolved) + ".tmp-" + process.pid + "-" + crypto.randomBytes(8).toString("hex"));
  let fd;
  try {
    fd = fs.openSync(temp, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o600);
    let offset = 0;
    while (offset < data.length) offset += fs.writeSync(fd, data, offset, data.length - offset, offset);
    fs.fsyncSync(fd);
    fs.closeSync(fd);
    fd = undefined;
    fs.renameSync(temp, resolved);
    const dirFd = fs.openSync(dir, fs.constants.O_RDONLY);
    try { fs.fsyncSync(dirFd); } finally { fs.closeSync(dirFd); }
  } catch (_error) {
    if (fd !== undefined) { try { fs.closeSync(fd); } catch (_) {} }
    try { fs.unlinkSync(temp); } catch (_) {}
    throw new RunnerError("ATOMIC_WRITE_FAILED", label + " could not be published atomically");
  }
  return { fileSha256: sha256Bytes(data), bytes: data.length };
}

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return Boolean(error && error.code === "EPERM");
  }
}

function acquireLock(journalPath) {
  const lockPath = path.resolve(journalPath) + ".lock";
  const ownerPath = path.join(lockPath, "owner.json");
  fs.mkdirSync(path.dirname(lockPath), { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      fs.mkdirSync(lockPath, { mode: 0o700 });
      fs.writeFileSync(ownerPath, JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() }) + "\n", { mode: 0o600, flag: "wx" });
      return function release() {
        try { fs.rmSync(lockPath, { recursive: true, force: true }); } catch (_) {}
      };
    } catch (error) {
      if (!error || error.code !== "EEXIST") throw new RunnerError("LOCK_FAILED", "journal lock could not be created");
      let owner = null;
      try { owner = JSON.parse(fs.readFileSync(ownerPath, "utf8")); } catch (_) {}
      if (owner && processAlive(owner.pid)) throw new RunnerError("JOURNAL_BUSY", "journal is already owned by another live process");
      const stale = lockPath + ".stale-" + process.pid + "-" + crypto.randomBytes(6).toString("hex");
      try {
        fs.renameSync(lockPath, stale);
        fs.rmSync(stale, { recursive: true, force: true });
      } catch (_error) {
        continue;
      }
    }
  }
  throw new RunnerError("STALE_LOCK_RACE", "journal stale-lock recovery did not converge");
}

function safeIdentity(input) {
  const source = input && typeof input === "object" ? input : {};
  return {
    referralId: String(source.referralId || ""),
    referralClass: String(source.referralClass || "")
  };
}

function sanitizeJournal(coreJournal) {
  const copy = jsonClone(coreJournal || core.createJournal());
  if (!copy.referrals || typeof copy.referrals !== "object" || Array.isArray(copy.referrals)) copy.referrals = {};
  Object.keys(copy.referrals).forEach((id) => {
    const state = copy.referrals[id];
    if (!state || typeof state !== "object") return;
    state.input = safeIdentity(state.input);
    const receipt = state.effects && state.effects.intakeReceipt;
    if (receipt && receipt.kind === "INTAKE_REFUSAL_RECEIPT" && Array.isArray(receipt.hits)) {
      receipt.hitCount = receipt.hits.length;
      receipt.hitKeysSha256 = sha256Text(canonical(receipt.hits.slice().sort()));
      delete receipt.hits;
    }
  });
  return copy;
}

function unsignedEnvelope(envelope) {
  const copy = jsonClone(envelope);
  delete copy.integritySha256;
  return copy;
}

function sealEnvelope(envelope) {
  const copy = jsonClone(envelope);
  delete copy.integritySha256;
  copy.integritySha256 = sha256Text(canonical(copy));
  return copy;
}

function emptyEnvelope() {
  return sealEnvelope({
    schema: JOURNAL_SCHEMA,
    coreVersion: core.VERSION,
    generation: 0,
    referrals: {},
    packetBindings: {},
    updatedAt: null
  });
}

function validateEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) throw new RunnerError("INVALID_JOURNAL", "journal root must be an object");
  if (envelope.schema !== JOURNAL_SCHEMA) throw new RunnerError("JOURNAL_SCHEMA_MISMATCH", "journal schema is not supported");
  if (envelope.coreVersion !== core.VERSION) throw new RunnerError("CORE_VERSION_MISMATCH", "journal core version does not match this runner");
  if (!Number.isInteger(envelope.generation) || envelope.generation < 0) throw new RunnerError("INVALID_GENERATION", "journal generation must be a non-negative integer");
  if (!envelope.referrals || typeof envelope.referrals !== "object" || Array.isArray(envelope.referrals)) throw new RunnerError("INVALID_REFERRALS", "journal referrals must be an object");
  if (!envelope.packetBindings || typeof envelope.packetBindings !== "object" || Array.isArray(envelope.packetBindings)) throw new RunnerError("INVALID_BINDINGS", "journal packet bindings must be an object");
  Object.keys(envelope.packetBindings).forEach((id) => {
    if (!SHA256_RE.test(String(envelope.packetBindings[id] || ""))) throw new RunnerError("INVALID_BINDING_SHA256", "journal packet binding is malformed");
  });
  if (!SHA256_RE.test(String(envelope.integritySha256 || ""))) throw new RunnerError("INVALID_JOURNAL_SHA256", "journal integrity digest is malformed");
  const expected = sha256Text(canonical(unsignedEnvelope(envelope)));
  if (expected !== envelope.integritySha256) throw new RunnerError("JOURNAL_INTEGRITY_MISMATCH", "journal integrity digest does not match its canonical content");
  return envelope;
}

function loadEnvelope(journalPath) {
  try {
    const loaded = readJsonFile(journalPath, "journal");
    return { envelope: validateEnvelope(loaded.value), fileSha256: loaded.fileSha256, existed: true };
  } catch (error) {
    if (error instanceof RunnerError && error.code === "FILE_NOT_FOUND") return { envelope: emptyEnvelope(), fileSha256: null, existed: false };
    throw error;
  }
}

function coreJournalFromEnvelope(envelope) {
  return { version: core.VERSION, referrals: jsonClone(envelope.referrals) };
}

function packetIdentity(packet) {
  const referralId = String(packet && packet.referralId != null ? packet.referralId : "").trim().toUpperCase();
  return {
    referralId,
    packetCanonicalSha256: sha256Text(canonical(packet))
  };
}

function durableReceipt(coreResult, meta) {
  const receipt = {
    schema: RECEIPT_SCHEMA,
    core: coreResult,
    durability: meta
  };
  receipt.receiptSha256 = sha256Text(canonical(receipt));
  return receipt;
}

function persistEnvelope(journalPath, priorEnvelope, coreJournal, packetBindings, now) {
  const next = sealEnvelope({
    schema: JOURNAL_SCHEMA,
    coreVersion: core.VERSION,
    generation: priorEnvelope.generation + 1,
    referrals: sanitizeJournal(coreJournal).referrals,
    packetBindings: jsonClone(packetBindings),
    updatedAt: now
  });
  const write = atomicWriteJson(journalPath, next, "journal");
  return { envelope: next, write };
}

function loadPacket(packetPath) {
  const loaded = readJsonFile(packetPath, "packet");
  if (!loaded.value || typeof loaded.value !== "object" || Array.isArray(loaded.value)) throw new RunnerError("INVALID_PACKET", "packet JSON root must be an object");
  return loaded;
}

function runPacket(args) {
  if (!args.packet || !args.journal) throw new RunnerError("USAGE", "run requires --packet and --journal", 2);
  if (args.crashAt && !["after_checklist", "after_queue"].includes(args.crashAt)) throw new RunnerError("USAGE", "--crash-at must be after_checklist or after_queue", 2);
  const packetLoaded = loadPacket(args.packet);
  const packet = packetLoaded.value;
  const identity = packetIdentity(packet);
  const now = args.now || new Date().toISOString();
  const release = acquireLock(args.journal);
  try {
    const loaded = loadEnvelope(args.journal);
    const prior = loaded.envelope;
    const bindings = jsonClone(prior.packetBindings);
    if (identity.referralId && bindings[identity.referralId] && bindings[identity.referralId] !== identity.packetCanonicalSha256) {
      throw new RunnerError("DURABLE_PACKET_CONFLICT", "same referral id is already bound to different canonical packet bytes");
    }
    const journal = coreJournalFromEnvelope(prior);
    const coreResult = core.processReferral(packet, journal, { now, crashAt: args.crashAt || "" });
    const resultId = String(coreResult && coreResult.referralId || identity.referralId || "").trim().toUpperCase();
    let stored = true;
    if (coreResult && coreResult.status === "PHI_REFUSED") {
      if (resultId) delete journal.referrals[resultId];
      if (resultId) delete bindings[resultId];
      stored = false;
    } else if (resultId) {
      bindings[resultId] = identity.packetCanonicalSha256;
    }
    const persisted = persistEnvelope(args.journal, prior, journal, bindings, now);
    const receipt = durableReceipt(coreResult, {
      journalSchema: JOURNAL_SCHEMA,
      generationBefore: prior.generation,
      generationAfter: persisted.envelope.generation,
      journalIntegritySha256: persisted.envelope.integritySha256,
      journalFileSha256: persisted.write.fileSha256,
      packetCanonicalSha256: identity.packetCanonicalSha256,
      packetFileSha256: packetLoaded.fileSha256,
      statePersisted: stored,
      privacy: stored ? "RAW_PACKET_FIELDS_NOT_STORED" : "PHI_REFUSAL_STATE_NOT_STORED",
      crashCheckpoint: args.crashAt || null
    });
    return { receipt, exitCode: String(coreResult && coreResult.status || "").startsWith("CRASHED_") ? INJECTED_CRASH_EXIT : 0 };
  } finally {
    release();
  }
}

function rollbackPacket(args) {
  if (!args.referralId || !args.journal) throw new RunnerError("USAGE", "rollback requires --referral-id and --journal", 2);
  const now = args.now || new Date().toISOString();
  const release = acquireLock(args.journal);
  try {
    const loaded = loadEnvelope(args.journal);
    if (!loaded.existed) throw new RunnerError("JOURNAL_NOT_FOUND", "cannot rollback without an existing journal");
    const prior = loaded.envelope;
    const journal = coreJournalFromEnvelope(prior);
    const coreResult = core.rollback(args.referralId, journal, { now });
    const persisted = persistEnvelope(args.journal, prior, journal, prior.packetBindings, now);
    const receipt = durableReceipt(coreResult, {
      journalSchema: JOURNAL_SCHEMA,
      generationBefore: prior.generation,
      generationAfter: persisted.envelope.generation,
      journalIntegritySha256: persisted.envelope.integritySha256,
      journalFileSha256: persisted.write.fileSha256,
      packetCanonicalSha256: prior.packetBindings[String(args.referralId).trim().toUpperCase()] || null,
      packetFileSha256: null,
      statePersisted: true,
      privacy: "RAW_PACKET_FIELDS_NOT_STORED",
      crashCheckpoint: null
    });
    return { receipt, exitCode: 0 };
  } finally {
    release();
  }
}

function verifyJournal(args) {
  if (!args.journal) throw new RunnerError("USAGE", "verify requires --journal", 2);
  const loaded = loadEnvelope(args.journal);
  if (!loaded.existed) throw new RunnerError("JOURNAL_NOT_FOUND", "journal does not exist");
  const envelope = loaded.envelope;
  const report = {
    schema: VERIFY_SCHEMA,
    valid: true,
    coreVersion: envelope.coreVersion,
    generation: envelope.generation,
    referralCount: Object.keys(envelope.referrals).length,
    packetBindingCount: Object.keys(envelope.packetBindings).length,
    journalIntegritySha256: envelope.integritySha256,
    journalFileSha256: loaded.fileSha256
  };
  report.verificationSha256 = sha256Text(canonical(report));
  return { receipt: report, exitCode: 0 };
}

function writeReceiptIfRequested(args, receipt) {
  if (args.receipt) atomicWriteJson(args.receipt, receipt, "receipt");
}

function fileEntryPath(filePath) {
  let directory = path.dirname(filePath);
  const suffix = [path.basename(filePath)];
  while (true) {
    try {
      // Compare directory entries, not inodes: replacing a separate hard link
      // with an atomic rename leaves the input's directory entry intact.
      return path.join(fs.realpathSync(directory), ...suffix);
    } catch (error) {
      const parent = path.dirname(directory);
      if (!error || error.code !== "ENOENT" || parent === directory) {
        throw new RunnerError("PATH_RESOLUTION_FAILED", "receipt or input directory could not be resolved");
      }
      suffix.unshift(path.basename(directory));
      directory = parent;
    }
  }
}

function assertDistinctReceiptPath(args) {
  if (!args.receipt) return;
  // atomicWriteJson resolves the destination before opening its directory.
  const receipt = fileEntryPath(path.resolve(args.receipt));
  const inputs = [["journal", args.journal]];
  if (args.journal && (args.command === "run" || args.command === "rollback")) {
    inputs.push(["journal", path.resolve(args.journal)]);
  }
  if (args.command === "run") inputs.push(["packet", args.packet]);
  for (const [label, filePath] of inputs) {
    if (filePath && receipt === fileEntryPath(filePath)) {
      throw new RunnerError("OUTPUT_PATH_COLLISION", "receipt path must differ from " + label + " path", 2);
    }
  }
}

function parseArgs(argv) {
  if (!argv.length) throw new RunnerError("USAGE", "expected command: run, rollback, or verify", 2);
  const command = argv[0];
  const parsed = { command };
  for (let i = 1; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) throw new RunnerError("USAGE", "unexpected positional argument", 2);
    const name = token.slice(2);
    if (!["packet", "journal", "now", "crash-at", "receipt", "referral-id"].includes(name)) throw new RunnerError("USAGE", "unknown option --" + name, 2);
    if (i + 1 >= argv.length || argv[i + 1].startsWith("--")) throw new RunnerError("USAGE", "missing value for --" + name, 2);
    const value = argv[++i];
    const key = name.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
    parsed[key] = value;
  }
  return parsed;
}

function safeErrorReceipt(error) {
  const code = error instanceof RunnerError ? error.code : "UNEXPECTED_ERROR";
  const message = error instanceof RunnerError ? error.message : "unexpected runner failure";
  const receipt = { schema: RECEIPT_SCHEMA, status: "FAILED", error: { code, message } };
  receipt.receiptSha256 = sha256Text(canonical(receipt));
  return { receipt, exitCode: error instanceof RunnerError ? error.exitCode : 1 };
}

function main(argv) {
  try {
    const args = parseArgs(argv);
    assertDistinctReceiptPath(args);
    let result;
    if (args.command === "run") result = runPacket(args);
    else if (args.command === "rollback") result = rollbackPacket(args);
    else if (args.command === "verify") result = verifyJournal(args);
    else throw new RunnerError("USAGE", "unknown command", 2);
    writeReceiptIfRequested(args, result.receipt);
    process.stdout.write(JSON.stringify(result.receipt, null, 2) + "\n");
    return result.exitCode;
  } catch (error) {
    const result = safeErrorReceipt(error);
    process.stdout.write(JSON.stringify(result.receipt, null, 2) + "\n");
    return result.exitCode;
  }
}

if (require.main === module) process.exitCode = main(process.argv.slice(2));

module.exports = {
  JOURNAL_SCHEMA,
  RECEIPT_SCHEMA,
  VERIFY_SCHEMA,
  INJECTED_CRASH_EXIT,
  canonical,
  sha256Text,
  sanitizeJournal,
  sealEnvelope,
  validateEnvelope,
  main
};
