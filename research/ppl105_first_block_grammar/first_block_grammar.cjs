'use strict';
const SCHEMA='commons.first_block_grammar/v1';
const LIMITS=Object.freeze({first_bound:12,horizon:512,word:4096,page:128,word_page:32});
const ALPHABET=['a','b'];
const clone=x=>JSON.parse(JSON.stringify(x));
function integer(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function word(x){if(typeof x!=='string'||x.length>LIMITS.word||!/^[ab]*$/.test(x))throw new TypeError('bounded binary word required');return x;}
function natural(x){
 if(typeof x==='number'){if(!Number.isSafeInteger(x)||x<0)throw new RangeError('unsafe rank');return BigInt(x);}
 if(typeof x==='bigint'){if(x<0n)throw new RangeError('negative rank');return x;}
 if(typeof x!=='string'||x.length>300||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError('canonical nonnegative rank required');
 return BigInt(x);
}
function buildIndex(firstBound,horizon){
 const B=integer(firstBound,0,LIMITS.first_bound,'first bound'),L=integer(horizon,0,LIMITS.horizon,'horizon');
 const states=[],initial=[],later=[];
 function add(value){const id=states.length;states.push({id,...value});return id;}
 for(let r=0;r<=B;r++)initial.push(add({kind:'first',length:r,accepting:false,access:'a'.repeat(r)}));
 for(let r=0;r<=B;r++){later[r]=[];for(let c=0;c<=r+1;c++)later[r].push(add({kind:'later',first_length:r,current_capped:c,cap:r+1,accepting:c===0,access:'a'.repeat(r)+'b'+'a'.repeat(c)}));}
 const dead=add({kind:'dead',accepting:false,access:'a'.repeat(B+1)}),N=states.length;
 const delta=states.map(s=>s.kind==='first'?[s.length<B?initial[s.length+1]:dead,later[s.length][0]]:
  s.kind==='later'?[later[s.first_length][Math.min(s.current_capped+1,s.cap)],s.current_capped===s.first_length?dead:later[s.first_length][0]]:[dead,dead]);
 const accepting=states.map(s=>s.accepting),incoming=Array.from({length:2},()=>Array.from({length:N},()=>[]));
 for(let q=0;q<N;q++)for(let a=0;a<2;a++)incoming[a][delta[q][a]].push(q);
 const distance=Array(N*N).fill(-1),queue=[];
 const pairKey=(a,b)=>a<b?a*N+b:b*N+a;
 const work={raw_states:N,raw_transitions:2*N,pair_count:N*(N-1)/2,acceptance_seed_pairs:0,reverse_predecessor_pairs:0,distinguished_pairs:0,quotient_states:0,grammar_rules:0,coefficient_cells:0,coefficient_additions:0};
 for(let a=0;a<N;a++)for(let b=a+1;b<N;b++)if(accepting[a]!==accepting[b]){distance[a*N+b]=0;queue.push([a,b]);work.acceptance_seed_pairs++;}
 for(let at=0;at<queue.length;at++){
  const [a,b]=queue[at],d=distance[a*N+b];
  for(let symbol=0;symbol<2;symbol++)for(const x of incoming[symbol][a])for(const y of incoming[symbol][b]){
   work.reverse_predecessor_pairs++;if(x===y)continue;const key=pairKey(x,y);
   if(distance[key]<0){distance[key]=d+1;queue.push(x<y?[x,y]:[y,x]);}
  }
 }
 work.distinguished_pairs=queue.length;
 const proof=new Map();
 for(const [a,b] of queue){
  const key=a*N+b,d=distance[key];
  if(d===0){proof.set(key,{left:a,right:b,length:0,suffix:'',symbol:null,next_pair:null});continue;}
  let chosen=null;
  for(let symbol=0;symbol<2;symbol++){
   const x=delta[a][symbol],y=delta[b][symbol];if(x===y)continue;
   const next=pairKey(x,y);if(distance[next]===d-1){const child=proof.get(next);if(!child)throw new Error('separator dependency order');chosen={left:a,right:b,length:d,suffix:ALPHABET[symbol]+child.suffix,symbol:ALPHABET[symbol],next_pair:x<y?[x,y]:[y,x]};break;}
  }
  if(!chosen)throw new Error('separator predecessor missing');proof.set(key,chosen);
 }
 const pairs=[];
 for(let a=0;a<N;a++)for(let b=a+1;b<N;b++)pairs.push(proof.get(a*N+b)||{left:a,right:b,length:null,suffix:null,symbol:null,next_pair:null});
 const classes=[],classOf=Array(N).fill(-1);
 for(let a=0;a<N;a++)if(classOf[a]<0){
  const id=classes.length,members=[];
  for(let b=a;b<N;b++)if(classOf[b]<0&&(a===b||distance[pairKey(a,b)]<0)){classOf[b]=id;members.push(b);}
  classes.push({id,representative:a,members,accepting:accepting[a],access:states[a].access});
 }
 const transitions=classes.map(c=>delta[c.representative].map(q=>classOf[q]));
 const start=classOf[initial[0]],finals=classes.map(c=>c.accepting),rules=[],ruleIndex=classes.map(()=>ALPHABET.map(()=>({continue:null,finish:null})));
 for(let q=0;q<classes.length;q++)for(let a=0;a<2;a++){
  const target=transitions[q][a],id=rules.length;
  rules.push({id,from:q,terminal:ALPHABET[a],tail:target});ruleIndex[q][a].continue=id;
  if(finals[target]){const stop=rules.length;rules.push({id:stop,from:q,terminal:ALPHABET[a],tail:null});ruleIndex[q][a].finish=stop;}
 }
 const coefficients=[finals.map(x=>x?'1':'0')];
 for(let k=1;k<=L;k++){
  const prior=coefficients[k-1],row=transitions.map(([a,b])=>{work.coefficient_additions++;return (BigInt(prior[a])+BigInt(prior[b])).toString();});
  coefficients.push(row);
 }
 work.quotient_states=classes.length;work.grammar_rules=rules.length;work.coefficient_cells=coefficients.length*classes.length;
 return {schema:SCHEMA,first_bound:B,horizon:L,alphabet:ALPHABET.slice(),
  language:'a^n1 b ... a^nk b, k>=1, 0<=n1<=B, all later ni>=0 and ni!=n1',
  raw:{start:initial[0],dead,states,transitions:delta,accepting},
  separation_pairs:pairs,quotient:{start,classes,class_of:classOf,transitions,accepting:finals},
  grammar:{start,rules,rule_index:ruleIndex,epsilon:false,shape:'terminal followed by zero or one nonterminal'},
  coefficients,work};
}
function openIndex(snapshot){
 const data=clone(snapshot);
 if(!data||data.schema!==SCHEMA)throw new TypeError('schema');
 const B=integer(data.first_bound,0,LIMITS.first_bound,'bound'),L=integer(data.horizon,0,LIMITS.horizon,'horizon');
 const raw=data.raw,q=data.quotient,N=raw.states.length,K=q.classes.length;
 integer(N,1,200,'raw states');integer(K,1,N,'quotient states');
 if(raw.transitions.length!==N||raw.accepting.length!==N||q.transitions.length!==K||q.accepting.length!==K||q.class_of.length!==N||data.coefficients.length!==L+1)throw new TypeError('shape');
 function transitions(rows,size){for(const row of rows){if(!Array.isArray(row)||row.length!==2)throw new TypeError('transition shape');row.forEach(x=>integer(x,0,size-1,'transition'));}}
 transitions(raw.transitions,N);transitions(q.transitions,K);q.class_of.forEach(x=>integer(x,0,K-1,'class'));
 integer(q.start,0,K-1,'start');integer(raw.start,0,N-1,'raw start');
 if(raw.accepting.some(x=>typeof x!=='boolean')||q.accepting.some(x=>typeof x!=='boolean')||q.accepting[q.start])throw new TypeError('acceptance contract');
 const coefficients=data.coefficients.map(row=>{if(!Array.isArray(row)||row.length!==K)throw new TypeError('coefficient shape');return row.map(x=>{if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError('coefficient');return BigInt(x);});});
 if(data.separation_pairs.length!==N*(N-1)/2)throw new TypeError('pair count');
 const pairs=new Map();let at=0;
 for(let a=0;a<N;a++)for(let b=a+1;b<N;b++){
  const p=data.separation_pairs[at++];if(p.left!==a||p.right!==b)throw new TypeError('pair order');
  if(p.length===null){if(p.suffix!==null)throw new TypeError('equivalence row');}
  else {integer(p.length,0,N*N,'separator length');word(p.suffix);if(p.suffix.length!==p.length)throw new TypeError('separator length mismatch');}
  pairs.set(a*N+b,p);
 }
 if(!Array.isArray(data.grammar.rules)||data.grammar.rule_index.length!==K||data.grammar.start!==q.start||data.grammar.epsilon!==false)throw new TypeError('grammar shape');
 data.grammar.rules.forEach((r,i)=>{if(r.id!==i||!ALPHABET.includes(r.terminal))throw new TypeError('rule');integer(r.from,0,K-1,'rule source');if(r.tail!==null)integer(r.tail,0,K-1,'rule tail');});
 const work={raw_states_indexed:N,quotient_states_indexed:K,pair_rows_indexed:pairs.size,coefficient_cells_indexed:(L+1)*K,queries:0,transition_lookups:0,coefficient_lookups:0,separator_lookups:0,rule_lookups:0,rank_additions:0,selection_steps:0,raw_transitions_built:0,separation_pairs_built:0,coefficient_cells_built:0};
 function step(state,symbol){work.transition_lookups++;return q.transitions[state][symbol==='a'?0:1];}
 function count(k,state){work.coefficient_lookups++;return coefficients[k][state];}
 function trace(w){let state=q.start;const path=[state];for(const symbol of w){state=step(state,symbol);path.push(state);}return {state,path,accepted:q.accepting[state]};}
 function derivation(w,path,accepted){if(!accepted||w.length===0)return null;return [...w].map((symbol,i)=>{work.rule_lookups++;return data.grammar.rule_index[path[i]][symbol==='a'?0:1][i===w.length-1?'finish':'continue'];});}
 function select(length,rank){
  integer(length,0,L,'length');let r=natural(rank),state=q.start;const total=count(length,state);if(r>=total)throw new RangeError('rank outside language');
  const original=r.toString(),decisions=[],path=[state];let w='';
  for(let i=0;i<length;i++){
   const targetA=step(state,'a'),left=count(length-i-1,targetA),before=r.toString();let symbol,target;
   if(r<left){symbol='a';target=targetA;}else{r-=left;symbol='b';target=step(state,'b');}
   decisions.push({position:i,state,a_count:left.toString(),rank_before:before,symbol,rank_after:r.toString(),next:target});
   w+=symbol;state=target;path.push(state);work.selection_steps++;
  }
  return {length,rank:original,total:total.toString(),word:w,accepted:q.accepting[state],states:path,decisions,derivation:derivation(w,path,q.accepting[state])};
 }
 return Object.freeze({
  summary(){work.queries++;return {first_bound:B,horizon:L,raw_states:N,quotient_states:K,pair_rows:pairs.size,grammar_rules:data.grammar.rules.length,count_at_horizon:count(L,q.start).toString(),construction_work:clone(data.work)};},
  rawState(id){work.queries++;integer(id,0,N-1,'raw state');return {state:clone(raw.states[id]),transitions:raw.transitions[id].slice(),quotient:q.class_of[id]};},
  quotient(){work.queries++;return clone(q);},
  grammar(){work.queries++;return clone(data.grammar);},
  distinguish(a,b){work.queries++;integer(a,0,N-1,'left');integer(b,0,N-1,'right');work.separator_lookups++;if(a===b)return {left:a,right:b,equivalent:true,length:null,suffix:null};const p=pairs.get(Math.min(a,b)*N+Math.max(a,b));return {...clone(p),equivalent:p.length===null};},
  pairPage(start=0,limit=16){work.queries++;integer(start,0,data.separation_pairs.length,'start');integer(limit,0,LIMITS.page,'limit');return {start,total:data.separation_pairs.length,rows:clone(data.separation_pairs.slice(start,start+limit))};},
  counts(){work.queries++;return coefficients.map((row,length)=>({length,count:row[q.start].toString()}));},
  count(length,prefix=''){work.queries++;integer(length,0,L,'length');word(prefix);if(prefix.length>length)return {length,prefix,count:'0',state:null};const t=trace(prefix);return {length,prefix,state:t.state,states:t.path,count:count(length-prefix.length,t.state).toString()};},
  membership(w){work.queries++;word(w);const t=trace(w);return {word:w,...t,derivation:derivation(w,t.path,t.accepted)};},
  rank(w){
   work.queries++;word(w);integer(w.length,0,L,'word length');let state=q.start,rank=0n;const path=[state],decisions=[];
   for(let i=0;i<w.length;i++){
    const a=step(state,'a'),less=w[i]==='b'?count(w.length-i-1,a):0n;if(w[i]==='b'){rank+=less;work.rank_additions++;}
    const next=w[i]==='a'?a:step(state,'b');decisions.push({position:i,state,symbol:w[i],smaller_count:less.toString(),insertion_rank:rank.toString(),next});state=next;path.push(state);
   }
   const accepted=q.accepting[state];return {word:w,accepted,rank:accepted?rank.toString():null,insertion_rank:rank.toString(),states:path,decisions,derivation:derivation(w,path,accepted)};
  },
  select(length,rank){work.queries++;return select(length,rank);},
  page(length,start=0,limit=8){work.queries++;integer(length,0,L,'length');const r=natural(start),total=count(length,q.start);integer(limit,0,LIMITS.word_page,'limit');if(r>total)throw new RangeError('page start');const rows=[];for(let i=0;i<limit&&r+BigInt(i)<total;i++)rows.push(select(length,r+BigInt(i)));return {length,start:r.toString(),total:total.toString(),rows};},
  work(){return clone(work);}
 });
}
module.exports={SCHEMA,LIMITS,buildIndex,openIndex};
