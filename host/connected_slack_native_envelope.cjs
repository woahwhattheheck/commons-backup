'use strict';

/**
 * Adapt a native {text: JSON-string} response to the text-block representation
 * already accepted by connected_slack_pages.cjs. Keep the original response
 * beside the derived view; neither its text nor existing fields are mutated.
 *
 * This performs no reads, JSON decoding, pagination inference, or retries.
 * Existing text blocks keep precedence. Projectors can therefore compare all
 * distinct representations and retain their existing limits/refusal behavior.
 */
function asSlackTextBlocks(response) {
  if (!response || typeof response !== 'object' || Array.isArray(response)
      || response instanceof Error || response.isError === true) return response;
  const own = (key) => Object.prototype.hasOwnProperty.call(response, key);
  if (!own('text')) return response;
  if (typeof response.text !== 'string') {
    throw new TypeError('Native Slack text must be a string');
  }
  if (own('content') && !Array.isArray(response.content)) {
    throw new TypeError('Existing native content must be an array');
  }
  const content = own('content') ? response.content : [];
  // Reusing an already adapted view must not grow it or charge the same text
  // block again. Different existing text remains visible to the projectors.
  if (content.some(block => block?.type === 'text' && block.text === response.text)) {
    return response;
  }
  return {...response, content: [...content, {type: 'text', text: response.text}]};
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {asSlackTextBlocks};
}
