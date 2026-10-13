'use strict';

// Saved-run analysis only. This module does not import or execute model code.
function fail(message) { throw new Error(message); }
function need(ok, message) { if (!ok) fail(message); }
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  need(value !== undefined && !(typeof value === 'number' && !Number.isFinite(value)), 'Non-JSON output value');
  return JSON.stringify(value);
}
function utf8(text) {
  const bytes = [];
  for (let i = 0; i < text.length; i++) {
    let n = text.codePointAt(i);
    if (n > 0xffff) i++;
    need(!(n >= 0xd800 && n <= 0xdfff), 'Unpaired UTF-16 surrogate in input');
    if (n < 0x80) bytes.push(n);
    else if (n < 0x800) bytes.push(0xc0 | n >> 6, 0x80 | n & 63);
    else if (n < 0x10000) bytes.push(0xe0 | n >> 12, 0x80 | n >> 6 & 63, 0x80 | n & 63);
    else bytes.push(0xf0 | n >> 18, 0x80 | n >> 12 & 63, 0x80 | n >> 6 & 63, 0x80 | n & 63);
  }
  return bytes;
}
function sha256(text) {
  const b = utf8(text), size = b.length;
  const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const rotr = (v,n) => v >>> n | v << (32-n);
  b.push(128);
  while (b.length % 64 !== 56) b.push(0);
  const hi = Math.floor(size / 0x20000000), lo = size * 8 >>> 0;
  for (const v of [hi,lo]) for (let n=24;n>=0;n-=8) b.push(v >>> n & 255);
  const w = new Array(64);
  for (let offset=0;offset<b.length;offset+=64) {
    for(let j=0;j<16;j++) {
      const p=offset+j*4;
      w[j]=(b[p]<<24 | b[p+1]<<16 | b[p+2]<<8 | b[p+3]) >>> 0;
    }
    for(let j=16;j<64;j++) {
      const a=w[j-15], z=w[j-2];
      w[j]=(w[j-16]+(rotr(a,7)^rotr(a,18)^a>>>3)+w[j-7]+(rotr(z,17)^rotr(z,19)^z>>>10)) >>> 0;
    }
    let [a,c,d,e,f,g,i,j]=h;
    for(let t=0;t<64;t++) {
      const u=(j+(rotr(f,6)^rotr(f,11)^rotr(f,25))+((f&g)^(~f&i))+k[t]+w[t])>>>0;
      const v=((rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&c)^(a&d)^(c&d)))>>>0;
      j=i;i=g;g=f;f=(e+u)>>>0;e=d;d=c;c=a;a=(u+v)>>>0;
    }
    [a,c,d,e,f,g,i,j].forEach((v,n)=>{h[n]=(h[n]+v)>>>0;});
  }
  return h.map(v=>v.toString(16).padStart(8,'0')).join('');
}
function strictJSON(text, label='JSON') {
  need(typeof text==='string', label+': expected text');
  let p=0;
  const err = message => fail(label+': '+message+' at character '+p);
  const ws=()=>{while(p<text.length && /[\t\r\n ]/.test(text[p]))p++;};
  function str() {
    const start=p++;
    while(p<text.length) {
      const c=text[p++];
      if(c==='"') { try { return JSON.parse(text.slice(start,p)); } catch { err('invalid string'); } }
      if(c==='\\') p++;
    }
    err('unterminated string');
  }
  function val(depth) {
    if(depth>512) err('nesting too deep');
    ws(); const c=text[p];
    if(c==='"') return str();
    if(c==='{') {
      p++;ws();const o=Object.create(null), seen=new Set();
      if(text[p]==='}') {p++;return o;}
      while(true) {
        ws();if(text[p]!=='"')err('expected object key');
        const key=str();if(seen.has(key))err('duplicate object key');seen.add(key);
        ws();if(text[p++]!==':')err('expected colon');
        o[key]=val(depth+1);ws();
        const separator=text[p++];if(separator==='}')return o;if(separator!==',')err('expected comma or closing brace');
      }
    }
    if(c==='[') {
      p++;ws();const a=[];if(text[p]===']'){p++;return a;}
      while(true) {a.push(val(depth+1));ws();const separator=text[p++];if(separator===']')return a;if(separator!==',')err('expected comma or closing bracket');}
    }
    for(const [literal,value] of [['true',true],['false',false],['null',null]])if(text.startsWith(literal,p)){p+=literal.length;return value;}
    const m=text.slice(p).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    if(!m)err('expected JSON value');
    p+=m[0].length;const n=Number(m[0]);if(!Number.isFinite(n))err('non-finite number');return n;
  }
  const result=val(0);ws();if(p!==text.length)err('trailing content');return result;
}
function flags(grade, label) {
  need(grade && typeof grade==='object',label+': missing grade');
  for(const k of ['semantic_pass','contract_pass','parse_pass'])need(typeof grade[k]==='boolean',label+': invalid '+k);
}
function setEqual(a,b) {return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length && new Set(a).size===a.length && canonical([...a].sort())===canonical([...b].sort());}
function sum(rows,key) {return rows.reduce((s,r)=>s+r[key],0);}
function stats(rows) {
  return {questions:rows.length,semantic_pass:rows.filter(r=>r.grade.semantic_pass).length,
    contract_pass:rows.filter(r=>r.grade.contract_pass).length,parse_pass:rows.filter(r=>r.grade.parse_pass).length,
    generation_seconds:sum(rows,'elapsed_seconds')};
}
const DEVELOPMENT_IDS = ['spatial-text_count','code_trace-alias','code_trace-closure','mtg-trample','mtg-first_strike',
  'games-takeaway','code_write-stable_unique','code_write-intervals','arithmetic-midnight','code_write-run_length',
  'logic-truthful','uncertainty-finite_pattern'].sort();
function analyze(inputs, regrade=null, v7Final=null) {
  need(Array.isArray(inputs)&&inputs.length>0,'Supply at least one run');
  const labels=new Set(), work=[];
  for(const input of inputs) {
    const {label,trace,config:configText,summary:summaryText}=input;
    need(typeof label==='string'&&label.length>0&&!labels.has(label),'Missing or duplicate run label');labels.add(label);
    const config=strictJSON(configText,label+' config'), summary=strictJSON(summaryText,label+' summary');
    need(config.label===label,label+': config label mismatch');
    const digest=sha256(trace), bytes=utf8(trace).length;
    need(digest===summary.trace_sha256,label+': trace SHA256 mismatch');
    need(bytes===summary.trace_bytes,label+': trace byte count mismatch');
    const requests=new Map(), results=new Set(), cases=new Map(), worlds=new Map();
    const lines=trace.split('\n');if(lines[lines.length-1]==='')lines.pop();
    let questionSeconds=0, worldSeconds=0;
    lines.forEach((line,index)=>{
      need(line.trim().length>0,label+': blank trace record');
      const r=strictJSON(line,label+' trace line '+(index+1));
      if(r.event==='request') {
        need(typeof r.operation_id==='string'&&!requests.has(r.operation_id),label+': duplicate/missing request operation');
        requests.set(r.operation_id,r);return;
      }
      if(r.event==='episode_start') {
        need(typeof r.id==='string'&&!worlds.has(r.id),label+': duplicate/missing world');
        worlds.set(r.id,{moves:[],start:r,end:null});return;
      }
      if(r.event==='episode_result') {
        const w=worlds.get(r.id);need(w&&!w.end,label+': unmatched/duplicate world result');w.end=r;return;
      }
      need(r.event==='case_result'||r.event==='episode_decision',label+': unknown trace event');
      need(requests.has(r.operation_id)&&!results.has(r.operation_id),label+': unmatched/duplicate response operation');
      results.add(r.operation_id);
      need(typeof r.elapsed_seconds==='number'&&r.elapsed_seconds>=0&&Number.isFinite(r.elapsed_seconds),label+': invalid elapsed time');
      if(r.event==='case_result') {
        need(typeof r.id==='string'&&!cases.has(r.id),label+': duplicate/missing case ID');
        need(r.split===config.split,label+': case split mismatch');flags(r.grade,label);
        need(r.operation_id===r.id,label+': case request identity mismatch');
        cases.set(r.id,r);questionSeconds+=r.elapsed_seconds;
      } else {
        const w=worlds.get(r.id);need(w&&!w.end,label+': world decision outside episode');
        need(r.step===w.moves.length,label+': nonsequential world decision');
        need(r.operation_id===r.id+':'+r.step,label+': world request identity mismatch');
        need(typeof r.accepted==='boolean'&&typeof r.won==='boolean',label+': invalid world flags');
        w.moves.push(r);worldSeconds+=r.elapsed_seconds;
      }
    });
    need(requests.size===results.size,label+': unanswered request');
    const questions=[...cases.values()];
    need(setEqual([...cases.keys()],config.selected_cases),label+': selected question IDs mismatch');
    need(setEqual([...worlds.keys()],config.selected_episodes),label+': selected world IDs mismatch');
    const original=stats(questions);
    for(const [a,b] of [['questions','case_count'],['semantic_pass','semantic_pass'],['contract_pass','contract_pass'],['parse_pass','parse_pass']])
      need(original[a]===summary[b],label+': summary '+b+' mismatch');
    need(Math.abs(questionSeconds+worldSeconds-summary.generation_seconds)<1e-6,label+': summary generation time mismatch');
    const summaryWorlds=new Map();
    for(const e of summary.episodes){need(!summaryWorlds.has(e.id),label+': duplicate summary world');summaryWorlds.set(e.id,e);}
    need(summaryWorlds.size===worlds.size,label+': summary world count mismatch');
    const episodes=[...worlds.entries()].map(([id,w])=>{
      need(w.end,label+': unfinished world');
      const invalid=w.moves.filter(r=>!r.accepted).length;
      need(w.end.decisions===w.moves.length&&w.end.invalid===invalid,label+': world counts mismatch');
      need(canonical(summaryWorlds.get(id))===canonical(Object.fromEntries(Object.entries(w.end).filter(([k])=>!['event','utc'].includes(k)))),label+': world summary mismatch');
      const last=w.moves[w.moves.length-1];
      need(last ? last.won===w.end.won : w.end.won===false,label+': final world state mismatch');
      return {id,decisions:w.moves.length,accepted:w.moves.length-invalid,invalid,won:w.end.won,reason:w.end.reason,
        generation_seconds:sum(w.moves,'elapsed_seconds'),
        actions:w.moves.map(r=>({step:r.step,action:typeof r.proposal?.action==='string'?r.proposal.action:null,accepted:r.accepted,won:r.won}))};
    }).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
    const controls={};
    for(const k of ['split','suite_sha256','episode_spec_sha256','model_sha256','model_bytes','runtime_version','sampler',
      'thinking_tokens','max_output_tokens','context_tokens','order_seed','backend','vision_backend',
      'system_prompt_sha256','interactive_prompt_sha256','support_sha256','support_file_sha256','source_sha256'])
      if(Object.hasOwn(config,k))controls[k]=config[k];
    work.push({label,digest,bytes,config,questions,cases,original,episodes,controls,requests:requests.size,
      world_decisions:sum(episodes,'decisions'),generation_seconds:questionSeconds+worldSeconds,
      v2:null,v2Cases:null,changedIds:[]});
  }
  if(regrade!==null) {
    need(regrade&&Array.isArray(regrade.runs),'Invalid regrade receipt');
    const receiptRuns=new Map();
    for(const r of regrade.runs){need(!receiptRuns.has(r.label),'Duplicate regrade run');receiptRuns.set(r.label,r);}
    for(const run of work) {
      const r=receiptRuns.get(run.label);need(r,run.label+': missing regrade run');
      need(r.trace_sha256===run.digest,run.label+': regrade trace hash mismatch');
      need(r.questions===run.questions.length&&r.original_strict_pass===run.original.semantic_pass,run.label+': regrade original counts mismatch');
      need(Array.isArray(r.changes),run.label+': invalid regrade changes');
      const changes=new Map();
      for(const c of r.changes) {
        need(!changes.has(c.id),run.label+': duplicate regrade case');
        const original=run.cases.get(c.id);need(original,run.label+': unknown regrade case');
        need(original.raw_response===c.raw_response,run.label+': regrade response mismatch');
        need(canonical(original.grade)===canonical(c.original_grade),run.label+': regrade original grade mismatch');
        flags(c.v2_grade,run.label);changes.set(c.id,c.v2_grade);
      }
      run.v2Cases=new Map(run.questions.map(q=>[q.id,{...q,grade:changes.get(q.id)||q.grade}]));
      run.v2=stats([...run.v2Cases.values()]);
      need(run.v2.semantic_pass===r.v2_pass,run.label+': regrade final count mismatch');
      run.changedIds=[...changes.keys()].sort();
    }
  }
  const byLabel=new Map(work.map(r=>[r.label,r]));
  const comparisons=[];
  function compare(name,names,ids,split) {
    const available=names.filter(n=>byLabel.has(n));
    if(available.length!==names.length){comparisons.push({name,status:'incomplete',missing:names.filter(n=>!byLabel.has(n))});return;}
    const runs=names.map(n=>byLabel.get(n));
    if(ids===null)ids=[...runs[0].cases.keys()].sort();
    for(const r of runs) {
      need(r.config.split===split,name+': split mismatch');
      need(ids.every(id=>r.cases.has(id)),name+': comparison question ID missing');
      if(r.label!=='aptitude-v1-baseline')need(setEqual([...r.cases.keys()],ids),name+': comparison question ID mismatch');
      for(const k of ['model_sha256','suite_sha256','order_seed','max_output_tokens','context_tokens'])
        need(canonical(r.config[k])===canonical(runs[0].config[k]),name+': differing '+k);
      need(canonical(r.config.sampler)===canonical(runs[0].config.sampler),name+': differing sampler');
    }
    comparisons.push({name,status:'complete',question_ids:ids,conditions:runs.map(r=>({
      label:r.label,original:stats(ids.map(id=>r.cases.get(id))),
      v2:r.v2Cases?stats(ids.map(id=>r.v2Cases.get(id))):null
    }))});
  }
  compare('selected_development',['aptitude-v1-baseline','aptitude-v1-development-thinking256','aptitude-v1-development-check-first'],DEVELOPMENT_IDS,'development');
  compare('reserved',['aptitude-v1-holdout-thinking0','aptitude-v1-holdout-thinking256','aptitude-v1-holdout-check-first'],null,'holdout');
  const v7={raw_trace_included:false,raw_trace_status:'not supplied',final_response:null};
  if(v7Final!==null) {
    need(v7Final.source_type==='cloud_final_response','V7 source must identify the original cloud final response');
    const fields=['source_type','task_id','message_id','source_url','decisions','actions','inspections','decision_errors','levels_completed',
      'elapsed_seconds','wall_seconds','archive_bytes','archive_sha256','trace_bytes','trace_sha256','cloud_tests_passed'];
    v7.final_response=Object.fromEntries(fields.filter(k=>Object.hasOwn(v7Final,k)).map(k=>[k,v7Final[k]]));
  }
  return {schema_version:1,
    totals:{runs:work.length,model_calls:sum(work,'requests'),question_attempts:work.reduce((n,r)=>n+r.questions.length,0),
      world_decisions:sum(work,'world_decisions'),generation_seconds:sum(work,'generation_seconds')},
    runs:work.sort((a,b)=>a.label<b.label?-1:a.label>b.label?1:0).map(r=>({label:r.label,trace_sha256:r.digest,trace_bytes:r.bytes,
      controls:r.controls,original:r.original,v2:r.v2,changed_case_ids:r.changedIds,episodes:r.episodes,
      model_calls:r.requests,generation_seconds:r.generation_seconds})),
    comparisons,v7,project_default_profile:'direct',new_model_calls:0};
}
function markdown(report) {
  const esc=v=>String(v).replace(/\|/g,'\\|').replace(/[\r\n]/g,' ');
  const lines=['# Titan ARC saved-run analysis','',
    report.totals.model_calls+' saved model calls: '+report.totals.question_attempts+' question attempts and '+report.totals.world_decisions+' world decisions.','',
    '| Run | Original semantic | V2 semantic | Contract | Parsed | Worlds won | Generation seconds |',
    '|---|---:|---:|---:|---:|---:|---:|'];
  for(const r of report.runs)lines.push('| '+esc(r.label)+' | '+r.original.semantic_pass+'/'+r.original.questions+' | '+
    (r.v2?r.v2.semantic_pass+'/'+r.v2.questions:'not supplied')+' | '+r.original.contract_pass+'/'+r.original.questions+' | '+
    r.original.parse_pass+'/'+r.original.questions+' | '+r.episodes.filter(e=>e.won).length+'/'+r.episodes.length+' | '+r.generation_seconds.toFixed(3)+' |');
  for(const c of report.comparisons) {
    lines.push('','## '+esc(c.name),'');
    if(c.status!=='complete'){lines.push('Missing runs: '+c.missing.map(esc).join(', '));continue;}
    lines.push('Matched questions: '+c.question_ids.map(esc).join(', '),'');
    for(const r of c.conditions)lines.push('- '+esc(r.label)+': '+r.original.semantic_pass+'/'+r.original.questions+' original; '+
      (r.v2?r.v2.semantic_pass+'/'+r.v2.questions+' v2':'v2 not supplied')+'; '+r.original.generation_seconds.toFixed(3)+' question-generation seconds.');
  }
  lines.push('','## ARC v7','',
    report.v7.final_response?'Original cloud final response is included separately; raw trace is not supplied.':'Raw trace and final response are not supplied.',
    'Direct remains the default profile. The saved aptitude conditions and world outcomes are reported separately.','');
  return lines.join('\n');
}
function cli(args) {
  const fs=require('node:fs'), path=require('node:path');
  const inputs=[];let regrade=null,v7=null,format='json',output=null;
  for(let i=0;i<args.length;i++) {
    const key=args[i];
    if(key==='--help'){console.log('node analyze_runs.cjs --run LABEL=DIRECTORY [--run ...] [--regrade FILE] [--v7-final FILE] [--format json|markdown] [--output NEW_FILE]');return;}
    need(['--run','--regrade','--v7-final','--format','--output'].includes(key),'Unknown option: '+key);
    const value=args[++i];need(value!==undefined,'Missing value for '+key);
    if(key==='--run') {
      const at=value.indexOf('=');need(at>0,'--run requires LABEL=DIRECTORY');
      const label=value.slice(0,at), dir=value.slice(at+1);
      inputs.push({label,trace:fs.readFileSync(path.join(dir,'trace.jsonl'),'utf8'),
        config:fs.readFileSync(path.join(dir,'config.json'),'utf8'),summary:fs.readFileSync(path.join(dir,'summary.json'),'utf8')});
    } else if(key==='--regrade')regrade=strictJSON(fs.readFileSync(value,'utf8'),'regrade');
    else if(key==='--v7-final')v7=strictJSON(fs.readFileSync(value,'utf8'),'v7 final');
    else if(key==='--format')format=value;
    else output=value;
  }
  need(format==='json'||format==='markdown','Format must be json or markdown');
  const result=analyze(inputs,regrade,v7), text=format==='json'?canonical(result)+'\n':markdown(result);
  if(output)fs.writeFileSync(output,text,{encoding:'utf8',flag:'wx'});else process.stdout.write(text);
}
if(typeof module!=='undefined') {
  module.exports={analyze,canonical,markdown,strictJSON,sha256,utf8};
  if(typeof require!=='undefined'&&require.main===module) {
    try{cli(process.argv.slice(2));}catch(error){console.error('ARC analysis failed: '+error.message);process.exitCode=2;}
  }
}
