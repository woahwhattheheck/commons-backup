'use strict';

// Pure formatting of selected fields from a caller-retained publisher result.
// No publication, lookup, source verification, main observation, or policy check.
const SHA = /^[0-9a-f]{40}$/;
const REPOSITORY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const PR_URL = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*$/;
const MAX_TEXT_CHARS = 4096;

function plainObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function ownField(object, key, sourcePath) {
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  if (!descriptor) return {state: 'missing', source_path: sourcePath, reason: 'own_field_absent'};
  if (!Object.prototype.hasOwnProperty.call(descriptor, 'value')) {
    return {state: 'invalid', source_path: sourcePath, reason: 'accessor_not_read'};
  }
  if (descriptor.value === null) return {state: 'null', source_path: sourcePath, reason: 'explicit_null'};
  return {state: 'candidate', source_path: sourcePath, value: descriptor.value};
}

function field(raw, accepts, reason) {
  if (raw.state !== 'candidate') return raw;
  if (!accepts(raw.value)) {
    return {state: 'invalid', source_path: raw.source_path, reason};
  }
  return {state: 'present', source_path: raw.source_path, value: raw.value};
}

function childField(parent, key, sourcePath) {
  if (parent.state !== 'candidate') {
    return {state: parent.state, source_path: sourcePath,
      reason: 'parent_' + parent.state, parent_source_path: parent.source_path};
  }
  if (!plainObject(parent.value)) {
    return {state: 'invalid', source_path: sourcePath,
      reason: 'parent_not_plain_object', parent_source_path: parent.source_path};
  }
  return ownField(parent.value, key, sourcePath);
}

function display(record) {
  return record.state === 'present' ? String(record.value) : 'unknown (' + record.state + ')';
}

function equality(left, right) {
  return left.state === 'present' && right.state === 'present'
    ? left.value === right.value : null;
}

/**
 * Format only the known publisher identity fields. Caller-authored summaries,
 * source/artifact details, main observations and publication decisions stay
 * outside this function. It does not authenticate its input or revalidate a publication.
 */
function formatGitHubPublicationIdentities(publication) {
  if (!plainObject(publication)) {
    throw new TypeError('publication must be a plain caller-retained publisher result object');
  }
  const root = key => ownField(publication, key, 'publication.' + key);
  const pull = root('pull_request');
  const nested = key => childField(pull, key, 'publication.pull_request.' + key);
  const isSHA = value => typeof value === 'string' && SHA.test(value);
  const fields = {
    repository: field(root('repository_full_name'),
      value => typeof value === 'string' && value.length <= 201 && REPOSITORY.test(value),
      'expected_bounded_owner_slash_repository'),
    pr_number: field(nested('number'),
      value => Number.isSafeInteger(value) && value > 0, 'expected_positive_safe_integer'),
    pr_url: field(nested('url'),
      value => typeof value === 'string' && value.length <= 512 && PR_URL.test(value),
      'expected_bounded_canonical_github_pull_url'),
    head: field(root('commit_sha'), isSHA, 'expected_40_lowercase_hex'),
    pr_head: field(nested('head_sha'), isSHA, 'expected_40_lowercase_hex'),
    merge: field(root('merge_sha'), isSHA, 'expected_40_lowercase_hex'),
    readback_ref: field(root('readback_ref'), isSHA, 'expected_40_lowercase_hex'),
  };
  const relationships = {
    head_matches_pr_head: equality(fields.head, fields.pr_head),
    merge_matches_readback_ref: equality(fields.merge, fields.readback_ref),
    pr_url_matches_repository_and_number:
      fields.repository.state === 'present' && fields.pr_number.state === 'present'
        && fields.pr_url.state === 'present'
        ? fields.pr_url.value === 'https://github.com/' + fields.repository.value
          + '/pull/' + fields.pr_number.value
        : null,
  };
  const disagreements = [];
  if (relationships.head_matches_pr_head === false) {
    disagreements.push('commit_sha differs from pull_request.head_sha');
  }
  if (relationships.merge_matches_readback_ref === false) {
    disagreements.push('merge_sha differs from readback_ref');
  }
  if (relationships.pr_url_matches_repository_and_number === false) {
    disagreements.push('pull_request.url differs from repository_full_name/pull_request.number');
  }
  const lines = [
    'Publication identities (retained publisher result):',
    'Repository: ' + display(fields.repository),
    'PR: ' + display(fields.pr_url),
    'Head: ' + display(fields.head),
    'PR head: ' + display(fields.pr_head),
    'Merge: ' + display(fields.merge),
    'Readback ref: ' + display(fields.readback_ref),
  ];
  for (const disagreement of disagreements) lines.push('Identity disagreement: ' + disagreement + '.');
  const text = lines.join('\n');
  if (text.length > MAX_TEXT_CHARS) throw new RangeError('Identity text exceeds fixed character bound');
  return {
    schema: 'commons.github_publication_identities/v1',
    text,
    fields,
    relationships,
    disagreements,
    counts: {
      selected_fields: 7,
      present_fields: Object.values(fields).filter(record => record.state === 'present').length,
      text_chars: text.length,
    },
    limits: {selected_fields: 7, text_chars: MAX_TEXT_CHARS},
    scope: {
      input: 'caller_retained_publisher_result',
      provider_or_authentication_verification: 'not_performed',
      publication_status_or_acceptance: 'not_assessed',
      source_or_artifact_bytes: 'not_inspected',
      main_observation: 'not_supplied',
      provider_calls: 0,
    },
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {formatGitHubPublicationIdentities};
}
