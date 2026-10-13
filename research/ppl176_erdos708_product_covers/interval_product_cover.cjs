"use strict";

/*
 * Exact minimum-cardinality product covers in a positive consecutive interval.
 * Prime/least-factor input is an identified premise; it is not regenerated.
 * Complete suffix counts and forward optimal-prefix counts are retained.
 * Pure CommonJS and BigInt; no I/O or dependencies.
 */

const PRODUCT_COVER_LIMITS=Object.freeze({
  max_interval_length:64,max_input_values:256,max_deficit_states:4096,
  max_offset_digits:80,max_product_digits:6000,max_page_size:64,
  max_snapshot_characters:8000000,max_encoded_row_characters:100000
});
const SCHEMA="commons.interval_product_cover/v1",INF=255;
const ALPHABET="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const BASE64_INDEX=Object.freeze(Object.fromEntries([...ALPHABET].map((x,i)=>[x,i])));

function fail(s){throw new Error(s);}
function integer(v,label,digits=80){
  let s;
  if(typeof v==="bigint")s=v.toString();
  else if(typeof v==="number"&&Number.isSafeInteger(v))s=String(v);
  else if(typeof v==="string")s=v;
  else fail(label+" must be an exact integer.");
  if(!/^(0|-?[1-9][0-9]*)$/.test(s)||s.replace("-","").length>digits)fail(label+" is not a canonical bounded integer.");
  return BigInt(s);
}
function small(v,min,max,label){
  const n=integer(v,label);
  if(n<BigInt(min)||n>BigInt(max))fail(label+" is outside its permitted range.");
  return Number(n);
}
function offset(v){const x=integer(v,"offset");if(x<0n)fail("offset must be nonnegative.");return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function boundedProduct(x){
  if(x.toString().length>PRODUCT_COVER_LIMITS.max_product_digits)fail("Product exceeds the digit bound.");
  return x;
}
function workRecord(){
  return {
    source_factor_steps:0,candidate_remainder_tests:0,candidate_divisions:0,
    deficit_digit_cells:0,transition_patterns:0,transition_coordinate_cells:0,
    suffix_state_updates:0,forward_states:0,forward_edges:0,marginal_products:0,
    suffix_cells_encoded:0,prefix_cells_encoded:0,
    loaded_suffix_cells:0,loaded_prefix_cells:0,loaded_runs:0,
    dp_constructions:0,factor_constructions:0,local_branch_checks:0,
    query_deficit_coordinates:0,select_calls:0,rank_calls:0,witnesses:0,
    witness_product_terms:0,participation_rows:0,period_views:0
  };
}
function pushVar(out,value){
  let x=BigInt(value);if(x<0n)fail("Unsigned encoding received a negative value.");
  do{let b=Number(x&127n);x>>=7n;if(x)b|=128;out.push(b);}while(x);
}
function readVar(bytes,pos,max){
  let x=0n,shift=0n,last=0,length=0;
  do{
    if(pos.i>=bytes.length||length>=10)fail("Truncated or oversized unsigned varint.");
    last=bytes[pos.i++];x|=BigInt(last&127)<<shift;shift+=7n;length++;
  }while(last&128);
  if(length>1&&(last&127)===0)fail("Noncanonical unsigned varint.");
  if(x>max)fail("Unsigned value exceeds the declared bound.");
  return x;
}
function toBase64(bytes){
  const out=[];
  for(let i=0;i<bytes.length;i+=3){
    const a=bytes[i],b=i+1<bytes.length?bytes[i+1]:0,c=i+2<bytes.length?bytes[i+2]:0;
    out.push(ALPHABET[a>>2],ALPHABET[((a&3)<<4)|(b>>4)],
      i+1<bytes.length?ALPHABET[((b&15)<<2)|(c>>6)]:"=",
      i+2<bytes.length?ALPHABET[c&63]:"=");
  }
  return out.join("");
}
function fromBase64(s){
  if(typeof s!=="string"||s.length>100000||s.length%4!==0||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(s))
    fail("Invalid bounded base64 row.");
  const out=[];
  for(let i=0;i<s.length;i+=4){
    const a=BASE64_INDEX[s[i]],b=BASE64_INDEX[s[i+1]],
      c=s[i+2]==="="?0:BASE64_INDEX[s[i+2]],d=s[i+3]==="="?0:BASE64_INDEX[s[i+3]];
    if(s[i+2]==="="&&(b&15)!==0)fail("Nonzero base64 padding bits.");
    if(s[i+3]==="="&&s[i+2]!=="="&&(c&3)!==0)fail("Nonzero base64 padding bits.");
    out.push((a<<2)|(b>>4));
    if(s[i+2]!=="=")out.push(((b&15)<<4)|(c>>2));
    if(s[i+3]!=="=")out.push(((c&3)<<6)|d);
  }
  return out;
}
function encodePairs(cost,counts){
  const bytes=[];
  for(let start=0;start<cost.length;){
    let end=start+1;
    while(end<cost.length&&cost[end]===cost[start]&&counts[end]===counts[start])end++;
    pushVar(bytes,end-start);bytes.push(cost[start]);pushVar(bytes,counts[start]);start=end;
  }
  return toBase64(bytes);
}
function encodeCounts(counts){
  const bytes=[];
  for(let start=0;start<counts.length;){
    let end=start+1;while(end<counts.length&&counts[end]===counts[start])end++;
    pushVar(bytes,end-start);pushVar(bytes,counts[start]);start=end;
  }
  return toBase64(bytes);
}
function decodePairs(encoded,states,M,w){
  const bytes=fromBase64(encoded),pos={i:0},cost=new Uint8Array(states),counts=Array(states);
  let at=0;const maxCount=1n<<BigInt(M);
  while(pos.i<bytes.length){
    const run=Number(readVar(bytes,pos,BigInt(states)));if(run<1||at+run>states)fail("Pair run exceeds its state row.");
    if(pos.i>=bytes.length)fail("Missing cost byte.");
    const c=bytes[pos.i++],v=readVar(bytes,pos,maxCount);
    if(c!==INF&&c>M)fail("Cost exceeds interval length.");
    if((c===INF)!==(v===0n))fail("Unreachable/count-zero disagreement.");
    cost.fill(c,at,at+run);for(let j=0;j<run;j++)counts[at+j]=v;
    at+=run;w.loaded_runs++;
  }
  if(at!==states)fail("Pair row has incomplete coverage.");
  w.loaded_suffix_cells+=states;return {cost,counts};
}
function decodeCounts(encoded,states,M,w){
  const bytes=fromBase64(encoded),pos={i:0},counts=Array(states);
  let at=0;const maxCount=1n<<BigInt(M);
  while(pos.i<bytes.length){
    const run=Number(readVar(bytes,pos,BigInt(states))),v=readVar(bytes,pos,maxCount);
    if(run<1||at+run>states)fail("Count run exceeds its state row.");
    for(let j=0;j<run;j++)counts[at+j]=v;
    at+=run;w.loaded_runs++;
  }
  if(at!==states)fail("Count row has incomplete coverage.");
  w.loaded_prefix_cells+=states;return counts;
}
function canonicalValues(raw){
  if(!Array.isArray(raw)||raw.length<1||raw.length>256)fail("values must contain between 1 and 256 input records.");
  const a=[...new Set(raw.map(x=>small(x,2,64,"set value")))].sort((x,y)=>x-y);
  return a;
}
function axesFromRequirements(requirements){
  if(!Array.isArray(requirements)||requirements.length<1||requirements.length>18)fail("Invalid prime requirements.");
  let states=1,last=1;
  const axes=requirements.map(v=>{
    if(!v||typeof v!=="object")fail("Invalid requirement.");
    const p=small(v.prime,2,64,"prime premise"),e=small(v.exponent,1,384,"required exponent");
    if(p<=last)fail("Prime requirements are not strictly increasing.");last=p;
    const axis={prime:p,exponent:e,radix:e+1,stride:states};
    states*=e+1;if(states>4096)fail("Prime-deficit lattice exceeds 4096 states.");
    return axis;
  });
  return {axes,states};
}
function afterState(state,vector,axes,w){
  let x=state,out=0;
  for(let j=0;j<axes.length;j++){
    const a=axes[j],d=x%a.radix;x=Math.floor(x/a.radix);
    out+=Math.max(0,d-vector[j])*a.stride;
    if(w)w.query_deficit_coordinates++;
  }
  return out;
}
function compileIntervalProductCover(input){
  if(!input||typeof input!=="object")fail("A product-cover input object is required.");
  const A=canonicalValues(input.values),M=A[A.length-1],x=offset(input.offset),w=workRecord();
  const b=input.factor_basis;
  if(!b||!Array.isArray(b.least_factor_by_integer)||!Array.isArray(b.primes))fail("An identified least-factor/prime basis is required.");
  const basisLimit=small(b.limit,M,16384,"basis limit");
  if(b.least_factor_by_integer.length<M+1||b.least_factor_by_integer.length>16385||b.primes.length>2000)
    fail("Basis arrays have unsupported lengths.");
  const lp=b.least_factor_by_integer.slice(0,M+1).map((v,i)=>small(v,0,M,"least factor "+i));
  if(lp[0]!==0||lp[1]!==1)fail("Basis zero/one convention mismatch.");
  let last=1;
  const allPrimes=b.primes.map(v=>{const p=small(v,2,basisLimit,"basis prime");if(p<=last)fail("Basis primes must be strictly increasing.");last=p;return p;});
  const primes=allPrimes.filter(p=>p<=M),primeSet=new Set(primes);
  const provenance=b.provenance===undefined?"caller_supplied_prime_and_least_factor_premise":b.provenance;
  if(typeof provenance!=="string"||provenance.length>2048)fail("Basis provenance must have at most 2048 characters.");
  const totals=new Map(),factorizations=[];let P=1n;
  for(const a of A){
    let current=a;const steps=[];P*=BigInt(a);
    while(current>1){
      const p=lp[current];if(p<2||!primeSet.has(p)||current%p!==0)fail("The supplied least-factor premise cannot factor a target value.");
      const next=current/p;steps.push([current,p,next]);current=next;
      totals.set(p,(totals.get(p)||0)+1);w.source_factor_steps++;
    }
    factorizations.push({value:a,division_steps:steps});
  }
  w.factor_constructions++;
  const requirements=[...totals].sort((a,b)=>a[0]-b[0]).map(([prime,exponent])=>({prime,exponent}));
  const {axes,states}=axesFromRequirements(requirements);
  const digits=Array.from({length:states},(_,state)=>{
    let t=state;return axes.map(a=>{const d=t%a.radix;t=Math.floor(t/a.radix);w.deficit_digit_cells++;return d;});
  });
  const candidates=[];
  for(let i=1;i<=M;i++){
    const value=x+BigInt(i),vector=[],proof=[];
    for(const axis of axes){
      let q=value,e=0,remainder=null;const p=BigInt(axis.prime);
      while(e<axis.exponent){
        remainder=Number(q%p);w.candidate_remainder_tests++;
        if(remainder!==0)break;
        q/=p;e++;w.candidate_divisions++;
      }
      vector.push(e);
      proof.push({prime:axis.prime,capped_exponent:e,quotient:q.toString(),
        next_remainder:e<axis.exponent?remainder:null,at_cap:e===axis.exponent});
    }
    candidates.push({offset:i,origin_value:value.toString(),capped_exponents:vector,valuation_witnesses:proof});
  }
  const maps=new Map(),candidateMaps=[];
  for(const c of candidates){
    const key=c.capped_exponents.join(",");
    if(!maps.has(key)){
      const transitions=new Uint16Array(states);
      for(let state=0;state<states;state++){
        let out=0;
        for(let j=0;j<axes.length;j++){out+=Math.max(0,digits[state][j]-c.capped_exponents[j])*axes[j].stride;w.transition_coordinate_cells++;}
        transitions[state]=out;
      }
      maps.set(key,transitions);w.transition_patterns++;
    }
    candidateMaps.push(maps.get(key));
  }
  const suffix=Array(M+1);
  const terminalCost=new Uint8Array(states);terminalCost.fill(INF);terminalCost[0]=0;
  const terminalCounts=Array(states).fill(0n);terminalCounts[0]=1n;
  suffix[M]={cost:terminalCost,counts:terminalCounts};
  for(let i=M-1;i>=0;i--){
    const next=suffix[i+1],cost=new Uint8Array(states),counts=Array(states),transition=candidateMaps[i];
    for(let state=0;state<states;state++){
      const skip=next.cost[state],rem=transition[state],take=next.cost[rem]===INF?INF:next.cost[rem]+1;
      const best=Math.min(skip,take);cost[state]=best;
      counts[state]=best===INF?0n:(skip===best?next.counts[state]:0n)+(take===best?next.counts[rem]:0n);
      w.suffix_state_updates++;
    }
    suffix[i]={cost,counts};
  }
  const full=states-1,minimum=suffix[0].cost[full],total=suffix[0].counts[full];
  if(minimum===INF||minimum<1||total<1n)fail("No feasible cover: the supplied finite premises or computation are inconsistent.");
  const prefix=Array(M+1),marginals=Array(M).fill(0n);
  prefix[0]=Array(states).fill(0n);prefix[0][full]=1n;
  for(let i=0;i<M;i++){
    const next=Array(states).fill(0n),transition=candidateMaps[i];
    for(let state=0;state<states;state++){
      const ways=prefix[i][state];if(ways===0n)continue;
      w.forward_states++;
      const best=suffix[i].cost[state],rem=transition[state];
      if(suffix[i+1].cost[state]===best){next[state]+=ways;w.forward_edges++;}
      if(suffix[i+1].cost[rem]!==INF&&suffix[i+1].cost[rem]+1===best){
        next[rem]+=ways;marginals[i]+=ways*suffix[i+1].counts[rem];
        w.forward_edges++;w.marginal_products++;
      }
    }
    prefix[i+1]=next;
  }
  if(prefix[M][0]!==total||prefix[M].some((v,i)=>i!==0&&v!==0n))fail("Forward/backward family totals disagree.");
  const incidenceTotal=marginals.reduce((a,b)=>a+b,0n);
  if(incidenceTotal!==BigInt(minimum)*total)fail("Participation count does not match minimum cardinality.");
  w.dp_constructions++;
  const suffixRows=suffix.map(row=>{w.suffix_cells_encoded+=states;return encodePairs(row.cost,row.counts);});
  const prefixRows=prefix.map(row=>{w.prefix_cells_encoded+=states;return encodeCounts(row);});
  const snapshot={
    schema:SCHEMA,values:A,offset:x.toString(),interval_length:M,
    target_product:P.toString(),period:P.toString(),
    basis:{limit:M,primes,least_factor_by_integer:lp,provenance},
    factorizations,requirements,axes,states,full_deficit_state:full,
    candidates,
    tables:{encoding:"rle_uleb128_base64_v1",unreachable_cost:INF,
      pair_run:"positive run length; one cost byte; unsigned count",
      count_run:"positive run length; unsigned count",
      rows:M+1,states,suffix_rows:suffixRows,prefix_rows:prefixRows},
    optimum:{minimum_cardinality:minimum,count:total.toString(),
      participation:marginals.map(String),
      forced_offsets:marginals.flatMap((v,i)=>v===total?[i+1]:[]),
      possible_offsets:marginals.flatMap((v,i)=>v>0n?[i+1]:[]),
      cardinality_incidence_total:incidenceTotal.toString()},
    construction_work:w
  };
  if(JSON.stringify(snapshot).length>PRODUCT_COVER_LIMITS.max_snapshot_characters)fail("Complete snapshot exceeds the encoded size cap.");
  return snapshot;
}
function openRetainedIntervalProductCover(retained){
  const text=typeof retained==="string"?retained:JSON.stringify(retained);
  if(typeof text!=="string"||text.length>8000000)fail("Snapshot is absent or exceeds its size cap.");
  const s=JSON.parse(text);if(s.schema!==SCHEMA)fail("Unknown product-cover snapshot.");
  const A=canonicalValues(s.values),M=A[A.length-1],sourceX=offset(s.offset),P=integer(s.target_product,"target_product",128);
  if(P<2n||s.period!==P.toString()||s.interval_length!==M||JSON.stringify(A)!==JSON.stringify(s.values))
    fail("Target/period/set convention mismatch.");
  const {axes,states}=axesFromRequirements(s.requirements),full=states-1,w=workRecord();
  if(s.states!==states||s.full_deficit_state!==full||JSON.stringify(axes)!==JSON.stringify(s.axes))fail("Deficit-axis mismatch.");
  if(!Array.isArray(s.candidates)||s.candidates.length!==M)fail("Incomplete candidate list.");
  const candidates=s.candidates.map((c,i)=>{
    if(!c||c.offset!==i+1||c.origin_value!==(sourceX+BigInt(i+1)).toString()||
      !Array.isArray(c.capped_exponents)||c.capped_exponents.length!==axes.length)fail("Candidate identity mismatch.");
    const v=c.capped_exponents.map((x,j)=>small(x,0,axes[j].exponent,"capped exponent"));
    return {...c,capped_exponents:v};
  });
  const t=s.tables;
  if(!t||t.encoding!=="rle_uleb128_base64_v1"||t.unreachable_cost!==INF||t.rows!==M+1||t.states!==states||
    !Array.isArray(t.suffix_rows)||t.suffix_rows.length!==M+1||
    !Array.isArray(t.prefix_rows)||t.prefix_rows.length!==M+1)fail("Incomplete table encoding.");
  const suffix=t.suffix_rows.map(row=>decodePairs(row,states,M,w));
  const prefix=t.prefix_rows.map(row=>decodeCounts(row,states,M,w));
  for(let i=0;i<=M;i++)if(suffix[i].cost[0]!==0||suffix[i].counts[0]!==1n)fail("Zero deficit must have the unique empty continuation.");
  for(let state=1;state<states;state++)if(suffix[M].cost[state]!==INF||suffix[M].counts[state]!==0n)fail("Terminal deficit row mismatch.");
  const minimum=suffix[0].cost[full],total=suffix[0].counts[full],o=s.optimum;
  if(minimum===INF||minimum<1||!o||o.minimum_cardinality!==minimum||o.count!==total.toString()||
    !Array.isArray(o.participation)||o.participation.length!==M)fail("Optimum summary mismatch.");
  const marginal=o.participation.map((x,i)=>{
    const v=integer(x,"participation "+i,32);if(v<0n||v>total)fail("Participation count is outside family total.");return v;
  });
  if(prefix[0][full]!==1n||prefix[0].some((x,i)=>i!==full&&x!==0n)||
    prefix[M][0]!==total||prefix[M].some((x,i)=>i!==0&&x!==0n))fail("Forward boundary mismatch.");
  const forced=marginal.flatMap((v,i)=>v===total?[i+1]:[]),possible=marginal.flatMap((v,i)=>v>0n?[i+1]:[]);
  const incidence=marginal.reduce((a,b)=>a+b,0n);
  if(incidence!==BigInt(minimum)*total||incidence.toString()!==o.cardinality_incidence_total||
    JSON.stringify(forced)!==JSON.stringify(o.forced_offsets)||JSON.stringify(possible)!==JSON.stringify(o.possible_offsets))
    fail("Participation summary mismatch.");
  function branch(i,state){
    const best=suffix[i].cost[state],rem=afterState(state,candidates[i].capped_exponents,axes,w);
    const skip=suffix[i+1].cost[state]===best;
    const take=suffix[i+1].cost[rem]!==INF&&suffix[i+1].cost[rem]+1===best;
    const skipCount=skip?suffix[i+1].counts[state]:0n,takeCount=take?suffix[i+1].counts[rem]:0n;
    if(skipCount+takeCount!==suffix[i].counts[state])fail("Selected path recurrence disagrees with retained counts.");
    w.local_branch_checks++;return {rem,skip,take,skipCount,takeCount};
  }
  function rankValue(v,label="rank"){
    const z=integer(v,label,32);if(z<0n||z>=total)fail(label+" is outside the minimum family.");return z;
  }
  function selectOffsets(rawRank){
    let rank=rankValue(rawRank),state=full;const selected=[];w.select_calls++;
    for(let i=0;i<M;i++){
      const b=branch(i,state);
      if(b.take&&rank<b.takeCount){selected.push(i+1);state=b.rem;}
      else{rank-=b.takeCount;if(!b.skip||rank>=b.skipCount)fail("No branch contains the selected rank.");}
    }
    if(state!==0||selected.length!==minimum||rank!==0n)fail("Selected path does not end at the minimum cover.");
    return selected;
  }
  function witness(offsets,viewX){
    const values=offsets.map(i=>viewX+BigInt(i));let product=1n;
    const coverage=Array(axes.length).fill(0);
    for(let j=0;j<offsets.length;j++){
      product=boundedProduct(product*values[j]);w.witness_product_terms++;
      for(let k=0;k<axes.length;k++)coverage[k]+=candidates[offsets[j]-1].capped_exponents[k];
    }
    if(coverage.some((v,j)=>v<axes[j].exponent)||product%P!==0n)fail("Selected witness does not cover the target.");
    w.witnesses++;
    return {offsets,values:values.map(String),cardinality:offsets.length,
      target_product:P.toString(),selected_product:product.toString(),quotient:(product/P).toString(),
      prime_coverage:axes.map((a,j)=>({prime:a.prime,required:a.exponent,capped_sum:coverage[j]})),
      valuation_basis:viewX===sourceX?"retained candidate valuations":"product-period translation of retained capped valuations",
      offset:viewX.toString(),period:P.toString(),period_multiplier:((viewX-sourceX)/P).toString()};
  }
  function normalizedOffsets(rawValues,viewX){
    if(!Array.isArray(rawValues)||rawValues.length>256)fail("A subset query has at most 256 records.");
    const values=[...new Set(rawValues.map(v=>integer(v,"subset value",81).toString()))].map(BigInt).sort((a,b)=>a<b?-1:a>b?1:0);
    return values.map(v=>{const o=v-viewX;if(o<1n||o>BigInt(M))fail("A subset value is outside this view.");return Number(o);});
  }
  function at(viewX){
    if((viewX-sourceX)%P!==0n)fail("A saved view must be congruent to the source offset modulo the target product.");
    return Object.freeze({
      summary(){return {schema:SCHEMA,values:A.slice(),offset:viewX.toString(),source_offset:sourceX.toString(),
        interval_start:(viewX+1n).toString(),interval_end:(viewX+BigInt(M)).toString(),interval_length:M,
        target_product:P.toString(),period:P.toString(),period_multiplier:((viewX-sourceX)/P).toString(),
        deficit_states:states,minimum_cardinality:minimum,count:total.toString(),
        forced_offsets:forced.slice(),possible_offsets:possible.slice(),
        scope:"minimum covers of this interval and its product-period translates",
        loader_assurance:"structural and selected-path checks; premise and full DP authentication are external",
        construction_work:copy(s.construction_work)};},
      count(){return total.toString();},
      select(rank=0){const r=rankValue(rank);return {rank:r.toString(),...witness(selectOffsets(r),viewX)};},
      rank(rawValues){
        const selected=normalizedOffsets(rawValues,viewX);
        if(selected.length!==minimum)fail("The normalized subset does not have minimum cardinality.");
        const set=new Set(selected);let state=full,rank=0n;w.rank_calls++;
        for(let i=0;i<M;i++){
          const b=branch(i,state);
          if(set.has(i+1)){if(!b.take)fail("The subset is not an optimal path.");state=b.rem;}
          else{if(!b.skip)fail("The subset is not an optimal path.");rank+=b.takeCount;}
        }
        if(state!==0||rank>=total)fail("The subset does not end at a valid family rank.");
        return {rank:rank.toString(),offsets:selected,values:selected.map(i=>(viewX+BigInt(i)).toString())};
      },
      page(start=0,count=16){
        const rank=integer(start,"page start",32);
        if(rank<0n||rank>total)fail("Page start is outside the family.");
        const limit=small(count,0,64,"page size"),rows=[];
        for(let j=0;j<limit&&rank+BigInt(j)<total;j++){
          const r=rank+BigInt(j);rows.push({rank:r.toString(),...witness(selectOffsets(r),viewX)});
        }
        const next=rank+BigInt(rows.length);
        return {start:rank.toString(),count:rows.length,total:total.toString(),rows,next_start:next<total?next.toString():null};
      },
      participationPage(start=0,count=64){
        const a=small(start,0,M,"participation start"),limit=small(count,0,64,"participation page size"),end=Math.min(M,a+limit);
        const rows=[];
        for(let i=a;i<end;i++){w.participation_rows++;rows.push({offset:i+1,value:(viewX+BigInt(i+1)).toString(),
          count:marginal[i].toString(),family_count:total.toString(),forced:marginal[i]===total,possible:marginal[i]>0n,
          capped_exponents:candidates[i].capped_exponents.slice()});}
        return {start:a,end,total:M,rows,next_start:end<M?end:null};
      },
      candidate(candidateOffset){
        const i=small(candidateOffset,1,M,"candidate offset")-1;
        return {offset:i+1,value:(viewX+BigInt(i+1)).toString(),source_offset:sourceX.toString(),
          origin_witness:copy(candidates[i]),period_multiplier:((viewX-sourceX)/P).toString()};
      },
      budget(h){
        const bound=integer(h,"cardinality budget",80);if(bound<0n)fail("Budget must be nonnegative.");
        return {budget:bound.toString(),minimum,interval_length:M,at_most_possible:BigInt(minimum)<=bound,
          exact_size_possible:BigInt(minimum)<=bound&&bound<=BigInt(M),
          minimum_family_count:total.toString(),counts_for_other_cardinalities:"not supplied"};
      },
      padToSize(h,rank=0){
        const size=small(h,minimum,M,"padded cardinality"),r=rankValue(rank),chosen=selectOffsets(r),set=new Set(chosen),added=[];
        for(let i=1;set.size<size;i++)if(!set.has(i)){set.add(i);added.push(i);}
        const all=[...set].sort((a,b)=>a-b);
        return {minimum_rank:r.toString(),minimum_offsets:chosen,added_offsets:added,
          padding_rule:"append the smallest unused offsets; no enumeration of all feasible subsets at this larger size",
          witness:witness(all,viewX)};
      },
      state(stage,deficits){
        const i=small(stage,0,M,"suffix stage");
        if(!Array.isArray(deficits)||deficits.length!==axes.length)fail("Wrong deficit dimension.");
        let code=0;const normalized=[];
        for(let j=0;j<axes.length;j++){
          const d=small(deficits[j],0,axes[j].exponent,"deficit");normalized.push(d);code+=d*axes[j].stride;
        }
        return {stage:i,state:code,deficits:normalized,cost:suffix[i].cost[code]===INF?null:suffix[i].cost[code],
          count:suffix[i].counts[code].toString(),optimal_prefix_count:prefix[i][code].toString()};
      },
      viewAtOffset(newOffset){w.period_views++;return at(offset(newOffset));},
      snapshot(){return copy(s);},
      work(){return copy(w);}
    });
  }
  return at(sourceX);
}
module.exports={compileIntervalProductCover,openRetainedIntervalProductCover,PRODUCT_COVER_LIMITS};
