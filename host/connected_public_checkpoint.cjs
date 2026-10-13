'use strict';

// Bank only caller-selected public UTF-8 artifacts. Native journals stay private.
// No discovery, execution, retries, refs, commits, branches, PRs, or routing.

const SHA = /^[0-9a-f]{40}$/;
const LIMITS = Object.freeze({artifacts: 64, artifact_bytes: 2097152,
  total_bytes: 16777216, lineage: 32, manifest_bytes: 131072});

class PublicCheckpointError extends Error {
  constructor(code, message, progress, cause, response) {
    super(message);
    this.name = 'PublicCheckpointError';
    this.code = code;
    this.progress = JSON.parse(JSON.stringify(progress));
    Object.defineProperty(this, 'cause', {value: cause, enumerable: false});
    Object.defineProperty(this, 'response', {value: response, enumerable: false});
  }
  toJSON() {
    return {name: this.name, code: this.code, message: this.message, progress: this.progress};
  }
}

function fields(value, names, where) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value)) ||
      Object.getOwnPropertySymbols(value).length) {
    throw new TypeError(where + ' must be a plain data object');
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const result = Object.create(null);
  for (const key of Object.keys(descriptors)) {
    const descriptor = descriptors[key];
    if (!names.includes(key) || !descriptor.enumerable ||
        !Object.prototype.hasOwnProperty.call(descriptor, 'value')) {
      throw new TypeError(where + ' contains an unsupported field');
    }
    result[key] = descriptor.value;
  }
  return result;
}

function string(value, max, where) {
  if (typeof value !== 'string' || !value.length || value.length > max) {
    throw new TypeError(where + ' must be a nonempty bounded string');
  }
  return value;
}

function sha(value, where) {
  if (typeof value !== 'string' || !SHA.test(value)) throw new TypeError(where + ' must be a Git SHA-1');
  return value;
}

function repository(value) {
  string(value, 201, 'repository_full_name');
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value) ||
      value.split('/').some(part => part === '.' || part === '..')) {
    throw new TypeError('repository_full_name must be owner/repository');
  }
  return value;
}

function path(value) {
  string(value, 1024, 'path');
  if (value.includes('\\') || /[\x00-\x1f\x7f]/.test(value) ||
      value.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new TypeError('path must be a canonical relative artifact path');
  }
  return value;
}

function array(value, max, where) {
  if (!Array.isArray(value) || value.length > max || Object.getOwnPropertySymbols(value).length) {
    throw new TypeError(where + ' must be a bounded dense array');
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Object.keys(descriptors).length !== value.length + 1) throw new TypeError(where + ' has holes or extra fields');
  return Array.from({length: value.length}, (_, i) => {
    const item = descriptors[String(i)];
    if (!item || !item.enumerable || !Object.prototype.hasOwnProperty.call(item, 'value')) {
      throw new TypeError(where + ' must contain data elements only');
    }
    return item.value;
  });
}

function identityOf(identity, content, max, where) {
  // UTF-16 length is a lower bound for UTF-8 bytes for valid Unicode.
  if (typeof content !== 'string' || content.length > max) throw new RangeError(where + ' exceeds the content bound');
  const measured = identity(content);
  if (!measured || !Number.isSafeInteger(measured.bytes) || measured.bytes < 0 ||
      measured.bytes > max || typeof measured.git_blob_sha !== 'string' || !SHA.test(measured.git_blob_sha)) {
    throw new TypeError(where + ' has an invalid or over-budget identity');
  }
  return {bytes: measured.bytes, git_blob_sha: measured.git_blob_sha};
}

function lineageRecord(value) {
  const item = fields(value, ['repository_full_name', 'pr_number', 'commit_sha',
    'ref', 'path', 'blob_sha', 'bytes', 'observation'], 'lineage record');
  const result = {repository_full_name: repository(item.repository_full_name)};
  if ('pr_number' in item) {
    if (!Number.isSafeInteger(item.pr_number) || item.pr_number < 1) throw new TypeError('lineage pr_number is invalid');
    result.pr_number = item.pr_number;
  }
  if ('commit_sha' in item) result.commit_sha = sha(item.commit_sha, 'lineage commit_sha');
  if ('ref' in item) result.ref = string(item.ref, 256, 'lineage ref');
  if ('path' in item) result.path = path(item.path);
  if ('blob_sha' in item) result.blob_sha = sha(item.blob_sha, 'lineage blob_sha');
  if ('bytes' in item) {
    if (!Number.isSafeInteger(item.bytes) || item.bytes < 0) throw new TypeError('lineage bytes is invalid');
    result.bytes = item.bytes;
  }
  if ('observation' in item) result.observation = string(item.observation, 1024, 'lineage observation');
  return result;
}

/**
 * Bank a new public checkpoint with a manifest written after artifact ACKs.
 * Inject the verified gitBlobIdentity function and already-discovered binding.
 * Pass recorder-wrapped bindings to retain native requests/raw outcomes privately.
 */
async function bankPublicGitHubCheckpoint(tools, input, options = {}) {
  const settings = fields(options, ['git_blob_identity', 'binding', 'onProgress'], 'options');
  const identity = settings.git_blob_identity;
  if (typeof identity !== 'function') throw new TypeError('Supply the verified gitBlobIdentity function');
  const binding = 'binding' in settings
    ? string(settings.binding, 256, 'binding') : 'mcp__codex_apps__github_create_blob';
  if (typeof tools?.[binding] !== 'function') throw new TypeError('The configured create_blob binding is absent');
  if ('onProgress' in settings && typeof settings.onProgress !== 'function') {
    throw new TypeError('onProgress must be a function');
  }
  const given = fields(input, ['repository_full_name', 'checkpoint_id', 'stage',
    'lineage', 'previous_manifest_sha', 'artifacts'], 'input');
  const repo = repository(given.repository_full_name);
  const checkpointId = string(given.checkpoint_id, 160, 'checkpoint_id');
  const stage = string(given.stage, 160, 'stage');
  const lineage = 'lineage' in given
    ? array(given.lineage, LIMITS.lineage, 'lineage').map(lineageRecord) : [];
  const previous = 'previous_manifest_sha' in given
    ? sha(given.previous_manifest_sha, 'previous_manifest_sha') : null;
  const items = array(given.artifacts, LIMITS.artifacts, 'artifacts');
  if (!items.length) throw new TypeError('artifacts must not be empty');
  const paths = new Set();
  const bySHA = new Map();
  let totalBytes = 0;
  // Copy immutable strings and all manifest fields before the first await.
  const artifacts = items.map((value, index) => {
    const item = fields(value, ['path', 'role', 'content', 'expected_blob_sha'], 'artifact');
    const artifactPath = path(item.path);
    if (paths.has(artifactPath)) throw new TypeError('Duplicate artifact path');
    paths.add(artifactPath);
    const role = string(item.role, 80, 'artifact role');
    const measured = identityOf(identity, item.content, LIMITS.artifact_bytes, 'artifact');
    if ('expected_blob_sha' in item &&
        sha(item.expected_blob_sha, 'expected_blob_sha') !== measured.git_blob_sha) {
      throw new TypeError('Artifact content differs from its supplied expected blob SHA');
    }
    totalBytes += measured.bytes;
    if (totalBytes > LIMITS.total_bytes) throw new RangeError('Checkpoint exceeds the total content byte bound');
    const prior = bySHA.get(measured.git_blob_sha);
    if (prior && prior.content !== item.content) throw new TypeError('Distinct content shares one computed blob SHA');
    const record = {source_index: index, path: artifactPath, role, content: item.content,
      bytes: measured.bytes, computed_blob_sha: measured.git_blob_sha};
    if (!prior) bySHA.set(measured.git_blob_sha, record);
    return record;
  });

  const progress = {schema: 'commons.public_git_checkpoint_operation/v1',
    repository_full_name: repo, checkpoint_id: checkpointId, stage_label: stage,
    status: 'incomplete', phase: 'prepared', limits: {...LIMITS},
    previous_manifest_sha: previous, lineage,
    selected_artifacts: artifacts.length, selected_content_bytes: totalBytes,
    unique_content_blobs: bySHA.size, calls: 0, artifact_create_calls: 0,
    manifest_create_calls: 0, artifacts: artifacts.map(({content, ...metadata}) =>
      ({...metadata, disposition: 'pending', acknowledged_blob_sha: null, create_call: null})),
    manifest: null, public_selection: 'caller_supplied_not_classified',
    native_outcome_custody: 'caller_binding_responsibility',
    indefinite_git_retention: 'not_established'};
  // Preflight the complete manifest before any write. These are expected ACK
  // values; this text is banked only after every actual response matches them.
  const manifest = {schema: 'commons.public_git_checkpoint/v1',
    repository_full_name: repo, checkpoint_id: checkpointId,
    stage_label: stage, disposition: 'all_selected_artifact_blobs_acknowledged',
    previous_manifest_sha: previous, lineage,
    artifacts: artifacts.map(({path, role, bytes, computed_blob_sha}) =>
      ({path, role, bytes, computed_blob_sha, acknowledged_blob_sha: computed_blob_sha})),
    scope: {public_selection: 'caller_supplied_not_classified',
      lineage: 'caller_reported_not_refetched', computation_or_spec_validity: 'not_assessed',
      branch_or_commit_created: false, indefinite_git_retention: 'not_established'}};
  const content = JSON.stringify(manifest) + '\n';
  const measured = identityOf(identity, content, LIMITS.manifest_bytes, 'manifest');
  let lastResponse;
  let phase = 'progress';
  async function announce() {
    if (settings.onProgress) {
      phase = 'progress';
      await settings.onProgress(JSON.parse(JSON.stringify(progress)));
    }
  }
  async function create(content, expected, kind) {
    progress.calls++;
    progress[kind + '_create_calls']++;
    phase = 'binding';
    lastResponse = undefined;
    const response = await tools[binding]({repository_full_name: repo, content, encoding: 'utf-8'});
    lastResponse = response;
    phase = 'acknowledgement';
    if (!response || response.isError === true ||
        (response.isError !== undefined && typeof response.isError !== 'boolean') ||
        typeof response.structuredContent?.sha !== 'string' ||
        !SHA.test(response.structuredContent.sha)) {
      const error = new Error('Native create_blob did not return a usable acknowledgement');
      error.checkpoint_code = 'BLOB_ACKNOWLEDGEMENT_UNAVAILABLE';
      throw error;
    }
    if (response.structuredContent.sha !== expected) {
      const error = new Error('Native blob SHA differs from the independently computed identity');
      error.checkpoint_code = 'BLOB_IDENTITY_MISMATCH';
      throw error;
    }
    return {sha: response.structuredContent.sha, call: progress.calls};
  }
  try {
    await announce();
    const acknowledged = new Map();
    for (let index = 0; index < artifacts.length; index++) {
      const artifact = artifacts[index];
      const record = progress.artifacts[index];
      progress.phase = 'bank_artifact';
      let ack = acknowledged.get(artifact.computed_blob_sha);
      if (!ack) {
        ack = await create(artifact.content, artifact.computed_blob_sha, 'artifact');
        acknowledged.set(artifact.computed_blob_sha, ack);
        record.disposition = 'acknowledged';
      } else {
        record.disposition = 'shared_acknowledged_blob';
      }
      record.acknowledged_blob_sha = ack.sha;
      record.create_call = ack.call;
      await announce();
    }
    progress.phase = 'bank_manifest';
    progress.manifest = {bytes: measured.bytes, computed_blob_sha: measured.git_blob_sha,
      acknowledged_blob_sha: null, disposition: 'pending'};
    await announce();
    const ack = await create(content, measured.git_blob_sha, 'manifest');
    progress.manifest.acknowledged_blob_sha = ack.sha;
    progress.manifest.disposition = 'acknowledged';
    progress.manifest.create_call = ack.call;
    progress.status = 'complete';
    progress.phase = 'complete';
    await announce();
    return {...progress, manifest_content: content, recovery_locator: {
      repository_full_name: repo, manifest_blob_sha: ack.sha,
      manifest_bytes: measured.bytes, checkpoint_id: checkpointId}};
  } catch (cause) {
    const failurePhase = phase;
    progress.status = 'incomplete';
    progress.failure_phase = failurePhase;
    const code = cause?.checkpoint_code ??
      (failurePhase === 'progress' ? 'PROGRESS_RETENTION_FAILED' : 'BINDING_THROWN');
    throw new PublicCheckpointError(code, failurePhase === 'progress'
      ? 'Checkpoint progress retention failed; no further writes'
      : 'Checkpoint banking stopped; no further writes', progress, cause, lastResponse);
  }
}

module.exports = {bankPublicGitHubCheckpoint, PublicCheckpointError};
