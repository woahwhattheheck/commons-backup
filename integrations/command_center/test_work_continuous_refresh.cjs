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

function cadenceContext(){
  const context=vm.createContext({now:1_000_000,calls:[]});
  context.Date={now:()=>context.now};
  context.refresh=force=>{context.calls.push(force);return force;};
  vm.runInContext([
    definition('const AUTO_REFRESH_MS='),
    definition('let lastCollectorRefresh='),
    definition('function autoRefresh'),
    'globalThis.autoRefresh=autoRefresh;'
  ].join('\n'),context);
  return context;
}

test('visible dashboard forces provider collection on a bounded five-minute cadence',()=>{
  const context=cadenceContext();
  context.autoRefresh();
  assert.deepEqual(context.calls,[true]);
  context.now+=30_000;
  context.autoRefresh();
  assert.deepEqual(context.calls,[true,false]);
  context.now+=269_999;
  context.autoRefresh();
  assert.deepEqual(context.calls,[true,false,false]);
  context.now+=1;
  context.autoRefresh();
  assert.deepEqual(context.calls,[true,false,false,true]);
  context.now=100;
  context.autoRefresh();
  assert.deepEqual(context.calls,[true,false,false,true,true]);
});

test('dashboard hooks use bounded auto refresh only while visible',()=>{
  assert.match(source,/setInterval\(\(\)=>\{if\(!document\.hidden\)autoRefresh\(\);\},30000\);/);
  assert.match(source,/visibilitychange',\(\)=>\{if\(!document\.hidden\)autoRefresh\(\);\}/);
  assert.match(source,/renderAll\(\);if\(document\.hidden\)refresh\(\);else autoRefresh\(\);/);
});
