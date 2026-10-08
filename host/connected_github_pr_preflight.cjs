'use strict';

// Read-only PR-create reconciliation after source publication, immediately
// before asking GitHub to create a pull request.
const SHA = /^[0-9a-f]{40}$/;

async function reconcileBeforePullCreate({fetchJSON, repository, baseBranch, branchName,
  expectedHead, initialBaseHead, files}) {
  if (typeof fetchJSON !== 'function') throw new TypeError('fetchJSON is required');
  if (typeof repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    throw new TypeError('repository must be owner/name');
  }
  if (typeof baseBranch !== 'string' || typeof branchName !== 'string'
    || !baseBranch || !branchName || !SHA.test(expectedHead) || !SHA.test(initialBaseHead)
    || !Array.isArray(files) || files.length === 0) {
    throw new TypeError('complete source and branch references are required');
  }

  const api = 'https://api.github.com/repos/' + repository;
  const owner = repository.split('/')[0];
  // CLOSED and MERGED carriers matter: an open-only census can duplicate a
  // peer's exact contribution two seconds after its merge.
  const head = encodeURIComponent(owner + ':' + branchName);
  const base = encodeURIComponent(baseBranch);
  const pulls = await fetchJSON(api + '/pulls?state=all&head=' + head +
    '&base=' + base + '&per_page=100&page=1');
  if (!Array.isArray(pulls) || pulls.length >= 100) {
    throw new Error('Cannot establish a complete same-branch PR census');
  }
  for (const pull of pulls) {
    if (!pull || pull.head?.ref !== branchName || pull.base?.ref !== baseBranch
      || String(pull.head?.repo?.full_name || '').toLowerCase() !== repository.toLowerCase()) {
      continue;
    }
    const observed = pull.head?.sha;
    if (observed !== expectedHead) {
      return {status: 'EXISTING_BRANCH_CONFLICT', pull_number: pull.number,
        observed_head: observed ?? null, expected_head: expectedHead};
    }
    return {status: 'EXISTING_PULL_REQUEST', pull_number: pull.number,
      url: pull.html_url || pull.url || null, state: pull.state,
      merged: Boolean(pull.merged_at), observed_head: observed};
  }

  // A peer may instead have squash-merged identical postimages under another
  // commit. Compare exact Git blobs, never infer equality from ancestry.
  const current = await fetchJSON(api + '/branches/' + encodeURIComponent(baseBranch));
  const currentBase = current?.commit?.sha;
  if (!SHA.test(currentBase)) throw new Error('Current base SHA unavailable');
  if (currentBase === initialBaseHead) return null;

  let compared = 0;
  for (const file of files) {
    if (!file || typeof file.path !== 'string' || !SHA.test(file.blob_sha)) return null;
    const relative = file.path.split('/').map(encodeURIComponent).join('/');
    let observed;
    try {
      observed = await fetchJSON(api + '/contents/' + relative + '?ref=' + encodeURIComponent(currentBase));
    } catch (error) {
      if (/\b(?:404|not[ _-]?found)\b/i.test(String(error?.message || error))) return null;
      throw error;
    }
    if (observed?.type !== 'file' || observed.sha !== file.blob_sha) return null;
    compared++;
  }
  return {status: 'SOURCE_ALREADY_ON_BASE', base_sha: currentBase,
    source_paths_matched: compared, expected_head: expectedHead};
}

module.exports = {reconcileBeforePullCreate};
