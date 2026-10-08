'use strict';

const assert = require('node:assert/strict');
const {reconcileBeforePullCreate} = require('./connected_github_pr_preflight.cjs');
const old = 'a'.repeat(40);
const desired = 'b'.repeat(40);
const current = 'c'.repeat(40);
const pin = 'd'.repeat(40);
const request = {repository: 'woahwhattheheck/commons', baseBranch: 'main',
  branchName: 'feat/snapshot-delta', expectedHead: desired, initialBaseHead: old,
  files: [{path: 'tools/mova_batch_sprint/snapshot_delta.py', blob_sha: pin}]};
const api = 'https://api.github.com/repos/woahwhattheheck/commons';
const listURL = api + '/pulls?state=all&head=woahwhattheheck%3Afeat%2Fsnapshot-delta&base=main&per_page=100&page=1';

(async () => {
  let queries = [];
  const closed = await reconcileBeforePullCreate({...request, fetchJSON: async url => {
    queries.push(url);
    assert.equal(url, listURL);
    return [{number: 32386, html_url: 'https://github.com/woahwhattheheck/commons/pull/32386',
      head: {ref: request.branchName, sha: desired, repo: {full_name: request.repository}},
      base: {ref: 'main'}, state: 'closed', merged_at: '2026-10-08T04:58:37Z'}];
  }});
  assert.equal(closed.status, 'EXISTING_PULL_REQUEST');
  assert.equal(closed.merged, true);
  assert.deepEqual(queries, [listURL]);

  queries = [];
  const mergedSource = await reconcileBeforePullCreate({...request, fetchJSON: async url => {
    queries.push(url);
    if (url === listURL) return [];
    if (url === api + '/branches/main') return {commit: {sha: current}};
    if (url === api + '/contents/tools/mova_batch_sprint/snapshot_delta.py?ref=' + current) {
      return {type: 'file', sha: pin};
    }
    throw new Error('Unexpected fetch: ' + url);
  }});
  assert.deepEqual(mergedSource, {status: 'SOURCE_ALREADY_ON_BASE', base_sha: current,
    source_paths_matched: 1, expected_head: desired});
  assert.equal(queries.length, 3);

  const stillNeeded = await reconcileBeforePullCreate({...request, fetchJSON: async url => {
    if (url === listURL) return [];
    if (url === api + '/branches/main') return {commit: {sha: current}};
    return {type: 'file', sha: 'e'.repeat(40)};
  }});
  assert.equal(stillNeeded, null);

  const changedPR = await reconcileBeforePullCreate({...request, fetchJSON: async url => {
    assert.equal(url, listURL);
    return [{number: 92, head: {ref: request.branchName, sha: current,
      repo: {full_name: request.repository}}, base: {ref: 'main'}, state: 'open'}];
  }});
  assert.equal(changedPR.status, 'EXISTING_BRANCH_CONFLICT');
  console.log('Focused native create-PR collision preflight: 4/4 PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
