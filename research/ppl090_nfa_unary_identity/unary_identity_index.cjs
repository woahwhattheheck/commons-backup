"use strict";
/* Finite Boolean-power identities and Shallit's source-defined word family.
 * No arbitrary-matrix transient bound is assumed.
 */
const UNARY_IDENTITY_LIMITS = Object.freeze({
  max_states:4,max_relations:65536,max_exponent_digits:300,
  max_saved_cells:2000000,max_snapshot_chars:12000000,
  max_page_rows:128,max_provenance_chars:32768,max_separator_states:24
});
const ID_SCHEMA="commons.unary_boolean_identity/v1";
const SEP_SCHEMA="commons.shallit_cycle_separator/v1";
function bad(s){throw new RangeError(s);}
function object(x,name){if(!x||typeof x!=="object"||Array.isArray(x))bad(name+" must be an object");return x;}
function integer(x,name,lo,hi){if(typeof x!=="number"||!Number.isSafeInteger(x)||x<lo||x>hi)bad(name+" out of range");return x;}
function natural(x,name){
  if(typeof x==="number"){if(!Number.isSafeInteger(x)||x<0)bad(name+" must be a safe natural");x=BigInt(x);}
  else if(typeof x==="string"){if(!/^(0|[1-9][0-9]*)$/.test(x)||x.length>300)bad(name+" must be canonical");x=BigInt(x);}
  else if(typeof x!=="bigint"||x<0n)bad(name+" must be natural");
  if(x.toString().length>300)bad(name+" too long");return x;
}
function clone(x){return JSON.parse(JSON.stringify(x));}
function origin(x){if(typeof x==="string")x=JSON.parse(x);object(x,"provenance");const s=JSON.stringify(x);if(s.length>32768)bad("provenance too long");return JSON.parse(s);}
function digits(n){return n===0n?[]:n.toString(2).split("").reverse().map(Number);}
function identity(n){return Array.from({length:n},(_,i)=>2**i);}
function decodeCode(code,n){const q=2**n,rows=[];for(let i=0;i<n;i++){rows.push(code%q);code=Math.floor(code/q);}return rows;}
function encodeRows(rows,n){let code=0,m=1;for(let i=0;i<n;i++){code+=rows[i]*m;m*=2**n;}return code;}
function validRows(rows,n){if(!Array.isArray(rows)||rows.length!==n)bad("row length");rows.forEach(x=>integer(x,"row mask",0,2**n-1));}
function product(left,right,n,work){
  const answer=[];
  for(let i=0;i<n;i++){let value=0;for(let j=0;j<n;j++)if(left[i]&(2**j)){value|=right[j];if(work)work.row_unions++;}answer.push(value);}
  if(work)work.boolean_products++;return answer;
}
function apply(rows,mask,n,work){
  let out=0;for(let i=0;i<n;i++)if(mask&(2**i)){out|=rows[i];if(work)work.query_row_unions++;}return out;
}
function powerPacket(rows,n,exponents,work){
  const bs=exponents.map(digits),bits=Math.max(0,...bs.map(x=>x.length)),powers=[];
  if(bits){powers.push(rows.slice());for(let bit=1;bit<bits;bit++)powers.push(product(powers[bit-1],powers[bit-1],n,work));}
  const evaluations=bs.map((b,index)=>{
    let current=identity(n);const steps=[];
    for(let bit=0;bit<b.length;bit++)if(b[bit]){
      current=product(current,powers[bit],n,work);
      steps.push({bit,accumulator_rows:current.slice()});
    }
    return{exponent:exponents[index].toString(),selected_bits:b.flatMap((v,i)=>v?[i]:[]),steps,result_rows:current};
  });
  return{binary_power_rows:powers,evaluations};
}
function compileUnaryPowerIdentity(input){
  object(input,"input");const n=integer(input.states,"states",1,4);
  const left=natural(input.left_exponent,"left_exponent"),right=natural(input.right_exponent,"right_exponent");
  const provenance=origin(input.provenance),relationCount=2**(n*n),bits=Math.max(digits(left).length,digits(right).length);
  const cells=relationCount*n*(bits+digits(left).reduce((a,b)=>a+b,0)+digits(right).reduce((a,b)=>a+b,0)+4);
  const maxCells=input.max_saved_cells===undefined?2000000:integer(input.max_saved_cells,"max_saved_cells",0,2000000);
  if(cells>maxCells)return{status:"INCOMPLETE_BUDGET",reason:"saved_cell_limit",snapshot:null,required_cells:cells};
  const work={relations:0,boolean_products:0,row_unions:0,binary_nfa_tables_enumerated:0,words_expanded:0};
  const records=[];let matches=0,firstFailure=null;
  for(let code=0;code<relationCount;code++){
    const rows=decodeCode(code,n),packet=powerPacket(rows,n,[left,right],work);
    const l=packet.evaluations[0].result_rows,r=packet.evaluations[1].result_rows;
    const difference_rows=l.map((v,i)=>v^r[i]),equal=difference_rows.every(v=>v===0);
    if(equal)matches++;else if(firstFailure===null)firstFailure=code;
    records.push({code,rows,...packet,difference_rows,equal});work.relations++;
  }
  const snapshot={schema:ID_SCHEMA,status:"COMPLETE_FINITE_IDENTITY_ATLAS",states:n,
    exponents:[left.toString(),right.toString()],relation_code:"row0 least significant base-2^states digit; target-state bit masks",
    records,summary:{states:n,relations:relationCount,equal_relations:matches,
      unequal_relations:relationCount-matches,all_relations_equal:matches===relationCount,first_unequal_code:firstFailure,
      lower_state_padding:true,scope:"all binary relations on these labelled states; no transition completeness requirement"},
    provenance,work,limits:{...UNARY_IDENTITY_LIMITS}};
  const chars=JSON.stringify(snapshot).length;
  if(chars>12000000)return{status:"INCOMPLETE_BUDGET",reason:"snapshot_char_limit",snapshot:null,work,snapshot_chars:chars};
  return{status:snapshot.status,snapshot,summary:clone(snapshot.summary),work:clone(work),snapshot_chars:chars};
}
function gcd(a,b,work){while(b){const r=a%b;a=b;b=r;work.gcd_divisions++;}return a;}
function compileShallitCycleSeparator(input){
  object(input,"input");const n=integer(input.states,"states",4,24),provenance=origin(input.provenance);
  const t=n*n-3*n+2,f=BigInt(t-1),work={gcd_divisions:0,lcm_rows:0,boolean_products:0,row_unions:0,words_expanded:0};
  let lcm=1n;const lcm_rows=[];
  for(let k=1;k<=t;k++){const g=gcd(lcm,BigInt(k),work),previous=lcm;lcm=lcm/g*BigInt(k);
    lcm_rows.push({k,previous:previous.toString(),gcd:g.toString(),value:lcm.toString()});work.lcm_rows++;}
  const g=f+lcm,zero=Array(n).fill(0),one=Array(n).fill(0);
  for(let i=0;i<n-2;i++)zero[i]=2**(i+1);
  zero[n-2]=1+2**(n-1);zero[n-1]=1;one[0]=1;
  const zeroPowers=powerPacket(zero,n,[f,g],work),onePowers=powerPacket(one,n,[f,g],work);
  const zeroShort=zeroPowers.evaluations[0].result_rows,zeroLong=zeroPowers.evaluations[1].result_rows;
  const oneShort=onePowers.evaluations[0].result_rows,oneLong=onePowers.evaluations[1].result_rows;
  const afterW0=apply(zeroLong,1,n),afterX0=apply(zeroShort,1,n);
  const endW=apply(oneShort,afterW0,n),endX=apply(oneLong,afterX0,n);
  const nCycles=g%BigInt(n-1),shortCycles=(g-BigInt(n)*nCycles)/BigInt(n-1);
  if(shortCycles<0n||!(endW&1)||(endX&1))bad("constructed separator failure");
  const snapshot={schema:SEP_SCHEMA,status:"EXACT_CONSTRUCTED_SEPARATOR",states:n,initial_mask:1,accepting_mask:1,
    t,lcm:lcm.toString(),short_exponent:f.toString(),long_exponent:g.toString(),
    words:{accepted:[{symbol:0,length:g.toString()},{symbol:1,length:f.toString()}],
      rejected:[{symbol:0,length:f.toString()},{symbol:1,length:g.toString()}],common_length:(f+g).toString()},
    transitions:{zero,one},lcm_rows,zero_powers:zeroPowers,one_powers:onePowers,
    endpoint_certificate:{accepted:{after_zero:afterW0,after_one:endW,accepts:!!(endW&1)},
      rejected:{after_zero:afterX0,after_one:endX,accepts:!!(endX&1)}},
    accepted_zero_walk:{cycle_lengths:[n-1,n],cycle_counts:[shortCycles.toString(),nCycles.toString()],
      reconstructed_length:(shortCycles*BigInt(n-1)+nCycles*BigInt(n)).toString(),
      note:"closed walks followed by the symbol1 self-loop; no expanded path"},
    rejected_zero_obstruction:{n_cycle_count_residue:n-2,modulus:n-1,
      minimum_n_cycle_contribution:String(n*(n-2)),target:f.toString(),
      reason:"Any nonnegative combination reaching the target needs at least n-2 cycles of length n; that contribution already exceeds the target."},
    summary:{states:n,common_word_length:(f+g).toString(),accepts_first:true,rejects_second:true,
      claimed_minimum:null,scope:"constructed upper bound; pair with a separate valid lower certificate"},
    provenance,work};
  return{status:snapshot.status,snapshot,summary:clone(snapshot.summary),work:clone(work),snapshot_chars:JSON.stringify(snapshot).length};
}
function openRetainedUnaryPowerIdentity(input){
  if(typeof input==="string"){if(input.length>12000000)bad("snapshot too large");input=JSON.parse(input);}
  object(input,"snapshot");const encoded=JSON.stringify(input);if(encoded.length>12000000)bad("snapshot too large");
  const snap=JSON.parse(encoded);if(snap.schema!==ID_SCHEMA||snap.status!=="COMPLETE_FINITE_IDENTITY_ATLAS")bad("snapshot schema");
  const n=integer(snap.states,"states",1,4),count=2**(n*n),full=2**n-1;
  if(!Array.isArray(snap.exponents)||snap.exponents.length!==2)bad("exponents");
  const exponents=snap.exponents.map((v,i)=>natural(v,"exponent"+i));
  const bits=Math.max(...exponents.map(v=>digits(v).length),0);
  if(!Array.isArray(snap.records)||snap.records.length!==count)bad("incomplete relation atlas");
  let equalCount=0,firstFailure=null;
  const stats={loaded_relations:count,structural_row_checks:0,saved_endpoint_comparisons:0,
    queries:0,summary_queries:0,source_queries:0,relation_queries:0,power_queries:0,
    apply_queries:0,pair_queries:0,page_queries:0,page_rows_returned:0,query_row_unions:0,
    relation_atlases_compiled:0,boolean_power_products_recomputed:0,words_expanded:0,
    validation:"structural and saved-final-row equality checks only; multiplication provenance not independently certified"};
  for(let code=0;code<count;code++){
    const r=snap.records[code];if(r.code!==code)bad("record code");validRows(r.rows,n);
    if(encodeRows(r.rows,n)!==code)bad("relation encoding");
    if(!Array.isArray(r.binary_power_rows)||r.binary_power_rows.length!==bits)bad("power coverage");
    r.binary_power_rows.forEach(rows=>{validRows(rows,n);stats.structural_row_checks++;});
    if(bits&&JSON.stringify(r.binary_power_rows[0])!==JSON.stringify(r.rows))bad("base power");
    if(!Array.isArray(r.evaluations)||r.evaluations.length!==2)bad("evaluation coverage");
    for(let side=0;side<2;side++){
      const e=r.evaluations[side],selected=digits(exponents[side]).flatMap((v,i)=>v?[i]:[]);
      if(e.exponent!==exponents[side].toString()||JSON.stringify(e.selected_bits)!==JSON.stringify(selected)||e.steps.length!==selected.length)bad("evaluation bits");
      e.steps.forEach((step,i)=>{if(step.bit!==selected[i])bad("step bit");validRows(step.accumulator_rows,n);stats.structural_row_checks++;});
      validRows(e.result_rows,n);
      const last=e.steps.length?e.steps.at(-1).accumulator_rows:identity(n);
      if(JSON.stringify(last)!==JSON.stringify(e.result_rows))bad("result pointer");
    }
    const difference=r.evaluations[0].result_rows.map((v,i)=>v^r.evaluations[1].result_rows[i]);
    const equal=difference.every(v=>v===0);
    if(JSON.stringify(r.difference_rows)!==JSON.stringify(difference)||r.equal!==equal)bad("endpoint mismatch");
    stats.saved_endpoint_comparisons+=n;
    if(equal)equalCount++;else if(firstFailure===null)firstFailure=code;
  }
  const summary={states:n,relations:count,equal_relations:equalCount,unequal_relations:count-equalCount,
    all_relations_equal:equalCount===count,first_unequal_code:firstFailure,
    lower_state_padding:true,scope:"all binary relations on these labelled states; no transition completeness requirement"};
  for(const k of Object.keys(summary))if(snap.summary?.[k]!==summary[k])bad("summary mismatch");
  origin(snap.provenance);
  function q(k){stats.queries++;stats[k]++;}
  function rec(code){integer(code,"relation code",0,count-1);return snap.records[code];}
  function side(v){return integer(v,"side",0,1);}
  function mask(v,name){return integer(v,name,0,full);}
  function runPair(input){
    object(input,"pair input");
    const zr=rec(input.zero_code),or=rec(input.one_code);
    const initial=mask(input.initial_mask,"initial_mask"),accepting=mask(input.accepting_mask,"accepting_mask");
    const zl=zr.evaluations[1].result_rows,zs=zr.evaluations[0].result_rows;
    const ol=or.evaluations[1].result_rows,os=or.evaluations[0].result_rows;
    const a0=apply(zl,initial,n,stats),b0=apply(zs,initial,n,stats);
    const a1=apply(os,a0,n,stats),b1=apply(ol,b0,n,stats);
    return{zero_code:input.zero_code,one_code:input.one_code,initial_mask:initial,accepting_mask:accepting,
      first_word:[{symbol:0,length:snap.exponents[1]},{symbol:1,length:snap.exponents[0]}],
      second_word:[{symbol:0,length:snap.exponents[0]},{symbol:1,length:snap.exponents[1]}],
      first:{after_zero:a0,after_one:a1,accepts:!!(a1&accepting)},
      second:{after_zero:b0,after_one:b1,accepts:!!(b1&accepting)},
      same_terminal_subset:a1===b1,separates:!!(a1&accepting)!==!!(b1&accepting)};
  }
  return Object.freeze({
    summary(){q("summary_queries");return clone(summary);},
    source(){q("source_queries");return clone(snap.provenance);},
    relation(code){q("relation_queries");return clone(rec(code));},
    power(code,which){q("power_queries");return clone(rec(code).evaluations[side(which)]);},
    applyPower(code,which,startMask){q("apply_queries");const r=rec(code),s=side(which),start=mask(startMask,"start_mask");
      return{code,exponent:r.evaluations[s].exponent,start_mask:start,result_mask:apply(r.evaluations[s].result_rows,start,n,stats)};},
    compareSwappedBlocks(input){q("pair_queries");return runPair(input);},
    page(options){
      q("page_queries");if(options===undefined)options={};object(options,"options");
      const start=options.start===undefined?0:integer(options.start,"start",0,count);
      const limit=options.limit===undefined?128:integer(options.limit,"limit",1,128);
      const records=clone(snap.records.slice(start,start+limit));stats.page_rows_returned+=records.length;
      return{start,total:count,count:records.length,records,next_start:start+records.length===count?null:start+records.length};},
    snapshot(){return clone(snap);},statistics(){return clone(stats);}
  });
}
module.exports={UNARY_IDENTITY_LIMITS,compileUnaryPowerIdentity,compileShallitCycleSeparator,openRetainedUnaryPowerIdentity};
