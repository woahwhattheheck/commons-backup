'use strict';
// Narrow consumer regressions; FIELDNOTE_MODEL optionally selects the original
// model for a discriminating before/after run. No network or browser mocks.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const F = require(process.env.FIELDNOTE_MODEL ? path.resolve(process.env.FIELDNOTE_MODEL) : './model.js');
const head = 'Company,Website,Industry,Location,Name,Email,Title,Source,Tags,Notes\n';
const alpha = 'Alpha Group,alpha.example,Software,North,Ada Example,ada@alpha.example,Lead,https://alpha.example/about,parent,Parent note\n';
const beta = 'Beta Studio,beta.example,Design,South,Ben Example,ben@beta.example,Founder,https://beta.example/about,subsidiary,Subsidiary note\n';
const gamma = 'Gamma Team,gamma.example,Services,West,Cam Example,cam@gamma.example,Owner,https://gamma.example/about,partner,Partner note\n';
const clock = '2026-09-08T10:00:00.000Z';
function load(csv = alpha + beta) { return F.commitImport(F.previewImport(F.empty(), head + csv, {filename:'fixture.csv'}), clock); }
function merged(csv = alpha + beta) { const s=load(csv); return F.mergeDuplicates(s,s.accounts.map(a=>a.id)).state; }
function again(s,csv=beta) { return F.previewImport(s,head+csv,{filename:'fixture.csv'}); }

test('merged-away domain reimport returns the retained account, not a new company',()=>{
 const s=merged(),result=again(s);
 assert.equal(result.report.created,0);
 assert.equal(result.state.accounts.length,1);
 assert.equal(result.state.accounts[0].id,s.accounts[0].id);
 assert.deepEqual(new Set(result.state.accounts[0].domainAliases),new Set(['alpha.example','beta.example']));
});
test('both original files can be reimported repeatedly without splitting the merge',()=>{
 let s=merged();for(let i=0;i<3;i++) {const result=again(s,alpha+beta);assert.equal(result.report.created,0);s=F.commitImport(result,clock);}
 assert.equal(s.accounts.length,1);assert.equal(s.accounts[0].contacts.length,2);
});
test('manual notes remain on the retained record after reimport through an alias',()=>{
 let s=merged();s=F.updateAccount(s,s.accounts[0].id,{notes:'Updated agenda',tags:'owner-edited'});
 const r=again(s);assert.equal(r.state.accounts.length,1);
 assert.match(r.state.accounts[0].notes,/Updated agenda/);
 assert.ok(r.state.accounts[0].tags.includes('owner-edited'));
});
test('multi-step merges retain transitive domain identities',()=>{
 let s=load(alpha+beta+gamma);s=F.mergeDuplicates(s,['a1','a2']).state;s=F.mergeDuplicates(s,['a3','a1']).state;
 assert.equal(s.accounts[0].domain,'gamma.example');
 assert.deepEqual(new Set(s.accounts[0].domainAliases),new Set(['alpha.example','beta.example','gamma.example']));
 assert.equal(again(s,alpha+beta+gamma).report.created,0);
});
test('reverse merge selection preserves the selected primary and the old primary alias',()=>{
 const s=F.mergeDuplicates(load(),['a2','a1']).state;
 assert.equal(s.accounts[0].domain,'beta.example');assert.equal(again(s,alpha).state.accounts.length,1);
});
test('merge retains existing sources, contacts, notes, tags and primary website',()=>{
 const s=merged(),a=s.accounts[0];
 assert.equal(a.website,'https://alpha.example/');assert.equal(a.contacts.length,2);
 assert.deepEqual(new Set(a.sources),new Set(['https://alpha.example/about','https://beta.example/about']));
 assert.match(a.notes,/Parent note/);assert.match(a.notes,/Subsidiary note/);assert.ok(a.tags.includes('subsidiary'));
 F.validateState(s);
});
test('JSON backup roundtrip preserves aliases for the existing opaque backup boundary',()=>{
 const s=merged(),payload=JSON.stringify(s),restored=JSON.parse(payload);
 F.validateState(restored);assert.equal(JSON.stringify(restored),payload);
 assert.equal(again(restored).report.created,0);
});
test('legacy v1 backup without aliases remains valid and a same-domain import is unchanged',()=>{
 const s=load(alpha);delete s.accounts[0].domainAliases;
 F.validateState(s);const r=again(s,alpha);assert.equal(r.report.unchanged,1);
 assert.equal(r.state.accounts[0].domainAliases,undefined);
});
test('company search finds an explicitly merged secondary domain',()=>{
 const s=merged();assert.equal(F.filterAccounts(s,{q:'beta.example'}).length,1);
 // No incidental email or source can make this assertion pass.
 s.accounts[0].contacts=[];s.accounts[0].sources=[];s.accounts[0].notes='';
 assert.equal(F.filterAccounts(s,{q:'beta.example'}).length,1);
});
test('overlapping aliases require an explicit choice rather than a first-record merge',()=>{
 const s=load();s.accounts[0].domainAliases=['alpha.example','shared.example'];s.accounts[1].domainAliases=['beta.example','shared.example'];
 const before=JSON.stringify(s.accounts),r=again(s,beta.replaceAll('beta.example','shared.example'));
 assert.equal(r.report.errors.length,1);assert.match(r.report.errors[0].message,/multiple accounts/);
 assert.equal(r.report.created,0);assert.equal(JSON.stringify(r.state.accounts),before);
});
test('malformed alias collections are rejected while ordinary v1 data remains accepted',()=>{
 for(const value of [null,'beta.example',[23],[''],['https://beta.example/path']]) {
  const s=load(alpha);s.accounts[0].domainAliases=value;assert.throws(()=>F.validateState(s));
 }
});
test('normalization handles reimports of www URLs with paths after a manual merge',()=>{
 const s=merged(),r=again(s,beta.replace(',beta.example,',',https://WWW.BETA.EXAMPLE/contact,'));
 assert.equal(r.report.created,0);assert.equal(r.state.accounts.length,1);
});
test('merge and alias import do not mutate their input states',()=>{
 const s=load(),original=JSON.stringify(s),m=F.mergeDuplicates(s,['a1','a2']).state;
 assert.equal(JSON.stringify(s),original);const before=JSON.stringify(m);again(m);assert.equal(JSON.stringify(m),before);
});
test('CRM export preserves the existing 12-column contract and contact cardinality',()=>{
 const a=merged().accounts,parsed=F.parseCSV(F.exportCSV(a));
 assert.equal(parsed.headers.length,12);assert.equal(parsed.rows.length,2);
 assert.equal(parsed.rows[0][0],parsed.rows[1][0]);
});
test('name-only records do not gain invented domain aliases',()=>{
 const text='Company,Location,Name\nName Only,Town,One\nName Only,Town,Two\n';
 const s=F.commitImport(F.previewImport(F.empty(),text),clock);
 assert.equal(s.accounts.length,1);assert.equal(s.accounts[0].domain,'');assert.equal(s.accounts[0].domainAliases,undefined);
});
