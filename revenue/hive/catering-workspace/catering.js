/* Catering Workspace: offline calculation and import/export, no provider calls. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Catering = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const fail = message => { throw new Error(message); };
  const text = (value, name) => typeof value === 'string' ? value.trim() : fail(`${name} must be text.`);
  function scaled(value, name, places = 2) {
    if (typeof value !== 'string' && typeof value !== 'number') fail(`${name} must be a number or decimal text.`);
    const s = String(value ?? '').trim();
    const pattern = new RegExp(`^\\d+(?:\\.\\d{1,${places}})?$`);
    if (!pattern.test(s)) fail(`${name} must be a non-negative decimal with at most ${places} decimal places.`);
    const [a, b = ''] = s.split('.');
    const n = BigInt(a) * (10n ** BigInt(places)) + BigInt(b.padEnd(places, '0'));
    return safe(n, name);
  }
  function safe(n, name) {
    if (n < 0n || n > BigInt(Number.MAX_SAFE_INTEGER)) fail(`${name} exceeds exact numeric capacity.`);
    return Number(n);
  }
  function integer(value, name, minimum = 0) {
    if (typeof value !== 'string' && typeof value !== 'number') fail(`${name} must be a number or whole-number text.`);
    const s = String(value ?? '').trim();
    if (!/^\d+$/.test(s)) fail(`${name} must be a whole number.`);
    const n = safe(BigInt(s), name);
    if (n < minimum) fail(`${name} must be at least ${minimum}.`);
    return n;
  }
  function percent(value, name) {
    const n = scaled(value, name);
    if (n > 10000) fail(`${name} must be between 0 and 100.`);
    return n;
  }
  const round = (n, d) => (n + d / 2n) / d;
  const ceil = (n, d) => (n + d - 1n) / d;
  const money = cents => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;
  const copy = value => JSON.parse(JSON.stringify(value));
  function menu(items) {
    if (!Array.isArray(items) || !items.length) fail('Import at least one menu item.');
    const seen = new Set();
    return items.map((item, i) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) fail(`Menu row ${i + 1} must be an object.`);
      const id = text(item.id, 'Menu ID');
      if (!id || seen.has(id)) fail(`Menu IDs must be nonempty and unique: ${id}.`);
      seen.add(id);
      const name = text(item.name, 'Menu name');
      const unit = text(item.unit, 'Selling unit');
      if (!name || !unit) fail(`Name and selling unit are required for ${id}.`);
      const serves = scaled(item.serves, `${id} portions per unit`);
      if (!serves) fail(`${id} portions per unit must be positive.`);
      return {id, name, unit, serves: String(item.serves), price: money(scaled(item.price, `${id} price`)),
        allergens: text(item.allergens ?? '', 'Allergen notes'), prep: text(item.prep ?? '', 'Preparation notes')};
    });
  }
  function quote(document) {
    if (!document || document.version !== 1) fail('Expected a Catering Workspace version 1 document.');
    const items = menu(document.menu), event = document.event;
    if (!event || typeof event !== 'object' || Array.isArray(event)) fail('Event details are required.');
    const revision = integer(document.revision, 'Revision', 1);
    for (const field of ['name', 'customer', 'date', 'location', 'dietary', 'notes', 'paymentLink']) text(event[field] ?? '', field);
    const headcount = integer(event.headcount, 'Headcount', 1);
    const buffer = percent(event.buffer, 'Preparation buffer');
    const serviceRate = percent(event.serviceRate, 'Service percentage');
    const taxRate = percent(event.taxRate, 'Tax percentage');
    const depositRate = percent(event.depositRate, 'Deposit percentage');
    const delivery = scaled(event.delivery, 'Delivery');
    const discount = scaled(event.discount, 'Discount');
    const received = scaled(event.received, 'Manually recorded received amount');
    if (!Array.isArray(event.lines) || !event.lines.length) fail('Select at least one menu item.');
    const byId = new Map(items.map(item => [item.id, item])), used = new Set();
    let subtotal = 0n;
    const lines = event.lines.map(line => {
      if (!line || typeof line !== 'object') fail('Each order line must be an object.');
      const item = byId.get(line.id);
      if (!item || used.has(line.id)) fail(`Order lines require distinct known menu IDs: ${line.id}.`);
      used.add(line.id);
      const guests = line.guests === '' || line.guests == null ? headcount : integer(line.guests, `${item.name} guest count`);
      if (guests > headcount) fail(`${item.name}: guest count exceeds the event headcount.`);
      const unitCents = scaled(line.price === '' || line.price == null ? item.price : line.price, `${item.name} price`);
      const portions = scaled(item.serves, `${item.name} portions`);
      const units = safe(ceil(BigInt(guests) * BigInt(10000 + buffer) * 100n, 10000n * BigInt(portions)), 'Prepared units');
      const cents = BigInt(units) * BigInt(unitCents);
      subtotal += cents;
      return {...item, guests, units, unitCents, lineCents: safe(cents, 'Line price'),
        plannedPortions: safe(BigInt(units) * BigInt(portions), 'Portions') / 100};
    });
    const service = round(subtotal * BigInt(serviceRate), 10000n);
    const beforeDiscount = subtotal + service + BigInt(delivery);
    if (BigInt(discount) > beforeDiscount) fail('Discount exceeds food, service and delivery combined.');
    const taxable = beforeDiscount - BigInt(discount);
    const tax = round(taxable * BigInt(taxRate), 10000n);
    const total = taxable + tax;
    const deposit = round(total * BigInt(depositRate), 10000n);
    const balance = total > BigInt(received) ? total - BigInt(received) : 0n;
    const credit = BigInt(received) > total ? BigInt(received) - total : 0n;
    const depositDue = deposit > BigInt(received) ? deposit - BigInt(received) : 0n;
    const values = {subtotal, service, delivery: BigInt(delivery), discount: BigInt(discount), tax, total,
      deposit, received: BigInt(received), balance, credit, depositDue};
    const totals = Object.fromEntries(Object.entries(values).map(([key, value]) => [key, safe(value, key)]));
    let paymentLink = '';
    if (event.paymentLink) {
      try {
        const url = new URL(event.paymentLink);
        if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error();
        paymentLink = url.href;
      } catch (_) { fail('Payment handoff must be an http(s) URL without embedded credentials.'); }
    }
    const confirmation = document.confirmation;
    if (confirmation != null && (typeof confirmation !== 'object' || Array.isArray(confirmation) ||
      typeof confirmation.reference !== 'string' || !confirmation.reference.trim() ||
      !Number.isSafeInteger(confirmation.revision) || confirmation.revision < 1)) fail('Confirmation requires a reference and a positive integer revision.');
    return {revision, headcount, lines, totals, paymentLink,
      confirmed: Boolean(confirmation && confirmation.revision === revision),
      dietary: event.dietary || '',
      warnings: ['Dietary requests and allergen notes require the caterer\'s review; no suitability is inferred.',
        'Amounts received are manual records, not processor-confirmed payments.']};
  }
  function parseCSV(source) {
    source = String(source).replace(/^\uFEFF/, '');
    const rows = []; let row = [], cell = '', state = 'start';
    const endCell = () => { row.push(cell); cell = ''; state = 'start'; };
    for (let i = 0; i < source.length; i++) {
      const c = source[i];
      if (state === 'quoted') {
        if (c === '"') { if (source[i + 1] === '"') { cell += '"'; i++; } else state = 'closed'; }
        else cell += c;
      } else if (c === ',' || c === '\n' || c === '\r') {
        endCell();
        if (c !== ',') { rows.push(row); row = []; if (c === '\r' && source[i + 1] === '\n') i++; }
      } else if (c === '"' && state === 'start') state = 'quoted';
      else {
        if (state === 'closed' || c === '"') fail('Malformed CSV quoting.');
        cell += c; state = 'plain';
      }
    }
    if (state === 'quoted') fail('CSV has an unfinished quoted field.');
    if (row.length || cell || state !== 'start') { endCell(); rows.push(row); }
    return rows.filter(r => r.some(c => c !== ''));
  }
  function importMenu(source) {
    const s = source.trim();
    if (s.startsWith('[') || s.startsWith('{')) {
      const value = JSON.parse(s); return menu(Array.isArray(value) ? value : value.menu);
    }
    const [header, ...rows] = parseCSV(source);
    if (!header) fail('Menu file is empty.');
    const columns = header.map(x => x.trim());
    if (new Set(columns).size !== columns.length) fail('CSV column names must be distinct.');
    for (const required of ['id', 'name', 'unit', 'serves', 'price']) if (!columns.includes(required)) fail(`CSV is missing ${required}.`);
    return menu(rows.map((row, i) => {
      if (row.length !== columns.length) fail(`CSV data row ${i + 1} has ${row.length} fields; expected ${columns.length}.`);
      return Object.fromEntries(columns.map((key, j) => [key, row[j]]));
    }));
  }
  const csvCell = value => {
    let s = String(value ?? '');
    if (/^[\s]*[=+@-]/.test(s) || /^[\t\r\n]/.test(s)) s = "'" + s;
    return '"' + s.replace(/"/g, '""') + '"';
  };
  const csv = rows => rows.map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
  function kitchenCSV(document) {
    const q = quote(document), e = document.event;
    return csv([
      ['event', 'revision', 'date', 'location', 'headcount', 'sku', 'item', 'guests', 'units', 'unit', 'portions', 'allergen_notes', 'prep_notes', 'dietary_requests', 'event_notes'],
      ...q.lines.map(l => [e.name, q.revision, e.date, e.location, q.headcount, l.id, l.name, l.guests,
        l.units, l.unit, l.plannedPortions, l.allergens || 'Not supplied', l.prep, q.dietary, e.notes])
    ]);
  }
  function load(source) { const d = JSON.parse(source), q = quote(d); d.revision = q.revision; return copy(d); }
  function sample() {
    return {version: 1, revision: 1, confirmation: null,
      menu: [
        {id: 'GARDEN', name: 'Garden salad', unit: 'tray', serves: '10', price: '45.00', allergens: 'Dressing ingredients to be reviewed', prep: 'Pack dressing separately.'},
        {id: 'MAIN', name: 'Roast main course', unit: 'tray', serves: '10', price: '80.00', allergens: 'Recipe details to be confirmed', prep: 'Confirm service and holding plan.'},
        {id: 'BREAD', name: 'Bread roll', unit: 'roll', serves: '1', price: '1.50', allergens: 'Wheat; verify supplier label', prep: 'Pack by service table.'}
      ],
      event: {name: 'Sample 40-person lunch', customer: 'Example only — replace before use', date: '', location: '', headcount: '40',
        buffer: '10', serviceRate: '10', taxRate: '0', delivery: '25.00', discount: '0.00', depositRate: '30', received: '0.00',
        dietary: 'Collect guest requests and review recipes before confirming.', notes: '', paymentLink: '',
        lines: ['GARDEN', 'MAIN', 'BREAD'].map(id => ({id, guests: '', price: ''}))}};
  }
  return {scaled, integer, money, menu, quote, parseCSV, importMenu, csv, kitchenCSV, load, sample, copy};
});
