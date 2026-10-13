"use strict";
const SCHEMA="factorial-shift-prefixes/v1",MAX_CUTOFF=128,MAX_END=48;
const clone=x=>JSON.parse(JSON.stringify(x));
function int(x,a,b,name){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function dec(x,name,signed=false){if(typeof x!=="string"||x.length>100000||!(signed?/^(0|-?[1-9][0-9]*)$/:/^(0|[1-9][0-9]*)$/).test(x))throw new TypeError(name);return BigInt(x);}
function gcd(a,b){while(b){const r=a%b;a=b;b=r;}return a;}
function rat(a,b){if(b<=0n)throw new RangeError("denominator");const g=gcd(a<0n?-a:a,b);return{numerator:String(a/g),denominator:String(b/g)};}
function rp(r){const a=dec(r.numerator,"numerator",true),b=dec(r.denominator,"denominator");if(!b)throw new RangeError("denominator");return[a,b];}
function floorDiv(a,b){let q=a/b;if(a<0n&&a%b)q--;return q;}
function compile(input){
 const M=int(input.cutoff,2,MAX_CUTOFF,"cutoff"),K=int(input.variable_end,2,Math.min(M,MAX_END),"variable_end");
 if(input.limits?.max_cutoff!==MAX_CUTOFF||input.limits?.max_variable_end!==MAX_END)throw new Error("fixed limits");
 if(!Array.isArray(input.factorials)||input.factorials.length!==M+1)throw new Error("factorial input rows");
 const F=[null];for(let i=0;i<input.factorials.length;i++){
  const row=input.factorials[i];if(row.n!==i+1)throw new Error("factorial row index");
  const f=dec(row.value,"factorial value");if(!f)throw new Error("positive factorial premise");F.push(f);
 }
 if(F[1]!==1n)throw new Error("1! premise");
 const work={factorial_recurrence_steps:0,lcm_updates:0,exact_quotient_weights:0,
  baseline_terms:0,suffix_additions:0,margin_rows:0,gap_types:0,enumerated_prefixes:0};
 // The supplied rows are identified factorial premises, not a reverified recurrence.
 const denominators=[2n];for(let n=2;n<=M;n++)denominators.push(F[n]+2n);
 for(let n=2;n<=K;n++)denominators.push(F[n]+1n);
 let D=1n;for(const d of denominators){D=(D/gcd(D,d))*d;work.lcm_updates++;}
 let B=D/2n;work.baseline_terms++;
 for(let n=2;n<=M;n++){B+=D/(F[n]+2n);work.baseline_terms++;}
 const W=[];for(let n=2;n<=K;n++){
  const d=(F[n]+1n)*(F[n]+2n);if(D%d)throw new Error("weight denominator premise");
  W.push(D/d);work.exact_quotient_weights++;
 }
 const m=W.length,suffix=Array(m+1).fill(0n),blocks=[1n];
 for(let i=m-1;i>=0;i--){suffix[i]=W[i]+suffix[i+1];work.suffix_additions++;}
 for(let i=1;i<=m;i++)blocks.push(2n*blocks[i-1]);
 const tail=rat(BigInt(M+2),BigInt(M+1)*F[M+1]),[tn,td]=rp(tail);
 const weights=[];let minMargin=null,disjoint=true;
 for(let i=0;i<m;i++){
  const margin=W[i]-suffix[i+1];if(margin<=0n)throw new Error("superincreasing weight condition");
  if(minMargin===null||margin<minMargin)minMargin=margin;
  const gapNumerator=margin*td-tn*D;
  if(gapNumerator<=0n)disjoint=false;
  weights.push({position:i,n:i+2,numerator:String(W[i]),
   increment_denominator:String((F[i+2]+1n)*(F[i+2]+2n)),
   suffix_after_numerator:String(suffix[i+1]),margin_numerator:String(margin),
   enclosure_gap:rat(gapNumerator,D*td),gap_count:String(blocks[i])});
  work.margin_rows++;work.gap_types++;
 }
 return {schema:SCHEMA,indexing:"n>=1",cutoff:M,variable_end:K,variable_count:m,
  fixed_first_shift:1,fixed_middle_shift:2,tail_alphabet:[1,2],
  factorial_source_rows:clone(input.factorials),common_denominator:String(D),
  baseline_numerator:String(B),weights,suffix_numerators:suffix.map(String),
  block_counts:blocks.map(String),count:String(blocks[m]),tail_upper:tail,
  minimum_margin_numerator:String(minMargin),all_enclosures_disjoint:disjoint,
  lower_prefix:rat(B,D),upper_prefix:rat(B+suffix[0],D),
  provenance:clone(input.provenance),limits:clone(input.limits),work};
}
function openIndex(saved){
 const S=clone(saved);if(S.schema!==SCHEMA||S.indexing!=="n>=1")throw new Error("schema");
 const M=int(S.cutoff,2,MAX_CUTOFF,"cutoff"),K=int(S.variable_end,2,Math.min(M,MAX_END),"end"),m=K-1;
 if(S.variable_count!==m||S.weights.length!==m||S.suffix_numerators.length!==m+1||S.block_counts.length!==m+1)throw new Error("shape");
 const D=dec(S.common_denominator,"D"),B=dec(S.baseline_numerator,"B"),count=dec(S.count,"count");
 if(!D||!count)throw new Error("positive saved scale");
 const W=S.weights.map((w,i)=>{if(w.position!==i||w.n!==i+2)throw new Error("weight index");rp(w.enclosure_gap);return dec(w.numerator,"weight");});
 const suffix=S.suffix_numerators.map(x=>dec(x,"suffix")),blocks=S.block_counts.map(x=>dec(x,"block count"));
 const [tn,td]=rp(S.tail_upper);if(tn<=0n)throw new Error("positive tail");
 // Only encoding/shape is checked. The identified saved inequalities are trusted.
 const work={queries:0,selected_bits:0,selected_weight_additions:0,rank_bits:0,
  count_steps:0,threshold_floor_divisions:0,query_rational_reductions:0,
  radix_powers:0,radix_floor_divisions:0,new_factorial_steps:0,new_lcm_updates:0,
  new_weights:0,new_suffix_sums:0,new_gap_types:0};
 function qr(a,b){work.query_rational_reductions++;return rat(a,b);}
 function rankValue(x,allowEnd=false){const r=dec(x,"rank");if(r>(allowEnd?count:count-1n))throw new RangeError("rank");return r;}
 function select(r,withChoices=true){
  const bits=r.toString(2).padStart(m,"0");let value=B;const choices=[];
  for(let i=0;i<m;i++){work.selected_bits++;const high=bits[i]==="1";if(high){value+=W[i];work.selected_weight_additions++;}
   if(withChoices)choices.push({n:i+2,b:high?1:2});
  }
  return {rank:String(r),bits,choices:withChoices?choices:undefined,
   scaled_prefix_numerator:String(value),common_denominator:S.common_denominator,
   partial:qr(value,D),enclosure:{lower:qr(value,D),upper:qr(value*td+tn*D,D*td)}};
 }
 function selectedChoices(xs){
  if(!Array.isArray(xs)||xs.length!==m)throw new Error("complete shift choices");
  let bits="";for(const x of xs){int(x,1,2,"shift");bits+=x===1?"1":"0";work.rank_bits++;}
  return {rank:BigInt("0b"+bits).toString(),bits};
 }
 function integerCount(t,trace=false){
  let at=0,total=0n;const steps=[];
  while(at<m){
   work.count_steps++;
   if(t<0n){if(trace)steps.push({position:at,decision:"below",target:String(t)});return{count:total,steps};}
   if(t>=suffix[at]){total+=blocks[m-at];if(trace)steps.push({position:at,decision:"whole_suffix",target:String(t),added:S.block_counts[m-at]});return{count:total,steps};}
   if(t>=W[at]){total+=blocks[m-at-1];if(trace)steps.push({position:at,decision:"high",target:String(t),added:S.block_counts[m-at-1]});t-=W[at];}
   else if(trace)steps.push({position:at,decision:"low",target:String(t)});
   at++;
  }
  if(t>=0n)total++;return{count:total,steps};
 }
 function countAt(r,strict=false,trace=false){
  const [a,b]=rp(r),numerator=a*D-B*b-(strict?1n:0n);work.threshold_floor_divisions++;
  const target=floorDiv(numerator,b),z=integerCount(target,trace);
  return {count:String(z.count),strict,threshold:r,target_numerator:String(target),steps:z.steps};
 }
 function window(lower,upper,intersects,trace=false){
  const [a,b]=rp(lower),[c,d]=rp(upper);if(a*d>c*b)throw new RangeError("window order");
  const startThreshold=intersects?qr(a*td-tn*b,b*td):lower;
  const before=countAt(startThreshold,true,trace),through=countAt(upper,false,trace),
    start=BigInt(before.count),end=BigInt(through.count),n=end-start;
  if(n<0n)throw new Error("saved count inconsistency");
  return {mode:intersects?"enclosures_intersect":"prefix_values_inside",lower,upper,
   count:String(n),first_rank:n?String(start):null,last_rank:n?String(end-1n):null,
   before,through,all_enclosures_disjoint:S.all_enclosures_disjoint};
 }
 function query(q){
  if(!q||typeof q!=="object")throw new TypeError("query");work.queries++;let out;
  switch(q.op){
   case "summary":out={cutoff:M,variable_end:K,variable_count:m,count:S.count,indexing:S.indexing,
    lower_prefix:S.lower_prefix,upper_prefix:S.upper_prefix,tail_upper:S.tail_upper,
    all_enclosures_disjoint:S.all_enclosures_disjoint,construction_work:S.work};break;
   case "select":out=select(rankValue(q.rank));break;
   case "rank":out=selectedChoices(q.choices);break;
   case "weight":out=S.weights[int(q.n,2,K,"n")-2];break;
   case "gap_types":out=S.weights.map(w=>({n:w.n,position:w.position,prefix_margin_numerator:w.margin_numerator,
    common_denominator:S.common_denominator,enclosure_gap:w.enclosure_gap,count:w.gap_count}));break;
   case "gap":{
    const r=rankValue(q.rank);if(r+1n>=count)throw new RangeError("last prefix has no following gap");
    const bits=r.toString(2).padStart(m,"0"),position=bits.lastIndexOf("0");
    out={rank:String(r),next_rank:String(r+1n),carry_position:position,
      gap_type:S.weights[position],left:select(r,false),right:select(r+1n,false)};break;
   }
   case "count":{
    out=countAt({numerator:q.numerator,denominator:q.denominator},q.strict===true,q.trace===true);break;
   }
   case "window":out=window(q.lower,q.upper,q.intersects===true,q.trace===true);break;
   case "locate":{
    const x={numerator:q.numerator,denominator:q.denominator},w=window(x,x,true,q.trace===true);
    out={...w,first:w.first_rank===null?null:select(BigInt(w.first_rank)),
      last:w.last_rank===null||w.first_rank===w.last_rank?null:select(BigInt(w.last_rank))};break;
   }
   case "block":{
    if(!Array.isArray(q.choices)||q.choices.length>m)throw new Error("prefix choices");
    let bits="";for(const x of q.choices){int(x,1,2,"shift");bits+=x===1?"1":"0";work.rank_bits++;}
    const prefix=bits?BigInt("0b"+bits):0n,left=prefix*blocks[m-bits.length],right=left+blocks[m-bits.length]-1n;
    const first=select(left),last=select(right);
    out={choices:q.choices,count:String(blocks[m-bits.length]),first_rank:String(left),last_rank:String(right),
      first,last,span:{lower:first.enclosure.lower,upper:last.enclosure.upper},
      span_is_not_a_claim_that_every_point_is_attained:true};break;
   }
   case "page":{
    const offset=rankValue(q.offset,true),limit=int(q.limit??10,0,32,"limit"),rows=[];
    let at=offset;for(let i=0;i<limit&&at<count;i++,at++)rows.push(select(at));
    out={offset:String(offset),count:S.count,next:at<count?String(at):null,rows};break;
   }
   case "digits":{
    const r=rankValue(q.rank),base=int(q.base,2,36,"base"),places=int(q.places,0,256,"places"),selected=select(r,false);
    const [a,b]=rp(selected.enclosure.lower),[c,d]=rp(selected.enclosure.upper),scale=BigInt(base)**BigInt(places);
    work.radix_powers++;const lo=a*scale/b,hi=c*scale/d;work.radix_floor_divisions+=2;
    let prefix=null;if(lo===hi){prefix=lo.toString(base);if(places){prefix=prefix.padStart(places+1,"0");prefix=prefix.slice(0,-places)+"."+prefix.slice(-places);}}
    out={rank:String(r),base,places,status:lo===hi?"certified":"undecided",radix_prefix:prefix,
      lower_scaled_floor:String(lo),upper_scaled_floor:String(hi),scale:String(scale),enclosure:selected.enclosure,
      meaning:"same truncated radix prefix for every allowed tail, when certified"};break;
   }
   default:throw new RangeError("operation");
  }
  return clone(out);
 }
 return {query,work:()=>clone(work)};
}
module.exports={compile,openIndex,SCHEMA};
