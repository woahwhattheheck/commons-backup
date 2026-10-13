'use strict';

// Pure retained-response projection. No provider calls, HTML rendering, or input mutation.
// Counts and limits use JavaScript UTF-16 code units; source paths refer to the input.
const DEFAULTS = Object.freeze({
  maxMessages: 10,
  maxBodyChars: 6000,
  maxTotalBodyChars: 18000,
  maxHeaderChars: 300,
  maxBodiesPerMessage: 8,
});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function fail(code, path, detail) {
  const error = new TypeError(`${code} at ${path}: ${detail}`);
  error.code = code;
  error.source_path = path;
  throw error;
}

function clip(value, limit) {
  let end = Math.min(value.length, limit);
  if (end < value.length && end > 0 && /[\uD800-\uDBFF]/.test(value[end - 1])
    && /[\uDC00-\uDFFF]/.test(value[end])) end -= 1;
  return value.slice(0, end);
}

function header(part, name) {
  if (part.headers === undefined) return '';
  if (!Array.isArray(part.headers)) fail('UNSUPPORTED_MIME', '$.headers', 'headers must be an array');
  const found = part.headers.find(h => record(h) && typeof h.name === 'string'
    && h.name.toLowerCase() === name);
  if (!found) return '';
  if (typeof found.value !== 'string') fail('UNSUPPORTED_MIME', '$.headers', 'header value must be text');
  return found.value;
}

function omittedCounts() {
  return {
    headers: 0, header_chars: 0, body_chars: 0, body_parts: 0,
    attachments: 0, forwarded_messages: 0, alternative_branches: 0,
    related_parts: 0, unsupported_parts: 0,
  };
}

const NATIVE_METADATA_LIMITS = Object.freeze({
  max_label_ids: 100,
  max_label_id_chars: 256,
  max_internal_date_chars: 64,
});

function projectNativeMetadata(item, source) {
  const labelPath = source + '.label_ids';
  let labels = { status: 'missing', source_path: labelPath };
  if (own(item, 'label_ids')) {
    const value = item.label_ids;
    if (!Array.isArray(value)) {
      labels.status = 'invalid';
    } else if (value.length > NATIVE_METADATA_LIMITS.max_label_ids) {
      labels.status = 'limit_exceeded';
    } else {
      let status = 'included';
      for (let index = 0; index < value.length; index += 1) {
        if (!own(value, index) || typeof value[index] !== 'string') {
          status = 'invalid';
          break;
        }
        if (value[index].length > NATIVE_METADATA_LIMITS.max_label_id_chars) {
          status = 'limit_exceeded';
          break;
        }
      }
      labels.status = status;
      if (status === 'included') labels.value = value.slice();
    }
  }

  const datePath = source + '.internal_date';
  let internalDate = { status: 'missing', source_path: datePath };
  if (own(item, 'internal_date')) {
    const value = item.internal_date;
    if (typeof value !== 'string') {
      internalDate.status = 'invalid';
    } else if (value.length > NATIVE_METADATA_LIMITS.max_internal_date_chars) {
      internalDate.status = 'limit_exceeded';
    } else {
      internalDate.status = 'included';
      internalDate.value = value;
    }
  }
  return { label_ids: labels, internal_date: internalDate };
}

/**
 * Project retained native full-MIME message and thread CallToolResults only.
 * Supported envelopes: structuredContent.{id,thread_id,payload}, or
 * structuredContent.responses[] containing those full message objects, or
 * structuredContent.{id,messages[]} from the native full-MIME thread reader,
 * or structuredContent.responses[] containing those native thread objects.
 * bodies[].text is plain text or explicitly labelled, unrendered HTML data.
 * Missing decoded content / external attachment_id bodies remain unavailable.
 * Encoded bodies and snippets are never substituted for exact body.content.
 */
function projectGmailMessages(response, options = {}) {
  if (!record(options)) fail('INVALID_OPTIONS', '$.options', 'expected an object');
  const limits = { ...DEFAULTS };
  const sparse = own(options, 'source_indices');
  const includeNativeMetadata = own(options, 'include_native_metadata') && options.include_native_metadata === true;
  if (own(options, 'include_native_metadata') && typeof options.include_native_metadata !== 'boolean') {
    fail('INVALID_OPTIONS', '$.options.include_native_metadata', 'expected a boolean');
  }
  for (const [key, value] of Object.entries(options)) {
    if (key === 'source_indices' || key === 'include_native_metadata') continue;
    if (!own(DEFAULTS, key) || !Number.isSafeInteger(value) || value < 0) {
      fail('INVALID_OPTIONS', `$.options.${key}`, 'expected a supported nonnegative integer limit');
    }
    limits[key] = value;
  }
  if (!record(response) || response.isError === true || response.error != null
    || !record(response.structuredContent)) {
    fail('UNSUPPORTED_GMAIL_RESPONSE', '$', 'expected a successful native full-MIME structuredContent response');
  }
  const structured = response.structuredContent;
  if (structured.isError === true || structured.error != null || structured.error_code != null) {
    fail('GMAIL_ERROR_RESPONSE', '$.structuredContent', 'error responses cannot be projected as messages');
  }
  const batch = own(structured, 'responses');
  const thread = own(structured, 'messages');
  if (batch && thread) {
    fail('UNSUPPORTED_GMAIL_RESPONSE', '$.structuredContent', 'multiple message collections are ambiguous');
  }
  if (thread && (typeof structured.id !== 'string' || !structured.id || structured.id.length > 1024)) {
    fail('UNSUPPORTED_GMAIL_THREAD', '$.structuredContent.id', 'expected the native thread id');
  }
  const collection = batch ? 'responses' : thread ? 'messages' : null;
  if (collection && !Array.isArray(structured[collection])) {
    fail('UNSUPPORTED_GMAIL_RESPONSE', '$.structuredContent.' + collection, 'expected an array of full messages');
  }
  const batchThreads = batch && structured.responses.some(item => record(item) && own(item, 'messages'));
  const threads = [];
  const locations = [];
  const inputs = batchThreads ? [] : collection ? structured[collection] : [structured];
  if (batchThreads) {
    for (let threadIndex = 0; threadIndex < structured.responses.length; threadIndex += 1) {
      const item = structured.responses[threadIndex];
      const source = `$.structuredContent.responses[${threadIndex}]`;
      if (!record(item) || item.isError === true || item.error != null || item.error_code != null
        || typeof item.id !== 'string' || !item.id || item.id.length > 1024
        || !Array.isArray(item.messages) || own(item, 'responses')) {
        fail('UNSUPPORTED_GMAIL_THREAD', source, 'expected a native thread id and full messages array, without an error');
      }
      const start = inputs.length;
      for (let messageIndex = 0; messageIndex < item.messages.length; messageIndex += 1) {
        inputs.push(item.messages[messageIndex]);
        locations.push({
          thread_source_index: threadIndex,
          thread_message_index: messageIndex,
          source_path: `${source}.messages[${messageIndex}]`,
        });
      }
      threads.push({
        source_index: threadIndex,
        id: item.id,
        source_path: source + '.id',
        message_count: item.messages.length,
        message_index_range: [start, inputs.length],
      });
    }
  }
  const sourceOf = index => batchThreads ? locations[index].source_path
    : collection ? `$.structuredContent.${collection}[${index}]` : '$.structuredContent';
  // Validate even omitted message envelopes, so raw/search/error entries are explicit failures.
  for (let index = 0; index < inputs.length; index += 1) {
    const item = inputs[index];
    if (!record(item) || item.isError === true || item.error != null || item.error_code != null
      || typeof item.id !== 'string' || !item.id || item.id.length > 1024
      || typeof item.thread_id !== 'string' || !item.thread_id || item.thread_id.length > 1024
      || !record(item.payload) || typeof item.payload.mime_type !== 'string') {
      fail('UNSUPPORTED_GMAIL_MESSAGE', sourceOf(index), 'expected id, thread_id and a full MIME payload, without an error');
    }
    const expectedThreadId = batchThreads ? threads[locations[index].thread_source_index].id
      : thread ? structured.id : null;
    if (expectedThreadId !== null && item.thread_id !== expectedThreadId) {
      fail('UNSUPPORTED_GMAIL_THREAD', sourceOf(index) + '.thread_id', 'message does not identify the retained native thread');
    }
  }

  let indices;
  if (sparse) {
    const selection = options.source_indices;
    if (!Array.isArray(selection) || selection.length > limits.maxMessages) {
      fail('INVALID_OPTIONS', '$.options.source_indices', 'expected an array with at most maxMessages source indices');
    }
    indices = [];
    for (let position = 0; position < selection.length; position += 1) {
      const index = selection[position];
      if (!own(selection, position) || !Number.isSafeInteger(index) || index < 0
        || index >= inputs.length || (position > 0 && index <= indices[position - 1])) {
        fail('INVALID_OPTIONS', `$.options.source_indices[${position}]`,
          'expected an in-range source index in strictly increasing order, without missing entries');
      }
      indices.push(index);
    }
    limits.source_indices = indices.slice();
  } else {
    indices = Array.from({ length: Math.min(inputs.length, limits.maxMessages) }, (_, index) => index);
  }

  if (includeNativeMetadata) {
    limits.include_native_metadata = true;
    limits.native_metadata = { ...NATIVE_METADATA_LIMITS };
  }
  const result = {
    format: 'gmail-mime-projection-v1',
    source_shape: batchThreads ? 'batch_threads' : batch ? 'batch' : thread ? 'thread' : 'single',
    message_count: inputs.length,
    messages: [],
    omitted: { messages: inputs.length - indices.length, body_chars: 0, header_chars: 0, body_parts: 0 },
    limits,
  };
  if (thread) {
    result.thread = { id: structured.id, source_path: '$.structuredContent.id' };
  }
  if (batchThreads) {
    result.thread_count = threads.length;
    result.threads = threads;
    result.thread_message_range_end = 'exclusive';
  }
  if (sparse) {
    const omittedRanges = [];
    let next = 0;
    for (const index of indices) {
      if (next < index) omittedRanges.push([next, index]);
      next = index + 1;
    }
    if (next < inputs.length) omittedRanges.push([next, inputs.length]);
    result.selection = {
      source_indices: indices.slice(),
      omitted_source_index_ranges: omittedRanges,
      range_end: 'exclusive',
    };
  }
  let remaining = limits.maxTotalBodyChars;
  for (const index of indices) {
    const item = inputs[index];
    const source = sourceOf(index);
    const omitted = omittedCounts();
    const message = { id: item.id, thread_id: item.thread_id, subject: '', from: '', date: '', bodies: [], unavailable_bodies: [], omitted };
    if (sparse || batchThreads) Object.assign(message, { source_index: index, source_path: source });
    if (batchThreads) Object.assign(message, {
      thread_source_index: locations[index].thread_source_index,
      thread_message_index: locations[index].thread_message_index,
    });
    if (includeNativeMetadata) message.native_metadata = projectNativeMetadata(item, source);
    let selectedHeaders = 0;
    for (const name of ['subject', 'from', 'date']) {
      const value = header(item.payload, name);
      if ((item.payload.headers || []).some(h => record(h) && typeof h.name === 'string' && h.name.toLowerCase() === name)) selectedHeaders += 1;
      message[name] = clip(value, limits.maxHeaderChars);
      omitted.header_chars += value.length - message[name].length;
    }
    omitted.headers = (item.payload.headers || []).length - selectedHeaders;

    let nodes = 0;
    const visited = new Set();
    function select(part, path, depth) {
      if (!record(part) || typeof part.mime_type !== 'string' || !part.mime_type) {
        fail('UNSUPPORTED_MIME', path, 'expected a MIME part with mime_type');
      }
      if (depth > 32 || ++nodes > 4096 || visited.has(part)) {
        fail('MIME_STRUCTURE_LIMIT', path, 'MIME tree is cyclic, too deep, or exceeds 4096 visited parts');
      }
      visited.add(part);
      const mime = part.mime_type.split(';')[0].trim().toLowerCase();
      if ((typeof part.filename === 'string' && part.filename.trim())
        || /^\s*attachment(?:\s*;|\s*$)/i.test(header(part, 'content-disposition'))) {
        omitted.attachments += 1;
        return [];
      }
      if (mime === 'message/rfc822' || mime === 'message/global') {
        omitted.forwarded_messages += 1;
        return [];
      }
      if (mime.startsWith('multipart/')) {
        if (!Array.isArray(part.parts)) fail('UNSUPPORTED_MIME', path + '.parts', 'multipart requires parts');
        if (mime === 'multipart/related' && part.parts.length) {
          const start = /(?:^|;)\s*start\s*=\s*(?:"([^"]*)"|([^;\s]+))/i.exec(header(part, 'content-type'));
          let chosen = 0;
          if (start) {
            const cid = (start[1] || start[2]).replace(/^<|>$/g, '');
            chosen = part.parts.findIndex(child => record(child)
              && header(child, 'content-id').trim().replace(/^<|>$/g, '') === cid);
            if (chosen < 0) fail('UNSUPPORTED_MIME', path, 'multipart/related start does not identify a child');
          }
          omitted.related_parts += part.parts.length - 1;
          return select(part.parts[chosen], `${path}.parts[${chosen}]`, depth + 1);
        }
        const children = part.parts.map((child, childIndex) => select(child, `${path}.parts[${childIndex}]`, depth + 1));
        if (mime === 'multipart/alternative') {
          const chosen = children.find(parts => parts.some(body => body.mime_type === 'text/plain'))
            || children.find(parts => parts.some(body => body.mime_type === 'text/html'));
          omitted.alternative_branches += Math.max(0, children.length - (chosen ? 1 : 0));
          return chosen || [];
        }
        return children.flat();
      }
      if (mime !== 'text/plain' && mime !== 'text/html') {
        omitted.unsupported_parts += 1;
        return [];
      }
      if (!record(part.body)) fail('UNSUPPORTED_MIME', path + '.body', 'text part requires a body object');
      return [{ mime_type: mime, source_path: path + '.body', body: part.body }];
    }

    const selected = select(item.payload, source + '.payload', 0);
    for (let bodyIndex = 0; bodyIndex < selected.length; bodyIndex += 1) {
      const selectedBody = selected[bodyIndex];
      const body = selectedBody.body;
      const path = selectedBody.source_path;
      const external = typeof body.attachment_id === 'string' && body.attachment_id.length > 0;
      const inline = !external && typeof body.content === 'string';
      if (!inline) {
        if (bodyIndex < limits.maxBodiesPerMessage) {
          message.unavailable_bodies.push({
            mime_type: selectedBody.mime_type,
            source_path: external ? path + '.attachment_id' : own(body, 'content') ? path + '.content' : path,
            reason: external ? 'external_attachment_id' : 'decoded_content_unavailable',
          });
        } else omitted.body_parts += 1;
        continue;
      }
      const content = body.content;
      if (bodyIndex >= limits.maxBodiesPerMessage) {
        omitted.body_parts += 1;
        omitted.body_chars += content.length;
        continue;
      }
      const text = clip(content, Math.min(limits.maxBodyChars, remaining));
      const lost = content.length - text.length;
      remaining -= text.length;
      omitted.body_chars += lost;
      message.bodies.push({ mime_type: selectedBody.mime_type, text, source_path: path + '.content', original_chars: content.length, omitted_chars: lost, truncated: lost > 0 });
    }
    result.messages.push(message);
    result.omitted.body_chars += omitted.body_chars;
    result.omitted.header_chars += omitted.header_chars;
    result.omitted.body_parts += omitted.body_parts;
  }
  return result;
}

module.exports = { projectGmailMessages };

