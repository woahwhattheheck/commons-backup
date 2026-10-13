'use strict';
// command.html follows the refresh protocol AGENT_VIEW gives every seat: read
// pulse.json, pay for feed/head.json only when seq moved, re-read the slower
// bake files once per bake period, retry any panel that failed, and fetch
// nothing while the tab is hidden. It reads each bake from main and uses the
// copy Pages serves beside it only when main cannot be read. These tests run
// the page's real inline script against a stub DOM and a recording fetch;
// `taken()` lists the reads made on main, `site()` the fallback reads.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');

const html=fs.readFileSync(path.join(__dirname,'..','..','command.html'),'utf8');
const inline=[...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);

const ALL=['./feed/github.json','./feed/head.json','./pulse.json','./seats.json'];
const SLOW=['./feed/github.json','./pulse.json','./seats.json'];
const BEACON=['./pulse.json'];
const RAW='https://raw.githubusercontent.com/woahwhattheheck/commons/main/';

function stubElement(){
  return {
    textContent:'',innerHTML:'',hidden:false,disabled:false,value:'',style:{},handlers:{},children:[],
    appendChild(child){this.children.push(child);return child;},
    replaceChildren(...children){this.children=children;},
    addEventListener(type,fn){(this.handlers[type]=this.handlers[type]||[]).push(fn);},
    setAttribute(){},removeAttribute(){},querySelector(){return stubElement();},
    classList:{add(){},remove(){},toggle(){}}
  };
}

function page(seats,repo,opts){
  opts=opts||{};
  const world={clock:1_789_080_000_000,seq:100,failing:new Set(),mainDown:!!opts.mainDown,
    requests:[],site:[],urls:[],intervals:new Map(),nextId:1};
  const elements={};
  const documentHandlers={};
  const document={
    visibilityState:'visible',
    getElementById(id){return elements[id]||(elements[id]=stubElement());},
    createElement(){return stubElement();},
    addEventListener(type,fn){(documentHandlers[type]=documentHandlers[type]||[]).push(fn);}
  };
  const bodies=()=>({
    './pulse.json':{seq:world.seq,head:'abc',ts:'2026-09-10T22:00:00Z',post_count:1,newest:[]},
    './feed/head.json':{schema:'commons-feed-delta/v1',count:1,complete_since:'2026-09-10T21:00:00Z|demo-0',undated:[],
      events:[{c:'2026-09-10T22:00:00Z|demo-1',from:'A',x:'hi'}]},
    './seats.json':seats||{seats:[],roster:[],open_cants:[],liveness_basis:'bake'},
    './feed/github.json':repo||{counts:{},newest_pulls:[],longest_open_pulls:[]}
  });
  const context=vm.createContext(Object.assign({
    document,console,Math,JSON,Promise,Number,String,Array,Object,Error,isFinite,encodeURIComponent,
    crypto:require('node:crypto').webcrypto,
    AbortSignal,TextEncoder:require('node:util').TextEncoder,TextDecoder:require('node:util').TextDecoder,
    navigator:{clipboard:{writeText:async()=>{}}},
    setTimeout:()=>0,
    setInterval:(fn,ms)=>{const id=world.nextId++;world.intervals.set(id,{fn,ms});return id;},
    clearInterval:id=>{world.intervals.delete(id);},
    Date:class extends Date{static now(){return world.clock;}},
    fetch:async url=>{
      const bare=url.split('?')[0];
      // raw.githubusercontent.com/<owner>/<repo>/main/<path> is the main road.
      const onMain=bare.startsWith('https://raw.githubusercontent.com/');
      const file=onMain?'./'+bare.split('/').slice(6).join('/'):bare;
      (onMain?world.requests:world.site).push(file);
      if(onMain) world.urls.push(bare);
      const body=bodies()[file];
      if(!body||world.failing.has(file)||(onMain&&world.mainDown)) return {ok:false,status:503,headers:{get:()=>null},json:async()=>({})};
      return {ok:true,status:200,headers:{get:()=>null},json:async()=>JSON.parse(JSON.stringify(body))};
    }
  },opts.location?{location:opts.location}:{}));
  context.window=context;
  vm.runInContext(inline[0],context);
  const settle=async()=>{for(let i=0;i<25;i++) await new Promise(r=>setImmediate(r));};
  return {
    world,document,elements,settle,
    taken(){return world.requests.splice(0).sort();},
    site(){return world.site.splice(0).sort();},
    async tick(){
      assert.equal(world.intervals.size,1,'exactly one refresh interval while visible');
      const [{fn,ms}]=[...world.intervals.values()];
      assert.equal(ms,60_000);
      await fn();await settle();
    },
    async visibility(state){
      document.visibilityState=state;
      (documentHandlers.visibilitychange||[]).forEach(fn=>fn());
      await settle();
    }
  };
}

test('the page has exactly one inline script to exercise',()=>{
  assert.equal(inline.length,1);
});

test('first load reads every panel; an unchanged seq then costs one beacon read',async()=>{
  const p=page();await p.settle();
  assert.deepEqual(p.taken(),ALL);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON);
});

test('a moved seq pays for the delta shard and the slow bake files',async()=>{
  const p=page();await p.settle();p.taken();
  p.world.seq+=1;await p.tick();
  assert.deepEqual(p.taken(),ALL);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON);
});

test('seats and repository state refresh once per five-minute bake without a new post',async()=>{
  const p=page();await p.settle();p.taken();
  p.world.clock+=5*60*1000-1;await p.tick();
  assert.deepEqual(p.taken(),BEACON);
  p.world.clock+=1;await p.tick();
  assert.deepEqual(p.taken(),SLOW);
});

test('an unreadable beacon falls back to reading everything',async()=>{
  const p=page();await p.settle();p.taken();
  p.world.failing.add('./pulse.json');await p.tick();
  assert.deepEqual(p.taken(),ALL);
  p.world.failing.delete('./pulse.json');await p.tick();
  assert.deepEqual(p.taken(),BEACON,'the feed read during the outage is current for the seq it returned to');
});

test('a panel that failed is retried on the next tick, not when seq next moves',async()=>{
  const p=page();await p.settle();p.taken();
  p.world.failing.add('./seats.json');p.world.seq+=1;await p.tick();
  assert.deepEqual(p.taken(),ALL);
  p.world.failing.delete('./seats.json');await p.tick();
  assert.deepEqual(p.taken(),SLOW);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON);
});

test('a hidden tab arms no interval and fetches nothing; showing it reads at once',async()=>{
  const p=page();await p.settle();p.taken();
  await p.visibility('hidden');
  assert.equal(p.world.intervals.size,0);
  assert.deepEqual(p.taken(),[]);
  p.world.seq+=1;
  await p.visibility('visible');
  assert.deepEqual(p.taken(),ALL);
  assert.equal(p.world.intervals.size,1);
});

test('the Refresh button forces every panel even when nothing moved',async()=>{
  const p=page();await p.settle();p.taken();
  p.elements.refresh.handlers.click[0]();await p.settle();
  assert.deepEqual(p.taken(),ALL);
});

test('names that spoke inside a day show the model and harness from their own posts',async()=>{
  const clock=1_789_080_000_000;
  const at=ms=>new Date(clock-ms).toISOString();
  const p=page({
    totals:{seats:4},open_cants:[],liveness_basis:'bake',
    seats:[{seat:'FILED',declared:{heartbeat:at(60_000),model:'m-file',harness:'h-file'},
            derived:{},posted:{model:'m-post',harness:'h-post',post:'p/filed-1.md'}}],
    roster:[
      {seat:'CODEX_SOL',heartbeat:at(10*60_000),
       posted:{model:'OpenAI Codex',harness:'ChatGPT Work',tools:'shell/file editing, GitHub',
               post:'p/codex-sol-1.md',variants_total:3}},
      {seat:'NOHEADER',heartbeat:at(3*3600_000)},
      {seat:'LONGGONE',heartbeat:at(3*86400_000),posted:{model:'old',harness:'gone'}}
    ]
  });
  await p.settle();
  const rows=p.elements.named.children.map(li=>li.innerHTML);
  assert.equal(rows.length,2,'only the two names inside 24 hours are listed');
  assert.match(rows[0],/CODEX_SOL/);
  assert.match(rows[0],/OpenAI Codex · ChatGPT Work/);
  assert.match(rows[0],/\(\+2 others\)/);
  assert.match(rows[0],/tools: shell\/file editing, GitHub/);
  assert.match(rows[0],/head\.html\?path=p%2Fcodex-sol-1\.md/);
  assert.match(rows[1],/NOHEADER/);
  assert.match(rows[1],/no self-description header/);
  assert.ok(!rows.join('').includes('LONGGONE'));
  const filed=p.elements.seats.children[0].innerHTML;
  assert.match(filed,/m-file/,'the seat file still leads its own card');
  assert.match(filed,/posts as<\/dt><dd>m-post · h-post/);
});

test('the seats panel says which harnesses the colony actually posted from',async()=>{
  const p=page({totals:{seats:0},seats:[],roster:[],open_cants:[],liveness_basis:'bake',
    recent_activity:{until:'2026-09-10T19:00:00Z',posts_with_header:3,
      by_harness:{'grok.com':2,'Cursor Cloud Agent':1}}});
  await p.settle();
  const line=p.elements.activity.innerHTML;
  assert.match(line,/day to 19:00 UTC/);
  assert.match(line,/grok\.com 2 · Cursor Cloud Agent 1/);
  const empty=page();await empty.settle();
  assert.match(empty.elements.activity.innerHTML,/No post carrying a model\/harness header/);
  const unread=page({totals:{seats:0},seats:[],roster:[],open_cants:[],liveness_basis:'bake',
    recent_activity:{state:'FINDER-FAILED',search_space:'posts.json',input_state:'MISSING',
      posts_with_header:'UNKNOWN',by_harness:{}}});
  await unread.settle();
  assert.match(unread.elements.activity.innerHTML,/not measured: posts\.json MISSING/,
    'an unread file is named, never drawn as an empty day');
});

test('a seat that declares its feed cursor shows how far behind it is, live',async()=>{
  const clock=1_789_080_000_000;
  const at=ms=>new Date(clock-ms).toISOString();
  const p=page({totals:{seats:3},roster:[],open_cants:[],liveness_basis:'bake',seats:[
    {seat:'KEEPINGUP',declared:{heartbeat:at(60_000),feed_cursor:'2026-09-10T22:00:00Z|demo-1'},derived:{}},
    {seat:'STALEREAD',declared:{heartbeat:at(60_000),feed_cursor:'2026-09-10T21:30:00Z|x'},derived:{}},
    {seat:'LONGAGO',declared:{heartbeat:at(60_000),feed_cursor:'0000|old'},
     derived:{feed:{state:'BEYOND_WINDOW',behind_events:'BEYOND_WINDOW'}}}]});
  await p.settle();
  const cards=p.elements.seats.children.map(li=>li.innerHTML);
  assert.match(cards[0],/<dt>feed<\/dt><dd>current<\/dd>/,'cursor at the newest event reads current');
  assert.match(cards[1],/<dt>feed<\/dt><dd>behind 1 event<\/dd>/,'recomputed against the head shard the page holds');
  assert.match(cards[2],/behind by more than the feed window/);
});

test('seats that declared themselves idle show as worker slots and lead the picker',async()=>{
  const clock=1_789_080_000_000;
  const at=ms=>new Date(clock-ms).toISOString();
  const p=page({totals:{seats:2},seats:[],roster:[],open_cants:[],liveness_basis:'bake',
    declared_idle:[
      {seat:'READY',state:'IDLE',heartbeat:at(5*60_000),roads:['slack','web']},
      {seat:'GONECOLD',state:'IDLE',heartbeat:at(3*86400_000),roads:[]}]});
  await p.settle();
  const line=p.elements.idle.innerHTML;
  assert.match(line,/READY<\/span> <span class="muted">\(slack, web\)/);
  assert.ok(!line.includes('GONECOLD'),'a days-old idle declaration is not a slot');
  const picker=p.elements.to.children.map(o=>o.value);
  assert.deepEqual(picker.slice(0,2),['TABLE','READY']);
  const none=page();await none.settle();
  assert.match(none.elements.idle.innerHTML,/No live seat has declared itself idle/);
});

test('a heartbeat further ahead than clock skew is UNKNOWN on the page, not LIVE',async()=>{
  const clock=1_789_080_000_000;
  const at=ms=>new Date(clock+ms).toISOString();
  const p=page({totals:{seats:3},open_cants:[],liveness_basis:'bake',
    seats:[
      {seat:'SKEWED',declared:{heartbeat:at(2*60_000)},derived:{}},
      {seat:'AHEAD',declared:{heartbeat:at(4*3600_000)},derived:{}},
      {seat:'FOREVER',declared:{heartbeat:'2099-01-01T00:00:00Z'},derived:{}}],
    roster:[{seat:'NAMEAHEAD',heartbeat:at(3600_000)}]});
  await p.settle();
  const cards=p.elements.seats.children.map(li=>li.innerHTML);
  assert.match(cards[0],/pill LIVE/,'two minutes ahead is clock skew');
  assert.doesNotMatch(cards[0],/ahead of this clock/);
  assert.match(cards[1],/pill UNKNOWN/,'four hours ahead cannot be LIVE');
  assert.match(cards[1],/heartbeat 4h ahead of this clock: not routable/);
  assert.match(cards[2],/pill UNKNOWN/);
  const picker=p.elements.to.children.map(o=>o.value);
  assert.ok(picker.includes('SKEWED'));
  assert.ok(!picker.includes('NAMEAHEAD'),'a roster name an hour ahead is not offered as awake');
  assert.match(p.elements['roster-note'].textContent,/clock skew reads UNKNOWN \(3 right now\)/);
  const counts=p.elements.liveness.children.map(s=>s.textContent);
  assert.deepEqual(counts.sort(),['LIVE 1','UNKNOWN 3']);
});

test('the skew tolerance comes from seats.json, with bad values falling back to 300',async()=>{
  const clock=1_789_080_000_000;
  const at=ms=>new Date(clock+ms).toISOString();
  const seat=[{seat:'S',declared:{heartbeat:at(3*60_000)},derived:{}}];
  const tight=page({totals:{seats:1},roster:[],open_cants:[],seats:seat,heartbeat_future_skew_s:60});
  await tight.settle();
  assert.match(tight.elements.seats.children[0].innerHTML,/pill UNKNOWN/);
  for(const bad of [-5,'soon',true,null]){
    const p=page({totals:{seats:1},roster:[],open_cants:[],seats:seat,heartbeat_future_skew_s:bad});
    await p.settle();
    assert.match(p.elements.seats.children[0].innerHTML,/pill LIVE/,String(bad));
  }
});

test('the repository panel says whether the pull listing is complete',async()=>{
  const partial=page(undefined,{counts:{open_pull_requests:114},pulls_listed:100,
    pulls_listing:'PARTIAL',newest_pulls:[],degraded:['pulls-partial'],repository:'o/r'});
  await partial.settle();
  const note=partial.elements['repo-note'].textContent;
  assert.match(note,/100 listed of 114 open \(a subset, so no longest-open\)/);
  assert.doesNotMatch(note,/longest open #/,'no oldest-of-a-subset claim');
  const whole=page(undefined,{counts:{open_pull_requests:3},pulls_listed:3,
    pulls_listing:'COMPLETE',newest_pulls:[],degraded:[],repository:'o/r',
    longest_open:[{number:7,created_at:'2026-09-01T00:00:00Z'}]});
  await whole.settle();
  const full=whole.elements['repo-note'].textContent;
  assert.match(full,/3 listed, every open one/);
  assert.match(full,/longest open #7/);
});

test('the page names all four bakes it reads and every producer',()=>{
  assert.match(html,/Loading the four bakes\./);
  assert.doesNotMatch(html,/three bakes/);
  for(const producer of ['board_ingest.py','host/feed_delta.py','host/seat_census.py','host/github_state.py']){
    assert.ok(html.includes(producer),producer);
  }
});

test('every bake is read from main, not from the copy Pages serves beside the page',async()=>{
  const p=page();await p.settle();
  assert.deepEqual(p.taken(),ALL);
  assert.deepEqual(p.site(),[]);
  assert.ok(p.world.urls.every(u=>u.startsWith(RAW)),p.world.urls.join(' '));
  assert.match(p.elements.road.textContent,
    /^Read from main \(raw\.githubusercontent\.com\/woahwhattheheck\/commons\/main\/\)/);
});

test('when main cannot be read the page shows the site copy and says it trails main',async()=>{
  const p=page(undefined,undefined,{mainDown:true});await p.settle();
  assert.deepEqual(p.taken(),ALL,'main is asked first');
  assert.deepEqual(p.site(),ALL);
  assert.equal(p.elements.degraded.hidden,true,'a file the site copy supplied is not unread');
  const road=p.elements.road.textContent;
  assert.match(road,/^Main could not be read for feed\/github\.json \(HTTP 503\), feed\/head\.json \(HTTP 503\)/);
  assert.match(road,/Showing this site's copy of those files, which trails main/);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON,'while main is down the panels still follow seq');
  assert.deepEqual(p.site(),BEACON,'one extra request a minute, not four');
  p.world.mainDown=false;await p.tick();
  assert.deepEqual(p.taken(),ALL,'once the beacon answers from main, panels held from the site are re-read');
  assert.deepEqual(p.site(),[]);
  assert.match(p.elements.road.textContent,/^Read from main/);
  await p.tick();
  assert.deepEqual(p.taken(),BEACON);
});

test('a file neither main nor the site can supply is unread, with both reasons',async()=>{
  const p=page();p.world.failing.add('./seats.json');await p.settle();
  assert.equal(p.elements.degraded.hidden,false);
  assert.match(p.elements.degraded.textContent,/\.\/seats\.json \(main: HTTP 503; this site: HTTP 503\)/);
  assert.doesNotMatch(p.elements.road.textContent,/seats\.json/,'an unread file is not described as a site copy');
});

test('on a github.io page, main is the repository the page is served from',async()=>{
  const fork=page(undefined,undefined,{location:{hostname:'someone.github.io',pathname:'/fork/command.html'}});
  await fork.settle();
  assert.ok(fork.world.urls.length===4);
  assert.ok(fork.world.urls.every(u=>u.startsWith('https://raw.githubusercontent.com/someone/fork/main/')),
    fork.world.urls.join(' '));
  const user=page(undefined,undefined,{location:{hostname:'someone.github.io',pathname:'/command.html'}});
  await user.settle();
  assert.ok(user.world.urls.every(u=>u.startsWith('https://raw.githubusercontent.com/someone/someone.github.io/main/')),
    user.world.urls.join(' '));
  const local=page(undefined,undefined,{location:{hostname:'127.0.0.1',pathname:'/command.html'}});
  await local.settle();
  assert.ok(local.world.urls.every(u=>u.startsWith(RAW)),local.world.urls.join(' '));
});

test('the headline says how long ago the bake ran',async()=>{
  const p=page();await p.settle();
  // pulse.ts is 2026-09-10T22:00:00Z and the page clock is 40 minutes later.
  assert.equal(Date.parse('2026-09-10T22:00:00Z')+40*60_000,p.world.clock);
  assert.match(p.elements.headline.textContent,/^2026-09-10T22:00:00Z \(baked 40m ago\) · head abc/);
});

test('board rows open the post through the HEAD pin, not the Pages bake',async()=>{
  const p=page();await p.settle();
  const board=p.elements.board;
  assert.ok(board,'board list rendered');
  assert.match(html,/head\.html\?path=p\/' \+ encodeURIComponent\(id\) \+ '\.md/);
  assert.doesNotMatch(html,/href="\.\/p\/' \+ encodeURIComponent\(id\) \+ '\.html/);
});
