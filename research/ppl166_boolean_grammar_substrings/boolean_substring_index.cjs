"use strict";

/*
 * Nonempty binary Boolean grammars on the substrings of one supplied word.
 * Every binary production includes an explicit negative epsilon guard.
 * Source conventions: A. Okhotin, arXiv:2012.03538 (2020), Definitions 3-5.
 * Positive parse counts do not define Boolean-grammar unambiguity.
 * No I/O, dependencies, general grammar normalization, or global ambiguity test.
 */

const BOOLEAN_SUBSTRING_LIMITS = Object.freeze({
  alphabet:16, nonterminals:24, rules:96, conjuncts_per_rule:8, shared_pairs:64,
  word_symbols:256, split_candidate_checks:20000000, decimal_digits:512,
  page_size:128, parse_nodes:4096, source_id_characters:2048
});
const SCHEMA="commons.boolean_substring_index/v1";
function fail(message){throw new RangeError(message);}
function obj(x,name){if(!x||typeof x!=="object"||Array.isArray(x))fail(name+" must be an object");return x;}
function arr(x,name,max,exact){
  if(!Array.isArray(x)||(max!==undefined&&x.length>max)||(exact!==undefined&&x.length!==exact))fail(name+" has invalid length");
  return x;
}
function integer(x,name,min,max){
  if(!Number.isSafeInteger(x)||x<min||x>max)fail(name+" is outside its integer bounds");return x;
}
function sourceId(x){
  if(typeof x!=="string"||!x.length||x.length>BOOLEAN_SUBSTRING_LIMITS.source_id_characters)fail("source_id is invalid");return x;
}
function unsigned(x,name,min=0n){
  let s;
  if(typeof x==="bigint")s=String(x);
  else if(typeof x==="number"&&Number.isSafeInteger(x))s=String(x);
  else if(typeof x==="string")s=x;
  else fail(name+" must be an exact integer");
  if(s.length>BOOLEAN_SUBSTRING_LIMITS.decimal_digits||!/^(0|[1-9][0-9]*)$/.test(s))fail(name+" violates the decimal contract");
  const v=BigInt(s);if(v<min)fail(name+" is below its minimum");return v;
}
function decimal(x,name,min=0n){if(typeof x!=="string")fail(name+" must be a decimal string");return unsigned(x,name,min);}
function bounded(x){if(x.toString().length>BOOLEAN_SUBSTRING_LIMITS.decimal_digits)fail("positive parse count exceeds the digit cap");return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function workCounters(){
  return {
    constructors:0,saved_opens:0,grammar_rules_read:0,word_symbols_read:0,
    chart_cells_evaluated:0,split_candidate_checks:0,successful_pair_splits:0,
    positive_count_products:0,positive_count_additions:0,rule_evaluations:0,
    rule_count_products:0,nonterminal_count_additions:0,
    pair_records_written:0,rule_records_written:0,nonterminal_records_written:0,
    saved_cells_loaded:0,saved_pair_records_loaded:0,saved_rule_records_loaded:0,
    saved_nonterminal_records_loaded:0,saved_mask_bits_checked:0,
    saved_rule_guard_checks:0,saved_count_sum_additions:0,
    saved_summary_additions:0,saved_occurrence_entries_checked:0,
    cell_queries:0,parse_count_queries:0,count_occurrence_queries:0,
    rank_occurrence_queries:0,select_occurrence_queries:0,page_occurrence_queries:0,
    rule_evidence_queries:0,split_page_queries:0,parse_queries:0,diagnostic_queries:0,
    occurrence_binary_steps:0,occurrences_returned:0,split_rows_returned:0,
    query_weight_products:0,parse_rule_rows_visited:0,parse_split_rows_visited:0,
    parse_nodes_returned:0,diagnostic_rows_returned:0
  };
}
function normalizeGrammar(input,work){
  obj(input,"grammar");
  if(input.nonempty_binary_guard!==true)fail("grammar must explicitly set nonempty_binary_guard:true");
  const sid=sourceId(input.source_id),alphabet=arr(input.alphabet,"alphabet",BOOLEAN_SUBSTRING_LIMITS.alphabet).slice();
  if(!alphabet.length)fail("alphabet must be nonempty");
  const alphabetSet=new Set();
  for(const symbol of alphabet){
    if(typeof symbol!=="string"||Array.from(symbol).length!==1)fail("each terminal is one Unicode scalar");
    const cp=symbol.codePointAt(0);
    if(cp>=0xd800&&cp<=0xdfff)fail("unpaired surrogate terminal");
    if(alphabetSet.has(symbol))fail("duplicate alphabet symbol");alphabetSet.add(symbol);
  }
  const names=arr(input.nonterminals,"nonterminals",BOOLEAN_SUBSTRING_LIMITS.nonterminals).slice();
  if(!names.length)fail("at least one nonterminal is required");
  const ids=new Map();
  names.forEach((name,i)=>{
    if(typeof name!=="string"||!/^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(name)||ids.has(name))fail("nonterminal names must be distinct canonical identifiers");
    ids.set(name,i);
  });
  if(!ids.has(input.start))fail("start is not a declared nonterminal");
  const pairIds=new Map(),pairs=[],compiled=[],canonical=[],duplicates=new Set();
  const rules=arr(input.rules,"rules",BOOLEAN_SUBSTRING_LIMITS.rules);
  function pairList(value,name){
    return arr(value,name,BOOLEAN_SUBSTRING_LIMITS.conjuncts_per_rule).map(pair=>{
      arr(pair,name+" pair",undefined,2);
      if(!ids.has(pair[0])||!ids.has(pair[1]))fail("conjunct references an undeclared nonterminal");
      const a=ids.get(pair[0]),b=ids.get(pair[1]),key=a+","+b;
      let p=pairIds.get(key);
      if(p===undefined){p=pairs.length;pairIds.set(key,p);pairs.push([a,b]);}
      return p;
    });
  }
  for(const r of rules){
    obj(r,"rule");if(!ids.has(r.head))fail("rule head is undeclared");
    const head=ids.get(r.head);let c,key,out;
    if(Object.prototype.hasOwnProperty.call(r,"terminal")){
      if(!alphabetSet.has(r.terminal)||r.positive!==undefined||r.negative!==undefined)fail("terminal rule has invalid conjunct fields");
      c={head,terminal:r.terminal,positive:[],negative:[]};out={head:r.head,terminal:r.terminal};
      key="t:"+head+":"+r.terminal;
    }else{
      const positive=pairList(r.positive,"positive"),negative=pairList(r.negative===undefined?[]:r.negative,"negative");
      if(!positive.length||positive.length+negative.length>BOOLEAN_SUBSTRING_LIMITS.conjuncts_per_rule)fail("binary rule needs bounded positive and negative conjuncts");
      if(new Set(positive).size!==positive.length||new Set(negative).size!==negative.length)fail("duplicate conjuncts are not independent parse choices");
      c={head,terminal:null,positive,negative};
      const named=list=>list.map(p=>pairs[p].map(i=>names[i]));
      out={head:r.head,positive:named(positive),negative:named(negative)};
      key="b:"+head+":"+positive.slice().sort((a,b)=>a-b).join(",")+":"+negative.slice().sort((a,b)=>a-b).join(",");
    }
    if(duplicates.has(key))fail("duplicate productions are not distinct grammar rules");
    duplicates.add(key);compiled.push(c);canonical.push(out);work.grammar_rules_read++;
  }
  if(pairs.length>BOOLEAN_SUBSTRING_LIMITS.shared_pairs)fail("too many shared binary pairs");
  const usage=pairs.map(()=>({positive_rules:[],negative_rules:[]}));
  compiled.forEach((r,i)=>{r.positive.forEach(p=>usage[p].positive_rules.push(i));r.negative.forEach(p=>usage[p].negative_rules.push(i));});
  return {canonical:{source_id:sid,alphabet,nonterminals:names,start:input.start,nonempty_binary_guard:true,rules:canonical},
    names,ids,alphabetSet,pairs,compiled,usage,start:ids.get(input.start)};
}
function dimensions(word,g,work){
  if(typeof word!=="string")fail("word must be a string");
  if(word.length>2*BOOLEAN_SUBSTRING_LIMITS.word_symbols)fail("word exceeds the scalar-storage cap");
  const symbols=Array.from(word);
  if(symbols.length>BOOLEAN_SUBSTRING_LIMITS.word_symbols)fail("word exceeds the symbol cap");
  for(const c of symbols)if(!g.alphabetSet.has(c))fail("word contains an undeclared terminal");
  work.word_symbols_read=symbols.length;
  const n=symbols.length,cells=n*(n+1)/2,checks=g.pairs.length*n*(n-1)*(n+1)/6;
  if(checks>BOOLEAN_SUBSTRING_LIMITS.split_candidate_checks)fail("complete split domain exceeds the constructor budget");
  const base=new Array(n+1).fill(0),starts=new Array(cells),ends=new Array(cells);
  for(let length=1;length<=n;length++){
    base[length]=(length-1)*(2*n-length+2)/2;
    for(let start=0;start+length<=n;start++){const id=base[length]+start;starts[id]=start;ends[id]=start+length;}
  }
  return {word,symbols,n,cells,checks,base,starts,ends};
}
function emptyTables(g,d){
  const vector=()=>new Array(d.cells).fill(0n);
  return {membership:new Array(d.cells).fill(0),
    pairMasks:g.pairs.map(vector),pairCounts:g.pairs.map(vector),
    ruleCounts:g.compiled.map(vector),counts:g.names.map(vector)};
}
function popcount(mask,work,saved=false){
  let count=0;while(mask){mask&=mask-1n;count++;if(saved)work.saved_mask_bits_checked++;}return count;
}
function validRule(rule,length,symbol,pairMasks,cell){
  if(rule.terminal!==null)return length===1&&rule.terminal===symbol;
  if(length<2)return false;
  return rule.positive.every(p=>pairMasks[p][cell]!==0n)&&rule.negative.every(p=>pairMasks[p][cell]===0n);
}
function metadata(g,d,t,work,saved=false){
  const occurrences=g.names.map(()=>[]),parseTotals=g.names.map(()=>0n),ruleOverlaps=[],multipleSplits=[];
  for(let cell=0;cell<d.cells;cell++){
    for(let nt=0;nt<g.names.length;nt++)if(t.counts[nt][cell]>0n){
      occurrences[nt].push(cell);parseTotals[nt]=bounded(parseTotals[nt]+t.counts[nt][cell]);
      if(saved)work.saved_summary_additions++;
      const rules=[];g.compiled.forEach((r,ri)=>{if(r.head===nt&&t.ruleCounts[ri][cell]>0n)rules.push(ri);});
      if(rules.length>1)ruleOverlaps.push([cell,nt,rules]);
    }
    for(let p=0;p<g.pairs.length;p++){
      const splits=popcount(t.pairMasks[p][cell],work);
      if(splits>1)multipleSplits.push([cell,p,splits]);
    }
  }
  const rootCell=d.n?d.base[d.n]:null;
  const summary={
    source_id:null,grammar_source_id:g.canonical.source_id,word_length:d.n,
    nonterminal_count:g.names.length,rule_count:g.compiled.length,shared_pair_count:g.pairs.length,
    chart_cells:d.cells,pair_mask_domain:d.cells*g.pairs.length,complete_split_candidate_domain:d.checks,
    start:g.names[g.start],full_word_accepted:rootCell===null?false:t.counts[g.start][rootCell]>0n,
    full_word_positive_parse_count:rootCell===null?"0":String(t.counts[g.start][rootCell]),
    nonterminal_occurrence_counts:occurrences.map(x=>String(x.length)),
    nonterminal_positive_parse_totals:parseTotals.map(String),
    rule_overlap_occurrences:ruleOverlaps.length,multiple_split_occurrences:multipleSplits.length,
    finite_boolean_unambiguity_on_substrings:ruleOverlaps.length===0&&multipleSplits.length===0,
    occurrence_order:"Increasing substring length, then increasing zero-based start; positions are distinct occurrences.",
    scope:"Only nonempty substring occurrences of this supplied word. Positive parse uniqueness is not Boolean or inherent unambiguity."
  };
  return {occurrences,ruleOverlaps,multipleSplits,summary};
}
function records(g,d,t,work){
  const pairRows=[],ruleRows=[],ntRows=[];
  for(let cell=0;cell<d.cells;cell++){
    for(let p=0;p<g.pairs.length;p++)if(t.pairMasks[p][cell]!==0n){
      pairRows.push([cell,p,t.pairMasks[p][cell].toString(16),String(t.pairCounts[p][cell]),popcount(t.pairMasks[p][cell],work)]);
      work.pair_records_written++;
    }
    for(let r=0;r<g.compiled.length;r++)if(t.ruleCounts[r][cell]>0n){ruleRows.push([cell,r,String(t.ruleCounts[r][cell])]);work.rule_records_written++;}
    for(let nt=0;nt<g.names.length;nt++)if(t.counts[nt][cell]>0n){ntRows.push([cell,nt,String(t.counts[nt][cell])]);work.nonterminal_records_written++;}
  }
  return {pair_rows:pairRows,rule_rows:ruleRows,nonterminal_rows:ntRows};
}
function snapshotData(sid,g,d,t,rows,meta){
  const summary={...meta.summary,source_id:sid};
  return {schema:SCHEMA,source_id:sid,grammar:g.canonical,word:d.word,word_length:d.n,chart_cells:d.cells,
    pairs:g.pairs.map(p=>p.map(nt=>g.names[nt])),pair_usage:g.usage,
    zero_default:"Absent pair/rule/nonterminal rows mean exact zero. Every nonempty substring cell is in the declared domain.",
    cell_order:"Increasing length, then increasing start; cell_id=(length-1)*(2*n-length+2)/2+start.",
    membership_masks:t.membership.slice(),...rows,occurrence_cells:meta.occurrences.map(x=>x.slice()),
    diagnostics:{rule_overlaps:meta.ruleOverlaps,multiple_splits:meta.multipleSplits},summary};
}
function compileBooleanSubstringIndex(options){
  obj(options,"options");const work=workCounters();work.constructors=1;
  const sid=sourceId(options.source_id),g=normalizeGrammar(options.grammar,work),d=dimensions(options.word,g,work),t=emptyTables(g,d);
  const bits=Array.from({length:d.n+1},(_,i)=>1n<<BigInt(i));
  for(let length=1;length<=d.n;length++)for(let start=0;start+length<=d.n;start++){
    const cell=d.base[length]+start;work.chart_cells_evaluated++;
    if(length>1)for(let p=0;p<g.pairs.length;p++){
      const [a,b]=g.pairs[p],abit=1<<a,bbit=1<<b;let mask=0n,count=0n;
      for(let offset=1;offset<length;offset++){
        work.split_candidate_checks++;
        const l=d.base[offset]+start,r=d.base[length-offset]+start+offset;
        if((t.membership[l]&abit)!==0&&(t.membership[r]&bbit)!==0){
          mask|=bits[offset];work.successful_pair_splits++;
          const weight=bounded(t.counts[a][l]*t.counts[b][r]);work.positive_count_products++;
          count=bounded(count+weight);work.positive_count_additions++;
        }
      }
      t.pairMasks[p][cell]=mask;t.pairCounts[p][cell]=count;
    }
    for(let ri=0;ri<g.compiled.length;ri++){
      const rule=g.compiled[ri];work.rule_evaluations++;
      if(!validRule(rule,length,d.symbols[start],t.pairMasks,cell))continue;
      let count=1n;
      for(const p of rule.positive){count=bounded(count*t.pairCounts[p][cell]);work.rule_count_products++;}
      t.ruleCounts[ri][cell]=count;t.counts[rule.head][cell]=bounded(t.counts[rule.head][cell]+count);work.nonterminal_count_additions++;
      t.membership[cell]|=1<<rule.head;
    }
  }
  if(work.split_candidate_checks!==d.checks)fail("complete split-domain accounting failed");
  const rows=records(g,d,t,work),meta=metadata(g,d,t,work),data=snapshotData(sid,g,d,t,rows,meta);
  return instantiate(data,g,d,t,meta,work);
}
function openRetainedBooleanSubstringIndex(snapshot){
  obj(snapshot,"snapshot");if(snapshot.schema!==SCHEMA)fail("unsupported saved schema");
  const work=workCounters();work.saved_opens=1;
  const sid=sourceId(snapshot.source_id),g=normalizeGrammar(snapshot.grammar,work),d=dimensions(snapshot.word,g,work),t=emptyTables(g,d);
  if(snapshot.word_length!==d.n||snapshot.chart_cells!==d.cells)fail("saved word dimensions disagree");
  if(JSON.stringify(snapshot.pairs)!==JSON.stringify(g.pairs.map(p=>p.map(nt=>g.names[nt])))||
     JSON.stringify(snapshot.pair_usage)!==JSON.stringify(g.usage))fail("saved shared-pair catalog disagrees with grammar");
  const masks=arr(snapshot.membership_masks,"membership masks",undefined,d.cells),maxMask=2**g.names.length-1;
  masks.forEach((m,i)=>{t.membership[i]=integer(m,"membership mask",0,maxMask);work.saved_cells_loaded++;});
  const pairRows=arr(snapshot.pair_rows,"pair rows",d.cells*g.pairs.length),ruleRows=arr(snapshot.rule_rows,"rule rows",d.cells*g.compiled.length);
  const ntRows=arr(snapshot.nonterminal_rows,"nonterminal rows",d.cells*g.names.length);
  let last=-1;
  for(const row of pairRows){
    arr(row,"pair row",undefined,5);
    const cell=integer(row[0],"pair cell",0,d.cells-1),p=integer(row[1],"pair id",0,g.pairs.length-1),key=cell*g.pairs.length+p;
    if(key<=last)fail("pair rows must be in strict cell/pair order");last=key;
    const length=d.ends[cell]-d.starts[cell],hex=row[2];
    if(typeof hex!=="string"||hex.length>64||!/^[1-9a-f][0-9a-f]*$/.test(hex))fail("pair split mask is not canonical nonzero hex");
    const mask=BigInt("0x"+hex);
    if((mask&1n)!==0n||(mask>>BigInt(length))!==0n)fail("pair split mask includes an empty or out-of-span partition");
    const weight=decimal(row[3],"pair positive parse count",1n),count=popcount(mask,work,true);
    if(row[4]!==count||weight<BigInt(count))fail("pair count disagrees with split support");
    t.pairMasks[p][cell]=mask;t.pairCounts[p][cell]=weight;work.saved_pair_records_loaded++;
  }
  function readCounts(rows,target,width,label){
    let previous=-1;
    for(const row of rows){
      arr(row,label+" row",undefined,3);
      const cell=integer(row[0],label+" cell",0,d.cells-1),id=integer(row[1],label+" id",0,width-1),key=cell*width+id;
      if(key<=previous)fail(label+" rows must be strictly ordered");previous=key;
      target[id][cell]=decimal(row[2],label+" count",1n);
      if(label==="rule")work.saved_rule_records_loaded++;else work.saved_nonterminal_records_loaded++;
    }
  }
  readCounts(ruleRows,t.ruleCounts,g.compiled.length,"rule");readCounts(ntRows,t.counts,g.names.length,"nonterminal");
  for(let cell=0;cell<d.cells;cell++){
    const sums=g.names.map(()=>0n),length=d.ends[cell]-d.starts[cell],symbol=d.symbols[d.starts[cell]];let mask=0;
    for(let ri=0;ri<g.compiled.length;ri++){
      const rule=g.compiled[ri],count=t.ruleCounts[ri][cell],valid=validRule(rule,length,symbol,t.pairMasks,cell);
      work.saved_rule_guard_checks++;
      if(valid!==(count>0n)||(valid&&rule.terminal!==null&&count!==1n))fail("saved rule truth disagrees with retained split masks or terminal");
      if(count>0n){sums[rule.head]=bounded(sums[rule.head]+count);work.saved_count_sum_additions++;}
    }
    for(let nt=0;nt<g.names.length;nt++){
      if(sums[nt]!==t.counts[nt][cell])fail("saved nonterminal count is not the sum of its rule counts");
      if(sums[nt]>0n)mask|=1<<nt;
    }
    if(mask!==t.membership[cell])fail("saved membership mask disagrees with nonterminal counts");
  }
  const meta=metadata(g,d,t,work,true);
  const occurrenceInput=arr(snapshot.occurrence_cells,"occurrence cells",undefined,g.names.length);
  for(let nt=0;nt<g.names.length;nt++){
    const values=arr(occurrenceInput[nt],"occurrence list",undefined,meta.occurrences[nt].length);
    for(let i=0;i<values.length;i++){if(values[i]!==meta.occurrences[nt][i])fail("saved occurrence index disagrees with chart");work.saved_occurrence_entries_checked++;}
  }
  if(JSON.stringify(snapshot.diagnostics)!==JSON.stringify({rule_overlaps:meta.ruleOverlaps,multiple_splits:meta.multipleSplits}))
    fail("saved finite ambiguity diagnostics disagree with rule/split support");
  const expectedSummary={...meta.summary,source_id:sid};
  if(JSON.stringify(snapshot.summary)!==JSON.stringify(expectedSummary))fail("saved summary disagrees with retained chart");
  // Child-membership convolution and pair/rule multiplicative parse counts are
  // retained premises. Loading checks structure, guards and additive totals,
  // not the complete split search or provenance of the supplied source.
  const data=snapshotData(sid,g,d,t,{pair_rows:copy(pairRows),rule_rows:copy(ruleRows),nonterminal_rows:copy(ntRows)},meta);
  return instantiate(data,g,d,t,meta,work);
}
function instantiate(data,g,d,t,meta,work){
  function ntId(name){if(!g.ids.has(name))fail("unknown nonterminal");return g.ids.get(name);}
  function span(start,end){
    integer(start,"span start",0,d.n);integer(end,"span end",start,d.n);
    const length=end-start;return {start,end,length,cell:length===0?null:d.base[length]+start};
  }
  function spanRecord(s){return {start:s.start,end:s.end,length:s.length,cell_id:s.cell,text:d.symbols.slice(s.start,s.end).join("")};}
  function indexedSpan(cell){return {start:d.starts[cell],end:d.ends[cell],length:d.ends[cell]-d.starts[cell],cell};}
  function countAt(nt,s){return s.cell===null?0n:t.counts[nt][s.cell];}
  function pairAt(p,s){
    integer(p,"pair id",0,g.pairs.length-1);
    const mask=s.cell===null?0n:t.pairMasks[p][s.cell],count=s.cell===null?0n:t.pairCounts[p][s.cell];
    return {mask,count,partitions:popcount(mask,work)};
  }
  function occurrence(nt,rank){
    const cell=meta.occurrences[nt][rank],s=indexedSpan(cell);
    return {nonterminal:g.names[nt],rank:String(rank),...spanRecord(s),positive_parse_count:String(t.counts[nt][cell])};
  }
  function pageLimit(options){
    obj(options,"page options");return options.limit===undefined?BOOLEAN_SUBSTRING_LIMITS.page_size:integer(options.limit,"page limit",1,BOOLEAN_SUBSTRING_LIMITS.page_size);
  }
  function ruleEvidence(ruleId,start,end){
    integer(ruleId,"rule id",0,g.compiled.length-1);const s=span(start,end),rule=g.compiled[ruleId];
    work.rule_evidence_queries++;
    const count=s.cell===null?0n:t.ruleCounts[ruleId][s.cell];
    function part(p){
      const r=pairAt(p,s);return {pair_id:p,symbols:g.pairs[p].map(i=>g.names[i]),
        partition_count:r.partitions,split_mask_hex:r.mask.toString(16),positive_parse_count:String(r.count)};
    }
    const headRules=s.cell===null?[]:g.compiled.map((r,i)=>r.head===rule.head&&t.ruleCounts[i][s.cell]>0n?i:-1).filter(i=>i>=0);
    return {rule_id:ruleId,head:g.names[rule.head],...spanRecord(s),valid:count>0n,positive_parse_count:String(count),
      terminal:rule.terminal,nonempty_guard:rule.terminal===null,
      positive:rule.positive.map(part),negative:rule.negative.map(part),valid_rules_for_head:headRules,
      rule_choice_unique_on_this_span:headRules.length<=1};
  }
  function splitPage(pairId,start,end,options={}){
    const s=span(start,end),r=pairAt(pairId,s),limit=pageLimit(options),offset=options.offset===undefined?0:integer(options.offset,"split-page offset",0,r.partitions);
    work.split_page_queries++;
    const [a,b]=g.pairs[pairId],rows=[];let skipped=0,seen=0;
    for(let cut=1;cut<s.length&&rows.length<limit;cut++)if(r.mask&(1n<<BigInt(cut))){
      if(skipped++<offset)continue;
      const left=span(s.start,s.start+cut),right=span(s.start+cut,s.end),lc=countAt(a,left),rc=countAt(b,right);
      const weight=bounded(lc*rc);work.query_weight_products++;
      rows.push({rank:String(offset+seen++),offset:cut,position:s.start+cut,
        left:{nonterminal:g.names[a],...spanRecord(left),positive_parse_count:String(lc)},
        right:{nonterminal:g.names[b],...spanRecord(right),positive_parse_count:String(rc)},positive_parse_count:String(weight)});
    }
    work.split_rows_returned+=rows.length;const next=offset+rows.length;
    return {pair_id:pairId,symbols:g.pairs[pairId].map(i=>g.names[i]),...spanRecord(s),
      partition_count:r.partitions,positive_parse_count:String(r.count),split_mask_hex:r.mask.toString(16),
      offset,returned:rows.length,next_offset:next===r.partitions?null:next,records:rows};
  }
  function selectParse(nonterminal,start,end,rankInput=0){
    const nt=ntId(nonterminal),s=span(start,end),rank=unsigned(rankInput,"parse rank"),total=countAt(nt,s);
    if(rank>=total)fail("parse rank is outside the positive parse family");
    work.parse_queries++;const nodes=[],known=new Map();
    function visit(a,cell,r){
      const key=a+":"+cell+":"+r;if(known.has(key))return known.get(key);
      if(nodes.length>=BOOLEAN_SUBSTRING_LIMITS.parse_nodes)fail("positive parse certificate exceeds its node cap");
      const id=nodes.length;known.set(key,id);nodes.push(null);
      const v=indexedSpan(cell);let chosen=-1,local=r;
      for(let ri=0;ri<g.compiled.length;ri++)if(g.compiled[ri].head===a){
        work.parse_rule_rows_visited++;const count=t.ruleCounts[ri][cell];
        if(local<count){chosen=ri;break;}local-=count;
      }
      if(chosen<0)fail("saved rule counts do not cover this parse rank");
      const rule=g.compiled[chosen],node={node_id:id,nonterminal:g.names[a],...spanRecord(v),rank:String(r),
        positive_parse_count:String(t.counts[a][cell]),rule_id:chosen,terminal:rule.terminal,conjuncts:[],negative_guards:[]};
      if(rule.terminal!==null){if(local!==0n||v.length!==1)fail("terminal parse rank is inconsistent");}
      else{
        const ranks=new Array(rule.positive.length);
        for(let j=rule.positive.length-1;j>=0;j--){
          const count=t.pairCounts[rule.positive[j]][cell];if(count===0n)fail("positive conjunct has no saved parses");
          ranks[j]=local%count;local/=count;
        }
        if(local!==0n)fail("saved rule count exceeds its conjunct product");
        for(let j=0;j<rule.positive.length;j++){
          const p=rule.positive[j],[b,c]=g.pairs[p],mask=t.pairMasks[p][cell];let pr=ranks[j],found=null;
          for(let cut=1;cut<v.length;cut++)if(mask&(1n<<BigInt(cut))){
            work.parse_split_rows_visited++;
            const l=d.base[cut]+v.start,rr=d.base[v.length-cut]+v.start+cut,lc=t.counts[b][l],rc=t.counts[c][rr];
            const weight=bounded(lc*rc);work.query_weight_products++;
            if(pr<weight){found={cut,l,rr,lr:pr/rc,rrank:pr%rc};break;}pr-=weight;
          }
          if(found===null)fail("saved pair counts do not cover this positive parse rank");
          const left=visit(b,found.l,found.lr),right=visit(c,found.rr,found.rrank);
          node.conjuncts.push({pair_id:p,pair_rank:String(ranks[j]),offset:found.cut,position:v.start+found.cut,left_node:left,right_node:right});
        }
        for(const p of rule.negative){
          if(t.pairMasks[p][cell]!==0n)fail("selected rule has a nonempty negative conjunct");
          node.negative_guards.push({pair_id:p,split_mask_hex:"0",partition_count:0});
        }
      }
      nodes[id]=node;return id;
    }
    const root=visit(nt,s.cell,rank);work.parse_nodes_returned+=nodes.length;
    return {nonterminal, ...spanRecord(s),rank:String(rank),positive_parse_count:String(total),root_node:root,nodes,
      scope:"A ranked positive parse certificate with retained negative guards. Its uniqueness does not establish Boolean or inherent unambiguity."};
  }
  return Object.freeze({
    summary(){return copy(data.summary);},
    cell(start,end){
      const s=span(start,end);work.cell_queries++;const members=[];
      for(let nt=0;nt<g.names.length;nt++){const count=countAt(nt,s);if(count>0n)members.push({nonterminal:g.names[nt],positive_parse_count:String(count)});}
      return {...spanRecord(s),members};
    },
    parseCount(nonterminal,start,end){
      const nt=ntId(nonterminal),s=span(start,end);work.parse_count_queries++;return String(countAt(nt,s));
    },
    countOccurrences(nonterminal=g.names[g.start]){const nt=ntId(nonterminal);work.count_occurrence_queries++;return String(meta.occurrences[nt].length);},
    rankOccurrence(nonterminal,start,end){
      const nt=ntId(nonterminal),s=span(start,end);work.rank_occurrence_queries++;
      if(countAt(nt,s)===0n)return {status:"not_member",nonterminal,...spanRecord(s)};
      const list=meta.occurrences[nt];let lo=0,hi=list.length;
      while(lo<hi){const mid=Math.floor((lo+hi)/2);work.occurrence_binary_steps++;if(list[mid]<s.cell)lo=mid+1;else hi=mid;}
      if(list[lo]!==s.cell)fail("saved occurrence list lacks an accepted cell");
      return {status:"found",...occurrence(nt,lo)};
    },
    selectOccurrence(nonterminal,rankInput){
      const nt=ntId(nonterminal),rank=unsigned(rankInput,"occurrence rank");
      if(rank>=BigInt(meta.occurrences[nt].length))fail("occurrence rank is outside its family");
      work.select_occurrence_queries++;work.occurrences_returned++;return occurrence(nt,Number(rank));
    },
    pageOccurrences(nonterminal,startInput,options={}){
      const nt=ntId(nonterminal),start=unsigned(startInput,"occurrence page start"),limit=pageLimit(options),total=meta.occurrences[nt].length;
      if(start>BigInt(total))fail("occurrence page starts beyond its family");work.page_occurrence_queries++;
      const from=Number(start),end=Math.min(total,from+limit),rows=[];
      for(let i=from;i<end;i++)rows.push(occurrence(nt,i));
      work.occurrences_returned+=rows.length;
      return {nonterminal,start:String(start),total:String(total),returned:rows.length,next_rank:end===total?null:String(end),records:rows};
    },
    ruleEvidence,splitPage,selectParse,
    diagnostics(options={}){
      obj(options,"diagnostic options");const kind=options.kind===undefined?"rule":options.kind;
      if(kind!=="rule"&&kind!=="split")fail("diagnostic kind must be rule or split");
      const rows=kind==="rule"?meta.ruleOverlaps:meta.multipleSplits,offset=options.offset===undefined?0:integer(options.offset,"diagnostic offset",0,rows.length),limit=pageLimit(options);
      const end=Math.min(rows.length,offset+limit);work.diagnostic_queries++;
      const selected=rows.slice(offset,end).map(row=>kind==="rule"?
        {...spanRecord(indexedSpan(row[0])),nonterminal:g.names[row[1]],valid_rule_ids:row[2].slice()}:
        {...spanRecord(indexedSpan(row[0])),pair_id:row[1],symbols:g.pairs[row[1]].map(nt=>g.names[nt]),partition_count:row[2],
          split_mask_hex:t.pairMasks[row[1]][row[0]].toString(16),usage:copy(g.usage[row[1]])});
      work.diagnostic_rows_returned+=selected.length;
      return {kind,total:rows.length,offset,returned:selected.length,next_offset:end===rows.length?null:end,records:selected,
        scope:"All nonempty substring occurrences of this word only; includes concatenations in rejected and negative contexts."};
    },
    snapshot(){return copy(data);},
    work(){return {...work};}
  });
}
module.exports={compileBooleanSubstringIndex,openRetainedBooleanSubstringIndex,BOOLEAN_SUBSTRING_LIMITS};
