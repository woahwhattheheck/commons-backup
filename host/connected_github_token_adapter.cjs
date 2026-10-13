'use strict';

// Explicit bridge to the existing GitHub publishers' native argument contracts.
// The caller supplies discovered token tools and an optional explicit native blob
// binding; no credentials, network client, retry or automatic transport fallback.
const READ = 'mcp__codex_apps__github_token_connection_github_read';
const WRITE = 'mcp__codex_apps__github_token_connection_github_repository_write';
const ACTIONS = ['fetch', 'fetch_file', 'fetch_blob', 'create_blob', 'create_tree',
  'create_commit', 'create_branch', 'create_file', 'update_file',
  'create_pull_request', 'merge_pull_request'];
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function required(value, name) {
  if (typeof value !== 'string' || !value) throw new TypeError(name + ' is required');
  return value;
}

function repository(value) {
  required(value, 'repository_full_name');
  const parts = value.split('/');
  if (parts.length !== 2 || parts.some(part => !part || part === '.' || part === '..')) {
    throw new TypeError('repository_full_name must have owner/repository form');
  }
  return '/repos/' + parts.map(encodeURIComponent).join('/');
}

function pathPart(value, name) {
  required(value, name);
  return encodeURIComponent(value);
}

function queryPart(value) {
  // The token route accepts slash/colon separators but rejects encoded slashes.
  // Encode query delimiters and literal plus signs before exposing these separators.
  return encodeURIComponent(value).replace(/%2F/gi, '/').replace(/%3A/gi, ':');
}

function filePath(value) {
  required(value, 'path');
  const parts = value.split('/');
  if (parts.some(part => !part || part === '.' || part === '..')) {
    throw new TypeError('path must be a canonical repository file path');
  }
  return parts.map(encodeURIComponent).join('/');
}

function bytesFromBase64(value) {
  if (typeof value !== 'string') throw new TypeError('GitHub file content must be base64 text');
  const content = value.replace(/[\r\n\t ]/g, '');
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(content)) {
    throw new TypeError('GitHub file content is not complete base64');
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const bytes = [];
  for (let index = 0; index < content.length; index += 4) {
    const a = alphabet.indexOf(content[index]), b = alphabet.indexOf(content[index + 1]);
    const c = alphabet.indexOf(content[index + 2]), d = alphabet.indexOf(content[index + 3]);
    bytes.push((a << 2) | (b >> 4));
    if (c >= 0) bytes.push(((b & 15) << 4) | (c >> 2));
    if (d >= 0) bytes.push(((c & 3) << 6) | d);
  }
  return {base64: content, bytes};
}

function utf8(bytes) {
  // decodeURIComponent rejects malformed UTF-8 rather than replacing source bytes.
  return decodeURIComponent(bytes.map(value => '%' + value.toString(16).padStart(2, '0')).join(''));
}

function base64FromUtf8(value) {
  if (typeof value !== 'string') throw new TypeError('content must be complete UTF-8 text');
  const bytes = [];
  for (const char of value) {
    let cp = char.codePointAt(0);
    // Match normal UTF-8 encoding for a JavaScript string's unpaired surrogate.
    if (cp >= 0xd800 && cp <= 0xdfff) cp = 0xfffd;
    if (cp < 0x80) bytes.push(cp);
    else if (cp < 0x800) bytes.push(0xc0 | (cp >> 6), 0x80 | (cp & 63));
    else if (cp < 0x10000) bytes.push(0xe0 | (cp >> 12), 0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
    else bytes.push(0xf0 | (cp >> 18), 0x80 | ((cp >> 12) & 63),
      0x80 | ((cp >> 6) & 63), 0x80 | (cp & 63));
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let encoded = '';
  for (let index = 0; index < bytes.length; index += 3) {
    const a = bytes[index], b = bytes[index + 1], c = bytes[index + 2];
    encoded += alphabet[a >> 2] + alphabet[((a & 3) << 4) | ((b ?? 0) >> 4)]
      + (b === undefined ? '=' : alphabet[((b & 15) << 2) | ((c ?? 0) >> 6)])
      + (c === undefined ? '=' : alphabet[c & 63]);
  }
  return encoded;
}

function contentsPayload(data, update) {
  if (!object(data) || !/^[0-9a-f]{40}$/.test(data.commit?.sha ?? '')) {
    throw new TypeError('GitHub Contents write response lacks the resulting commit SHA');
  }
  const payload = {commit_sha: data.commit.sha};
  if (update) {
    if (!/^[0-9a-f]{40}$/.test(data.content?.sha ?? '')) {
      throw new TypeError('GitHub Contents update response lacks the resulting content SHA');
    }
    payload.content_sha = data.content.sha;
  }
  return payload;
}

function filePayload(data, args) {
  if (!object(data) || data.type !== 'file' || typeof data.sha !== 'string') {
    throw new TypeError('GitHub Contents response does not identify a file');
  }
  const encoding = args.encoding ?? 'utf-8';
  if (!['utf-8', 'base64'].includes(encoding)) throw new TypeError('encoding must be utf-8 or base64');
  if (data.path !== args.path) throw new TypeError('GitHub Contents response identifies a different path');
  const payload = {sha: data.sha, encoding, path: data.path,
    display_url: args.ref == null ? data.html_url
      : `https://github.com/${args.repository_full_name}/blob/${args.ref}/${args.path}`,
    display_title: data.path, size: data.size};
  // Contents may legitimately omit large-file bodies. Preserve omission for the
  // publisher's immutable blob readback instead of claiming an empty postimage.
  if (data.encoding === 'none' || !own(data, 'content')) return payload;
  if (data.encoding !== 'base64') throw new TypeError('GitHub Contents response has unsupported encoding');
  const decoded = bytesFromBase64(data.content);
  if (encoding === 'base64') {
    if (args.start_line != null || args.end_line != null) throw new TypeError('Line ranges require utf-8');
    payload.content = decoded.base64;
  } else {
    payload.content = utf8(decoded.bytes);
    if (args.start_line != null || args.end_line != null) {
      const start = args.start_line ?? 1, end = args.end_line;
      if (!Number.isSafeInteger(start) || start < 1
          || (end != null && (!Number.isSafeInteger(end) || end < start))) {
        throw new TypeError('Line range must use positive ordered integers');
      }
      // Preserve terminators so a whole-file request remains byte exact.
      const lines = payload.content.match(/[^\n]*\n|[^\n]+$/g) ?? [];
      payload.content = lines.slice(start - 1, end ?? lines.length).join('');
    }
  }
  return payload;
}

function blobPayload(data, args) {
  if (!object(data) || data.sha !== args.blob_sha || data.encoding !== 'base64') {
    throw new TypeError('GitHub blob response does not identify the requested base64 blob');
  }
  return {...data, content: utf8(bytesFromBase64(data.content).bytes), encoding: 'utf-8'};
}

function failure(response, wrapper, message) {
  const data = object(wrapper?.data) ? wrapper.data : {};
  const status = Number.isInteger(wrapper?.status) ? wrapper.status : undefined;
  const code = status === 404 && data.message === 'Not Found' ? 'NOT_FOUND'
    : typeof wrapper?.error_code === 'string' ? wrapper.error_code
      : message ? 'TOKEN_RESPONSE_SHAPE' : 'GITHUB_HTTP_ERROR';
  return {isError: true, content: response?.content ?? [],
    structuredContent: {error_code: code,
      error_data: {...data, ...(status === undefined ? {} : {status}),
        ...(object(wrapper?.headers) ? {headers: wrapper.headers} : {}),
        ...(message ? {message} : {})}}, token_response: response};
}

/** Return publisher-compatible functions plus options.bindings for explicit use. */
function createGitHubTokenAdapter(tools, options = {}) {
  const readBinding = options.read_binding ?? READ;
  const writeBinding = options.write_binding ?? WRITE;
  if (typeof tools?.[readBinding] !== 'function' || typeof tools?.[writeBinding] !== 'function') {
    throw new TypeError('Supply the discovered token read and repository write bindings');
  }
  const nativeCreateBlobBinding = options.native_create_blob_binding;
  if (nativeCreateBlobBinding !== undefined) {
    required(nativeCreateBlobBinding, 'native_create_blob_binding');
    if (typeof tools?.[nativeCreateBlobBinding] !== 'function') {
      throw new TypeError('Supply the selected native create-blob binding');
    }
  }
  if (options.onResponse !== undefined && typeof options.onResponse !== 'function') {
    throw new TypeError('onResponse must be a function');
  }
  const calls = [], surface = {};
  const bindings = Object.fromEntries(ACTIONS.map(action => [action, 'github_token_adapter_' + action]));
  const invoke = async (action, method, path, body, project = data => data) => {
    const binding = method === 'GET' ? readBinding : writeBinding;
    const record = {action, binding, method, path, outcome: 'pending'};
    calls.push(record);
    let response;
    try {
      response = await tools[binding](method === 'GET' ? {path} : {method, path, body});
    } catch (error) {
      record.outcome = 'threw';
      record.error = String(error?.message ?? error);
      throw error;
    }
    const wrapper = response?.structuredContent;
    if (Number.isInteger(wrapper?.status)) record.status = wrapper.status;
    record.outcome = response?.isError === true || wrapper?.ok === false
      || (Number.isInteger(wrapper?.status) && (wrapper.status < 200 || wrapper.status >= 300))
      ? 'provider_error' : 'returned';
    if (options.onResponse) {
      try { await options.onResponse({action, binding, method, path, response}); }
      catch (error) { record.callback_error = String(error?.message ?? error); }
    }
    if (record.outcome === 'provider_error') return failure(response, wrapper);
    if (!object(wrapper) || wrapper.ok !== true || !Number.isInteger(wrapper.status)
        || wrapper.status < 200 || wrapper.status >= 300 || !own(wrapper, 'data')) {
      record.outcome = 'response_shape';
      return failure(response, wrapper, 'Token response lacks a confirmed successful GitHub data envelope');
    }
    try {
      const payload = project(wrapper.data);
      if (!object(payload)) throw new TypeError(action + ' requires a GitHub object response');
      record.outcome = 'success';
      return {isError: false, structuredContent: payload, token_response: response};
    } catch (error) {
      record.outcome = 'response_shape';
      return failure(response, wrapper, String(error?.message ?? error));
    }
  };

  surface[bindings.fetch] = args => {
    const url = required(args.url, 'url');
    if (!url.startsWith('https://api.github.com/')) {
      throw new TypeError('The publisher adapter fetch contract uses GitHub REST API URLs');
    }
    // Preserve native URL parameter encoding except slash separators required
    // by the current token transport's relative-path parser.
    return invoke('fetch', 'GET', url.slice('https://api.github.com'.length).replace(/%2F/gi, '/'));
  };
  surface[bindings.fetch_file] = args => {
    const path = repository(args.repository_full_name) + '/contents/' + filePath(args.path)
      + (args.ref == null ? '' : '?ref=' + queryPart(args.ref));
    return invoke('fetch_file', 'GET', path, undefined, data => filePayload(data, args));
  };
  surface[bindings.fetch_blob] = args => invoke('fetch_blob', 'GET',
    repository(args.repository_full_name) + '/git/blobs/' + pathPart(args.blob_sha, 'blob_sha'),
    undefined, data => blobPayload(data, args));
  const invokeNativeCreateBlob = async args => {
    const binding = nativeCreateBlobBinding;
    const record = {action: 'create_blob', binding, transport: 'native', outcome: 'pending'};
    calls.push(record);
    let response;
    try { response = await tools[binding](args); }
    catch (error) {
      record.outcome = 'threw';
      record.error = String(error?.message ?? error);
      throw error;
    }
    record.outcome = response?.isError === true ? 'provider_error' : 'returned';
    if (options.onResponse) {
      try { await options.onResponse({action: 'create_blob', binding, transport: 'native', response}); }
      catch (error) { record.callback_error = String(error?.message ?? error); }
    }
    // The existing publisher already decodes its native response contract and
    // verifies the actual SHA against the prepared source pin. Keep that raw
    // envelope intact rather than forcing it through the token decoder.
    return response;
  };
  surface[bindings.create_blob] = args => nativeCreateBlobBinding === undefined
    ? invoke('create_blob', 'POST', repository(args.repository_full_name) + '/git/blobs',
      {content: args.content, encoding: args.encoding ?? 'utf-8'})
    : invokeNativeCreateBlob(args);
  surface[bindings.create_tree] = args => invoke('create_tree', 'POST',
    repository(args.repository_full_name) + '/git/trees',
    {tree: args.tree_elements, ...(args.base_tree_sha == null ? {} : {base_tree: args.base_tree_sha})});
  surface[bindings.create_commit] = args => invoke('create_commit', 'POST',
    repository(args.repository_full_name) + '/git/commits',
    {message: args.message, tree: args.tree_sha,
      parents: [args.parent_sha, ...(args.additional_parent_shas ?? [])]});
  surface[bindings.create_branch] = args => {
    // GitData publication already supplies the exact created commit. No existing
    // ref update or extra resolution read is needed by this adapter contract.
    if (args.base_ref != null || !/^[0-9a-f]{40}$/.test(args.sha ?? '')) {
      throw new TypeError('Publisher branch creation requires an exact commit sha');
    }
    return invoke('create_branch', 'POST', repository(args.repository_full_name) + '/git/refs',
      {ref: 'refs/heads/' + required(args.branch_name, 'branch_name'), sha: args.sha});
  };
  const contentsWrite = (action, args, update) => {
    if (update && !/^[0-9a-f]{40}$/.test(args.sha ?? '')) {
      throw new TypeError('Contents update requires the observed existing blob sha');
    }
    const path = repository(args.repository_full_name) + '/contents/' + filePath(args.path);
    const body = {message: required(args.message, 'message'), content: base64FromUtf8(args.content),
      ...(args.branch == null ? {} : {branch: args.branch}), ...(update ? {sha: args.sha} : {})};
    return invoke(action, 'PUT', path, body, data => contentsPayload(data, update));
  };
  surface[bindings.create_file] = args => contentsWrite('create_file', args, false);
  surface[bindings.update_file] = args => contentsWrite('update_file', args, true);
  surface[bindings.create_pull_request] = args => {
    const body = {};
    for (const key of ['title', 'body', 'draft', 'head_repo', 'issue', 'maintainer_can_modify']) {
      if (args[key] != null) body[key] = args[key];
    }
    if (args.head != null || args.head_branch != null) body.head = args.head ?? args.head_branch;
    if (args.base != null || args.base_branch != null) body.base = args.base ?? args.base_branch;
    return invoke('create_pull_request', 'POST', repository(args.repository_full_name) + '/pulls', body,
      data => ({...data, url: data.html_url, head_sha: data.head?.sha}));
  };
  surface[bindings.merge_pull_request] = args => {
    const body = {};
    for (const key of ['commit_title', 'commit_message', 'merge_method']) {
      if (args[key] != null) body[key] = args[key];
    }
    if (args.expected_head_sha != null) body.sha = args.expected_head_sha;
    return invoke('merge_pull_request', 'PUT', repository(args.repository_full_name)
      + '/pulls/' + args.pr_number + '/merge', body);
  };
  return {tools: surface, bindings, calls};
}

module.exports = {createGitHubTokenAdapter};

