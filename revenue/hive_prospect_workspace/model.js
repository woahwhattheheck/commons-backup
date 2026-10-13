/* Fieldnote data model. No network, dependencies, or browser globals required. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Fieldnote = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const VERSION = 1;
  const FIELDS = ['company', 'website', 'industry', 'location', 'name', 'email', 'title', 'source', 'tags', 'notes'];
  const ALIASES = {
    company: ['company', 'companyname', 'account', 'accountname', 'organization', 'organisation'],
    website: ['website', 'companywebsite', 'domain', 'companydomain', 'url'],
    industry: ['industry', 'sector'], location: ['location', 'city', 'headquarters'],
    name: ['name', 'contactname', 'fullname', 'personname'], email: ['email', 'emailaddress', 'workemail', 'contactemail'],
    title: ['title', 'jobtitle', 'position', 'role'], source: ['source', 'sourceurl', 'sourcelink', 'linkedinurl'],
    tags: ['tags', 'tag', 'labels'], notes: ['notes', 'note', 'description']
  };
  const clean = value => String(value == null ? '' : value).trim();
  const key = value => clean(value).toLocaleLowerCase('en-US').replace(/\s+/g, ' ');
  const unique = list => [...new Set(list.filter(Boolean))];
  function empty() { return { version: VERSION, nextId: 1, accounts: [], imports: [], segments: [] }; }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function safeURL(value) {
    try {
      const u = new URL(clean(value));
      return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : '';
    } catch (_) { return ''; }
  }
  function domain(value) {
    const v = clean(value);
    if (!v) return '';
    const u = safeURL(/^[a-z][a-z0-9+.-]*:\/\//i.test(v) ? v : 'https://' + v);
    if (!u) return '';
    const host = new URL(u).hostname.toLowerCase().replace(/^www\./, '').replace(/\.$/, '');
    return host.includes('.') && !host.includes(' ') ? host : '';
  }
  function parseCSV(text) {
    text = String(text).replace(/^\uFEFF/, '');
    const rows = []; let row = [], cell = '', quoted = false, closed = false;
    function endCell() { row.push(cell); cell = ''; closed = false; }
    function endRow() { endCell(); if (row.some(v => v.trim())) rows.push(row); row = []; }
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (c === '"') { quoted = false; closed = true; }
        else cell += c;
      } else if (c === '"') {
        if (cell.length || closed) throw new Error('Unexpected quote in CSV. Quote the entire field.');
        quoted = true;
      } else if (c === ',') endCell();
      else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; endRow(); }
      else if (closed) {
        if (c !== ' ' && c !== '\t') throw new Error('Unexpected text after a quoted CSV field.');
      } else cell += c;
    }
    if (quoted) throw new Error('CSV has an unfinished quoted field.');
    if (cell || row.length || closed) endRow();
    if (!rows.length) throw new Error('The CSV is empty.');
    const headers = rows.shift().map(clean);
    if (headers.some(h => !h)) throw new Error('Every CSV column needs a heading.');
    if (new Set(headers.map(key)).size !== headers.length) throw new Error('CSV column headings must be distinct.');
    return { headers, rows };
  }
  function suggestMapping(headers) {
    const result = {};
    for (const field of FIELDS) result[field] = headers.find(h => ALIASES[field].includes(key(h).replace(/[^a-z0-9]/g, ''))) || '';
    return result;
  }
  function splitTags(value) { return unique(clean(value).split(/[;,|]/).map(key)).sort(); }
  function mergeNotes(a, b) { return unique([clean(a), clean(b)].flatMap(v => v.split(/\n\n+/)).map(clean)).join('\n\n'); }
  function recordConflict(account, field, kept, incoming, source) {
    if (!kept || !incoming || key(kept) === key(incoming)) return;
    const item = { field, kept, incoming, source };
    if (!account.conflicts.some(x => JSON.stringify(x) === JSON.stringify(item))) account.conflicts.push(item);
  }
  function mergeAccount(target, incoming, source) {
    let changed = false;
    const before = JSON.stringify(target);
    for (const field of ['company', 'website', 'domain', 'industry', 'location']) {
      recordConflict(target, field, target[field], incoming[field], source);
      if (!target[field]) target[field] = incoming[field];
    }
    // An explicit company merge must retain every known domain identity. Otherwise
    // reimporting a merged-away account recreates it as a separate company.
    const domains = unique([target.domain, ...(target.domainAliases || []),
      incoming.domain, ...(incoming.domainAliases || [])]);
    if (domains.length > 1 || target.domainAliases || incoming.domainAliases) target.domainAliases = domains;
    target.tags = unique([...target.tags, ...incoming.tags]).sort();
    target.sources = unique([...target.sources, ...incoming.sources]);
    target.notes = mergeNotes(target.notes, incoming.notes);
    for (const contact of incoming.contacts) {
      const existing = target.contacts.find(c => contact.email ? key(c.email) === key(contact.email) : !c.email && key(c.name) === key(contact.name) && key(c.title) === key(contact.title));
      if (!existing) target.contacts.push(clone(contact));
      else {
        for (const field of ['name', 'email', 'title']) {
          recordConflict(target, 'contact.' + field, existing[field], contact[field], source);
          if (!existing[field]) existing[field] = contact[field];
        }
        existing.sources = unique([...existing.sources, ...contact.sources]);
      }
    }
    target.conflicts = [...target.conflicts];
    for (const c of incoming.conflicts || []) if (!target.conflicts.some(x => JSON.stringify(x) === JSON.stringify(c))) target.conflicts.push(clone(c));
    changed = JSON.stringify(target) !== before;
    return changed;
  }
  function previewImport(state, text, options = {}) {
    validateState(state);
    const parsed = parseCSV(text), mapping = options.mapping || suggestMapping(parsed.headers);
    if (!mapping.company && !mapping.website) throw new Error('Map at least Company or Website / domain.');
    const active = Object.values(mapping).filter(Boolean);
    if (active.some(h => !parsed.headers.includes(h))) throw new Error('A mapped column is not present in this CSV.');
    if (new Set(active).size !== active.length) throw new Error('Map each CSV column to only one field.');
    const next = clone(state), filename = clean(options.filename) || 'Customer import';
    const report = { filename, rows: parsed.rows.length, created: 0, merged: 0, unchanged: 0, errors: [], warnings: [] };
    parsed.rows.forEach((values, index) => {
      const rowNumber = index + 2;
      if (values.length > parsed.headers.length) { report.errors.push({ row: rowNumber, message: 'More values than column headings.' }); return; }
      const get = field => mapping[field] ? clean(values[parsed.headers.indexOf(mapping[field])]) : '';
      const company = get('company'), rawWebsite = get('website'), host = domain(rawWebsite);
      if (!company && !host) { report.errors.push({ row: rowNumber, message: 'Company name or valid company domain is required.' }); return; }
      if (rawWebsite && !host) { report.errors.push({ row: rowNumber, message: 'Website / domain is not a valid HTTP(S) company address.' }); return; }
      const email = get('email').toLowerCase();
      if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { report.errors.push({ row: rowNumber, message: 'Email is malformed; correct this row before import.' }); return; }
      const source = get('source'), name = get('name'), title = get('title');
      if (source && !safeURL(source)) report.warnings.push({ row: rowNumber, message: 'Source preserved as text, not a clickable web link.' });
      const sources = source ? [source] : [];
      const incoming = {
        id: '', company: company || host, website: host ? safeURL(/^[a-z][a-z0-9+.-]*:\/\//i.test(rawWebsite) ? rawWebsite : 'https://' + rawWebsite) : '',
        domain: host, industry: get('industry'), location: get('location'), stage: 'Research', tags: splitTags(get('tags')), notes: get('notes'),
        sources, contacts: (name || email) ? [{ name, email, title, sources }] : [], conflicts: [], importFiles: [filename]
      };
      // Domain is the strongest account identity. Name-only matches also require location.
      const domainMatches = host ? next.accounts.filter(a => a.domain === host || (a.domainAliases || []).includes(host)) : [];
      if (domainMatches.length > 1) {
        report.errors.push({ row: rowNumber, message: 'This domain matches multiple accounts. Merge the intended accounts explicitly before retrying.' }); return;
      }
      let existing = domainMatches[0];
      if (!existing) {
        const possible = next.accounts.filter(a => key(a.company) === key(incoming.company) && key(a.location) === key(incoming.location) && (!host || !a.domain));
        if (possible.length === 1) existing = possible[0];
        else if (possible.length > 1) { report.errors.push({ row: rowNumber, message: 'Ambiguous company name. Add the company domain to resolve this row.' }); return; }
      }
      if (existing) {
        const changed = mergeAccount(existing, incoming, filename);
        existing.importFiles = unique([...existing.importFiles, filename]);
        report[changed ? 'merged' : 'unchanged']++;
      } else { incoming.id = 'a' + next.nextId++; next.accounts.push(incoming); report.created++; }
    });
    return { state: next, report, headers: parsed.headers, mapping };
  }
  function commitImport(preview, now = new Date().toISOString()) {
    const result = clone(preview.state);
    result.imports.unshift({ ...clone(preview.report), at: now });
    validateState(result); return result;
  }
  function mergeDuplicates(state, ids) {
    const selected = unique(ids);
    if (selected.length < 2) throw new Error('Select at least two accounts to merge.');
    const next = clone(state), accounts = selected.map(id => next.accounts.find(a => a.id === id));
    if (accounts.some(a => !a)) throw new Error('A selected account no longer exists.');
    const target = accounts[0];
    for (const other of accounts.slice(1)) {
      mergeAccount(target, other, 'Manual merge: ' + other.id);
      target.importFiles = unique([...target.importFiles, ...other.importFiles]);
    }
    next.accounts = next.accounts.filter(a => !selected.slice(1).includes(a.id));
    return { state: next, id: target.id };
  }
  function updateAccount(state, id, changes) {
    const next = clone(state), account = next.accounts.find(a => a.id === id);
    if (!account) throw new Error('Account not found.');
    for (const field of ['notes', 'stage', 'industry', 'location']) if (field in changes) account[field] = clean(changes[field]);
    if ('tags' in changes) account.tags = Array.isArray(changes.tags) ? unique(changes.tags.map(key)).sort() : splitTags(changes.tags);
    return next;
  }
  function filterAccounts(state, filters = {}) {
    const q = key(filters.q), industry = key(filters.industry), tag = key(filters.tag), stage = key(filters.stage);
    return state.accounts.filter(a => (!q || key([a.company, a.domain, ...(a.domainAliases || []), a.industry, a.location, a.notes, ...a.tags, ...a.contacts.flatMap(c => [c.name, c.email, c.title])].join(' ')).includes(q)) && (!industry || key(a.industry) === industry) && (!tag || a.tags.includes(tag)) && (!stage || key(a.stage) === stage) && (!filters.withEmail || a.contacts.some(c => c.email))).sort((a, b) => a.company.localeCompare(b.company) || a.id.localeCompare(b.id));
  }
  function csvCell(value) {
    let v = String(value == null ? '' : value);
    // Spreadsheet-safe export; user text must remain text, not a formula.
    if (/^[\s\uFEFF]*[=+\-@]/.test(v) || /^[\t\r\n]/.test(v)) v = "'" + v;
    return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }
  function exportCSV(accounts) {
    const headers = ['account_id', 'company', 'website', 'industry', 'location', 'stage', 'tags', 'contact_name', 'email', 'job_title', 'sources', 'notes'];
    const rows = [headers];
    for (const a of accounts) for (const c of (a.contacts.length ? a.contacts : [{ name: '', email: '', title: '', sources: [] }])) rows.push([a.id, a.company, a.website, a.industry, a.location, a.stage, a.tags.join('; '), c.name, c.email, c.title, unique([...a.sources, ...c.sources]).join(' | '), a.notes]);
    return '\uFEFF' + rows.map(r => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
  }
  function saveSegment(state, name, filters) {
    name = clean(name); if (!name) throw new Error('Give this segment a name.');
    const next = clone(state);
    const item = { name, filters: { q: clean(filters.q), industry: clean(filters.industry), tag: clean(filters.tag), stage: clean(filters.stage), withEmail: Boolean(filters.withEmail) } };
    const index = next.segments.findIndex(s => key(s.name) === key(name));
    if (index < 0) next.segments.push(item); else next.segments[index] = item;
    return next;
  }
  function validateState(s) {
    const fail = () => { throw new Error('This is not a valid Fieldnote v1 workspace backup.'); };
    const strings = (o, fields) => fields.every(f => typeof o[f] === 'string');
    const stringArray = a => Array.isArray(a) && a.every(x => typeof x === 'string');
    if (!s || s.version !== VERSION || !Number.isSafeInteger(s.nextId) || s.nextId < 1 || !Array.isArray(s.accounts) || !Array.isArray(s.imports) || !Array.isArray(s.segments)) fail();
    const ids = new Set();
    for (const a of s.accounts) {
      if (!a || !strings(a, ['id', 'company', 'website', 'domain', 'industry', 'location', 'stage', 'notes']) || !/^a[1-9]\d*$/.test(a.id) || Number(a.id.slice(1)) >= s.nextId || ids.has(a.id) || !stringArray(a.tags) || !stringArray(a.sources) || !stringArray(a.importFiles) || !Array.isArray(a.contacts) || !Array.isArray(a.conflicts)) fail();
      ids.add(a.id);
      // Legacy v1 backups omit this additive field and remain valid.
      if ('domainAliases' in a && (!stringArray(a.domainAliases) || a.domainAliases.some(d => !d || domain(d) !== d))) fail();
      for (const c of a.contacts) if (!c || !strings(c, ['name', 'email', 'title']) || !stringArray(c.sources)) fail();
      for (const c of a.conflicts) if (!c || !strings(c, ['field', 'kept', 'incoming', 'source'])) fail();
    }
    for (const x of s.imports) {
      if (!x || !strings(x, ['filename', 'at']) || !['rows', 'created', 'merged', 'unchanged'].every(k => Number.isSafeInteger(x[k]) && x[k] >= 0) || !Array.isArray(x.errors) || !Array.isArray(x.warnings)) fail();
      for (const e of [...x.errors, ...x.warnings]) if (!e || !Number.isSafeInteger(e.row) || typeof e.message !== 'string') fail();
    }
    for (const segment of s.segments) if (!segment || typeof segment.name !== 'string' || !segment.filters || !strings(segment.filters, ['q', 'industry', 'tag', 'stage']) || typeof segment.filters.withEmail !== 'boolean') fail();
    return true;
  }
  return { VERSION, FIELDS, empty, clone, safeURL, domain, parseCSV, suggestMapping, previewImport, commitImport, mergeDuplicates, updateAccount, filterAccounts, exportCSV, csvCell, saveSegment, validateState };
});
