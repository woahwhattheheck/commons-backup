'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const C = require('./catering.js');
const event = () => C.sample();
test('40-person event produces exact quote, deposit and kitchen quantities', () => {
  const d = event(), q = C.quote(d);
  assert.deepEqual(q.lines.map(l => l.units), [5, 5, 44]);
  assert.deepEqual(q.totals, {subtotal: 69100, service: 6910, delivery: 2500, discount: 0, tax: 0,
    total: 78510, deposit: 23553, received: 0, balance: 78510, credit: 0, depositDue: 23553});
  assert.equal(C.parseCSV(C.kitchenCSV(d))[1][8], '5');
});
test('60-person revision recalculates quote and kitchen from identical lines', () => {
  const d = event(); d.event.headcount = '60'; d.revision = 2;
  const q = C.quote(d), rows = C.parseCSV(C.kitchenCSV(d));
  assert.deepEqual(q.lines.map(l => l.units), [7, 7, 66]);
  assert.equal(q.totals.subtotal, 97400); assert.equal(q.totals.total, 109640); assert.equal(q.totals.deposit, 32892);
  assert.deepEqual(rows.slice(1).map(r => Number(r[8])), [7, 7, 66]);
  assert.ok(rows.slice(1).every(r => r[1] === '2' && r[4] === '60'));
});
test('zero guest segment and zero price differ from empty defaults', () => {
  const d = event(); d.event.lines[0].guests = '0'; d.event.lines[1].price = '0.00';
  const q = C.quote(d); assert.equal(q.lines[0].units, 0); assert.equal(q.lines[1].units, 5);
  assert.equal(q.lines[1].lineCents, 0); assert.equal(q.lines[2].lineCents, 6600);
});
test('fractional portions use exact batch rounding', () => {
  const d = event(); d.menu[0].serves = '2.50'; d.event.headcount = '7'; d.event.buffer = '0';
  assert.equal(C.quote(d).lines[0].units, 3); assert.equal(C.quote(d).lines[0].plannedPortions, 7.5);
});
test('one-cent boundary does not add a phantom batch', () => {
  const d = event(); d.event.headcount = '100'; d.event.buffer = '0.01'; d.menu[0].serves = '100.01';
  assert.equal(C.quote(d).lines[0].units, 1);
});
test('service then delivery then discount then tax, with half-up cent rounding', () => {
  const d = event(); d.event.taxRate = '7.25'; d.event.discount = '10.00';
  const q = C.quote(d); assert.equal(q.totals.tax, 5619); assert.equal(q.totals.total, 83129); assert.equal(q.totals.deposit, 24939);
});
test('manual receipts reduce deposit due and balance without claiming payment verification', () => {
  const d = event(); d.event.received = '235.53'; const q = C.quote(d);
  assert.equal(q.totals.depositDue, 0); assert.equal(q.totals.balance, 54957); assert.ok(q.warnings[1].includes('manual'));
  d.event.received = '800.00'; const over = C.quote(d); assert.equal(over.totals.balance, 0); assert.equal(over.totals.credit, 1490);
});
test('CSV handles BOM, CRLF, escaped quotes, commas and multiline preparation', () => {
  const rows = C.importMenu('\uFEFFid,name,unit,serves,price,allergens,prep\r\nA,"Salad, \"\"garden\"\"",tray,10,45.00,,"Line 1\r\nLine 2"\r\n');
  assert.equal(rows[0].name, 'Salad, "garden"'); assert.equal(rows[0].prep, 'Line 1\r\nLine 2');
});
test('CSV rejects malformed quoting, duplicate headers and wrong row shape', () => {
  for (const s of ['"unfinished', 'a"b', '"a"x']) assert.throws(() => C.parseCSV(s));
  assert.throws(() => C.importMenu('id,name,unit,serves,price,price\nA,a,tray,1,2,2'));
  assert.throws(() => C.importMenu('id,name,unit,serves,price\nA,a,tray,1'));
});
test('menu import validates duplicate IDs and preserves known supplied fields', () => {
  const d = event(); assert.deepEqual(C.importMenu(JSON.stringify(d.menu)), d.menu);
  assert.throws(() => C.menu([...d.menu, d.menu[0]]), /unique/);
  assert.throws(() => C.menu([{...d.menu[0], serves: '0'}]), /positive/);
});
test('save/load is lossless and does not mutate input during calculation', () => {
  const d = event(); d.event.dietary = '8 vegetarian guests; recipes awaiting review'; const before = JSON.stringify(d);
  C.quote(d); C.kitchenCSV(d); assert.equal(JSON.stringify(d), before); assert.deepEqual(C.load(before), d);
  assert.throws(() => C.load('{"version":2}'));
  const imported = C.load(JSON.stringify({...d, revision: '7'}));
  assert.equal(imported.revision, 7);
  imported.confirmation = {revision: imported.revision, reference: 'Imported event reference'};
  assert.equal(C.quote(imported).confirmed, true);
});
test('confirmation belongs to exact revision and malformed confirmation cannot import', () => {
  const d = event(); d.confirmation = {revision: 1, reference: 'Example confirmation'};
  assert.equal(C.quote(d).confirmed, true); d.revision++; assert.equal(C.quote(d).confirmed, false);
  d.confirmation = {revision: 2, reference: ''}; assert.throws(() => C.quote(d));
});
test('nonfinite, negative, missing, imprecise and oversized numeric input is rejected', () => {
  for (const value of ['NaN', 'Infinity', '-1', '', '1e2', '0.001', '9007199254740992']) assert.throws(() => C.scaled(value, 'Value'));
  const d = event(); for (const value of ['0', '1.5', '-1', '']) { d.event.headcount = value; assert.throws(() => C.quote(d)); }
});
test('invalid percentages, discounts, overallocated segments and unknown selections produce actionable errors', () => {
  for (const [field, value, pattern] of [['buffer', '101', /between/], ['discount', '9999', /exceeds/]]) {
    const d = event(); d.event[field] = value; assert.throws(() => C.quote(d), pattern);
  }
  const d = event(); d.event.lines[0].guests = '41'; assert.throws(() => C.quote(d), /headcount/);
  d.event.lines[0] = {id: 'missing'}; assert.throws(() => C.quote(d), /known/);
});
test('payment links are ordinary handoffs, never script URLs or embedded secrets', () => {
  const d = event(); d.event.paymentLink = 'https://example.com/existing-payment'; assert.equal(C.quote(d).paymentLink, d.event.paymentLink);
  for (const s of ['javascript:void(0)', 'https://user:pass@example.com', '/relative']) { d.event.paymentLink = s; assert.throws(() => C.quote(d)); }
});
test('CSV keeps dietary requests and neutralizes formula-like cells', () => {
  const d = event(); d.event.name = '=EXAMPLE'; d.event.dietary = 'Review sesame request';
  const rows = C.parseCSV(C.kitchenCSV(d)); assert.equal(rows[1][0], "'=EXAMPLE"); assert.equal(rows[1][13], d.event.dietary);
});
test('rounding is monotone over 1 through 1000 guests and inputs stay independent', () => {
  const d = event(); let prior = 0;
  for (let guests = 1; guests <= 1000; guests++) { d.event.headcount = String(guests); const q = C.quote(d);
    assert.ok(q.totals.total >= prior); prior = q.totals.total;
    q.lines.forEach(l => assert.ok(l.plannedPortions * 100 + 1e-7 >= guests * 110));
  }
  assert.equal(event().event.headcount, '40');
});
