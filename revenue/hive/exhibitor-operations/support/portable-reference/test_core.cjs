'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('./core.js');
const NOW = '2026-09-08T12:00:00.000Z';
const LATER = '2026-09-08T13:00:00.000Z';
const file = (id = 'asset-one', data = Buffer.from([0, 1, 2, 128, 255])) => ({id, name: 'original-logo.bin', mime: 'application/octet-stream', size: data.length, base64: data.toString('base64')});
function setup() {return D.sample(NOW);}
function first(state) {return state.exhibitors[0];}
function reply(state, patch = {}, acknowledged = true) {return D.submission(D.portal(state, first(state).id), patch, acknowledged, NOW);}

test('blank and sample have independent identifiers, deadlines, and collections', () => {
  const a = D.blank(NOW), b = D.blank(NOW); assert.notEqual(a.event.id, b.event.id);
  assert.equal(a.event.deadline, '2026-09-22T12:00:00.000Z'); a.exhibitors.push('x'); assert.deepEqual(b.exhibitors, []);
});
test('onboarding keeps earlier records and does not mutate caller state', () => {
  const s = setup(), before = JSON.stringify(s), out = D.saveExhibitor(s, null, {company: 'Second company'}, NOW);
  assert.equal(out.state.exhibitors.length, 2); assert.equal(JSON.stringify(s), before);
  assert.notEqual(out.id, first(s).id); assert.deepEqual(out.state.exhibitors[1].assets, []);
});
test('event changes create a new current notice and retain old event fields', () => {
  const s = setup(), n = D.saveEvent(s, {deadline: '2026-09-25T18:00:00Z', instructions: 'Updated load-in'}, NOW);
  assert.equal(n.event.revision, s.event.revision + 1); assert.equal(n.event.deadline, '2026-09-25T18:00:00.000Z');
  assert.equal(n.eventHistory.at(-1).previous.deadline, s.event.deadline); assert.equal(s.event.instructions.includes('Synthetic'), true);
});
test('deadline validation rejects invalid dates and local times without timezone', () => {
  for (const value of ['2026-02-30T12:00:00Z', '2026-13-01T12:00:00Z', '2026-09-08T12:00', 'garbage', '2026-09-08T25:00:00Z']) assert.throws(() => D.instant(value));
  assert.equal(D.instant('2028-02-29T12:00:00Z'), '2028-02-29T12:00:00.000Z');
});
test('portable portal contains only selected exhibitor, no other companies or history', () => {
  let s = setup(); s = D.saveExhibitor(s, null, {company: 'OTHER-COMPANY-PRIVATE', notes: 'UNRELATED-SECRET'}, NOW).state;
  const p = D.portal(s, first(s).id), json = JSON.stringify(p);
  assert.equal(json.includes('OTHER-COMPANY-PRIVATE'), false); assert.equal(json.includes('UNRELATED-SECRET'), false);
  assert.equal('history' in p.details, false); assert.equal('submissions' in p.details, false); assert.equal('exhibitors' in p, false);
});
test('original attachment bytes survive portal and returned submission and backup', () => {
  const s = setup(), sub = reply(s, {assets: [file()]}), out = D.importSubmission(s, sub, LATER);
  assert.equal(out.status, 'applied'); const n = D.validateWorkspace(JSON.parse(JSON.stringify(out.state)));
  assert.deepEqual(Buffer.from(first(n).assets[0].base64, 'base64'), Buffer.from([0, 1, 2, 128, 255]));
  assert.deepEqual(first(n).submissions[0].value.details.assets, [file()]);
});
test('asset encoding validates size, empty files, and duplicate IDs', () => {
  assert.equal(D.asset(file('empty', Buffer.alloc(0))).size, 0);
  assert.throws(() => D.asset({...file(), size: 100}), /size/);
  assert.throws(() => D.asset({...file(), base64: '%%%'}), /encoding/);
  assert.throws(() => D.saveExhibitor(setup(), null, {company: 'X', assets: [file(), file()]}, NOW), /Duplicate/);
});
test('exact repeat of an already received submission is idempotent', () => {
  const s = setup(), sub = reply(s, {notes: 'Incoming'}), a = D.importSubmission(s, sub, NOW), b = D.importSubmission(a.state, sub, LATER);
  assert.equal(b.status, 'duplicate'); assert.deepEqual(b.state, a.state); assert.equal(first(b.state).submissions.length, 1);
});
test('reusing a submission ID for different content never overwrites evidence', () => {
  const s = setup(), sub = reply(s), a = D.importSubmission(s, sub, NOW), before = JSON.stringify(a.state);
  assert.throws(() => D.importSubmission(a.state, {...sub, details: {...sub.details, notes: 'Changed'}}, LATER), /different content/);
  assert.equal(JSON.stringify(a.state), before);
});
test('different event or missing exhibitor leaves workspace unchanged', () => {
  const s = setup(), before = JSON.stringify(s), sub = reply(s);
  assert.throws(() => D.importSubmission(s, {...sub, eventId: 'different'}, NOW), /different event/);
  assert.throws(() => D.importSubmission(s, {...sub, exhibitorId: 'different'}, NOW), /not found/);
  assert.equal(JSON.stringify(s), before);
});
test('stale submission is retained as a review item without replacing current fields', () => {
  const s = setup(), sub = reply(s, {booth: 'C-09', notes: 'Incoming request'});
  const current = D.saveExhibitor(s, first(s).id, {power: 'Organizer confirmed 20 A'}, NOW).state;
  const result = D.importSubmission(current, sub, LATER);
  assert.equal(result.status, 'conflict'); assert.equal(first(result.state).booth, 'B-12');
  assert.equal(first(result.state).power, 'Organizer confirmed 20 A'); assert.equal(first(result.state).revision, first(current).revision);
  assert.equal(D.status(result.state, first(result.state), NOW), 'Submission to review');
});
test('selective conflict merge preserves unrelated edits and unions assets', () => {
  let s = setup(); const sub = reply(s, {booth: 'C-09', notes: 'Incoming', assets: [file('incoming')]});
  s = D.saveExhibitor(s, first(s).id, {notes: 'Organizer notes', assets: [file('organizer')]}, NOW).state;
  s = D.importSubmission(s, sub, LATER).state;
  const n = D.resolveSubmission(s, first(s).id, sub.id, ['booth', 'assets'], LATER);
  assert.equal(first(n).booth, 'C-09'); assert.equal(first(n).notes, 'Organizer notes'); assert.equal(first(n).assets.length, 2);
  assert.equal(first(n).submissions[0].status, 'reviewed'); assert.equal(first(n).acknowledgedEventRevision, 0);
});
test('conflicting asset identity does not overwrite current or retained bytes', () => {
  let s = setup(); const sub = reply(s, {assets: [file('same', Buffer.from('incoming'))]});
  s = D.saveExhibitor(s, first(s).id, {assets: [file('same', Buffer.from('current'))]}, NOW).state;
  s = D.importSubmission(s, sub, NOW).state; const before = JSON.stringify(s);
  assert.throws(() => D.resolveSubmission(s, first(s).id, sub.id, ['assets'], NOW), /different bytes/);
  assert.equal(JSON.stringify(s), before);
});
test('keep-current disposition preserves original returned submission', () => {
  let s = setup(); const sub = reply(s, {notes: 'Old notes'}); s = D.saveExhibitor(s, first(s).id, {notes: 'Current'}, NOW).state;
  s = D.importSubmission(s, sub, NOW).state; s = D.dismissSubmission(s, first(s).id, sub.id, 'Discussed with exhibitor; keep current', NOW);
  assert.equal(first(s).notes, 'Current'); assert.equal(first(s).submissions[0].value.details.notes, 'Old notes');
  assert.equal(first(s).submissions[0].status, 'kept-current'); assert.deepEqual(D.validateWorkspace(s), s);
});
test('old notice acknowledgement does not acknowledge an updated deadline', () => {
  const s = setup(), sub = reply(s), n = D.saveEvent(s, {deadline: '2026-10-01T18:00:00Z'}, NOW), out = D.importSubmission(n, sub, NOW).state;
  assert.equal(D.status(out, first(out), NOW), 'Current notice unacknowledged');
  assert.equal(first(out).acknowledgedEventRevision, s.event.revision);
  assert.match(D.reminder(out, first(out).id), /2026-10-01T18:00:00.000Z/);
});
test('latest returned acknowledgement changes notice state and unresolved requests stay visible', () => {
  let s = setup(); s = D.importSubmission(s, reply(s), NOW).state;
  assert.equal(D.status(s, first(s), NOW), 'Current notice acknowledged');
  s = D.importSubmission(s, reply(s, {changeRequest: 'Need a wider booth'}), NOW).state;
  assert.equal(D.status(s, first(s), NOW), 'Change needs review');
  s = D.saveExhibitor(s, first(s).id, {booth: 'D-02', resolution: 'Changed to 6 m × 3 m at D-02'}, NOW).state;
  assert.equal(D.status(s, first(s), NOW), 'Current notice acknowledged');
});
test('future notice acknowledgement is rejected without mutation', () => {
  const s = setup(), sub = reply(s), before = JSON.stringify(s);
  assert.throws(() => D.importSubmission(s, {...sub, acknowledgedEventRevision: s.event.revision + 1}, NOW), /newer/);
  assert.equal(JSON.stringify(s), before);
});
test('deadline passed label does not imply automatic sending or receipt', () => {
  const s = setup(); assert.match(D.status(s, first(s), '2027-01-01T00:00:00.000Z'), /Deadline passed/);
  assert.match(D.reminder(s, first(s).id), /Draft only — not sent/);
});
test('floor-plan CSV quotes fields and neutralizes spreadsheet formula-like prefixes', () => {
  let s = setup(); s = D.saveExhibitor(s, first(s).id, {company: '=1+1', notes: 'Line one\n"Line two"', power: '  +SUM(A1:A2)'}, NOW).state;
  const csv = D.floorplan(s); assert.match(csv, /"'=1\+1"/); assert.match(csv, /"'  \+SUM/); assert.match(csv, /Line one\n""Line two""/);
});
test('calendar keeps stable event UID and advances sequence for deadline updates', () => {
  const s = setup(), id = first(s).id, a = D.calendar(s, id, NOW);
  const n = D.saveEvent(s, {deadline: '2026-10-01T18:00:00Z'}, NOW), b = D.calendar(n, id, LATER);
  assert.equal(a.match(/UID:([^\r]+)/)[1], b.match(/UID:([^\r]+)/)[1]);
  assert.match(b, new RegExp('SEQUENCE:' + n.event.revision)); assert.match(b, /DTSTART:20261001T180000Z/);
});
test('calendar folds UTF-8 lines by byte length without splitting code points', () => {
  const s = D.saveEvent(setup(), {name: '展示会🎪'.repeat(40), instructions: 'Bring a table; two chairs, please.\nReply here.'}, NOW);
  const cal = D.calendar(s, first(s).id, NOW);
  for (const line of cal.split('\r\n')) assert.ok(Buffer.byteLength(line) <= 75);
  assert.match(cal, /\\;/); assert.match(cal, /\\,/); assert.match(cal, /\\n/); assert.equal(cal.includes('\uFFFD'), false);
});
test('backup validation round-trips full assets, old revisions, and conflict dispositions', () => {
  let s = setup(); const sub = reply(s, {assets: [file()], notes: 'Incoming'});
  s = D.saveExhibitor(s, first(s).id, {notes: 'Current'}, NOW).state; s = D.importSubmission(s, sub, LATER).state;
  s = D.resolveSubmission(s, first(s).id, sub.id, ['assets'], LATER);
  assert.deepEqual(D.validateWorkspace(JSON.parse(JSON.stringify(s))), s);
});
test('malformed backups cannot mix companies, duplicate rows, or corrupt retained originals', () => {
  const s = setup(), dup = D.copy(s); dup.exhibitors.push(D.copy(first(s))); assert.throws(() => D.validateWorkspace(dup), /duplicate/);
  const bad = D.copy(s); bad.exhibitors[0].assets = [{...file(), size: 999}]; assert.throws(() => D.validateWorkspace(bad), /size/);
  let mixed = D.importSubmission(s, reply(s), NOW).state; mixed.exhibitors[0].submissions[0].value.exhibitorId = 'OTHER';
  assert.throws(() => D.validateWorkspace(mixed), /different event or exhibitor/);
});
test('normal import ignores unrelated prototype-shaped fields without modifying prototypes', () => {
  const s = setup(), raw = JSON.parse('{"company":"Safe","__proto__":{"polluted":true}}');
  const n = D.saveExhibitor(s, first(s).id, raw, NOW).state;
  assert.equal({}.polluted, undefined); assert.equal(first(n).company, 'Safe'); assert.equal(Object.hasOwn(first(n), '__proto__'), false);
});
