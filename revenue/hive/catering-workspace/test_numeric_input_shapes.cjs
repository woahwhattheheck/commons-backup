'use strict';
// Exercises the complete shipped calculator, not a duplicate implementation.
const test = require('node:test');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const C = require('./catering.js');

function rejectsDocument(change, label) {
  const document = C.sample();
  change(document);
  const serialized = JSON.stringify(document);
  assert.throws(() => C.load(serialized), Error, label);
  assert.equal(JSON.stringify(document), serialized, 'rejection must not mutate the caller');
}

test('scaled rejects arrays and objects without invoking coercion', () => {
  for (const value of [[45], ['45.00'], [[45]], new Number(45), new String('45.00'),
    {toString() { throw new Error('coercion must not execute'); }}]) {
    assert.throws(() => C.scaled(value, 'Amount'), /Amount must be a number or decimal text/);
  }
});

test('integer rejects arrays and objects without invoking coercion', () => {
  for (const value of [[40], ['40'], [[40]], new Number(40), new String('40'),
    {toString() { throw new Error('coercion must not execute'); }}]) {
    assert.throws(() => C.integer(value, 'Count'), /Count must be a number or whole-number text/);
  }
});

test('event JSON numeric fields cannot be single-element arrays', () => {
  const fields = ['headcount', 'buffer', 'serviceRate', 'taxRate', 'depositRate',
    'delivery', 'discount', 'received'];
  for (const field of fields) {
    for (const wrap of [value => [value], value => [[value]]]) {
      rejectsDocument(d => { d.event[field] = wrap(d.event[field]); }, field);
    }
  }
});

test('revision arrays cannot become valid confirmation revisions on load', () => {
  rejectsDocument(d => {
    d.revision = [1];
    d.confirmation = {revision: 1, reference: 'synthetic confirmation'};
  }, 'revision');
});

test('line guest override arrays cannot become real guest counts', () => {
  rejectsDocument(d => { d.event.lines[0].guests = [20]; }, 'line guests');
});

test('line price override arrays cannot become actual quote prices', () => {
  rejectsDocument(d => { d.event.lines[0].price = ['45.00']; }, 'line price');
});

test('menu JSON import refuses array-valued price and serves', () => {
  for (const field of ['price', 'serves']) {
    const items = C.sample().menu;
    items[0][field] = [items[0][field]];
    for (const payload of [items, {menu: items}]) {
      assert.throws(() => C.importMenu(JSON.stringify(payload)), Error, field);
    }
    rejectsDocument(d => { d.menu[0][field] = [d.menu[0][field]]; }, field);
  }
});

test('kitchen export refuses malformed numeric inputs instead of publishing units', () => {
  const d = C.sample();
  d.event.headcount = ['40'];
  assert.throws(() => C.kitchenCSV(d), Error);
});

test('zero, whitespace, leading zeros and numeric scalar inputs retain exact values', () => {
  for (const [value, expected] of [[0, 0], ['0', 0], [45, 4500], [45.5, 4550],
    [' 0045.50 ', 4550], ['0.01', 1], ['90071992547409.91', Number.MAX_SAFE_INTEGER]]) {
    assert.equal(C.scaled(value, 'Amount'), expected);
  }
  for (const [value, expected] of [[0, 0], ['0', 0], [40, 40], [' 0040 ', 40],
    [Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER]]) {
    assert.equal(C.integer(value, 'Count'), expected);
  }
});

test('old invalid formats and range bounds still fail', () => {
  for (const value of [null, undefined, true, false, {}, [], '', ' ', '-1', '1e3',
    '0.001', NaN, Infinity, -Infinity, '90071992547409.92']) {
    assert.throws(() => C.scaled(value, 'Amount'), Error);
  }
  for (const value of [null, undefined, true, false, {}, [], '', '-1', '1.5',
    '1e3', NaN, Infinity, '9007199254740992']) {
    assert.throws(() => C.integer(value, 'Count'), Error);
  }
  assert.throws(() => C.integer(0, 'Count', 1), /at least 1/);
});

test('40-person sample retains exact cents and kitchen quantities', () => {
  const q = C.quote(C.sample());
  assert.deepEqual(q.lines.map(l => l.units), [5, 5, 44]);
  assert.equal(q.totals.total, 78510);
  assert.equal(q.totals.deposit, 23553);
  assert.equal(q.confirmed, false);
});

test('60-person change retains exact cents and quantities', () => {
  const d = C.sample();
  d.event.headcount = 60;
  const q = C.quote(d);
  assert.deepEqual(q.lines.map(l => l.units), [7, 7, 66]);
  assert.equal(q.totals.total, 109640);
  assert.equal(q.totals.deposit, 32892);
});

test('numeric text revision still normalizes and confirms only the matching revision', () => {
  const d = C.sample();
  d.revision = ' 01 ';
  d.confirmation = {revision: 1, reference: 'synthetic confirmation'};
  const loaded = C.load(JSON.stringify(d));
  assert.equal(loaded.revision, 1);
  assert.equal(C.quote(loaded).confirmed, true);
  loaded.revision = 2;
  assert.equal(C.quote(loaded).confirmed, false);
});

test('optional line defaults and explicit numeric zero still differ correctly', () => {
  for (const blank of ['', null, undefined]) {
    const d = C.sample();
    d.event.lines[0].guests = blank;
    d.event.lines[0].price = blank;
    assert.equal(C.quote(d).totals.total, 78510);
  }
  const d = C.sample();
  d.event.lines[0].guests = 0;
  d.event.lines[1].price = 0;
  const q = C.quote(d);
  assert.equal(q.lines[0].units, 0);
  assert.equal(q.lines[1].unitCents, 0);
});

test('valid CSV menu and JSON source produce the same exact quote', () => {
  const d = C.sample();
  const columns = ['id', 'name', 'unit', 'serves', 'price', 'allergens', 'prep'];
  const csv = C.csv([columns, ...d.menu.map(row => columns.map(key => row[key]))]);
  const fromCSV = C.copy(d);
  fromCSV.menu = C.importMenu(csv);
  const fromJSON = C.copy(d);
  fromJSON.menu = C.importMenu(JSON.stringify(d.menu));
  assert.deepEqual(C.quote(fromCSV), C.quote(fromJSON));
  assert.equal(C.kitchenCSV(fromCSV), C.kitchenCSV(fromJSON));
});

test('full valid quote and CSV outputs match the immutable baseline digest', () => {
  const outputs = [];
  for (const headcount of [1, 40, 60, 120]) {
    const d = C.sample();
    d.event.headcount = headcount;
    d.event.taxRate = '7.25';
    d.event.received = '250.00';
    outputs.push({quote: C.quote(d), kitchen: C.kitchenCSV(d), loaded: C.load(JSON.stringify(d))});
  }
  const actual = createHash('sha256').update(JSON.stringify(outputs)).digest('hex');
  assert.equal(actual, 'b907046488765ea137277768f29cc064dda17a710af1c00e65f0392110009837');
});
