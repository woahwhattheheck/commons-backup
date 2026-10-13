'use strict';

// Replays the complete production retained-tree validator on an exported Git tree.
// No provider calls, credentials, repository mutation, or dependency installation.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const os = require('node:os');
const {performance} = require('node:perf_hooks');

const [beforePath, afterPath, rawPath, expectedSHA, parentPath, changedPath] = process.argv.slice(2);
if (!changedPath || process.argv.length !== 8) {
  throw new Error('Usage: node benchmark_retained_tree.cjs BEFORE.cjs AFTER.cjs TREE.raw TREE_SHA PARENT_PATH CHANGED_FILE');
}
const raw = fs.readFileSync(rawPath);
const gitSHA = (type, bytes) => crypto.createHash('sha1').update(type + ' ' + bytes.length + '\0').update(bytes).digest('hex');
assert.equal(gitSHA('tree', raw), expectedSHA, 'Retained tree must match its native Git object');
const input = [{path: parentPath, tree_sha: expectedSHA, raw_base64: raw.toString('base64')}];
const files = [{path: changedPath}];
function load(path) {
  const source = fs.readFileSync(path);
  const methods = new Function(source.toString('utf8') + '\nreturn {validateRetainedTrees, retainedTreeSHA};')();
  return {source_sha: gitSHA('blob', source), ...methods};
}
const implementations = {before: load(beforePath), after: load(afterPath)};
function run(name) {
  const started = performance.now();
  const result = implementations[name].validateRetainedTrees(input, files).get(parentPath);
  return {elapsed_ms: performance.now() - started, result};
}
// One complete equality comparison is outside the timed paired sample series.
const baseline = run('before').result;
assert.deepEqual(run('after').result, baseline);
const samples = [];
for (let pair = 0; pair < 5; pair++) {
  const sample = {pair: pair + 1, order: pair % 2 ? ['after', 'before'] : ['before', 'after']};
  for (const name of sample.order) {
    const measured = run(name);
    sample[name + '_ms'] = measured.elapsed_ms;
    assert.deepEqual(measured.result, baseline);
  }
  samples.push(sample);
}
// Independently check framing across padding boundaries and the admitted maximum.
const lengths = [0, 1, 46, 47, 48, 49, 111, 112, 113, 1024, 16 * 1024 * 1024];
for (const length of lengths) {
  const bytes = Buffer.alloc(length, 0xa7);
  assert.equal(implementations.after.retainedTreeSHA(bytes), gitSHA('tree', bytes));
}
const changed = Buffer.from(raw);
assert.ok(changed.length > 0);
changed[changed.length - 1] ^= 1;
assert.throws(() => implementations.after.validateRetainedTrees([
  {...input[0], raw_base64: changed.toString('base64')}
], files), /do not match their Git object SHA/);
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
console.log(JSON.stringify({
  runtime: {node: process.version, v8: process.versions.v8, platform: process.platform,
    arch: process.arch, cpu: os.cpus()[0]?.model},
  source: {before: implementations.before.source_sha, after: implementations.after.source_sha},
  input: {git_tree_sha: expectedSHA, bytes: raw.length, entries: baseline.tree.length},
  method: {warmups_per_version: 1, alternating_pairs: 5, clock: 'performance.now',
    scope: 'complete production validateRetainedTrees, no provider I/O', equality_checks_outside_timing: true},
  samples,
  median_ms: {before: median(samples.map(x => x.before_ms)), after: median(samples.map(x => x.after_ms))},
  controls: {complete_results_equal: true, framing_lengths: lengths,
    native_crypto_equal: true, changed_bytes_rejected: true, provider_calls: 0}
}, null, 2));
