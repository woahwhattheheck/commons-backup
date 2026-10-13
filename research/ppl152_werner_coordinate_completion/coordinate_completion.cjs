"use strict";
// Exact coordinate completions from an authenticated saved positive LDL certificate.
const MAX_DIGITS=4096;
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){const t=a%b;a=b;b=t;}return a;}
function rat(n,d=1n){if(d===0n)throw new RangeError("zero denominator");if(d<0n){n=-n;d=-d;}const g=gcd(n,d);n/=g;d/=g;if(n.toString().length>MAX_DIGITS||d.toString().length>MAX_DIGITS)throw new RangeError("rational resource bound");return[n,d];}
const Z=[0n,1n],O=[1n,1n];
function parse(v,cap=4096){if(typeof v!=="string"||v.length>cap*2+2||!/^(-?(?:0|[1-9][0-9]*))(?:\/([1-9][0-9]*))?$/.test(v))throw new TypeError("canonical integer/fraction string required");const a=v.split("/");if(a.some(s=>s.replace("-","").length>cap))throw new RangeError("input digit bound");return rat(BigInt(a[0]),a[1]?BigInt(a[1]):1n);}
function out(a){return a[1]===1n?a[0].toString():a[0]+"/"+a[1];}
function add(a,b){return rat(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);}
function sub(a,b){return rat(a[0]*b[1]-b[0]*a[1],a[1]*b[1]);}
function mul(a,b){return rat(a[0]*b[0],a[1]*b[1]);}
function div(a,b){return rat(a[0]*b[1],a[1]*b[0]);}
function neg(a){return[-a[0],a[1]];}
function eq(a,b){return a[0]===b[0]&&a[1]===b[1];}
function cmp(a,b){const d=a[0]*b[1]-b[0]*a[1];return d<0n?-1:d>0n?1:0;}
function bits(m){const a=[];for(let j=0;j<8;j++)if(m&(1<<j))a.push(j);return a;}
function mask(m){if(!Number.isInteger(m)||m<0||m>255)throw new RangeError("mask must be 0..255");return m;}
function matrix(a,n,m){if(!Array.isArray(a)||a.length!==n||a.some(r=>!Array.isArray(r)||r.length!==m))throw new TypeError("matrix shape");return a.map(r=>r.map(x=>parse(x)));}
function clone(v){return JSON.parse(JSON.stringify(v));}
function compile(input){
 if(input.schema!=="commons.werner_coordinate_completion_input/v1")throw new TypeError("input schema");
 const J=input.coordinates;if(!Array.isArray(J)||J.length!==8||new Set(J).size!==8||J.some(j=>!Number.isInteger(j)||j<0||j>=32))throw new TypeError("eight distinct coordinates required");
 const L=matrix(input.L,32,32),D=input.D.map(x=>parse(x));if(D.length!==32||D.some(x=>x[0]<=0n))throw new TypeError("strictly positive retained pivots required");
 for(let i=0;i<32;i++)for(let j=i;j<32;j++)if(!eq(L[i][j],i===j?O:Z))throw new TypeError("unit lower triangular factor required");
 const work={rhs:0,forwardTerms:0,diagonalDivisions:0,backwardTerms:0,profileUpdates:0,schurProducts:0,inverseUpdates:0,oldFormConstructions:0,oldEliminations:0};
 const A=Array.from({length:32},()=>Array(8).fill(Z));
 for(let c=0;c<8;c++){
  const y=Array(32).fill(Z);for(let i=0;i<32;i++){let q=i===J[c]?O:Z;for(let j=0;j<i;j++){q=sub(q,mul(L[i][j],y[j]));work.forwardTerms++;}y[i]=q;}
  const z=y.map((x,i)=>{work.diagonalDivisions++;return div(x,D[i]);}),x=Array(32).fill(Z);
  for(let i=31;i>=0;i--){let q=z[i];for(let j=i+1;j<32;j++){q=sub(q,mul(L[j][i],x[j]));work.backwardTerms++;}x[i]=q;}
  for(let i=0;i<32;i++)A[i][c]=x[i];work.rhs++;
 }
 const Q=J.map(i=>A[i].slice());const profiles=[{mask:0,indices:[],coordinates:[],parent:null,added_index:null,schur:null,inverse:[]}],internal=[[]];
 for(let m=1;m<256;m++){
  const ss=bits(m),j=ss[ss.length-1],p=m^(1<<j),ps=bits(p),B=internal[p],h=ps.map(i=>Q[i][j]),u=ps.map((_,i)=>{let x=Z;for(let k=0;k<ps.length;k++){x=add(x,mul(B[i][k],h[k]));work.schurProducts++;}return x;});
  let sch=Q[j][j];for(let i=0;i<ps.length;i++){sch=sub(sch,mul(h[i],u[i]));work.schurProducts++;}
  if(sch[0]<=0n)throw new Error("new principal Schur pivot is not positive");
  const inv=Array.from({length:ss.length},()=>Array(ss.length).fill(Z)),v=div(O,sch),n=ps.length;
  for(let i=0;i<n;i++){for(let k=0;k<n;k++){inv[i][k]=add(B[i][k],mul(mul(u[i],u[k]),v));work.inverseUpdates++;}inv[i][n]=inv[n][i]=neg(mul(u[i],v));}
  inv[n][n]=v;internal[m]=inv;profiles.push({mask:m,indices:ss,coordinates:ss.map(i=>J[i]),parent:p,added_index:j,schur:out(sch),inverse:inv.map(r=>r.map(out))});work.profileUpdates++;
 }
 return{schema:"commons.werner_coordinate_completion/v1",input_source:clone(input.source),coordinates:J.slice(),dimension:32,variable_order:input.tensor.variable_order,objective:"v* K v = 4 q(U V^T), complex v",state_expectation_denominator:"784",inverse_columns:A.map(r=>r.map(out)),coordinate_gram:Q.map(r=>r.map(out)),profiles,work};
}
function open(cert,input){
 if(cert.schema!=="commons.werner_coordinate_completion/v1")throw new TypeError("certificate schema");
 const J=cert.coordinates,A=matrix(cert.inverse_columns,32,8),K=matrix(input.integer_form,32,32),G=matrix(input.support_gram,2,2);
 const prof=cert.profiles;if(prof.length!==256)throw new TypeError("profile count");const inv=prof.map((p,m)=>{if(p.mask!==m||JSON.stringify(p.indices)!==JSON.stringify(bits(m)))throw new TypeError("profile order");return matrix(p.inverse,p.indices.length,p.indices.length);});
 const work={solves:0,cacheHits:0,multiplierTerms:0,completionTerms:0,stationarityTerms:0,energyTerms:0,normTerms:0,newProfiles:0,newFactorSolves:0,oldFormConstructions:0,oldEliminations:0},cache=new Map();
 function solve(m,values){
  mask(m);const ss=bits(m);if(!Array.isArray(values)||values.length!==ss.length)throw new TypeError("one complex pair per constrained coordinate");
  const g=values.map(z=>{if(!Array.isArray(z)||z.length!==2)throw new TypeError("complex pair required");return z.map(x=>parse(x,80));}),normed=g.map(z=>z.map(out)),key=JSON.stringify([m,normed]);
  if(cache.has(key)){work.cacheHits++;return clone(cache.get(key));}if(cache.size>=1024)throw new RangeError("cache capacity");
  const B=inv[m],lam=ss.map((_,i)=>[0,1].map(part=>{let v=Z;for(let j=0;j<ss.length;j++){v=add(v,mul(B[i][j],g[j][part]));work.multiplierTerms++;}return v;}));
  const v=A.map(row=>[0,1].map(part=>{let z=Z;for(let j=0;j<ss.length;j++){z=add(z,mul(row[ss[j]],lam[j][part]));work.completionTerms++;}return z;}));
  const kv=K.map(row=>[0,1].map(part=>{let z=Z;for(let j=0;j<32;j++){z=add(z,mul(row[j],v[j][part]));work.stationarityTerms++;}return z;}));
  const at=new Map(ss.map((j,i)=>[J[j],i]));let stationarity=true,feasible=true;
  for(let i=0;i<32;i++)for(let part=0;part<2;part++){const expected=at.has(i)?lam[at.get(i)][part]:Z;if(!eq(kv[i][part],expected))stationarity=false;}
  for(let i=0;i<ss.length;i++)for(let part=0;part<2;part++)if(!eq(v[J[ss[i]]][part],g[i][part]))feasible=false;
  let energy=Z,direct=Z,norm=Z;
  for(let i=0;i<ss.length;i++)for(let part=0;part<2;part++){energy=add(energy,mul(g[i][part],lam[i][part]));work.energyTerms++;}
  for(let i=0;i<32;i++)for(let part=0;part<2;part++){direct=add(direct,mul(v[i][part],kv[i][part]));work.energyTerms++;}
  for(let a=0;a<2;a++)for(let b=0;b<2;b++)for(let i=0;i<16;i++)for(let part=0;part<2;part++){norm=add(norm,mul(G[a][b],mul(v[16*a+i][part],v[16*b+i][part])));work.normTerms++;}
  if(!stationarity||!feasible||!eq(energy,direct)||energy[0]<0n||norm[0]<0n)throw new Error("new completion identity failed");
  const r={mask:m,coordinates:ss.map(j=>J[j]),values:normed,multipliers:lam.map(z=>z.map(out)),minimizer:v.map(z=>z.map(out)),minimum_form:out(energy),minimum_unnormalized_state_expectation:out(div(energy,[784n,1n])),state_norm_squared:out(norm),unit_vector_expectation_at_form_minimizer:norm[0]===0n?null:out(div(energy,mul([784n,1n],norm))),free_complex_dimension:32-ss.length,identities:{constraints_exact:feasible,stationarity_exact:stationarity,direct_energy_exact:eq(energy,direct)},claim:"unique minimum of unnormalized form on the coordinate-affine family; unit-vector ratio is only its evaluated value"};
  cache.set(key,r);work.solves++;return clone(r);
 }
 return{summary:()=>({dimension:32,coordinates:J.slice(),profiles:256,objective:cert.objective,assurance:"authenticated saved K=LDL^T is an input premise; no old identity audit"}),profile:m=>clone(prof[mask(m)]),solve,work:()=>clone(work),snapshot:()=>({schema:"commons.werner_coordinate_completion_reader/v1",cache:[...cache].map(([key,response])=>({key,response})),work:clone(work)})};
}
function buildFixtureIndex(responses){
 if(!Array.isArray(responses)||responses.length!==256||responses.some((r,i)=>r.mask!==i))throw new TypeError("all masks in numeric order required");
 const energies=responses.map(r=>parse(r.minimum_form)),edges=[];for(let m=0;m<256;m++)for(let j=0;j<8;j++)if(!(m&(1<<j))){const n=m|(1<<j),d=sub(energies[n],energies[m]);if(d[0]<0n)throw new Error("inconsistent fixture monotonicity");edges.push({from:m,to:n,added_index:j,increase:out(d)});}
 const energy_order=Array.from({length:256},(_,m)=>m).sort((a,b)=>cmp(energies[a],energies[b])||a-b);
 return{schema:"commons.werner_completion_fixture_index/v1",energies:responses.map(r=>r.minimum_form),energy_order,cover_edges:edges,work:{energyValuesCopied:256,coverDifferences:1024,optimizerReplays:0}};
}
function openFixtureIndex(index){
 const E=index.energies.map(x=>parse(x)),cache=new Map();const work={conditions:0,conditionHits:0,rowsScanned:0,rankLookups:0,selections:0};
 function condition(c={}){
  const require=mask(c.require??0),forbid=mask(c.forbid??0),lo=c.min_size??0,hi=c.max_size??8;if(!Number.isInteger(lo)||!Number.isInteger(hi))throw new TypeError("integer sizes");
  const emin=c.min_energy===undefined?null:parse(c.min_energy,80),emax=c.max_energy===undefined?null:parse(c.max_energy,80);
  const key=JSON.stringify([require,forbid,lo,hi,emin&&out(emin),emax&&out(emax)]);if(cache.has(key)){work.conditionHits++;return cache.get(key);}
  const rows=[];for(const m of index.energy_order){work.rowsScanned++;const size=bits(m).length;if((m&require)!==require||(m&forbid)||size<lo||size>hi||(emin&&cmp(E[m],emin)<0)||(emax&&cmp(E[m],emax)>0))continue;rows.push(m);}
  const r={key,count:rows.length,masks:rows};cache.set(key,r);work.conditions++;return r;
 }
 return{condition:c=>clone(condition(c)),select:(c,r)=>{const a=condition(c);if(!Number.isInteger(r)||r<0||r>=a.count)throw new RangeError("rank out of range");work.selections++;const m=a.masks[r];return{rank:r,mask:m,energy:out(E[m])};},rank:(c,m)=>{mask(m);work.rankLookups++;const a=condition(c),r=a.masks.indexOf(m);return{mask:m,rank:r<0?null:r};},snapshot:()=>({conditions:[...cache.values()].map(clone),work:clone(work)}),work:()=>clone(work)};
}
module.exports={compile,open,buildFixtureIndex,openFixtureIndex};
