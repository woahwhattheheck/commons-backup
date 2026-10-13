"use strict";

/*
 * Certified mean-distance enclosure for an orthogonal spherical zigzag family.
 * The source problem is Kimberling's section 10; the guide declares uniform
 * surface area as the averaging convention. Pure BigInt interval arithmetic.
 * No floating transcendental value, I/O, random sampling or optimization claim.
 */
const SPHERICAL_MEAN_LIMITS=Object.freeze({
  min_m:3,max_m:16,max_height_bands:512,max_longitude_bands:512,
  max_cells:16384,min_angle_bins:64,max_angle_bins:4096,
  min_fraction_bits:40,max_fraction_bits:64,max_page_size:256,
  max_rational_digits:128,max_atan_terms:128,taylor_terms:24,max_threshold_cache_entries:16
});
const SCHEMA="commons.orthogonal_spherical_zigzag_mean.v1";
const copy=x=>JSON.parse(JSON.stringify(x));
function fail(s){throw new Error(s);}
function object(x,name){if(!x||typeof x!=="object"||Array.isArray(x))fail(name+" must be an object");return x;}
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside supported integer range");return x;}
function nat(x,name){
  let s;
  if(typeof x==="bigint")s=x.toString();
  else if(typeof x==="number"&&Number.isSafeInteger(x)&&x>=0)s=String(x);
  else if(typeof x==="string")s=x;
  else fail(name+" must be a bounded nonnegative integer");
  if(!/^(0|[1-9][0-9]*)$/.test(s)||s.length>SPHERICAL_MEAN_LIMITS.max_rational_digits)
    fail(name+" must use bounded canonical nonnegative decimal notation");
  return BigInt(s);
}
function floorDiv(a,b){if(b<=0n)fail("positive denominator required");const q=a/b,r=a%b;return r<0n?q-1n:q;}
function ceilDiv(a,b){return -floorDiv(-a,b);}
function gcd(a,b){while(b){const r=a%b;a=b;b=r;}return a;}
function normalizedFraction(n,d){const g=gcd(n,d);return [n/g,d/g];}
function workRecord(phase){
 return {
  phase,pi_series_terms:0,arctangent_series_terms:0,arctangent_requests:0,arctangent_cache_hits:0,
  universal_bound_series_terms:0,cosine_requests:0,cosine_cache_hits:0,cosine_polynomials:0,
  taylor_terms:0,interval_multiplications:0,interval_squares:0,
  interval_divisions_by_integer:0,interval_reciprocals:0,
  interval_square_roots:0,integer_sqrt_iterations:0,
  cosine_monotone_comparisons:0,samples_constructed:0,
  vertex_dot_products:0,arc_support_pairs:0,angle_bin_comparisons:0,
  retained_samples:0,retained_cosine_bins:0,retained_extra_cosines:0,
  retained_vertex_rows:0,reader_sum_additions:0,reader_bound_comparisons:0,
  query_calls:0,sample_rows_returned:0,cosine_rows_returned:0,
  threshold_compilations:0,threshold_sample_comparisons:0,threshold_cache_hits:0,threshold_cache_evictions:0
 };
}
function makeEngine(bits,work){
 const Q=1n<<BigInt(bits),cache=new Map(),atanCache=new Map(),extra=[];
 const I=(a,b=a)=>[a,b];
 const add=(a,b)=>I(a[0]+b[0],a[1]+b[1]);
 const neg=a=>I(-a[1],-a[0]);
 const sub=(a,b)=>add(a,neg(b));
 function mul(a,b){
  work.interval_multiplications++;
  const v=[a[0]*b[0],a[0]*b[1],a[1]*b[0],a[1]*b[1]];
  let lo=v[0],hi=v[0];for(const x of v){if(x<lo)lo=x;if(x>hi)hi=x;}
  return I(floorDiv(lo,Q),ceilDiv(hi,Q));
 }
 function square(a){
  work.interval_squares++;
  const x=a[0]*a[0],y=a[1]*a[1];
  const lo=a[0]<=0n&&a[1]>=0n?0n:(x<y?x:y),hi=x>y?x:y;
  return I(floorDiv(lo,Q),ceilDiv(hi,Q));
 }
 function divInt(a,n){work.interval_divisions_by_integer++;n=BigInt(n);return I(floorDiv(a[0],n),ceilDiv(a[1],n));}
 function scale(a,n){n=BigInt(n);return n>=0n?I(a[0]*n,a[1]*n):I(a[1]*n,a[0]*n);}
 function rational(n,d){n=BigInt(n);d=BigInt(d);return I(floorDiv(n*Q,d),ceilDiv(n*Q,d));}
 function reciprocal(a){
  work.interval_reciprocals++;if(a[0]<=0n)fail("positive reciprocal interval required");
  return I(floorDiv(Q*Q,a[1]),ceilDiv(Q*Q,a[0]));
 }
 function isqrt(n){
  if(n<0n)fail("negative square-root input");if(n<2n)return n;
  let x=1n<<BigInt(Math.ceil(n.toString(2).length/2));
  while(true){work.integer_sqrt_iterations++;const y=(x+n/x)>>1n;if(y>=x)return x;x=y;}
 }
 function sqrt(a){
  work.interval_square_roots++;if(a[0]<0n)fail("negative interval square-root endpoint");
  const lo=isqrt(a[0]*Q),r=isqrt(a[1]*Q);
  return I(lo,r*r===a[1]*Q?r:r+1n);
 }
 function clip01(a){const lo=a[0]<0n?0n:a[0],hi=a[1]>Q?Q:a[1];if(lo>hi)fail("empty unit interval");return I(lo,hi);}
 function atanReciprocal(b){
  b=BigInt(b);if(b<2n)fail("reciprocal arctangent requires b>=2");
  work.arctangent_requests++;if(atanCache.has(b.toString())){work.arctangent_cache_hits++;return atanCache.get(b.toString());}
  let power=b,sum=I(0n),records=[];
  for(let n=0;n<SPHERICAL_MEAN_LIMITS.max_atan_terms;n++){
   const denominator=BigInt(2*n+1)*power,term=I(Q/denominator,ceilDiv(Q,denominator));
   sum=n%2?sub(sum,term):add(sum,term);work.arctangent_series_terms++;
   records.push({degree:2*n+1,denominator:denominator.toString(),
    sign:n%2?-1:1,lower:term[0].toString(),upper:term[1].toString()});
   power*=b*b;const nextDen=BigInt(2*n+3)*power,tail=ceilDiv(Q,nextDen);
   if(tail<=1n){
    const out=(n+1)%2?I(sum[0]-tail,sum[1]):I(sum[0],sum[1]+tail);
    const result={value:out,record:{reciprocal_denominator:b.toString(),terms:records,
      next_denominator:nextDen.toString(),tail_upper:tail.toString(),
      interval:out.map(String)}};
    atanCache.set(b.toString(),result);return result;
   }
  }
  fail("arctangent term cap reached");
 }
 const at5=atanReciprocal(5),at239=atanReciprocal(239),
  pi=sub(scale(at5.value,16),scale(at239.value,4));
 if(!(pi[0]>0n&&pi[0]<=pi[1]&&pi[1]<4n*Q))fail("Machin enclosure failed");
 work.pi_series_terms=work.arctangent_series_terms;
 let factorial=1n;for(let j=2;j<=50;j++)factorial*=BigInt(j);
 const tail=ceilDiv(Q*(1n<<50n),factorial);
 function cosine(n,d,markExtra=true){
  work.cosine_requests++;n=BigInt(n);d=BigInt(d);
  if(d<=0n||n<0n||2n*n>d)fail("cosine requires a rational pi multiple in [0,1/2]");
  const f=normalizedFraction(n,d),key=f[0]+"/"+f[1];
  if(cache.has(key)){work.cosine_cache_hits++;return cache.get(key);}
  let result;
  if(n===0n)result=I(Q);
  else if(2n*n===d)result=I(0n);
  else {
   work.cosine_polynomials++;
   const x=divInt(scale(pi,n),d),x2=square(x);
   let term=I(Q),sum=I(Q);
   for(let j=1;j<=SPHERICAL_MEAN_LIMITS.taylor_terms;j++){
    term=divInt(mul(term,x2),BigInt((2*j-1)*(2*j)));
    sum=j%2?sub(sum,term):add(sum,term);work.taylor_terms++;
   }
   result=clip01(I(sum[0]-tail,sum[1]+tail));
  }
  cache.set(key,result);
  if(markExtra)extra.push({numerator:f[0].toString(),denominator:f[1].toString(),
    interval:result.map(String)});
  return result;
 }
 function sincos(n,d){
  n=BigInt(n);d=BigInt(d);
  return {cos:cosine(n,d),sin:cosine(d-2n*n,2n*d)};
 }
 function fullSinCos(j,m){
  const r=((j%(2*m))+2*m)%(2*m),u=r<=m?r:2*m-r,
    first=2*u<=m,fold=first?u:m-u;
  const t=sincos(fold,m);
  return {cos:first?t.cos:neg(t.cos),sin:r<=m?t.sin:neg(t.sin)};
 }
 return {Q,I,add,sub,neg,mul,square,divInt,scale,rational,reciprocal,sqrt,clip01,
  cosine,sincos,fullSinCos,pi,extra,atanReciprocal,
  piRecord:{identity:"pi=16*atan(1/5)-4*atan(1/239)",
   atan5:at5.record,atan239:at239.record,interval:pi.map(String)},
  cosineProof:{terms:24,degree:48,argument_upper:"2",
    remainder_formula:"2^50/50!",remainder_fixed_upper:tail.toString()}};
}
function encodeInt(x,width){const s=x.toString(16);if(s.length>width||x<0n)fail("encoded integer overflow");return s.padStart(width,"0");}
function decodeInt(s,width,Q,name){
 if(typeof s!=="string"||s.length!==width||!/^[0-9a-f]+$/.test(s))fail(name+" is not a fixed-width hexadecimal integer");
 const n=BigInt("0x"+s);if(n>Q)fail(name+" exceeds the unit interval");return n;
}
function encodeSample(lo,hi,l,u,w,bw){
 return encodeInt(lo,w)+encodeInt(hi,w)+encodeInt(BigInt(l),bw)+encodeInt(BigInt(u),bw);
}
function sampleFields(raw,w,bw,Q,K){
 if(typeof raw!=="string"||raw.length!==2*w+2*bw||!/^[0-9a-f]+$/.test(raw))fail("invalid encoded sample row");
 const lo=decodeInt(raw.slice(0,w),w,Q,"sample lower"),
  hi=decodeInt(raw.slice(w,2*w),w,Q,"sample upper"),
  l=Number(BigInt("0x"+raw.slice(2*w,2*w+bw))),
  u=Number(BigInt("0x"+raw.slice(2*w+bw)));
 if(lo>hi||l>u||u>K)fail("encoded sample interval order mismatch");
 return {lo,hi,l,u};
}
function compileOrthogonalZigzagMean(input){
 object(input,"input");
 const m=integer(input.m,3,SPHERICAL_MEAN_LIMITS.max_m,"m"),
  M=integer(input.height_bands,1,SPHERICAL_MEAN_LIMITS.max_height_bands,"height_bands"),
  J=integer(input.longitude_bands,1,SPHERICAL_MEAN_LIMITS.max_longitude_bands,"longitude_bands"),
  K=integer(input.angle_bins,SPHERICAL_MEAN_LIMITS.min_angle_bins,SPHERICAL_MEAN_LIMITS.max_angle_bins,"angle_bins"),
  bits=integer(input.fraction_bits,SPHERICAL_MEAN_LIMITS.min_fraction_bits,SPHERICAL_MEAN_LIMITS.max_fraction_bits,"fraction_bits");
 if(M*J>SPHERICAL_MEAN_LIMITS.max_cells)fail("sample-cell cap exceeded");
 const work=workRecord("constructor"),E=makeEngine(bits,work),Q=E.Q,
  w=Math.ceil((bits+1)/4),bw=K.toString(16).length;
 const table=[];
 for(let i=0;i<=K;i++){
  const c=E.cosine(i,2*K,false),s=E.square(c);
  table.push({cos:c,sq:s});
 }
 for(let i=K-1;i>=0;i--){work.cosine_monotone_comparisons++;
  if(table[i].sq[0]<table[i+1].sq[0])table[i].sq[0]=table[i+1].sq[0];}
 for(let i=1;i<=K;i++){work.cosine_monotone_comparisons++;
  if(table[i].sq[1]>table[i-1].sq[1])table[i].sq[1]=table[i-1].sq[1];}
 const cDelta=E.cosine(1,m),a2=E.reciprocal(E.add(E.I(Q),cDelta)),
  b2=E.sub(E.I(Q),a2),a=E.sqrt(a2),b=E.sqrt(b2);
 const vertices=[];
 for(let j=0;j<2*m;j++){
  const t=E.fullSinCos(j,m);
  vertices.push([E.mul(a,t.cos),E.mul(a,t.sin),j%2?E.neg(b):b]);
 }
 const zNodes=[],thetaNodes=[];
 for(let i=0;i<M;i++){
  const z=E.rational(2*i+1,2*M),rho=E.sqrt(E.sub(E.I(Q),E.square(z)));
  zNodes.push({numerator:2*i+1,denominator:2*M,z,rho});
 }
 for(let j=0;j<J;j++){
  const t=E.sincos(2*j+1,2*m*J);
  thetaNodes.push({numerator:2*j+1,denominator:2*m*J,cos:t.cos,sin:t.sin});
 }
 function bin(lo,hi){
  let a=0,b=K;
  while(a<b){const mid=Math.ceil((a+b)/2);work.angle_bin_comparisons++;
   if(table[mid].sq[0]>=hi)a=mid;else b=mid-1;}
  const lower=a;a=0;b=K;
  while(a<b){const mid=(a+b)>>1;work.angle_bin_comparisons++;
   if(table[mid].sq[1]<=lo)b=mid;else a=mid+1;}
  if(lower>a)fail("angle interval is reversed");
  return [lower,a];
 }
 const encoded=[],sum=[0n,0n];
 for(let i=0;i<M;i++)for(let j=0;j<J;j++){
  const z=zNodes[i],t=thetaNodes[j],point=[E.mul(z.rho,t.cos),E.mul(z.rho,t.sin),z.z],
    dots=[];
  for(const v of vertices){
   let d=E.I(0n);
   for(let c=0;c<3;c++)d=E.add(d,E.mul(point[c],v[c]));
   dots.push(d);work.vertex_dot_products++;
  }
  let low=0n,high=0n;
  const squares=dots.map(d=>E.square([d[0]<0n?0n:d[0],d[1]<0n?0n:d[1]]));
  for(let e=0;e<2*m;e++){
   const s=E.add(squares[e],squares[(e+1)%(2*m)]);work.arc_support_pairs++;
   if(s[0]>low)low=s[0];if(s[1]>high)high=s[1];
  }
  if(high>Q)high=Q;if(low>high)fail("support enclosure is empty");
  const v=bin(low,high);sum[0]+=BigInt(v[0]);sum[1]+=BigInt(v[1]);
  encoded.push(encodeSample(low,high,v[0],v[1],w,bw));work.samples_constructed++;
 }
 const C=BigInt(M*J),den=2n*BigInt(K)*C,
  errN=BigInt(M+m*J),errD=2n*BigInt(m*M*J);
 const lowerNum=sum[0]*errD-errN*den,upperNum=sum[1]*errD+errN*den,
  meanDen=den*errD;
 const reducedLo=normalizedFraction(lowerNum<0n?0n:lowerNum,meanDen),
  reducedHi=normalizedFraction(upperNum,meanDen),
  mean={
   sample_lower_bin_sum:sum[0].toString(),sample_upper_bin_sum:sum[1].toString(),
   sample_mean_pi_denominator:den.toString(),
   quadrature_error_pi_numerator:errN.toString(),quadrature_error_pi_denominator:errD.toString(),
   lower_pi_numerator:reducedLo[0].toString(),lower_pi_denominator:reducedLo[1].toString(),
   upper_pi_numerator:reducedHi[0].toString(),upper_pi_denominator:reducedHi[1].toString(),
   interpretation:"uniform-area mean geodesic distance of this fixed feasible curve; not an optimum certificate"
  };
 const priorAtanTerms=work.arctangent_series_terms,universal=E.atanReciprocal(m);
 work.universal_bound_series_terms=work.arctangent_series_terms-priorAtanTerms;
 const snapshot={
  schema:SCHEMA,parameters:{m,height_bands:M,longitude_bands:J,angle_bins:K,fraction_bits:bits},
  scale:Q.toString(),encoding:{fraction_hex_width:w,bin_hex_width:bw,
   sample:"support_square_lower | support_square_upper | lower_angle_bin | upper_angle_bin",
   cosine:"cos_lower | cos_upper | monotone_cos_square_lower | monotone_cos_square_upper",
   radix:16,row_order:"height index first, longitude index second; zero based"},
  curve:{vertex_count:2*m,arc_length_pi_fraction:[1,2],total_length_pi_multiple:m,
   a_squared:a2.map(String),b_squared:b2.map(String),a:a.map(String),b:b.map(String),
   cos_pi_over_m:cDelta.map(String),vertices:vertices.map(v=>v.map(x=>x.map(String))),
   symbolic:"v_j=(a*cos(j*pi/m),a*sin(j*pi/m),(-1)^j*b); a^2=1/(1+cos(pi/m)); b^2=1-a^2",
   simplicity:"each minor arc has strictly increasing longitude in its own consecutive wedge"},
  symmetry:{group_order:4*m,domain:"0<=z<=1, 0<=theta<=pi/m",uniform_cell_weight:"1/(height_bands*longitude_bands)"},
  pi:E.piRecord,cosine_remainder:E.cosineProof,
  cosine_table:table.map(t=>[...t.cos,...t.sq].map(x=>encodeInt(x,w)).join("")),
  extra_cosines:copy(E.extra),
  height_nodes:zNodes.map(z=>({numerator:z.numerator,denominator:z.denominator,z:z.z.map(String),radial:z.rho.map(String)})),
  longitude_nodes:thetaNodes.map(t=>({numerator:t.numerator,denominator:t.denominator,cos:t.cos.map(String),sin:t.sin.map(String)})),
  samples:encoded,mean,
  universal_lower_bound:{formula:"atan(1/m)",interval:universal.value.map(String),
   arctangent_record:universal.record,
   scope:"every continuous rectifiable spherical path of length m*pi, with uniform surface-area mean; no equality claim"},
  source:{url:"https://faculty.evansville.edu/ck6/integer/unsolved.html",section:10,
   averaging_convention:"uniform surface area explicitly adopted; source leaves the averaging measure implicit"},
  mathematical_scope:"a feasible simple closed curve of length m*pi and its rigorous mean enclosure; no global minimizer or arbitrary-length claim",
  construction_work:null
 };
 work.retained_samples=encoded.length;work.retained_cosine_bins=table.length;
 work.retained_extra_cosines=E.extra.length;work.retained_vertex_rows=vertices.length;
 snapshot.construction_work=copy(work);
 return makeInterface(snapshot,work);
}
function validateSnapshot(raw){
 object(raw,"snapshot");if(raw.schema!==SCHEMA)fail("unsupported snapshot schema");
 const p=object(raw.parameters,"parameters"),
  m=integer(p.m,3,SPHERICAL_MEAN_LIMITS.max_m,"m"),
  M=integer(p.height_bands,1,SPHERICAL_MEAN_LIMITS.max_height_bands,"height bands"),
  J=integer(p.longitude_bands,1,SPHERICAL_MEAN_LIMITS.max_longitude_bands,"longitude bands"),
  K=integer(p.angle_bins,SPHERICAL_MEAN_LIMITS.min_angle_bins,SPHERICAL_MEAN_LIMITS.max_angle_bins,"angle bins"),
  bits=integer(p.fraction_bits,SPHERICAL_MEAN_LIMITS.min_fraction_bits,SPHERICAL_MEAN_LIMITS.max_fraction_bits,"fraction bits"),
  Q=1n<<BigInt(bits),w=Math.ceil((bits+1)/4),bw=K.toString(16).length;
 if(M*J>SPHERICAL_MEAN_LIMITS.max_cells||raw.scale!==Q.toString())fail("snapshot size/scale mismatch");
 if(!raw.encoding||raw.encoding.fraction_hex_width!==w||raw.encoding.bin_hex_width!==bw||raw.encoding.radix!==16)
  fail("snapshot encoding mismatch");
 if(!Array.isArray(raw.samples)||raw.samples.length!==M*J||
    !Array.isArray(raw.cosine_table)||raw.cosine_table.length!==K+1)fail("complete sample/cosine arrays required");
 const work=workRecord("saved_reader"),tableLower=[],tableUpper=[];let prevLo=Q,prevHi=Q;
 for(let i=0;i<=K;i++){
  const s=raw.cosine_table[i];
  if(typeof s!=="string"||s.length!==4*w)fail("invalid cosine row length");
  const v=[0,1,2,3].map(j=>decodeInt(s.slice(j*w,(j+1)*w),w,Q,"cosine field"));
  if(v[0]>v[1]||v[2]>v[3]||v[2]>prevLo||v[3]>prevHi)fail("cosine enclosure/order mismatch");
  if((i===0&&v.some(x=>x!==Q))||(i===K&&v.some(x=>x!==0n)))fail("cosine endpoint mismatch");
  prevLo=v[2];prevHi=v[3];tableLower.push(v[2]);tableUpper.push(v[3]);
 }
 let sumL=0n,sumU=0n;
 for(const r of raw.samples){
  const v=sampleFields(r,w,bw,Q,K);work.reader_bound_comparisons+=2;
  if(tableLower[v.l]<v.hi||tableUpper[v.u]>v.lo)fail("saved sample angle-bin witness mismatch");
  sumL+=BigInt(v.l);sumU+=BigInt(v.u);work.reader_sum_additions+=2;
 }
 const mean=object(raw.mean,"mean");
 if(mean.sample_lower_bin_sum!==sumL.toString()||mean.sample_upper_bin_sum!==sumU.toString()||
    mean.sample_mean_pi_denominator!==(2*K*M*J).toString())fail("sample aggregate mismatch");
 const en=BigInt(M+m*J),ed=BigInt(2*m*M*J),den=2n*BigInt(K*M*J),
  loN=sumL*ed-en*den,hiN=sumU*ed+en*den,
  lf=normalizedFraction(loN<0n?0n:loN,den*ed),uf=normalizedFraction(hiN,den*ed);
 if(mean.quadrature_error_pi_numerator!==en.toString()||mean.quadrature_error_pi_denominator!==ed.toString()||
    mean.lower_pi_numerator!==lf[0].toString()||mean.lower_pi_denominator!==lf[1].toString()||
    mean.upper_pi_numerator!==uf[0].toString()||mean.upper_pi_denominator!==uf[1].toString())
  fail("mean envelope/aggregation mismatch");
 const pi=object(raw.pi,"pi");
 if(!Array.isArray(pi.interval)||pi.interval.length!==2)fail("pi interval required");
 const piLo=nat(pi.interval[0],"pi lower"),piHi=nat(pi.interval[1],"pi upper");
 if(piLo<=0n||piLo>piHi||piHi>=4n*Q)fail("invalid pi envelope");
 const universal=object(raw.universal_lower_bound,"universal lower bound");
 if(universal.formula!=="atan(1/m)"||!Array.isArray(universal.interval)||universal.interval.length!==2||
    !universal.arctangent_record||universal.arctangent_record.reciprocal_denominator!==String(m))fail("universal-bound source binding mismatch");
 const uLo=nat(universal.interval[0],"universal lower"),uHi=nat(universal.interval[1],"universal upper");
 if(uLo<=0n||uLo>uHi||uHi>Q)fail("universal-bound interval mismatch");
 function signedInterval(a,name){
  if(!Array.isArray(a)||a.length!==2||a.some(x=>typeof x!=="string"||!(/^-?(0|[1-9][0-9]*)$/).test(x)||x.length>128))
    fail(name+" requires two bounded signed decimal strings");
  const x=a.map(BigInt);if(x[0]>x[1]||x[0]<-Q||x[1]>Q)fail(name+" outside unit coordinates");
 }
 if(!raw.curve||raw.curve.vertex_count!==2*m||raw.curve.total_length_pi_multiple!==m||
    !Array.isArray(raw.curve.vertices)||raw.curve.vertices.length!==2*m)
  fail("curve size/length metadata mismatch");
 for(const v of raw.curve.vertices){if(!Array.isArray(v)||v.length!==3)fail("three coordinates required");v.forEach(a=>signedInterval(a,"vertex"));}
 if(!raw.symmetry||raw.symmetry.group_order!==4*m||
    !Array.isArray(raw.height_nodes)||raw.height_nodes.length!==M||
    !Array.isArray(raw.longitude_nodes)||raw.longitude_nodes.length!==J||
    !Array.isArray(raw.extra_cosines)||raw.extra_cosines.length>2*J+2*m+2)fail("saved axis/symmetry shape mismatch");
 raw.height_nodes.forEach((a,i)=>{if(a.numerator!==2*i+1||a.denominator!==2*M)fail("height grid mismatch");signedInterval(a.z,"height");signedInterval(a.radial,"radial");});
 raw.longitude_nodes.forEach((a,j)=>{if(a.numerator!==2*j+1||a.denominator!==2*m*J)fail("longitude grid mismatch");signedInterval(a.cos,"cosine");signedInterval(a.sin,"sine");});
 raw.extra_cosines.forEach(a=>{const n=nat(a.numerator,"cosine numerator"),d=nat(a.denominator,"cosine denominator");
  if(d===0n||2n*n>d)fail("extra cosine angle mismatch");signedInterval(a.interval,"extra cosine");});
 object(raw.construction_work,"construction_work");object(raw.source,"source");
 work.retained_samples=M*J;work.retained_cosine_bins=K+1;
 work.retained_extra_cosines=raw.extra_cosines.length;work.retained_vertex_rows=2*m;
 return {snapshot:copy(raw),work};
}
function openRetainedSphericalMean(snapshot){const v=validateSnapshot(snapshot);return makeInterface(v.snapshot,v.work);}
function makeInterface(snapshot,work){
 const p=snapshot.parameters,m=p.m,M=p.height_bands,J=p.longitude_bands,K=p.angle_bins,
  Q=BigInt(snapshot.scale),w=snapshot.encoding.fraction_hex_width,bw=snapshot.encoding.bin_hex_width,
  C=M*J,thresholdCache=new Map();
 function smallRank(x,total,name,end){const n=nat(x,name),t=BigInt(total);if(n>t||(!end&&n===t))fail(name+" outside family");return Number(n);}
 function limit(x){return integer(x,1,SPHERICAL_MEAN_LIMITS.max_page_size,"page limit");}
 function sampleAt(id){
  const f=sampleFields(snapshot.samples[id],w,bw,Q,K),i=Math.floor(id/J),j=id%J;
  return {sample_index:id,height_index:i,longitude_index:j,
   z_fraction:{numerator:2*i+1,denominator:2*M},
   theta_pi_fraction:{numerator:2*j+1,denominator:2*m*J},
   support_square_interval:{lower:f.lo.toString(),upper:f.hi.toString(),denominator:Q.toString()},
   distance_pi_interval:{lower_numerator:f.l,upper_numerator:f.u,denominator:2*K}};
 }
 function threshold(n,d){
  n=nat(n,"threshold numerator");d=nat(d,"threshold denominator");
  if(d===0n||2n*n>d)fail("threshold must be a pi multiple in [0,1/2]");
  const f=normalizedFraction(n,d),key=f[0]+"/"+f[1];
  if(thresholdCache.has(key)){work.threshold_cache_hits++;return thresholdCache.get(key);}
  const groups={at_most:[],greater:[],unresolved:[]},bound=f[0]*BigInt(2*K);
  for(let id=0;id<C;id++){
   const x=sampleFields(snapshot.samples[id],w,bw,Q,K);work.threshold_sample_comparisons++;
   if(BigInt(x.u)*f[1]<=bound)groups.at_most.push(id);
   else {work.threshold_sample_comparisons++;
    if(BigInt(x.l)*f[1]>bound)groups.greater.push(id);else groups.unresolved.push(id);}
  }
  const out={numerator:f[0].toString(),denominator:f[1].toString(),groups};
  if(thresholdCache.size>=SPHERICAL_MEAN_LIMITS.max_threshold_cache_entries){thresholdCache.delete(thresholdCache.keys().next().value);work.threshold_cache_evictions++;}
  thresholdCache.set(key,out);work.threshold_compilations++;return out;
 }
 function category(s){if(s!=="at_most"&&s!=="greater"&&s!=="unresolved")fail("invalid threshold category");return s;}
 function decimalEndpoint(n,d,digits,up){
  const scale=10n**BigInt(digits),x=up?ceilDiv(n*scale,d):floorDiv(n*scale,d),
    s=x.toString().padStart(digits+1,"0");
  return digits?s.slice(0,-digits)+"."+s.slice(-digits):s;
 }
 function meanInterval(digits){
  const a=snapshot.mean,pi=snapshot.pi.interval.map(BigInt);
  return {lower:decimalEndpoint(BigInt(a.lower_pi_numerator)*pi[0],BigInt(a.lower_pi_denominator)*Q,digits,false),
   upper:decimalEndpoint(BigInt(a.upper_pi_numerator)*pi[1],BigInt(a.upper_pi_denominator)*Q,digits,true),
   digits,unit:"radians",averaging_measure:"uniform surface area",curve_length_pi_multiple:m};
 }
 return Object.freeze({
  summary(){work.query_calls++;return {schema:SCHEMA,parameters:copy(p),sample_count:C,
   curve_length_pi_multiple:m,curve_vertex_count:2*m,symmetry_group_order:4*m,
   mean:copy(snapshot.mean),scope:snapshot.mathematical_scope};},
  curve(){work.query_calls++;return copy(snapshot.curve);},
  meanEnclosure(){work.query_calls++;return {mean:copy(snapshot.mean),pi:copy(snapshot.pi.interval),scale:snapshot.scale};},
  meanDecimal(digits=6){work.query_calls++;integer(digits,0,18,"decimal digits");return meanInterval(digits);},
  infimumBracket(digits=6){
   work.query_calls++;integer(digits,0,18,"decimal digits");const feasible=meanInterval(digits);
   return {lower:decimalEndpoint(BigInt(snapshot.universal_lower_bound.interval[0]),Q,digits,false),
    upper:feasible.upper,digits,unit:"radians",curve_length_pi_multiple:m,
    lower_reason:"universal swept-cap bound atan(1/m)",upper_reason:"this feasible curve's rigorous mean upper enclosure",
    optimum_or_attainment_proved:false};
  },
  sample(i,j){work.query_calls++;integer(i,0,M-1,"height index");integer(j,0,J-1,"longitude index");
   work.sample_rows_returned++;return sampleAt(i*J+j);},
  page(start=0,count=64){
   work.query_calls++;const s=smallRank(start,C,"sample start",true),l=limit(count),end=Math.min(C,s+l);
   work.sample_rows_returned+=end-s;
   return {total:C,start:s,rows:Array.from({length:end-s},(_,j)=>sampleAt(s+j)),next:end<C?end:null};
  },
  cosinePage(start=0,count=64){
   work.query_calls++;const s=smallRank(start,K+1,"cosine start",true),l=limit(count),end=Math.min(K+1,s+l);
   work.cosine_rows_returned+=end-s;
   return {total:K+1,start:s,rows:Array.from({length:end-s},(_,j)=>{
    const i=s+j,r=snapshot.cosine_table[i],v=[0,1,2,3].map(c=>decodeInt(r.slice(c*w,(c+1)*w),w,Q,"cosine").toString());
    return {index:i,angle_pi_fraction:{numerator:i,denominator:2*K},
     cosine_interval:{lower:v[0],upper:v[1],denominator:Q.toString()},
     monotone_cosine_square_interval:{lower:v[2],upper:v[3],denominator:Q.toString()}};}),
    next:end<K+1?end:null};
  },
  thresholdCounts(n,d){
   work.query_calls++;const x=threshold(n,d);
   return {threshold_pi:{numerator:x.numerator,denominator:x.denominator},sample_count:C,
    counts:Object.fromEntries(Object.entries(x.groups).map(([k,a])=>[k,a.length])),
    scope:"finite midpoint samples only; unresolved means the certified interval crosses the threshold"};
  },
  selectThreshold(n,d,type,rank){
   work.query_calls++;const x=threshold(n,d),g=x.groups[category(type)],r=smallRank(rank,g.length,"threshold rank",false);
   work.sample_rows_returned++;return {category:type,rank:r,threshold_pi:{numerator:x.numerator,denominator:x.denominator},sample:sampleAt(g[r])};
  },
  rankThreshold(n,d,type,sampleIndex){
   work.query_calls++;const x=threshold(n,d),g=x.groups[category(type)],
    id=integer(sampleIndex,0,C-1,"sample index");
   let lo=0,hi=g.length;
   while(lo<hi){const mid=(lo+hi)>>1;if(g[mid]<id)lo=mid+1;else hi=mid;}
   return {category:type,sample_index:id,found:lo<g.length&&g[lo]===id,
    rank:lo<g.length&&g[lo]===id?lo:null,insertion_rank:lo};
  },
  pageThreshold(n,d,type,start=0,count=64){
   work.query_calls++;const x=threshold(n,d),g=x.groups[category(type)],
    s=smallRank(start,g.length,"threshold start",true),l=limit(count),end=Math.min(g.length,s+l);
   work.sample_rows_returned+=end-s;
   return {category:type,total:g.length,start:s,threshold_pi:{numerator:x.numerator,denominator:x.denominator},
    rows:g.slice(s,end).map((id,j)=>({rank:s+j,sample:sampleAt(id)})),next:end<g.length?end:null};
  },
  snapshot(){return copy(snapshot);},
  work(){return copy(work);}
 });
}
module.exports={compileOrthogonalZigzagMean,openRetainedSphericalMean,SPHERICAL_MEAN_LIMITS};
