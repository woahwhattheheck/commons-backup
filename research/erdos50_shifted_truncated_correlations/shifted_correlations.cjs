"use strict";
function ok(x,m){if(!x)throw new TypeError(m);}
function mask(x,n){ok(Number.isSafeInteger(x)&&x>=0&&x<(1<<n),"invalid support mask");return x;}
function integer(x,signed=false){ok(typeof x==="string"&&(signed?/^(0|-?[1-9][0-9]*)$/:/^(0|[1-9][0-9]*)$/).test(x)&&x.length<=2048,"canonical decimal string required");return BigInt(x);}
function rational(x){ok(Array.isArray(x)&&x.length===2,"rational pair required");const a=integer(x[0]),b=integer(x[1]);ok(b>0n&&a<=b,"rational outside [0,1]");return [a,b];}
function construct(input){
 const primes=input.primes,n=primes.length,Q=BigInt(input.period);ok(n>=1&&n<=10,"unsupported basis");
 const atoms=input.atoms,byMask=new Map();
 ok(atoms.length===(1<<n),"incomplete saved atom table");
 for(let i=0;i<atoms.length;i++){const a=atoms[i];mask(a.mask,n);ok(!byMask.has(a.mask),"duplicate source mask");byMask.set(a.mask,i);}
 const work={savedAtoms:atoms.length,ratioUnitConversions:0,marginalMomentTerms:0,newJointProfiles:0,copiedDiagonalProfiles:0,localBranches:0,jointWeightProducts:0,newJointRows:0,copiedDiagonalRows:0,jointMomentTerms:0,oldAtomReconstructions:0,sieveRuns:0,primeTailCalculations:0,primorialResiduesEnumerated:0};
 const units=atoms.map(a=>{const den=BigInt(a.denominator);ok(Q%den===0n,"saved ratio denominator does not divide period");work.ratioUnitConversions++;return String(BigInt(a.numerator)*(Q/den));});
 let firstMoment=0n;for(let i=0;i<atoms.length;i++){firstMoment+=BigInt(atoms[i].weight)*BigInt(units[i]);work.marginalMomentTerms++;}
 const profiles=[];
 for(let hmask=0;hmask<(1<<n);hmask++){
  const rows=[];
  if(hmask===(1<<n)-1){
   for(let i=0;i<atoms.length;i++)rows.push([i,i,Number(atoms[i].weight)]);
   work.copiedDiagonalProfiles++;work.copiedDiagonalRows+=rows.length;
  }else{
   work.newJointProfiles++;
   function walk(i,L,R,w){
    if(i===n){rows.push([byMask.get(L),byMask.get(R),w]);work.newJointRows++;return;}
    const p=primes[i],bit=1<<i;
    const options=hmask&bit?[[bit,bit,1],[0,0,p-1]]:[[bit,0,1],[0,bit,1],[0,0,p-2]];
    for(const [a,b,f] of options)if(f>0){work.localBranches++;work.jointWeightProducts++;walk(i+1,L|a,R|b,w*f);}
   }
   walk(0,0,0,1);rows.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  }
  let mass=0,moment=0n;
  for(const [L,R,w] of rows){mass+=w;moment+=BigInt(w)*BigInt(units[L])*BigInt(units[R]);work.jointMomentTerms++;}
  ok(BigInt(mass)===Q,"joint CRT mass mismatch");
  profiles.push({lag_mask:hmask,rows,mass,moment_numerator:String(moment),moment_denominator:String(Q*Q*Q),covariance_numerator:String(moment*Q-firstMoment*firstMoment),covariance_denominator:String(Q*Q*Q*Q),provenance:hmask===(1<<n)-1?"copied saved diagonal masses; new moment":"new joint local CRT product"});
 }
 return {schema:"commons.erdos50.shifted_truncated_products/v1",input_id:input.id,primes,period:input.period,atoms,ratio_units:units,first_moment:{numerator:String(firstMoment),denominator:String(Q*Q)},profiles,work,order:"left saved ratio row then right saved ratio row; support identities preserved"};
}
function createReader(c){
 ok(c.schema==="commons.erdos50.shifted_truncated_products/v1","unrecognized certificate");
 const n=c.primes.length,Q=BigInt(c.period),conditions=new Map();
 const work={lagRemainders:0,conditionsBuilt:0,conditionHits:0,jointRowsScanned:0,ratioComparisons:0,conditionalMomentTerms:0,savedFullMoments:0,selectionRows:0,rankRows:0,marginalRows:0,rowMaterializations:0,newJointRows:0,oldAtomReconstructions:0,sieveRuns:0,primeTailCalculations:0};
 function lag(h){const H=integer(h,true);let m=0;for(let i=0;i<n;i++){if(H%BigInt(c.primes[i])===0n)m|=1<<i;work.lagRemainders++;}return m;}
 function normalize(q){
  const h=q.lag===undefined?"1":q.lag,m=lag(h);
  const reqL=mask(q.require_left||0,n),excL=mask(q.exclude_left||0,n),reqR=mask(q.require_right||0,n),excR=mask(q.exclude_right||0,n);
  const left=q.left||{},right=q.right||{};
  function bounds(b){const lo=b.lower||["0","1"],hi=b.upper||["1","1"];rational(lo);rational(hi);return {lower:lo,upper:hi,lower_closed:b.lower_closed!==false,upper_closed:b.upper_closed!==false};}
  return {lag:h,lag_mask:m,require_left:reqL,exclude_left:excL,require_right:reqR,exclude_right:excR,left:bounds(left),right:bounds(right)};
 }
 function inBounds(atom,b){
  const v=BigInt(atom.numerator),d=BigInt(atom.denominator),lo=rational(b.lower),hi=rational(b.upper);
  const lc=v*lo[1]-lo[0]*d,hc=v*hi[1]-hi[0]*d;work.ratioComparisons+=2;
  return (b.lower_closed?lc>=0n:lc>0n)&&(b.upper_closed?hc<=0n:hc<0n);
 }
 function build(q){
  const a=normalize(q),key=JSON.stringify({...a,lag:undefined});
  if(conditions.has(key)){work.conditionHits++;return {a,state:conditions.get(key)};}
  work.conditionsBuilt++;const p=c.profiles[a.lag_mask],indices=[],cumulative=[];
  let mass=0,moment=0n;
  const contradiction=(a.require_left&a.exclude_left)||(a.require_right&a.exclude_right);
  const allBounds=b=>b.lower[0]==="0"&&b.upper[0]===b.upper[1]&&b.lower_closed&&b.upper_closed;
  const full=!a.require_left&&!a.exclude_left&&!a.require_right&&!a.exclude_right&&allBounds(a.left)&&allBounds(a.right);
  if(!contradiction)for(let j=0;j<p.rows.length;j++){
   const [L,R,w]=p.rows[j],l=c.atoms[L],r=c.atoms[R];work.jointRowsScanned++;
   if((l.mask&a.require_left)!==a.require_left||(l.mask&a.exclude_left)||(r.mask&a.require_right)!==a.require_right||(r.mask&a.exclude_right))continue;
   if(!full&&(!inBounds(l,a.left)||!inBounds(r,a.right)))continue;
   indices.push(j);mass+=w;cumulative.push(mass);
   if(!full){moment+=BigInt(w)*BigInt(c.ratio_units[L])*BigInt(c.ratio_units[R]);work.conditionalMomentTerms++;}
  }
  if(full){moment=BigInt(p.moment_numerator);work.savedFullMoments++;}
  const state={key,lag_mask:a.lag_mask,condition:{...a,lag:undefined},indices,cumulative,mass,atom_count:indices.length,probability:{numerator:String(mass),denominator:c.period},conditional_product_moment:mass?{numerator:String(moment),denominator:String(BigInt(mass)*Q*Q)}:null,weighted_product_sum:String(moment),empty:mass===0};
  conditions.set(key,state);return {a,state};
 }
 function summary(q={}){const {a,state}=build(q);return {lag:a.lag,...state};}
 function row(state,index){
  const p=c.profiles[state.lag_mask],j=state.indices[index],[L,R,w]=p.rows[j];work.rowMaterializations++;
  return {profile_row:j,atom_rank:index,left_source_row:L,right_source_row:R,left_mask:c.atoms[L].mask,right_mask:c.atoms[R].mask,left_ratio:[c.atoms[L].numerator,c.atoms[L].denominator],right_ratio:[c.atoms[R].numerator,c.atoms[R].denominator],mass:w,weight_start:index?state.cumulative[index-1]:0};
 }
 function select(q){
  const {a,state}=build(q);ok(Number.isSafeInteger(q.rank)&&q.rank>=0,"invalid rank");
  const weighted=q.weighted===true,total=weighted?state.mass:state.atom_count;
  if(q.rank>=total)return {status:"OUT_OF_RANGE",lag:a.lag,total,weighted};
  let i=q.rank,offset=0;
  if(weighted){i=0;while(state.cumulative[i]<=q.rank){i++;work.selectionRows++;}work.selectionRows++;offset=q.rank-(i?state.cumulative[i-1]:0);}
  const out=row(state,i);
  return {status:"FOUND",lag:a.lag,lag_mask:a.lag_mask,total,weighted,rank:q.rank,...out,mass_offset:weighted?offset:null};
 }
 function rank(q){
  const {a,state}=build(q);ok(Number.isSafeInteger(q.profile_row)&&q.profile_row>=0,"invalid profile row");
  let i=0;while(i<state.indices.length&&state.indices[i]!==q.profile_row){i++;work.rankRows++;}
  if(i===state.indices.length)return {status:"NOT_IN_CONDITION",lag:a.lag};
  work.rankRows++;const out=row(state,i),weighted=q.weighted===true,offset=q.mass_offset===undefined?0:q.mass_offset;
  if(weighted)ok(Number.isSafeInteger(offset)&&offset>=0&&offset<out.mass,"mass offset outside fiber");
  return {status:"FOUND",lag:a.lag,weighted,rank:weighted?out.weight_start+offset:i,total:weighted?state.mass:state.atom_count,profile_row:q.profile_row,mass_offset:weighted?offset:null};
 }
 function page(q){
  const {state}=build(q);ok(Number.isSafeInteger(q.start)&&q.start>=0&&Number.isSafeInteger(q.limit)&&q.limit>=0&&q.limit<=10000,"invalid page");
  const rows=[];for(let i=q.start;i<Math.min(state.atom_count,q.start+q.limit);i++)rows.push(row(state,i));
  return {atom_count:state.atom_count,mass:state.mass,start:q.start,returned:rows.length,rows};
 }
 function marginals(q){
  const {a,state}=build(q),L=Array(c.atoms.length).fill(0),R=Array(c.atoms.length).fill(0),p=c.profiles[state.lag_mask];
  for(const j of state.indices){const [l,r,w]=p.rows[j];L[l]+=w;R[r]+=w;work.marginalRows++;}
  return {lag:a.lag,lag_mask:a.lag_mask,mass:state.mass,left:L,right:R,conditional_denominator:state.mass?String(state.mass):null};
 }
 return {condition:summary,select,rank,page,marginals,profile:q=>{const m=lag(q.lag);const p=c.profiles[m];return {lag:q.lag,lag_mask:m,atom_count:p.rows.length,mass:p.mass,moment:{numerator:p.moment_numerator,denominator:p.moment_denominator},covariance:{numerator:p.covariance_numerator,denominator:p.covariance_denominator},provenance:p.provenance};},work:()=>({...work}),snapshot:()=>({conditions:Array.from(conditions.values())})};
}
module.exports={construct,createReader};
