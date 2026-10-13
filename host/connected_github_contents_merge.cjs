'use strict';

// Continue a confirmed Contents publication. This module never creates source
// objects, branches, files, or pull requests, and never retries a provider call.
const SHA = /^[a-f0-9]{40}$/;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const describe = error => String(error && error.message !== undefined ? error.message : error).slice(0, 1200);

function required(value, name) {
  if (typeof value !== 'string' || !value || value.length > 1024) throw new TypeError(name + ' must be a bounded nonempty string');
  return value;
}

function sha(value, name) {
  if (typeof value !== 'string' || !SHA.test(value)) throw new TypeError(name + ' must be an observed Git SHA');
  return value;
}

function branch(value, name) {
  required(value, name);
  if (value === '@' || value.startsWith('-') || value.startsWith('refs/')
      || /[\x00-\x20\x7f~^:?*\[\\]/.test(value) || value.includes('..') || value.includes('@{')
      || value.split('/').some(part => !part || part.startsWith('.') || part.endsWith('.') || part.endsWith('.lock'))) {
    throw new TypeError(name + ' must be a short Git branch name');
  }
  return value;
}

function prepared(change, saved) {
  if (!record(change) || !record(saved) || saved.operation !== 'contents_publication'
      || saved.branch_created !== true || saved.pending_write !== null) {
    throw new TypeError('Retain a Contents checkpoint with a confirmed branch and no pending write');
  }
  const repo = required(change.repository_full_name, 'repository_full_name');
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)
      || repo.split('/').some(part => part === '.' || part === '..')) throw new TypeError('Invalid repository_full_name');
  const base = branch(change.base_branch === undefined ? 'main' : change.base_branch, 'base_branch');
  const head = branch(change.branch_name, 'branch_name');
  if (base === head || change.merge !== true) throw new TypeError('Choose a separate branch and explicit merge: true');
  const method = change.merge_method === undefined ? 'merge' : change.merge_method;
  if (!['merge', 'squash', 'rebase'].includes(method)) throw new TypeError('Unsupported merge_method');
  for (const [key, expected] of [['repository_full_name', repo], ['base_branch', base], ['branch_name', head]]) {
    if (saved[key] !== expected) throw new TypeError('Contents checkpoint differs from prepared ' + key);
  }
  const baseSHA = sha(saved.base_commit_sha, 'Retained Contents base');
  const headSHA = sha(saved.commit_sha, 'Retained Contents head');
  if (!Array.isArray(change.files) || !change.files.length || change.files.length > 300
      || !Array.isArray(saved.files) || saved.files.length !== change.files.length
      || !Array.isArray(saved.serial_writes)) throw new TypeError('Retain the complete ordered Contents file set');
  const paths = new Set();
  const files = change.files.map((source, index) => {
    const retained = saved.files[index];
    if (!record(source) || !record(retained)) throw new TypeError('Invalid prepared or retained file');
    const path = required(source.path, 'file.path');
    if (/[\x00-\x1f\x7f\\]/.test(path) || path.split('/').some(part => !part || part === '.' || part === '..')
        || paths.has(path)) throw new TypeError('Noncanonical or repeated file path');
    paths.add(path);
    if (source.delete === true || source.mode !== undefined
        || (source.encoding !== undefined && source.encoding !== 'utf-8')
        || typeof source.content !== 'string') throw new TypeError('Continuation supports UTF-8 create/update without caller-selected modes');
    if (!own(source, 'expected_blob_sha')
        || (source.expected_blob_sha !== null && (typeof source.expected_blob_sha !== 'string'
          || !SHA.test(source.expected_blob_sha)))) throw new TypeError('Retain the observed file preimage or null');
    const next = sha(source.expected_new_blob_sha, 'Prepared new blob pin');
    if (retained.path !== path || retained.previous_blob_sha !== source.expected_blob_sha
        || retained.expected_new_blob_sha !== next
        || (retained.blob_sha !== undefined && retained.blob_sha !== next)
        || typeof retained.write_required !== 'boolean') throw new TypeError('Retained file versions differ from the prepared change');
    if (retained.write_required === false && source.expected_blob_sha !== next) throw new TypeError('Retained no-op file has a different preimage');
    return {source, retained, path, blob_sha: next, previous_blob_sha: source.expected_blob_sha};
  });
  for (const path of paths) {
    const parts = path.split('/');
    while (parts.length > 1) {
      parts.pop();
      if (paths.has(parts.join('/'))) throw new TypeError('A prepared file is also a parent path');
    }
  }
  const changed = files.filter(file => file.retained.write_required);
  if (!changed.length || saved.serial_writes.length !== changed.length) throw new TypeError('Every required Contents write must already be acknowledged');
  let parent = baseSHA;
  const writes = saved.serial_writes.map((write, index) => {
    const file = changed[index];
    const action = file.previous_blob_sha === null ? 'create_file' : 'update_file';
    if (!record(write) || write.path !== file.path || write.action !== action
        || write.parent_sha !== parent) throw new TypeError('Retained Contents writes have a different order or parent chain');
    const commit = sha(write.commit_sha, 'Acknowledged Contents commit');
    if (commit === parent
        || (write.response_blob_sha !== undefined && write.response_blob_sha !== file.blob_sha)
        || (write.commit_blob_sha !== undefined && write.commit_blob_sha !== file.blob_sha)) {
      throw new TypeError('Retained Contents acknowledgement has inconsistent versions');
    }
    parent = commit;
    return {path: file.path, action, parent_sha: write.parent_sha, commit_sha: commit, blob_sha: file.blob_sha};
  });
  if (parent !== headSHA) throw new TypeError('Retained Contents head does not end the acknowledged write chain');
  return {repo, base, head, method, baseSHA, headSHA, files, changed, writes};
}

function confirmedPR(saved, supplied) {
  let value;
  if (supplied !== undefined) {
    if (!record(supplied) || supplied.isError === true
        || (supplied.isError !== undefined && typeof supplied.isError !== 'boolean')
        || !record(supplied.structuredContent)) {
      throw new TypeError('confirmed_pull_request must be the successful native PR acknowledgement');
    }
    value = supplied.structuredContent;
    if (value.isError === true || value.ok === false || value.error != null || value.error_code != null
        || (Number.isInteger(value.status) && value.status >= 400)) {
      throw new TypeError('The confirmed PR acknowledgement reports an error');
    }
  } else value = saved.pull_request;
  if (!record(value) || !Number.isSafeInteger(value.number) || value.number < 1) {
    throw new TypeError('Retain a confirmed existing pull request; this continuation never creates one');
  }
  const head = sha(value.head_sha, 'Confirmed PR head');
  if (saved.pull_request !== undefined && supplied !== undefined
      && (saved.pull_request.number !== value.number || saved.pull_request.head_sha !== head)) {
    throw new TypeError('The supplied and retained pull requests differ');
  }
  return {number: value.number, head_sha: head,
    url: typeof value.url === 'string' ? value.url : typeof value.display_url === 'string' ? value.display_url : undefined};
}

async function settle(items, limit, read) {
  const results = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next++;
      try { results[index] = {status: 'fulfilled', value: await read(items[index])}; }
      catch (reason) { results[index] = {status: 'rejected', reason}; }
    }
  };
  await Promise.all(Array.from({length: Math.min(limit, items.length)}, worker));
  return results;
}

/**
 * Bind the existing publisher's literal readback and error helpers once.
 * The returned async continuation accepts tools, change, Contents progress,
 * and optional explicit bindings/confirmed PR/callbacks/readback concurrency.
 */
function createGitHubContentsMergeContinuation(publisher) {
  if (!record(publisher) || typeof publisher.resolveReadback !== 'function'
      || typeof publisher.inspectToolError !== 'function'
      || typeof publisher.GitHubPublishError !== 'function') {
    throw new TypeError('Supply the loaded connected_github_publish exports');
  }
  return async function continueGitHubContentsMerge(tools, change, saved, options = {}) {
    const progress = {operation: 'contents_merge_continuation', status: 'incomplete', stage: 'validate',
      calls: {}, files: [], pending_write: null, callback_errors: [], progress_callback_errors: [],
      mode_verification: 'not_performed', whole_tree_verification: 'not_performed'};
    let lastResponse;
    let lastFailureResponse;
    let announce = async () => {};
    try {
      if (!record(options) || Object.keys(options).some(key => !['bindings', 'confirmed_pull_request',
        'onResponse', 'onProgress', 'readback_concurrency'].includes(key))) throw new TypeError('Unsupported continuation option');
      for (const key of ['onResponse', 'onProgress']) {
        if (options[key] !== undefined && typeof options[key] !== 'function') throw new TypeError(key + ' must be a function');
      }
      const concurrency = options.readback_concurrency === undefined ? 4 : options.readback_concurrency;
      if (!Number.isSafeInteger(concurrency) || concurrency < 1 || concurrency > 16) throw new TypeError('readback_concurrency must be from 1 through 16');
      if (options.bindings !== undefined && (!record(options.bindings)
          || Object.keys(options.bindings).some(key => !['fetch', 'fetch_file', 'fetch_blob', 'merge_pull_request'].includes(key))
          || Object.values(options.bindings).some(value => typeof value !== 'string' || !value))) throw new TypeError('Invalid continuation bindings');
      const spec = prepared(change, saved);
      const retainedPR = confirmedPR(saved, options.confirmed_pull_request);
      if (retainedPR.head_sha !== spec.headSHA) throw new TypeError('Confirmed PR does not identify the acknowledged Contents head');
      Object.assign(progress, {repository_full_name: spec.repo, base_branch: spec.base,
        branch_name: spec.head, base_commit_sha: spec.baseSHA, commit_sha: spec.headSHA,
        readback_concurrency: concurrency, pull_request: retainedPR,
        files: spec.files.map(file => ({path: file.path, previous_blob_sha: file.previous_blob_sha, blob_sha: file.blob_sha})),
        retained_checkpoint_reconciliation_required: saved.reconciliation_required === true,
        serial_lineage_verification: 'retained_metadata_only', aggregate_paths_verification: 'not_performed'});
      const bindings = Object.fromEntries(['fetch', 'fetch_file', 'fetch_blob', 'merge_pull_request']
        .map(action => [action, options.bindings && options.bindings[action] || 'mcp__codex_apps__github_' + action]));
      const requireBinding = action => {
        if (!tools || typeof tools[bindings[action]] !== 'function') throw new Error('Binding not present: ' + bindings[action]);
      };
      requireBinding('fetch');
      requireBinding('fetch_file');
      announce = async () => {
        if (!options.onProgress) return;
        try { await options.onProgress(JSON.parse(JSON.stringify(progress))); }
        catch (error) { progress.progress_callback_errors.push(describe(error)); }
      };
      const call = async (action, args) => {
        requireBinding(action);
        progress.calls[action] = (progress.calls[action] || 0) + 1;
        lastResponse = undefined;
        const response = await tools[bindings[action]](args);
        lastResponse = response;
        if (options.onResponse) {
          try { await options.onResponse({action, binding: bindings[action], args, response}); }
          catch (error) { progress.callback_errors.push({action, message: describe(error)}); }
        }
        const nativeError = publisher.inspectToolError(action, response);
        if (nativeError) {
          lastFailureResponse = response;
          (progress.failed_responses || (progress.failed_responses = [])).push({action, binding: bindings[action], args, response});
          const error = new Error(nativeError.message);
          error.tool_error = nativeError;
          error.native_response = response;
          throw error;
        }
        const value = response && response.structuredContent;
        if (!record(value) || value.isError === true || value.ok === false || value.error != null || value.error_code != null
            || (Number.isInteger(value.status) && value.status >= 400)) {
          lastFailureResponse = response;
          (progress.failed_responses || (progress.failed_responses = [])).push({action, binding: bindings[action], args, response});
          const error = new TypeError('Native response has no successful structured payload');
          error.native_response = response;
          throw error;
        }
        return value;
      };
      const json = async url => {
        const value = await call('fetch', {url});
        const parsed = typeof value.content === 'string' ? JSON.parse(value.content) : value;
        if (!record(parsed)) throw new TypeError('Native resource must be a REST object');
        return parsed;
      };
      const api = 'https://api.github.com/repos/' + spec.repo;
      const refURL = name => api + '/git/ref/heads/' + name.split('/').map(encodeURIComponent).join('/');
      progress.stage = 'read_pull_request';
      const pr = await json(api + '/pulls/' + retainedPR.number);
      if (pr.number !== retainedPR.number || !record(pr.head) || pr.head.sha !== spec.headSHA
          || pr.head.ref !== spec.head || !record(pr.head.repo)
          || typeof pr.head.repo.full_name !== 'string' || pr.head.repo.full_name.toLowerCase() !== spec.repo.toLowerCase()
          || !record(pr.base) || pr.base.ref !== spec.base) throw new Error('Current PR differs from the confirmed Contents publication');
      if (typeof pr.html_url === 'string') progress.pull_request.url = pr.html_url;
      if (pr.merged === true) {
        if (pr.state !== 'closed') throw new Error('Merged PR has an inconsistent state');
        progress.merge_sha = sha(pr.merge_commit_sha, 'Existing Contents merge');
        progress.publication_status = 'merged';
        progress.merge_skipped = 'already_merged';
        await announce();
      } else {
        if (pr.merged !== false || pr.state !== 'open') throw new Error('PR is neither open nor confirmed merged');
        progress.publication_status = 'pull_request_open';
        progress.stage = 'reconcile_contents_lineage';
        for (const write of spec.writes) {
          const commit = await json(api + '/commits/' + write.commit_sha + '?per_page=2&page=1');
          const status = write.action === 'create_file' ? 'added' : 'modified';
          if (commit.sha !== write.commit_sha || !Array.isArray(commit.parents) || commit.parents.length !== 1
              || commit.parents[0].sha !== write.parent_sha || !Array.isArray(commit.files) || commit.files.length !== 1
              || commit.files[0].filename !== write.path || commit.files[0].status !== status
              || commit.files[0].sha !== write.blob_sha || commit.files[0].previous_filename !== undefined) {
            throw new Error('Observed Contents commit differs from the acknowledged sole-parent, sole-path chain');
          }
        }
        progress.serial_lineage_verification = 'observed';
        const comparison = await json(api + '/compare/' + spec.baseSHA + '...' + spec.headSHA + '?per_page=1&page=1');
        if (comparison.status !== 'ahead' || comparison.total_commits !== spec.writes.length
            || comparison.ahead_by !== spec.writes.length || comparison.behind_by !== 0
            || !record(comparison.base_commit) || comparison.base_commit.sha !== spec.baseSHA
            || !record(comparison.merge_base_commit)
            || comparison.merge_base_commit.sha !== spec.baseSHA || !Array.isArray(comparison.files)
            || comparison.files.length !== spec.changed.length
            || !spec.changed.every(file => comparison.files.some(item => item.filename === file.path
              && item.sha === file.blob_sha && item.status === (file.previous_blob_sha === null ? 'added' : 'modified')
              && item.previous_filename === undefined))) throw new Error('Contents aggregate paths differ from the prepared change');
        progress.aggregate_paths_verification = 'observed';
        const head = await json(refURL(spec.head));
        if (head.ref !== 'refs/heads/' + spec.head || !record(head.object)
            || head.object.type !== 'commit' || head.object.sha !== spec.headSHA) throw new Error('Contents branch moved; reconcile before merging');
        progress.stage = 'check_current_preimages';
        const base = await json(refURL(spec.base));
        if (base.ref !== 'refs/heads/' + spec.base || !record(base.object) || base.object.type !== 'commit') throw new Error('Current base ref is inconsistent');
        progress.current_base_commit_sha = sha(base.object.sha, 'Current pre-merge base');
        for (const file of spec.files) {
          try {
            const current = await call('fetch_file', {repository_full_name: spec.repo, path: file.path,
              ref: progress.current_base_commit_sha, encoding: 'utf-8'});
            if (current.sha !== file.previous_blob_sha) throw new Error('Current base file changed: ' + file.path);
          } catch (error) {
            if (file.previous_blob_sha !== null || !error.tool_error || error.tool_error.http_status !== 404) throw error;
          }
        }
        progress.current_preimages_verified = true;
        await announce();
        progress.stage = 'merge_pull_request';
        progress.pending_write = {action: 'merge_pull_request', pr_number: retainedPR.number,
          expected_head_sha: spec.headSHA, state: 'calling'};
        await announce();
        const merged = await call('merge_pull_request', {repository_full_name: spec.repo,
          pr_number: retainedPR.number, expected_head_sha: spec.headSHA, merge_method: spec.method});
        if (merged.merged !== true) throw new Error('Provider did not confirm the Contents merge');
        progress.merge_sha = sha(merged.sha, 'Contents merge');
        progress.merge_result = merged;
        progress.pending_write = null;
        progress.publication_status = 'merged';
        await announce();
      }
      progress.stage = 'readback';
      progress.readback_ref = progress.merge_sha;
      const readBlob = tools && typeof tools[bindings.fetch_blob] === 'function'
        ? blob_sha => call('fetch_blob', {repository_full_name: spec.repo, blob_sha}) : undefined;
      const reads = await settle(spec.files, concurrency, async file => {
        const data = await call('fetch_file', {repository_full_name: spec.repo,
          path: file.path, ref: progress.readback_ref, encoding: 'utf-8'});
        return publisher.resolveReadback({path: file.path, blob_sha: file.blob_sha}, file.source, data, readBlob);
      });
      progress.readback = reads.map((read, index) => read.status === 'fulfilled' ? read.value
        : {path: spec.files[index].path, matches: false, error: describe(read.reason),
          ...(read.reason.tool_error ? {tool_error: read.reason.tool_error} : {}),
          ...(read.reason.native_response ? {native_response: read.reason.native_response} : {})});
      progress.readback_status = progress.readback.every(read => read.matches === true) ? 'complete' : 'incomplete';
      if (progress.readback_status !== 'complete') throw new Error('Merged Contents readback is incomplete; retain the merge and reconcile readback only');
      progress.status = 'merged';
      progress.stage = 'complete';
      await announce();
      return progress;
    } catch (error) {
      if (error.tool_error) progress.tool_error = error.tool_error;
      progress.reconciliation_required = progress.pending_write !== null || progress.publication_status !== undefined;
      await announce();
      const failure = new publisher.GitHubPublishError(describe(error), progress, error);
      failure.response = error.native_response || lastFailureResponse || lastResponse;
      throw failure;
    }
  };
}

module.exports = {createGitHubContentsMergeContinuation};
