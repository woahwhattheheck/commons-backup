'use strict';

// Native Slack bindings only. No transport, credentials, automatic retry or text rewrite.
class SlackPublishError extends Error {
  constructor(message, progress, cause) {
    super(message);
    this.name = 'SlackPublishError';
    this.progress = progress;
    this.cause = cause;
  }
}

function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(label + ' must be an object');
  }
  return value;
}

function text(value, label) {
  if (typeof value !== 'string' || !value.trim()) throw new TypeError(label + ' is required');
  return value;
}

function timestamp(value, label) {
  if (typeof value !== 'string' || !/^\d+\.\d+$/.test(value)) {
    throw new TypeError(label + ' must be the observed Slack timestamp string');
  }
  return value;
}

function unpack(result, action) {
  object(result, action + ' response');
  if (result.isError === true) throw new Error(action + ' returned a native tool error');
  if (result.structuredContent && typeof result.structuredContent === 'object'
      && !Array.isArray(result.structuredContent)) return result.structuredContent;
  for (const block of result.content ?? []) {
    if (block?.type !== 'text' || typeof block.text !== 'string') continue;
    try { return object(JSON.parse(block.text), action + ' payload'); }
    catch (_) { /* Try the next native text block. */ }
  }
  throw new Error(action + ' did not return a readable native acknowledgement');
}


function readbackBinding(tools, options) {
  const name = options.bindings?.readback ?? 'mcp__codex_apps__slack_slack_read_thread';
  if (typeof tools?.[name] !== 'function') {
    throw new Error('Binding not present: ' + name
      + '. Repeat discovery alongside useful work.');
  }
  return name;
}

function readbackArguments(progress, options) {
  const channel = text(progress.channel_id, 'confirmed channel_id');
  const target = timestamp(progress.message_id, 'confirmed message_id');
  const parent = timestamp(options.readback_thread_ts ?? progress.readback_thread_ts
    ?? progress.thread_ts ?? target, 'readback thread timestamp');
  const args = {channel_id: channel, message_ts: parent, limit: 1};
  if (parent !== target) {
    // Read only the selected reply's timestamp window, not the surrounding feed.
    const [seconds, fractional] = target.split('.');
    const precision = Math.max(6, fractional.length);
    const ticks = BigInt(seconds + fractional.padEnd(precision, '0'));
    const format = value => {
      const digits = String(value).padStart(precision + 1, '0');
      return digits.slice(0, -precision) + '.' + digits.slice(-precision);
    };
    args.oldest = format(ticks > 0n ? ticks - 1n : 0n);
    args.latest = format(ticks + 1n);
  }
  return args;
}

/** Capture one native read for a confirmed edit; never repeat its send or edit. */
async function readSlackPublication(tools, published, options = {}) {
  const progress = {status: 'incomplete', stage: 'validate_readback',
    message_state: 'not_selected', calls: {}, readback_status: 'not_performed',
    progress_callback_errors: 0};
  let lastResponse;
  let announce = async () => {};
  try {
    object(published, 'published progress');
    // Provider bodies stay outside observer metadata, including on continuation.
    for (const key of ['status', 'stage', 'message_state', 'readback_status',
      'progress_callback_errors', 'channel_id', 'message_id', 'message_link',
      'thread_ts', 'readback_thread_ts', 'readback_request']) {
      if (published[key] !== undefined) progress[key] = published[key];
    }
    progress.calls = {...object(published.calls ?? {}, 'published call counts')};
    progress.stage = 'validate_readback';
    progress.readback_status = 'not_performed';
    if (progress.message_state !== 'edit_confirmed') {
      throw new TypeError('Readback continuation requires a confirmed edit');
    }
    const observer = options.onProgress;
    if (observer !== undefined && typeof observer !== 'function') {
      throw new TypeError('onProgress must be a function');
    }
    announce = async () => {
      if (!observer) return;
      try { await observer(JSON.parse(JSON.stringify(progress))); }
      catch (_) { progress.progress_callback_errors += 1; }
    };
    const binding = readbackBinding(tools, options);
    const args = readbackArguments(progress, options);
    progress.readback_request = args;
    progress.readback_thread_ts = args.message_ts;
    progress.stage = 'readback';
    progress.readback_status = 'pending';
    await announce();
    progress.calls.readback = (progress.calls.readback ?? 0) + 1;
    lastResponse = await tools[binding](args);
    unpack(lastResponse, 'readback');
    progress.readback_status = 'captured';
    progress.stage = 'complete';
    await announce();
    return {...progress, readback_response: lastResponse};
  } catch (error) {
    if (progress.readback_status === 'pending') progress.readback_status = 'failed';
    await announce();
    const failure = new SlackPublishError(String(error?.message ?? error), progress, error);
    failure.response = lastResponse;
    throw failure;
  }
}

/** Send and restore the caller's exact text, or edit one already-confirmed message. */
async function publishSlackMessage(tools, request, options = {}) {
  const progress = {status: 'incomplete', stage: 'validate', message_state: 'not_attempted',
    calls: {}, readback_status: 'not_performed', progress_callback_errors: 0};
  let lastResponse;
  let announce = async () => {};
  try {
    object(request, 'request');
    const allowed = new Set(['channel_id', 'message', 'message_id', 'thread_ts',
      'reply_broadcast', 'unfurl_app_links']);
    for (const key of Object.keys(request)) {
      if (!allowed.has(key)) throw new TypeError('Unsupported request field: ' + key);
    }
    const channel = text(request.channel_id, 'channel_id');
    const message = text(request.message, 'message');
    const editing = request.message_id !== undefined;
    const messageId = editing ? timestamp(request.message_id, 'message_id') : undefined;
    const thread = request.thread_ts === undefined ? undefined : timestamp(request.thread_ts, 'thread_ts');
    if (editing && thread !== undefined) throw new TypeError('thread_ts applies only to a new send');
    const sendOptions = {};
    for (const key of ['reply_broadcast', 'unfurl_app_links']) {
      if (request[key] === undefined) continue;
      if (typeof request[key] !== 'boolean') throw new TypeError(key + ' must be boolean');
      if (editing) throw new TypeError(key + ' applies only to a new send');
      sendOptions[key] = request[key];
    }
    const bindings = {
      send: options.bindings?.send ?? 'mcp__codex_apps__slack_slack_send_message',
      edit: options.bindings?.edit ?? 'mcp__codex_apps__slack_slack_edit_message',
    };
    for (const action of editing ? ['edit'] : ['send', 'edit']) {
      if (typeof tools?.[bindings[action]] !== 'function') {
        throw new Error('Binding not present: ' + bindings[action]
          + '. Repeat discovery alongside useful work.');
      }
    }
    if (options.readback !== undefined && typeof options.readback !== 'boolean') {
      throw new TypeError('readback must be boolean');
    }
    if (options.readback_thread_ts !== undefined) {
      timestamp(options.readback_thread_ts, 'readback_thread_ts');
      if (thread !== undefined && options.readback_thread_ts !== thread) {
        throw new TypeError('readback_thread_ts differs from the new message thread');
      }
    }
    if (options.readback === true) readbackBinding(tools, options);
    const observer = options.onProgress;
    if (observer !== undefined && typeof observer !== 'function') throw new TypeError('onProgress must be a function');
    announce = async () => {
      if (!observer) return;
      try { await observer(JSON.parse(JSON.stringify(progress))); }
      catch (_) { progress.progress_callback_errors += 1; }
    };
    const call = async (action, args) => {
      progress.calls[action] = (progress.calls[action] ?? 0) + 1;
      lastResponse = undefined;
      lastResponse = await tools[bindings[action]](args);
      return unpack(lastResponse, action);
    };
    progress.channel_id = channel;
    if (thread !== undefined) progress.thread_ts = thread;
    if (editing) {
      progress.message_id = messageId;
      progress.message_state = 'existing_message_selected';
    } else {
      progress.stage = 'send';
      progress.message_state = 'send_outcome_unknown';
      await announce();
      const sent = await call('send', {channel_id: channel, message,
        ...(thread === undefined ? {} : {thread_ts: thread}), ...sendOptions});
      const context = object(sent.message_context, 'send message_context');
      progress.channel_id = text(context.channel_id, 'returned channel_id');
      progress.message_id = timestamp(context.message_ts, 'returned message_ts');
      if (typeof sent.message_link === 'string') progress.message_link = sent.message_link;
      progress.message_state = 'sent';
      await announce();
    }
    progress.stage = 'edit';
    progress.message_state = 'edit_outcome_unknown';
    await announce();
    const edited = await call('edit', {channel_id: progress.channel_id,
      message_id: progress.message_id, message: {markdown_text: message}});
    if (edited.message_id !== progress.message_id) {
      throw new Error('Edit acknowledgement did not identify the selected message');
    }
    progress.message_state = 'edit_confirmed';
    progress.status = 'updated';
    if (options.readback === true) return await readSlackPublication(tools, progress, options);
    progress.stage = 'complete';
    await announce();
    return progress;
  } catch (error) {
    if (error instanceof SlackPublishError) throw error;
    await announce();
    const failure = new SlackPublishError(String(error?.message ?? error), progress, error);
    failure.response = lastResponse;
    throw failure;
  }
}


/** Select the existing bounded native rendering without changing body characters. */
function selectSlackPublicationBody(published, result) {
  const refuse = reason => ({failure: {...result, reason}});
  if (published.message_state !== 'edit_confirmed' || published.readback_status !== 'captured') {
    return refuse('confirmed_edit_and_capture_required');
  }
  let args;
  try {
    args = readbackArguments(published, {});
    object(published.readback_request, 'retained readback request');
  } catch (_) {
    return refuse('missing_readback_identity');
  }
  result.channel_id = args.channel_id;
  result.message_id = published.message_id;
  result.parent_message_id = args.message_ts;
  const request = published.readback_request;
  if (Object.keys(request).length !== Object.keys(args).length
      || Object.keys(args).some(key => request[key] !== args[key])
      || (published.thread_ts !== undefined && published.thread_ts !== args.message_ts)) {
    return refuse('readback_request_identity_mismatch');
  }

  // Do not choose the first readable object when provider representations conflict.
  const response = published.readback_response;
  if (!response || typeof response !== 'object' || Array.isArray(response)
      || response.isError === true) return refuse('readback_response_unavailable');
  const payloads = [];
  if (response.structuredContent !== undefined) payloads.push(response.structuredContent);
  if (response.content !== undefined) {
    if (!Array.isArray(response.content)) return refuse('unrecognized_readback_payload');
    for (const block of response.content) {
      if (block?.type !== 'text' || typeof block.text !== 'string') {
        return refuse('unrecognized_readback_payload');
      }
      try { payloads.push(JSON.parse(block.text)); }
      catch (_) { return refuse('unrecognized_readback_payload'); }
    }
  }
  if (!payloads.length || payloads.some(payload => !payload || typeof payload !== 'object'
      || Array.isArray(payload) || typeof payload.messages !== 'string'
      || typeof payload.pagination_info !== 'string'
      || Object.keys(payload).some(key => !['messages', 'pagination_info'].includes(key)))) {
    return refuse('unrecognized_readback_payload');
  }
  const representations = new Set(payloads.map(payload =>
    JSON.stringify([payload.messages, payload.pagination_info])));
  if (representations.size !== 1) return refuse('conflicting_readback_payloads');

  const rendered = payloads[0].messages;
  const parent = /^=== THREAD PARENT MESSAGE ===\nFrom: [^\r\n]+\nTime: [^\r\n]+\nMessage TS: (\d+\.\d+)\n/.exec(rendered);
  if (!parent || parent[1] !== args.message_ts) return refuse('unrecognized_parent_framing');
  const tail = rendered.slice(parent[0].length);
  const noReplies = '\n\nNo thread messsages\n';
  const separator = '\n\n=== THREAD REPLIES (1 total) ===\n\n--- Reply 1 of 1 ---\n';
  const records = [];
  if (tail.endsWith(noReplies)) {
    if (tail.includes(separator)) return refuse('ambiguous_message_framing');
    records.push({id: parent[1], body: tail.slice(0, -noReplies.length)});
  } else {
    const parts = tail.split(separator);
    if (parts.length !== 2) return refuse('unrecognized_reply_framing');
    const reply = /^From: [^\r\n]+\nTime: [^\r\n]+\nMessage TS: (\d+\.\d+)\n([\s\S]*)\n$/.exec(parts[1]);
    if (!reply) return refuse('unrecognized_reply_framing');
    records.push({id: parent[1], body: parts[0]}, {id: reply[1], body: reply[2]});
  }
  const marker = /^(?:=== THREAD |--- Reply |Message TS: |No thread messsages$)/m;
  if (records.some(record => marker.test(record.body))
      || new Set(records.map(record => record.id)).size !== records.length) {
    return refuse('ambiguous_message_framing');
  }
  const selected = records.filter(record => record.id === published.message_id);
  if (selected.length !== 1) return refuse('selected_message_not_found');
  return {body: selected[0].body};
}

/** Compare one retained bounded rendering. This pure operation never reads or writes Slack. */
function compareSlackPublication(published, expectedMessage, options = {}) {
  object(published, 'published result');
  text(expectedMessage, 'expected message');
  object(options, 'comparison options');
  for (const key of Object.keys(options)) {
    if (key !== 'normalization') throw new TypeError('Unsupported comparison option: ' + key);
  }
  const normalization = options.normalization === undefined ? 'none' : options.normalization;
  if (!['none', 'slack_bare_urls_entities',
    'slack_bare_urls_entities_fragment_labels',
    'slack_bare_urls_entities_www_slash_labels',
    'slack_bare_urls_entities_www_or_slash_labels',
    'slack_bare_urls_entities_github_blob_labels'].includes(normalization)) {
    throw new TypeError('normalization must be none, slack_bare_urls_entities, '
      + 'slack_bare_urls_entities_fragment_labels, slack_bare_urls_entities_www_slash_labels, '
      + 'slack_bare_urls_entities_www_or_slash_labels, or slack_bare_urls_entities_github_blob_labels');
  }
  const allowFragmentLabels = normalization === 'slack_bare_urls_entities_fragment_labels';
  const allowWwwSlashLabels = normalization === 'slack_bare_urls_entities_www_slash_labels';
  const allowIndependentLabels = normalization === 'slack_bare_urls_entities_www_or_slash_labels';
  const allowGitHubBlobLabels = normalization === 'slack_bare_urls_entities_github_blob_labels';
  const result = {status: 'uncomparable', matches: null, literal_match: null,
    body_source: 'native_read_thread_rendering', channel_binding: 'retained_readback_request',
    normalization, normalizations_applied: {bare_url_wrappers: 0, entities: 0}};
  if (allowGitHubBlobLabels) result.normalizations_applied.github_blob_labels = 0;
  if (allowFragmentLabels) result.normalizations_applied.fragment_labels = 0;
  if (allowWwwSlashLabels) result.normalizations_applied.www_slash_labels = 0;
  if (allowIndependentLabels) {
    result.normalizations_applied.www_prefix_omissions = 0;
    result.normalizations_applied.terminal_slash_omissions = 0;
  }
  const selection = selectSlackPublicationBody(published, result);
  if (selection.failure) return selection.failure;
  const observed = selection.body;
  result.literal_match = observed === expectedMessage;
  if (result.literal_match) return {...result, status: 'exact', matches: true};
  if (normalization === 'none') {
    return {...result, status: 'mismatch', matches: false, reason: 'different_rendered_body'};
  }

  // Only observed bare-URL label forms are eligible; the URL target is unchanged.
  let comparable = observed.replace(/<(https?:\/\/[^<>\s|]+)(?:\|([^<>\r\n]+))?>/g,
    (whole, target, label) => {
      const withoutScheme = target.replace(/^https?:\/\//, '');
      const fragment = withoutScheme.indexOf('#');
      const fragmentLabel = allowFragmentLabels && fragment >= 0
        && fragment < withoutScheme.length - 1
        && label === withoutScheme.slice(0, fragment + 1) + '\u2026';
      const wwwSlashLabel = allowWwwSlashLabels && withoutScheme.startsWith('www.')
        && withoutScheme.endsWith('/') && !/[?#]/.test(withoutScheme)
        && label === withoutScheme.slice(4, -1);
      const independentTarget = allowIndependentLabels && !/[?#]/.test(withoutScheme);
      const wwwOnlyLabel = independentTarget && withoutScheme.startsWith('www.')
        && label === withoutScheme.slice(4);
      const slashOnlyLabel = independentTarget && withoutScheme.endsWith('/')
        && label === withoutScheme.slice(0, -1);
      const independentBothLabel = independentTarget && withoutScheme.startsWith('www.')
        && withoutScheme.endsWith('/') && label === withoutScheme.slice(4, -1);
      // One observed immutable GitHub blob display form; never shorten the target.
      const githubBlobTarget = allowGitHubBlobLabels
        && /^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/blob)\/[0-9a-f]{40}\/(?:[A-Za-z0-9_.-]+\/)*([A-Za-z0-9_.-]+)$/.exec(target);
      const githubBlobLabel = githubBlobTarget
        && label === 'github.com/' + githubBlobTarget[1] + '/\u2026/' + githubBlobTarget[2];
      if (label !== undefined && label !== target && label !== withoutScheme
        && !fragmentLabel && !wwwSlashLabel
        && !wwwOnlyLabel && !slashOnlyLabel && !independentBothLabel && !githubBlobLabel) {
        return whole;
      }
      if (githubBlobLabel) result.normalizations_applied.github_blob_labels += 1;
      if (fragmentLabel) result.normalizations_applied.fragment_labels += 1;
      if (wwwSlashLabel) result.normalizations_applied.www_slash_labels += 1;
      if (wwwOnlyLabel || independentBothLabel) result.normalizations_applied.www_prefix_omissions += 1;
      if (slashOnlyLabel || independentBothLabel) result.normalizations_applied.terminal_slash_omissions += 1;
      result.normalizations_applied.bare_url_wrappers += 1;
      return target;
    });
  // Decode once, after link recognition: escaped angle brackets cannot create a link.
  const entities = {'&amp;': '&', '&lt;': '<', '&gt;': '>'};
  comparable = comparable.replace(/&(?:amp|lt|gt);/g, entity => {
    result.normalizations_applied.entities += 1;
    return entities[entity];
  });
  return comparable === expectedMessage
    ? {...result, status: 'presentation_match', matches: true}
    : {...result, status: 'mismatch', matches: false, reason: 'different_rendered_body'};
}

/** Compare only the exact raw span inside one unambiguous triple-backtick pair. */
function compareSlackFencedPayload(published, expectedPayload) {
  object(published, 'published result');
  text(expectedPayload, 'expected payload');
  const result = {status: 'uncomparable', matches: null, literal_match: null,
    evidence_scope: 'single_fenced_payload',
    body_source: 'native_read_thread_rendering', channel_binding: 'retained_readback_request',
    normalization: 'none', whole_message_comparison: 'not_performed'};
  const refuse = reason => ({...result, reason});
  const selection = selectSlackPublicationBody(published, result);
  if (selection.failure) return selection.failure;
  const observed = selection.body;
  const fences = [...observed.matchAll(/`{3,}/g)];
  if (fences.length !== 2 || fences.some(fence => fence[0] !== '```')) {
    return refuse('single_triple_backtick_pair_required');
  }
  if (/^[ \t]*~{3,}/m.test(observed)) return refuse('unsupported_fence_form');
  const opening = fences[0].index;
  const closing = fences[1].index;
  if ((opening !== 0 && observed[opening - 1] !== '\n')
      || (closing + 3 !== observed.length && observed[closing + 3] !== '\n')) {
    return refuse('unsupported_fence_boundaries');
  }
  const start = opening + 3;
  const payload = observed.slice(start, closing);
  result.fence = {delimiter: '```', offset_origin: 'selected_rendered_body',
    offset_unit: 'utf16_code_units', range_end: 'exclusive',
    opening: [opening, start], payload: [start, closing], closing: [closing, closing + 3]};
  result.expected_length = expectedPayload.length;
  result.observed_length = payload.length;
  result.literal_match = payload === expectedPayload;
  return result.literal_match
    ? {...result, status: 'exact', matches: true}
    : {...result, status: 'mismatch', matches: false, reason: 'different_fenced_payload'};
}


/** Select only the narrow native send acknowledgement used for parent routing. */
function routingSendAcknowledgement(response) {
  object(response, 'retained native send response');
  if (response.isError === true) throw new TypeError('Native send response is an error');
  const candidates = [];
  if (response.message_context !== undefined || response.message_link !== undefined) {
    candidates.push({value: response, source: 'native_payload'});
  } else {
    if (response.structuredContent !== undefined) {
      candidates.push({value: response.structuredContent, source: 'structuredContent'});
    }
    if (response.content !== undefined) {
      if (!Array.isArray(response.content) || response.content.length > 8) {
        throw new TypeError('Unsupported native send content blocks');
      }
      for (let i = 0; i < response.content.length; i++) {
        const block = response.content[i];
        if (block?.type !== 'text' || typeof block.text !== 'string' || block.text.length > 4096) {
          throw new TypeError('Unsupported native send content block');
        }
        candidates.push({value: JSON.parse(block.text), source: 'content[' + i + '].text'});
      }
    }
  }
  if (!candidates.length) throw new TypeError('Missing native send acknowledgement');
  for (const candidate of candidates) {
    const value = object(candidate.value, 'native send acknowledgement');
    const context = object(value.message_context, 'native send message_context');
    if (Object.keys(value).some(key => !['message_link', 'message_context'].includes(key))
        || Object.keys(context).some(key => !['message_ts', 'channel_id'].includes(key))
        || typeof value.message_link !== 'string' || value.message_link.length > 2048
        || typeof context.channel_id !== 'string' || !/^[CDG][A-Z0-9]+$/.test(context.channel_id)
        || context.channel_id.length > 80
        || typeof context.message_ts !== 'string' || !/^[1-9][0-9]{0,15}\.[0-9]{6}$/.test(context.message_ts)) {
      throw new TypeError('Unsupported native send acknowledgement shape');
    }
    candidate.identity = JSON.stringify([value.message_link, context.channel_id, context.message_ts]);
  }
  if (new Set(candidates.map(candidate => candidate.identity)).size !== 1) {
    throw new TypeError('Conflicting native send acknowledgements');
  }
  return {value: candidates[0].value, sources: candidates.map(candidate => candidate.source)};
}

/** One explicitly selected native-parent read; existing publication inputs stay intact. */
async function readSlackPublicationAtNativeParent(tools, published, retainedSendResponse, options = {}) {
  object(published, 'published progress');
  object(options, 'native-parent read options');
  for (const key of Object.keys(options)) {
    if (!['bindings', 'onProgress', 'readback_thread_ts'].includes(key)) {
      throw new TypeError('Unsupported native-parent read option: ' + key);
    }
  }
  if (published.message_state !== 'edit_confirmed') {
    throw new TypeError('Native-parent readback requires a confirmed edit');
  }
  if (options.onProgress !== undefined && typeof options.onProgress !== 'function') {
    throw new TypeError('onProgress must be a function');
  }
  const ack = routingSendAcknowledgement(retainedSendResponse);
  const context = ack.value.message_context;
  const link = ack.value.message_link;
  if (context.channel_id !== published.channel_id || context.message_ts !== published.message_id
      || link !== published.message_link) {
    throw new TypeError('Native send acknowledgement differs from the retained publication');
  }
  const match = /^https:\/\/([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.slack\.com)\/archives\/([CDG][A-Z0-9]+)\/p([0-9]+)\?([^#]+)$/.exec(link);
  if (!match || match[2] !== context.channel_id
      || match[3] !== context.message_ts.replace('.', '')) {
    throw new TypeError('Native message link does not bind the selected channel and message');
  }
  const query = {};
  const pairs = match[4].split('&');
  if (pairs.length !== 2) throw new TypeError('Native message link needs exactly thread_ts and cid');
  for (const pair of pairs) {
    const parts = pair.split('=');
    if (parts.length !== 2 || !['thread_ts', 'cid'].includes(parts[0])
        || Object.prototype.hasOwnProperty.call(query, parts[0])) {
      throw new TypeError('Ambiguous or unsupported native message link query');
    }
    query[parts[0]] = parts[1];
  }
  if (query.cid !== context.channel_id || !/^[1-9][0-9]{0,15}\.[0-9]{6}$/.test(query.thread_ts ?? '')
      || BigInt(query.thread_ts.replace('.', '')) > BigInt(context.message_ts.replace('.', ''))) {
    throw new TypeError('Native message link has an invalid parent or channel query');
  }
  if (options.readback_thread_ts !== undefined
      && timestamp(options.readback_thread_ts, 'readback_thread_ts') !== query.thread_ts) {
    throw new TypeError('Explicit readback_thread_ts conflicts with the native parent');
  }
  const requested = published.thread_ts === undefined ? null : timestamp(published.thread_ts, 'retained thread_ts');
  const prior = published.readback_thread_ts === undefined ? null
    : timestamp(published.readback_thread_ts, 'retained readback_thread_ts');
  const routing = {
    source: 'caller_retained_native_send_acknowledgement',
    authority: 'reported_routing_metadata', authentication: 'not_performed',
    acknowledgement_sources: ack.sources, native_message_link: link,
    channel_id: context.channel_id, message_id: context.message_ts,
    requested_thread_ts: requested, prior_readback_thread_ts: prior,
    native_parent_thread_ts: query.thread_ts,
  };
  const copyRouting = () => JSON.parse(JSON.stringify(routing));
  const selected = {};
  for (const key of ['status', 'stage', 'message_state', 'progress_callback_errors',
    'channel_id', 'message_id', 'message_link', 'calls']) {
    if (published[key] !== undefined) selected[key] = published[key];
  }
  selected.thread_ts = query.thread_ts;
  selected.readback_thread_ts = query.thread_ts;
  const readOptions = {...options, readback_thread_ts: query.thread_ts};
  if (options.onProgress) {
    readOptions.onProgress = progress => options.onProgress({
      routing: copyRouting(), observation: progress,
    });
  }
  try {
    const observation = await readSlackPublication(tools, selected, readOptions);
    return {schema: 'commons.connected_slack_native_parent_readback/v1',
      routing: copyRouting(), observation};
  } catch (error) {
    if (error instanceof SlackPublishError) error.routing = copyRouting();
    throw error;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {SlackPublishError, publishSlackMessage, readSlackPublication,
    compareSlackPublication, compareSlackFencedPayload, readSlackPublicationAtNativeParent};
}
