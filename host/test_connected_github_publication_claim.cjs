'use strict';

const assert = require('node:assert/strict');
const {preparePublicationClaim, mutatePublicationClaims} = require('./connected_github_publication_claim.cjs');

const sha = ch => ch.repeat(40);
let seq = 1;
const state = {files: new Map(), writes: 0, failOnce: false};
const readFile = async ({path}) => {
  const row = state.files.get(path);
  return row ? {data: {content: row.content, sha: row.sha}} : {absent: true};
};
const call = async (action, args) => {
  if (!['create_file', 'update_file'].includes(action)) throw new Error('unexpected action ' + action);
  state.writes++;
  if (state.failOnce) {
    state.failOnce = false;
    const error = new Error('conflict'); error.tool_error = {http_status: 409}; throw error;
  }
  const old = state.files.get(args.path);
  if (action === 'create_file') assert.equal(old, undefined);
  if (action === 'update_file') assert.equal(args.sha, old.sha);
  const next = seq.toString(16).padStart(40, '0'); seq++;
  state.files.set(args.path, {content: args.content, sha: next});
  return {commit_sha: sha('c'), content_sha: next};
};

(async () => {
  const base = {repository_full_name: 'woahwhattheheck/gyroflow', base_branch: 'main',
    branch_name: 'fix/shared'};
  const a = preparePublicationClaim({holder: 'seat-A', ttl_s: 300, issue_key: '#742'},
    {...base, files: [{path: 'src/a.rs'}, {path: 'src/b.rs'}]});
  const b = preparePublicationClaim({holder: 'seat-B', ttl_s: 300, issue_key: '#742'},
    {...base, files: [{path: 'src/b.rs'}, {path: 'src/c.rs'}]});
  const c = preparePublicationClaim({holder: 'seat-C', ttl_s: 300, issue_key: '#742'},
    {...base, files: [{path: 'src/z.rs'}]});
  assert.equal(a.key, b.key);

  const first = await mutatePublicationClaims({readFile, call, config: a, action: 'take', now: 1000000});
  assert.equal(first.status, 'ACQUIRED'); assert.equal(first.provider_writes, 1);

  const beforePeer = state.writes;
  const peer = await mutatePublicationClaims({readFile, call, config: b, action: 'take', now: 1001000});
  assert.equal(peer.status, 'HELD_BY_PEER'); assert.deepEqual(peer.conflicts[0].paths, ['src/b.rs']);
  assert.equal(state.writes, beforePeer, 'overlap contention must not write provider state');

  const disjoint = await mutatePublicationClaims({readFile, call, config: c, action: 'take', now: 1001000});
  assert.equal(disjoint.status, 'ACQUIRED'); assert.equal(disjoint.live_leases, 2);

  const released = await mutatePublicationClaims({readFile, call, config: a, action: 'release', now: 1002000});
  assert.equal(released.status, 'RELEASED');
  const second = await mutatePublicationClaims({readFile, call, config: b, action: 'take', now: 1003000});
  assert.equal(second.status, 'ACQUIRED');

  await mutatePublicationClaims({readFile, call, config: b, action: 'release', now: 1004000});
  state.failOnce = true;
  const retried = await mutatePublicationClaims({readFile, call, config: b, action: 'take', now: 1005000});
  assert.equal(retried.status, 'ACQUIRED'); assert.equal(retried.attempt, 2);

  console.log('Focused publication claim lease: 6/6 PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
