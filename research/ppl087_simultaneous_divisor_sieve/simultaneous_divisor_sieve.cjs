'use strict';

/* Exact finite small-divisor navigation. Survivors are not primality claims. */
const SCHEMA = 'commons.simultaneous_divisor_index/v1';
const LIMITS = Object.freeze({digits:2048, modulus:257, modulusSum:2000, product:1000000, rows:200000, page:128});
const clone = x => JSON.parse(JSON.stringify(x));
function nat(x,name,maxDigits=LIMITS.digits) {
  if (typeof x !== 'string' || !/^(0|[1-9][0-9]*)$/.test(x) || x.length>maxDigits)
    throw new TypeError(name+' must be a canonical nonnegative decimal string within the digit cap');
  return BigInt(x);
}
function integer(x,lo,hi,name) {
  if (!Number.isSafeInteger(x)||x<lo||x>hi) throw new RangeError(name+' out of range');
  return x;
}
function gcd(a,b) { while(b) { const r=a%b; a=b; b=r; } return a; }
function inputContract(input) {
  if (!input || typeof input!=='object' || Array.isArray(input)) throw new TypeError('input object required');
  const n=nat(input.n,'n');
  if (!Array.isArray(input.moduli)||!input.moduli.length) throw new TypeError('nonempty moduli required');
  let product=1,sum=0;
  const moduli=input.moduli.map((m,i)=>{
    integer(m,2,LIMITS.modulus,'modulus');
    if (n<=BigInt(m)) throw new RangeError('n must exceed every supplied modulus');
    for(let j=0;j<i;j++) if(gcd(m,input.moduli[j])!==1) throw new RangeError('moduli must be pairwise coprime');
    product*=m;sum+=m;
    if(product>LIMITS.product||sum>LIMITS.modulusSum) throw new RangeError('modulus budget exceeded');
    return m;
  });
  return {n,moduli,product};
}
function inverse(a,m) {
  let oldr=a,r=m,olds=1,s=0;
  while(r){const q=Math.floor(oldr/r);[oldr,r]=[r,oldr-q*r];[olds,s]=[s,olds-q*s];}
  if(oldr!==1)throw new Error('inverse requires coprimality');
  return ((olds%m)+m)%m;
}
function buildIndex(input) {
  const {n,moduli}=inputContract(input);
  const local=[],stages=[];
  const work={local_residue_tests:0,crt_rows_created:0,inverses:0,primality_tests:0};
  let product=1,previous=[[0,0]];
  for(const m of moduli) {
    const nmod=Number(n%BigInt(m)), flags=[], allowed=[];
    for(let r=0;r<m;r++){
      const f=((nmod+r)%m===0?1:0)|((nmod+r*r)%m===0?2:0);
      flags.push(f); if(f===0)allowed.push(r); work.local_residue_tests++;
    }
    const inv=inverse(product%m,m);work.inverses++;
    const size=previous.length*allowed.length;
    if(work.crt_rows_created+size>LIMITS.rows)throw new RangeError('CRT row budget exceeded');
    const rows=[];
    for(const old of previous)for(const residue of allowed){
      const step=(((residue-old[0])%m+m)%m*inv)%m;
      rows.push([old[0]+product*step,step]);
    }
    local.push({modulus:m,n_residue:nmod,flags,allowed});
    stages.push({modulus:m,previous_product:product,product:product*m,inverse:inv,rows});
    work.crt_rows_created+=rows.length;product*=m;previous=rows;
  }
  const order=previous.map((_,i)=>i).sort((a,b)=>previous[a][0]-previous[b][0]);
  return {schema:SCHEMA,input:{n:input.n,moduli},period:product,local,stages,
    order_by_residue:order,conventions:{
      domain:'0 <= k < n',
      flags:'bit 1 divides n+k; bit 2 divides n+k*k; zero survives supplied tests',
      primality:'No primality assertion is made for a survivor',
      row_order:'mixed local-choice rank; row=[residue, CRT step]',
      phase_count:'one phase for each surviving residue, without symmetry quotient'
    },construction_work:work};
}
function openIndex(value) {
  // This validates shape and indexes saved rows; it does not reprove their CRT provenance.
  const data=clone(value);
  if(data.schema!==SCHEMA)throw new TypeError('schema mismatch');
  const {n,moduli,product}=inputContract(data.input);
  if(data.period!==product||!Array.isArray(data.local)||!Array.isArray(data.stages)||
    data.local.length!==moduli.length||data.stages.length!==moduli.length)throw new TypeError('metadata mismatch');
  let previousProduct=1,previousCount=1,totalRows=0;
  for(let i=0;i<moduli.length;i++){
    const m=moduli[i],l=data.local[i],s=data.stages[i];
    if(l.modulus!==m||s.modulus!==m||s.previous_product!==previousProduct||s.product!==previousProduct*m)
      throw new TypeError('stage products mismatch');
    integer(l.n_residue,0,m-1,'saved n residue');integer(s.inverse,0,m-1,'saved inverse');
    if(!Array.isArray(l.flags)||l.flags.length!==m||!Array.isArray(l.allowed)||!Array.isArray(s.rows))throw new TypeError('stage shape');
    const zeros=[];
    l.flags.forEach((f,r)=>{integer(f,0,3,'flag');if(f===0)zeros.push(r);});
    if(JSON.stringify(zeros)!==JSON.stringify(l.allowed))throw new TypeError('allowed list mismatch');
    if(s.rows.length!==previousCount*l.allowed.length)throw new TypeError('row cardinality mismatch');
    for(const row of s.rows){
      if(!Array.isArray(row)||row.length!==2)throw new TypeError('row shape');
      integer(row[0],0,s.product-1,'saved residue');integer(row[1],0,m-1,'saved CRT step');
    }
    totalRows+=s.rows.length;if(totalRows>LIMITS.rows)throw new RangeError('saved row budget exceeded');
    previousProduct=s.product;previousCount=s.rows.length;
  }
  const last=data.stages[data.stages.length-1].rows,order=data.order_by_residue;
  if(!Array.isArray(order)||order.length!==last.length)throw new TypeError('order shape');
  const seen=new Set(),residues=[];
  for(const id of order){
    integer(id,0,last.length-1,'saved choice rank');
    if(seen.has(id))throw new TypeError('duplicate choice rank');seen.add(id);
    const r=last[id][0];
    if(residues.length&&residues[residues.length-1]>=r)throw new TypeError('residues not strictly increasing');
    residues.push(r);
  }
  const P=BigInt(product),S=BigInt(residues.length);
  const work={saved_rows_indexed:totalRows,final_phases_indexed:residues.length,
    queries:0,binary_search_steps:0,saved_row_lookups:0,bigint_divisions:0,bigint_remainders:0,
    polynomial_evaluations:0,quotient_witnesses:0,crt_rows_created:0,local_residue_tests:0,primality_tests:0};
  function div(a,b){work.bigint_divisions++;return a/b;}
  function rem(a,b){work.bigint_remainders++;return a%b;}
  function lower(x){
    let lo=0,hi=residues.length;
    while(lo<hi){work.binary_search_steps++;const mid=(lo+hi)>>1;if(residues[mid]<x)lo=mid+1;else hi=mid;}
    return lo;
  }
  function bound(x,name,allowEnd=true){const v=nat(x,name);if(v>n||(!allowEnd&&v===n))throw new RangeError(name+' outside [0,n'+(allowEnd?']':')'));return v;}
  function countAt(b){return div(b,P)*S+BigInt(lower(Number(rem(b,P))));}
  const total=countAt(n);
  function selectAt(j){
    if(j<0n||j>=total)throw new RangeError('candidate rank outside family');
    if(!residues.length)throw new RangeError('empty family');
    const block=div(j,S),position=Number(rem(j,S));work.saved_row_lookups++;
    return block*P+BigInt(residues[position]);
  }
  function pathAt(position) {
    if(position<0||position>=residues.length)return null;
    let rank=order[position];const path=[];
    for(let i=data.stages.length-1;i>=0;i--){
      const s=data.stages[i],l=data.local[i],a=l.allowed.length;
      const localChoice=rank%a,row=s.rows[rank];work.saved_row_lookups++;
      path.push({stage:i,choice_rank:rank,parent_rank:Math.floor(rank/a),local_choice:localChoice,
        local_residue:l.allowed[localChoice],modulus:l.modulus,previous_product:s.previous_product,
        inverse:s.inverse,step:row[1],residue:row[0],product:s.product});
      rank=Math.floor(rank/a);
    }
    return path.reverse();
  }
  return Object.freeze({
    summary(){
      work.queries++;
      return {n:data.input.n,moduli:moduli.slice(),period:product,phases:residues.length,total:total.toString(),
        local_allowed_counts:data.local.map(l=>l.allowed.length),stage_row_counts:data.stages.map(s=>s.rows.length),
        construction_work:clone(data.construction_work),survivor_meaning:'avoids supplied divisors only'};
    },
    local(){work.queries++;return clone(data.local);},
    stagePage(stage,start=0,limit=16){
      work.queries++;integer(stage,0,data.stages.length-1,'stage');integer(start,0,data.stages[stage].rows.length,'start');
      integer(limit,0,LIMITS.page,'limit');
      const s=data.stages[stage],end=Math.min(start+limit,s.rows.length);work.saved_row_lookups+=end-start;
      return {stage,start,total:s.rows.length,rows:s.rows.slice(start,end).map((r,j)=>({choice_rank:start+j,residue:r[0],step:r[1]}))};
    },
    phasePage(start=0,limit=16){
      work.queries++;integer(start,0,residues.length,'start');integer(limit,0,LIMITS.page,'limit');
      const end=Math.min(start+limit,residues.length);work.saved_row_lookups+=end-start;
      return {start,total:residues.length,rows:residues.slice(start,end).map((r,j)=>({phase_rank:start+j,residue:r,choice_rank:order[start+j]}))};
    },
    count(end){work.queries++;return countAt(bound(end,'end')).toString();},
    interval(lo,hi){
      work.queries++;const a=bound(lo,'lo'),b=bound(hi,'hi');if(a>b)throw new RangeError('lo exceeds hi');
      return {lo,hi,count:(countAt(b)-countAt(a)).toString(),interval:'[lo,hi)'};
    },
    select(rank){work.queries++;const j=nat(rank,'rank');return {rank,k:selectAt(j).toString()};},
    rank(k){
      work.queries++;const v=bound(k,'k',false),r=Number(rem(v,P)),position=lower(r);
      return {k,rank:position<residues.length&&residues[position]===r?(div(v,P)*S+BigInt(position)).toString():null};
    },
    page(start,limit=16){
      work.queries++;const j=nat(start,'start');integer(limit,0,LIMITS.page,'limit');
      if(j>total)throw new RangeError('page start exceeds family');
      const out=[];for(let z=j;z<total&&out.length<limit;z++)out.push({rank:z.toString(),k:selectAt(z).toString()});
      return {start,total:total.toString(),rows:out};
    },
    crtPath(residue){
      work.queries++;integer(residue,0,product-1,'residue');const position=lower(residue);
      return {residue,phase_rank:position<residues.length&&residues[position]===residue?position:null,
        path:position<residues.length&&residues[position]===residue?pathAt(position):null};
    },
    inspect(k){
      work.queries++;const v=bound(k,'k',false),hits=[];
      let firstLinear=null,firstQuadratic=null;
      for(const l of data.local){
        const r=Number(rem(v,BigInt(l.modulus))),flags=l.flags[r];work.saved_row_lookups++;
        if(flags){hits.push({modulus:l.modulus,residue:r,flags});
          if((flags&1)&&firstLinear===null)firstLinear=l.modulus;
          if((flags&2)&&firstQuadratic===null)firstQuadratic=l.modulus;
        }
      }
      const linear=n+v,quadratic=n+v*v;work.polynomial_evaluations+=2;
      function witness(value,m){
        if(m===null)return null;
        const divisor=BigInt(m),quotient=div(value,divisor),remainder=rem(value,divisor);
        work.quotient_witnesses++;
        return {divisor:m,quotient:quotient.toString(),remainder:remainder.toString(),proper:1n<divisor&&divisor<value};
      }
      return {k,survives:hits.length===0,hits,
        linear:{value:linear.toString(),witness:witness(linear,firstLinear)},
        quadratic:{value:quadratic.toString(),witness:witness(quadratic,firstQuadratic)},
        prime_status:'not tested'};
    },
    work(){return clone(work);}
  });
}
module.exports={buildIndex,openIndex,SCHEMA,LIMITS};
