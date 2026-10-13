"use strict";

/*
 * Exact representation navigation for the classical Raikov-Stohr binary-position
 * basis A=A0 union 2A0, where A0 has only base-4 digits 0 and 1.
 * The formal convolution counts ordered pairs, with zero and repetitions.
 * See DIGITAL_BASIS_API.md for attribution, disjointness and finite scope.
 */
const DIGITAL_BASIS_LIMITS=Object.freeze({
  max_target_bits:2048,max_base4_digits:1024,max_decimal_digits:650,
  max_digit_records:2048,max_provenance_chars:32768,
  max_snapshot_chars:250000,max_page_rows:128
});
const SCHEMA="commons.raikov_stohr_target/v1";
const COMPLETE="EXACT_REPRESENTATION_INDEX";
function bad(s){throw new RangeError(s);}
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)bad(name+" is out of range");return x;}
function object(x,name){if(!x||typeof x!=="object"||Array.isArray(x))bad(name+" must be an object");return x;}
function array(x,name,n){if(!Array.isArray(x)||(n!==undefined&&x.length!==n))bad(name+" has invalid array shape");return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function decimal(x,name){
  if(typeof x!=="string"||x.length>DIGITAL_BASIS_LIMITS.max_decimal_digits||!/^(0|[1-9][0-9]*)$/.test(x))bad(name+" must be a bounded canonical decimal string");
  return BigInt(x);
}
function natural(x,name){
  let n;
  if(typeof x==="bigint")n=x;
  else if(typeof x==="number"){if(!Number.isSafeInteger(x))bad(name+" Number must be safe");n=BigInt(x);}
  else n=decimal(x,name);
  if(n<0n||n.toString(2).length>DIGITAL_BASIS_LIMITS.max_target_bits)bad(name+" exceeds the natural-number contract");
  return n;
}
function pow2(k){return 1n<<BigInt(k);}
function detached(x,name,cap){
  const s=typeof x==="string"?x:JSON.stringify(object(x,name));
  if(s.length>cap)bad(name+" exceeds its character cap");
  return object(JSON.parse(s),name);
}
function budget(x,name,cap){return x===undefined?cap:integer(x,name,0,cap);}
function same(a,b){
  if(a===b)return true;
  if(!a||!b||typeof a!=="object"||typeof b!=="object")return false;
  if(Array.isArray(a)||Array.isArray(b))return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>same(v,b[i]));
  const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
  return ak.length===bk.length&&ak.every((k,i)=>k===bk[i]&&same(a[k],b[k]));
}
function base4Input(word,work){
  if(typeof word!=="string"||word.length>DIGITAL_BASIS_LIMITS.max_base4_digits||!/^(0|[1-3][0-3]*)$/.test(word))bad("target_base4 must be canonical and bounded");
  let n=0n;
  for(const ch of word){n=4n*n+BigInt(ch);work.input_base4_digits++;}
  return n;
}
function digitDescriptor(n,component,work){
  if(component===1&&(n&1n)!==0n)return {component,applicable:false,reason:"odd_target",reduced_target:null,digits_lsf:[],
    admissible:false,fixed_first:null,free_mask:null,free_positions:[],ordered_count:"0"};
  const reduced=n>>BigInt(component),digits=[],positions=[];
  let x=reduced,fixed=0n,free=0n,ok=true,i=0;
  do{
    const digit=Number(x&3n),bit=2*i+component;
    digits.push({index:i,digit,first_coordinate_bit:bit});
    if(digit===1){positions.push(bit);free|=pow2(bit);}
    else if(digit===2)fixed|=pow2(bit);
    else if(digit===3)ok=false;
    x>>=2n;i++;work.digit_records++;
  }while(x!==0n);
  return {component,applicable:true,reduced_target:reduced.toString(),digits_lsf:digits,
    admissible:ok,fixed_first:fixed.toString(),free_mask:free.toString(),
    free_positions:positions,ordered_count:ok?pow2(positions.length).toString():"0"};
}
function cube(id,kind,component,fixed,positions,omitted){
  let mask=0n;for(const bit of positions)mask|=pow2(bit);
  return {id,kind,component,fixed_first:fixed.toString(),free_mask:mask.toString(),
    free_positions:positions.slice(),cardinality:pow2(positions.length).toString(),
    omitted_highest_free_position:omitted};
}
function compileDigitalBasisTarget(input){
  object(input,"input");
  const work={input_base4_digits:0,digit_records:0,binary_split_digits:0,ordered_cubes:0,unordered_cubes:0,
    represented_pairs_enumerated:0,basis_elements_enumerated:0,integer_target_sweep:0};
  const hasDecimal=input.target!==undefined,hasBase4=input.target_base4!==undefined;
  if(hasDecimal===hasBase4)bad("supply exactly one of target and target_base4");
  const n=hasBase4?base4Input(input.target_base4,work):natural(input.target,"target");
  const bits=n.toString(2).length;
  if(bits>DIGITAL_BASIS_LIMITS.max_target_bits)bad("target exceeds its bit cap");
  const provenance=detached(input.provenance,"provenance",DIGITAL_BASIS_LIMITS.max_provenance_chars);
  const neededDigits=Math.ceil(bits/2)+((n&1n)===0n?Math.ceil(Math.max(1,bits-1)/2):0);
  const allowedBits=budget(input.max_bits,"max_bits",DIGITAL_BASIS_LIMITS.max_target_bits);
  const allowedDigits=budget(input.max_digit_records,"max_digit_records",DIGITAL_BASIS_LIMITS.max_digit_records);
  if(bits>allowedBits||neededDigits>allowedDigits)return {schema:SCHEMA,status:"INCOMPLETE_BUDGET",snapshot:null,work,
    stop:{stage:"before_digit_classification",required_bits:bits,allowed_bits:allowedBits,required_digit_records:neededDigits,allowed_digit_records:allowedDigits}};
  const descriptors=[digitDescriptor(n,0,work),digitDescriptor(n,1,work)];
  let even=0n,odd=0n;
  for(const r of descriptors[0].digits_lsf){
    if(r.digit&1)even|=pow2(2*r.index);
    if(r.digit&2)odd|=pow2(2*r.index+1);
    work.binary_split_digits++;
  }
  const member0=odd===0n,member1=even===0n,ordered=[],unordered=[];
  if(n===0n){
    ordered.push(cube("zero","zero",null,0n,[],null));
    unordered.push(cube("zero","zero",null,0n,[],null));
  }else{
    for(const d of descriptors)if(d.applicable&&d.admissible){
      const id=d.component===0?"A0+A0":"A1+A1",fixed=BigInt(d.fixed_first),pos=d.free_positions;
      ordered.push(cube(id,"homogeneous",d.component,fixed,pos,null));
      unordered.push(cube(id,"homogeneous",d.component,fixed,pos.length?pos.slice(0,-1):pos,pos.length?pos[pos.length-1]:null));
    }
    if(even!==0n&&odd!==0n){
      ordered.push(cube("A0+A1","mixed",null,even,[],null));
      ordered.push(cube("A1+A0","mixed",null,odd,[],null));
      unordered.push(cube("mixed","mixed",null,even<odd?even:odd,[],null));
    }
  }
  work.ordered_cubes=ordered.length;work.unordered_cubes=unordered.length;
  const count=rows=>rows.reduce((s,r)=>s+BigInt(r.cardinality),0n);
  const orderedCount=count(ordered),unorderedCount=count(unordered);
  const diagonal=ordered.filter(r=>r.kind!=="mixed"&&r.free_positions.length===0).length;
  const formula=BigInt(descriptors[0].ordered_count)+BigInt(descriptors[1].ordered_count)+2n-
    (member0?2n:0n)-(member1?2n:0n)+(n===0n?1n:0n);
  if(orderedCount!==formula||orderedCount!==2n*unorderedCount-BigInt(diagonal))throw new Error("representation accounting mismatch");
  const snapshot={schema:SCHEMA,status:COMPLETE,target:n.toString(),bit_length:bits,
    basis:{definition:"A0 has base4 digits 0/1; A1=2*A0; A=A0 union A1",includes_zero:true,repeated_summands:true,
      ordered:"all (a,b) in A^2 with a+b=target",unordered:"a<=b, with repetitions retained",
      rank_order:"increasing first coordinate"},
    input_encoding:hasBase4?{kind:"base4",word:input.target_base4}:{kind:"natural",value:n.toString()},
    descriptors,split:{even_position_part:even.toString(),odd_position_part:odd.toString(),
      target_in_A0:member0,target_in_A1:member1,mixed_pairs_retained:even!==0n&&odd!==0n},
    families:{ordered,unordered},
    summary:{target:n.toString(),bit_length:bits,ordered_count:orderedCount.toString(),unordered_count:unorderedCount.toString(),
      diagonal_count:diagonal,ordered_cube_count:ordered.length,unordered_cube_count:unordered.length,
      ordered_formula_count:formula.toString(),basis_representation_exists:orderedCount>0n,
      scope:"exact fixed-target representations of the specified infinite classical basis"},
    provenance,work,limits:copy(DIGITAL_BASIS_LIMITS)};
  const chars=JSON.stringify(snapshot).length;
  if(chars>DIGITAL_BASIS_LIMITS.max_snapshot_chars)return {schema:SCHEMA,status:"INCOMPLETE_BUDGET",snapshot:null,work,
    stop:{stage:"snapshot",actual_chars:chars,allowed_chars:DIGITAL_BASIS_LIMITS.max_snapshot_chars}};
  return {schema:SCHEMA,status:COMPLETE,snapshot,summary:copy(snapshot.summary),work:copy(work),snapshot_chars:chars};
}
function openRetainedDigitalBasisTarget(value){
  const s=detached(value,"snapshot",DIGITAL_BASIS_LIMITS.max_snapshot_chars);
  if(s.schema!==SCHEMA||s.status!==COMPLETE)bad("a complete digital-basis target snapshot is required");
  const n=decimal(s.target,"target"),bits=integer(s.bit_length,"bit_length",1,DIGITAL_BASIS_LIMITS.max_target_bits);
  if(n.toString(2).length!==bits)bad("inconsistent target bit length");
  const expectedBasis={definition:"A0 has base4 digits 0/1; A1=2*A0; A=A0 union A1",includes_zero:true,repeated_summands:true,
    ordered:"all (a,b) in A^2 with a+b=target",unordered:"a<=b, with repetitions retained",
    rank_order:"increasing first coordinate"};
  if(!same(s.basis,expectedBasis))bad("unsupported saved basis convention");
  detached(s.provenance,"provenance",DIGITAL_BASIS_LIMITS.max_provenance_chars);
  const stats={saved_digit_checks:0,saved_descriptor_checks:0,saved_split_digit_checks:0,saved_cube_checks:0,
    saved_cube_disjointness_checks:0,saved_count_identity_checks:0,indexed_bit_rows:0,indexed_power_entries:0,
    queries:0,summary_queries:0,digit_queries:0,family_queries:0,count_queries:0,select_queries:0,rank_queries:0,
    interval_queries:0,pair_queries:0,page_queries:0,page_rows_returned:0,selection_bit_steps:0,rank_bit_steps:0,
    prefix_count_bit_steps:0,compiler_calls:0,digit_descriptor_constructions:0,cube_family_constructions:0,
    represented_pairs_enumerated:0,basis_elements_enumerated:0,integer_target_sweep:0};
  const desc=array(s.descriptors,"descriptors",2);
  for(let c=0;c<2;c++){
    const d=object(desc[c],"descriptor");
    if(d.component!==c)bad("descriptor component mismatch");
    if(c===1&&(n&1n)!==0n){
      const expected={component:1,applicable:false,reason:"odd_target",reduced_target:null,digits_lsf:[],
        admissible:false,fixed_first:null,free_mask:null,free_positions:[],ordered_count:"0"};
      if(!same(d,expected))bad("invalid odd-target descriptor");stats.saved_descriptor_checks++;continue;
    }
    const reduced=n>>BigInt(c),rows=array(d.digits_lsf,"digits");
    if(d.applicable!==true||decimal(d.reduced_target,"reduced_target")!==reduced||
      rows.length!==Math.ceil(reduced.toString(2).length/2))bad("incomplete saved digits");
    let fixed=0n,free=0n,ok=true;
    const positions=[];
    for(let i=0;i<rows.length;i++){
      const r=object(rows[i],"digit row"),digit=Number((reduced>>BigInt(2*i))&3n),bit=2*i+c;
      if(r.index!==i||r.digit!==digit||r.first_coordinate_bit!==bit)bad("saved digit mismatch");
      if(digit===1){positions.push(bit);free|=pow2(bit);}
      else if(digit===2)fixed|=pow2(bit);
      else if(digit===3)ok=false;
      stats.saved_digit_checks++;
    }
    if(d.admissible!==ok||decimal(d.fixed_first,"fixed_first")!==fixed||decimal(d.free_mask,"free_mask")!==free||
      !same(d.free_positions,positions)||decimal(d.ordered_count,"component count")!==(ok?pow2(positions.length):0n))bad("saved descriptor mismatch");
    stats.saved_descriptor_checks++;
  }
  let even=0n,odd=0n;
  for(const r of desc[0].digits_lsf){
    if(r.digit&1)even|=pow2(2*r.index);
    if(r.digit&2)odd|=pow2(2*r.index+1);
    stats.saved_split_digit_checks++;
  }
  const split=object(s.split,"split"),member0=odd===0n,member1=even===0n,mixed=even!==0n&&odd!==0n;
  if(decimal(split.even_position_part,"even part")!==even||decimal(split.odd_position_part,"odd part")!==odd||
    split.target_in_A0!==member0||split.target_in_A1!==member1||split.mixed_pairs_retained!==mixed||even+odd!==n)bad("saved binary split mismatch");
  const families=object(s.families,"families"),indexes={},totals={};
  let maxFree=0;
  for(const mode of ["ordered","unordered"]){
    const rows=array(families[mode],"cube family"),ids=[];
    if(n===0n)ids.push("zero");
    else{
      for(const d of desc)if(d.applicable&&d.admissible)ids.push(d.component===0?"A0+A0":"A1+A1");
      if(mixed)ids.push(...(mode==="ordered"?["A0+A1","A1+A0"]:["mixed"]));
    }
    if(rows.length!==ids.length)bad("incomplete cube family");
    const idx=[];let total=0n;
    for(let j=0;j<rows.length;j++){
      const r=object(rows[j],"cube"),id=ids[j];
      if(r.id!==id)bad("cube order or identity mismatch");
      let fixed,positions,omitted=null,component=null,kind;
      if(id==="zero"){fixed=0n;positions=[];kind="zero";}
      else if(id==="A0+A0"||id==="A1+A1"){
        component=id==="A0+A0"?0:1;kind="homogeneous";
        const d=desc[component];fixed=BigInt(d.fixed_first);positions=d.free_positions;
        if(mode==="unordered"&&positions.length){omitted=positions[positions.length-1];positions=positions.slice(0,-1);}
      }else{
        kind="mixed";positions=[];
        fixed=id==="A0+A1"?even:id==="A1+A0"?odd:(even<odd?even:odd);
      }
      let free=0n;for(const b of positions)free|=pow2(b);
      const card=pow2(positions.length);
      if(r.kind!==kind||r.component!==component||decimal(r.fixed_first,"cube fixed")!==fixed||
        decimal(r.free_mask,"cube free")!==free||!same(r.free_positions,positions)||
        decimal(r.cardinality,"cube count")!==card||r.omitted_highest_free_position!==omitted||
        (fixed&free)!==0n||(fixed|free)>n||(mode==="unordered"&&(fixed|free)>n/2n))bad("saved cube mismatch");
      const types=[],below=[];let freeBefore=0;
      for(let b=0;b<bits;b++){
        const mask=pow2(b);below.push(freeBefore);
        if((free&mask)!==0n){types.push(-1);freeBefore++;}
        else types.push((fixed&mask)!==0n?1:0);
        stats.indexed_bit_rows++;
      }
      idx.push({id,fixed,free,card,types,below,record:r});total+=card;
      maxFree=Math.max(maxFree,positions.length);stats.saved_cube_checks++;
    }
    for(let i=0;i<idx.length;i++)for(let j=i+1;j<idx.length;j++){
      if(((idx[i].fixed^idx[j].fixed)&~(idx[i].free|idx[j].free))===0n)bad("cube families overlap");
      stats.saved_cube_disjointness_checks++;
    }
    indexes[mode]=idx;totals[mode]=total;
  }
  const diagonal=families.ordered.filter(r=>r.kind!=="mixed"&&r.free_positions.length===0).length;
  const formula=BigInt(desc[0].ordered_count)+BigInt(desc[1].ordered_count)+2n-(member0?2n:0n)-(member1?2n:0n)+(n===0n?1n:0n);
  const summary=object(s.summary,"summary");
  if(summary.target!==s.target||summary.bit_length!==bits||
    decimal(summary.ordered_count,"ordered count")!==totals.ordered||
    decimal(summary.unordered_count,"unordered count")!==totals.unordered||
    summary.diagonal_count!==diagonal||summary.ordered_cube_count!==families.ordered.length||
    summary.unordered_cube_count!==families.unordered.length||
    decimal(summary.ordered_formula_count,"formula count")!==formula||totals.ordered!==formula||
    totals.ordered!==2n*totals.unordered-BigInt(diagonal)||summary.basis_representation_exists!==true||totals.ordered===0n)bad("saved count identities mismatch");
  stats.saved_count_identity_checks=3;
  const powers=Array.from({length:maxFree+1},(_,i)=>pow2(i));stats.indexed_power_entries=powers.length;
  function modeName(mode){if(mode!=="ordered"&&mode!=="unordered")bad("mode must be ordered or unordered");return mode;}
  function query(kind){stats.queries++;stats[kind]++;}
  function zeroCount(active,bit){let count=0n;for(const f of active)if(f.types[bit]!==1)count+=powers[f.below[bit]];return count;}
  function nextActive(active,bit,value){return active.filter(f=>f.types[bit]===-1||f.types[bit]===value);}
  function selectCore(mode,rank,trace){
    let active=indexes[mode],remaining=rank,first=0n;const steps=[];
    for(let bit=bits-1;bit>=0;bit--){
      const before=remaining,zero=zeroCount(active,bit),value=remaining<zero?0:1;
      if(value){remaining-=zero;first|=pow2(bit);}
      active=nextActive(active,bit,value);stats.selection_bit_steps++;
      if(trace)steps.push({bit,rank_before:before.toString(),zero_count:zero.toString(),chosen:value,
        rank_after:remaining.toString(),active_families:active.map(f=>f.id)});
    }
    if(active.length!==1||remaining!==0n)throw new Error("saved selection invariant failed");
    return {mode,rank:rank.toString(),first:first.toString(),second:(n-first).toString(),family:active[0].id,...(trace?{steps}:{})};
  }
  function rankCore(mode,first){
    let active=indexes[mode],rank=0n;
    for(let bit=bits-1;bit>=0;bit--){
      const value=Number((first>>BigInt(bit))&1n);
      if(value)rank+=zeroCount(active,bit);
      active=nextActive(active,bit,value);stats.rank_bit_steps++;
      if(active.length===0)return null;
    }
    if(active.length!==1)throw new Error("saved rank invariant failed");
    return {mode,rank:rank.toString(),first:first.toString(),second:(n-first).toString(),family:active[0].id};
  }
  function atMostCore(mode,limit){
    if(limit<0n)return 0n;
    if(limit>=n)return totals[mode];
    let active=indexes[mode],count=0n;
    for(let bit=bits-1;bit>=0;bit--){
      const value=Number((limit>>BigInt(bit))&1n);
      if(value)count+=zeroCount(active,bit);
      active=nextActive(active,bit,value);stats.prefix_count_bit_steps++;
      if(active.length===0)return count;
    }
    return count+BigInt(active.length);
  }
  function pageBounds(options,total){
    if(options===undefined)options={};object(options,"page options");
    const start=options.start===undefined?0n:natural(options.start,"page start");
    if(start>total)bad("page start exceeds its family");
    const limit=options.limit===undefined?DIGITAL_BASIS_LIMITS.max_page_rows:integer(options.limit,"page limit",1,DIGITAL_BASIS_LIMITS.max_page_rows);
    return {start,stop:start+BigInt(limit)<total?start+BigInt(limit):total,total};
  }
  function pageRecords(options,total,select){
    const p=pageBounds(options,total),records=[];
    for(let r=p.start;r<p.stop;r++)records.push(select(r));
    stats.page_queries++;stats.page_rows_returned+=records.length;
    return {start:p.start.toString(),count:records.length,total:total.toString(),next_start:p.stop<total?p.stop.toString():null,records};
  }
  const api={
    summary(){query("summary_queries");return copy(summary);},
    source(){query("summary_queries");return copy(s.provenance);},
    count(mode){query("count_queries");return totals[modeName(mode)].toString();},
    digitPage(component,options){query("digit_queries");integer(component,"component",0,1);const d=desc[component];
      return {component,applicable:d.applicable,...pageRecords(options,BigInt(d.digits_lsf.length),r=>copy(d.digits_lsf[Number(r)]))};},
    familyPage(mode,options){query("family_queries");modeName(mode);return {mode,...pageRecords(options,BigInt(families[mode].length),r=>copy(families[mode][Number(r)]))};},
    select(mode,rank,options={}){
      query("select_queries");modeName(mode);object(options,"selection options");
      if(Object.keys(options).some(k=>k!=="trace")||(options.trace!==undefined&&typeof options.trace!=="boolean"))bad("only boolean trace is a selection option");
      rank=natural(rank,"rank");if(rank>=totals[mode])bad("rank exceeds its family");
      return selectCore(mode,rank,options.trace===true);
    },
    rank(mode,first){
      query("rank_queries");modeName(mode);first=natural(first,"first coordinate");
      if(first>n)bad("first coordinate exceeds the target");
      const r=rankCore(mode,first);if(!r)bad("first coordinate is not represented in this mode");return r;
    },
    locatePair(mode,first,second){
      query("pair_queries");modeName(mode);first=natural(first,"first");second=natural(second,"second");
      if(first+second!==n)return {mode,represented:false,reason:"wrong_sum"};
      if(mode==="unordered"&&first>second)return {mode,represented:false,reason:"noncanonical_order"};
      const r=rankCore(mode,first);return r?{represented:true,...r}:{mode,represented:false,reason:"outside_basis"};
    },
    countAtMost(mode,first){query("interval_queries");modeName(mode);first=natural(first,"upper first coordinate");
      return {mode,upper_first:first.toString(),count:atMostCore(mode,first).toString()};},
    countInterval(mode,lower,upper){
      query("interval_queries");modeName(mode);lower=natural(lower,"lower");upper=natural(upper,"upper");if(lower>upper)bad("interval bounds are reversed");
      return {mode,lower_first:lower.toString(),upper_first:upper.toString(),count:(atMostCore(mode,upper)-atMostCore(mode,lower-1n)).toString()};
    },
    page(mode,options){query("select_queries");modeName(mode);return {mode,...pageRecords(options,totals[mode],r=>selectCore(mode,r,false))};},
    snapshot(){return copy(s);},statistics(){return copy(stats);}
  };
  return Object.freeze(api);
}
module.exports={DIGITAL_BASIS_LIMITS,compileDigitalBasisTarget,openRetainedDigitalBasisTarget};
