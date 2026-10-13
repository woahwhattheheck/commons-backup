'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

const source=fs.readFileSync(path.join(__dirname,'web/work.js'),'utf8');
function definition(prefix){
  const start=source.indexOf(prefix);
  assert.ok(start>=0,'missing '+prefix);
  const end=source.indexOf('\n',start);
  assert.ok(end>start,'unterminated '+prefix);
  return source.slice(start,end).trim();
}
const context=vm.createContext({});
vm.runInContext([
  definition('const first='),
  definition('const date='),
  definition('const activity='),
  'globalThis.activity=activity;globalThis.date=date;'
].join('\n'),context);

test('work activity does not promote metadata update timestamps',()=>{
  const metadataUpdate='2026-09-08T02:00:00Z';
  assert.equal(context.activity({activity_observed_at:null,updated_at:metadataUpdate}),null);
  assert.equal(context.activity({activity_observed_at:'',updated_at:metadataUpdate}),null);
  assert.equal(context.date(context.activity({activity_observed_at:null,updated_at:metadataUpdate})),'Unknown activity time');
});

test('explicit work activity wins even when metadata is newer',()=>{
  const activity='2026-09-01T10:00:00Z';
  const metadataUpdate='2026-09-08T02:00:00Z';
  assert.equal(context.activity({activity_observed_at:activity,updated_at:metadataUpdate}),activity);
});

test('invalid explicit work activity stays unknown instead of falling back to metadata',()=>{
  const metadataUpdate='2026-09-08T02:00:00Z';
  assert.equal(context.date(context.activity({activity_observed_at:'not-a-date',updated_at:metadataUpdate})),'Unknown activity time');
});
