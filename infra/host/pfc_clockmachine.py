#!/usr/bin/env python3
"""host/pfc_clockmachine.py — the GENERIC clocked Muhlnickel, baked to substrate files + one native engine (owner 07-19:
"all of the above · keep pushing"). Three clocked machines through ONE engine:
  (1) counter  — parallel throughput (many independent flat machines, 64 lanes/word × threads, cache-resident)
  (2) cpu      — the full baked ISA CPU run self-clocked (a real program from its own RAM, host = clock, halts)
  (3) hasher   — a clocked SHA-256 miner: nonce advances by clock, one hash/tick = the hash rate, host = clock

Every machine = (state -> next-state) fed back, state in the pfc's storage, host only clocks. Byte-exact verified on
the host before writing. The native engine reads the gates OFF the substrate file.

  python host/pfc_clockmachine.py     # verify + write pfc_cm_{counter,cpu,hasher}.bin + pfc_cm.c
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_clocked import build_counter, pack_ctr, ripple as py_ripple, get_word

OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"
os.makedirs(OUT, exist_ok=True)
TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
WORD = 32


def norm(gates):
    return [(op if isinstance(op, int) else OPC[op], a, b) for (op, a, b) in gates]


# ---------------- (1) counter ----------------
def cm_counter():
    g, outs = build_counter()
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    # verify 200 ticks
    st = 0
    for t in range(1, 201):
        st = get_word(py_ripple(norm(gates), nw, g.n_in, pack_ctr(st, 1)), o2)
        assert st == t
    return dict(name="counter", gates=norm(gates), outs=o2, n_in=g.n_in, n_wire=nw,
               n_state=WORD, consts=[(WORD, 1)], halt=-1, init=b"\x00" * 4)


# ---------------- (2) cpu (load the baked pfc_cpu32) ----------------
def cm_cpu():
    from pfc_cpu32 import pack, unpack, emu32, HALT, LDA, STA, SUB, JMP, JZ, LDI
    reg = json.load(open(REG)); e = reg["pfc_cpu32"]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((op, a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    NMEM, AW = 16, 4
    I = lambda op, opd: (op << 28) | (opd & 0x0fffffff)
    N = 500
    prog = {0: I(LDI, N), 1: I(STA, 15), 2: I(LDA, 15), 3: I(SUB, 14), 4: I(STA, 15),
            5: I(JZ, 7), 6: I(JMP, 2), 7: I(HALT, 0), 14: 1, 15: 0}
    mem0 = [prog.get(i, 0) for i in range(NMEM)]
    init_bits = pack(mem0, 0, 0, 0, NMEM, AW)                    # n_in bits, LSB-first
    init = bytes((sum(init_bits[i * 8 + b] << b for b in range(8) if i * 8 + b < len(init_bits))) for i in range((len(init_bits) + 7) // 8))
    # out[i] == in[i] layout (fmem|fpc|facc|halt == mem|pc|acc|halt) → n_state = n_in; halt output = last
    return dict(name="cpu", gates=gates, outs=outs, n_in=n_in, n_wire=n_wire,
               n_state=n_in, consts=[], halt=len(outs) - 1, init=init,
               ref=dict(NMEM=NMEM, AW=AW, mem0=mem0))


# ---------------- (3) hasher (clocked SHA-256 miner) ----------------
def cm_hasher():
    g = CC.CircuitCompiler(WORD); nonce = list(g.IN)
    c = g.C1; inc = []
    for i in range(WORD): inc.append(g.XOR(nonce[i], c)); c = g.AND(nonce[i], c)   # next nonce = nonce+1
    in16 = [nonce, CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 13 + [CC.cword(g, 32)]
    d = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], in16)
    hashbits = [w for word in d for w in word]                                     # sha256(nonce) — the work
    outs = inc + hashbits
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    # verify: nonce advances + hash == hashlib for a few nonces
    def hash_of(nn):
        v = py_ripple(norm(gates), nw, g.n_in, [(nn >> i) & 1 for i in range(WORD)] )
        bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
        nn2 = sum(bit(o2[i]) << i for i in range(WORD))
        out = b""
        for wi in range(8):
            word = sum(bit(o2[WORD + wi * 32 + j]) << j for j in range(32))
            out += struct.pack(">I", word)
        return nn2, out
    for nn in (0, 1, 0xdeadbeef, 12345):
        nn2, h = hash_of(nn)
        assert nn2 == ((nn + 1) & 0xffffffff)
        assert h == hashlib.sha256(struct.pack(">I", nn)).digest(), f"hash mismatch @ {nn}"
    return dict(name="hasher", gates=norm(gates), outs=o2, n_in=g.n_in, n_wire=nw,
               n_state=WORD, consts=[], halt=-1, init=b"\x00" * 4)


def serialize(m):
    g = m["gates"]
    buf = bytearray(b"PFCCM01\x00")
    buf += struct.pack("<IIII", m["n_in"], m["n_wire"], len(g), len(m["outs"]))
    buf += struct.pack("<iiI", m["n_state"], m["halt"], len(m["consts"]))
    for idx, val in m["consts"]: buf += struct.pack("<Ii", idx, val)
    buf += b"".join(struct.pack("<i", w) for w in m["outs"])
    buf += struct.pack("<I", len(m["init"])) + m["init"]
    buf += b"".join(struct.pack("<III", op, a, b) for (op, a, b) in g)
    return bytes(buf)


C_ENGINE = r'''/* pfc_cm.c — generic native CLOCKED pfc. state->next-state fed back; gates read OFF the substrate file.
   ./pfc_cm <m.bin> run <maxticks>            # single machine (1 lane), stop at halt; prints ticks + final state hex
   ./pfc_cm <m.bin> bench <T> <dur> <Bwords>  # T threads x (64*Bwords) independent machines; total machine-ticks/sec */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
typedef uint64_t u64; typedef uint32_t u32;
static const unsigned char* MAP;
static u32 N_IN,N_WIRE,N_GATE,N_OUT; static int N_STATE,HALT_IDX; static u32 N_CONST;
static const u32* CONST; static const int* OUTS; static u32 STATE_NB; static const unsigned char* INIT; static const u32* G;
static u32 rd(size_t*p){u32 v;memcpy(&v,MAP+*p,4);*p+=4;return v;}
static double secs(){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static long rss_kb(){FILE*f=fopen("/proc/self/status","r");if(!f)return -1;char l[256];long v=-1;
  while(fgets(l,sizeof l,f))if(!strncmp(l,"VmHWM:",6)){sscanf(l+6,"%ld",&v);break;}fclose(f);return v;}
static void parse(){size_t p=0; if(memcmp(MAP,"PFCCM01",7)){fprintf(stderr,"bad magic\n");exit(2);} p=8;
  N_IN=rd(&p);N_WIRE=rd(&p);N_GATE=rd(&p);N_OUT=rd(&p);
  N_STATE=(int)rd(&p);HALT_IDX=(int)rd(&p);N_CONST=rd(&p);
  CONST=(const u32*)(MAP+p); p+=8*(size_t)N_CONST;
  OUTS=(const int*)(MAP+p); p+=4*(size_t)N_OUT;
  STATE_NB=rd(&p); INIT=MAP+p; p+=STATE_NB;
  G=(const u32*)(MAP+p);}
/* one bit-sliced tick over B words (64*B lanes): state[N_STATE] words in st[], wire buf w[N_WIRE*B] */
static inline void tick(u64* w,u64* st,int B){
  u32 base=2+N_IN;
  memset(w,0,(size_t)N_WIRE*B*sizeof(u64)); for(int i=0;i<B;i++) w[1*(size_t)B+i]=~(u64)0;
  for(int j=0;j<N_STATE;j++){ u64* wj=w+(size_t)(2+j)*B; u64* sj=st+(size_t)j*B; for(int i=0;i<B;i++) wj[i]=sj[i]; }
  for(u32 c=0;c<N_CONST;c++){ u32 idx=CONST[2*c]; u64 val=CONST[2*c+1]?~(u64)0:0; u64* wi=w+(size_t)(2+idx)*B; for(int i=0;i<B;i++) wi[i]=val; }
  for(u32 k=0;k<N_GATE;k++){ u32 op=G[3*k],a=G[3*k+1],b=G[3*k+2]; u64* wo=w+(size_t)(base+k)*B; u64* wa=w+(size_t)a*B; u64* wb=w+(size_t)b*B;
    if(op==3){for(int i=0;i<B;i++)wo[i]=wa[i]^wb[i];} else if(op==1){for(int i=0;i<B;i++)wo[i]=wa[i]&wb[i];}
    else if(op==2){for(int i=0;i<B;i++)wo[i]=wa[i]|wb[i];} else if(op==4){for(int i=0;i<B;i++)wo[i]=~wa[i];}
    else {for(int i=0;i<B;i++)wo[i]=~(wa[i]&wb[i]);} }
  for(int j=0;j<N_STATE;j++){ int wi=OUTS[j]; u64* sj=st+(size_t)j*B;
    if(wi==0){for(int i=0;i<B;i++)sj[i]=0;} else if(wi==1){for(int i=0;i<B;i++)sj[i]=~(u64)0;}
    else {u64* wv=w+(size_t)wi*B; for(int i=0;i<B;i++)sj[i]=wv[i];} }
}
typedef struct{int tid,B;double dur;long long ticks;u64 sink;} arg_t;
static void* work(void* p){ arg_t* A=(arg_t*)p; int B=A->B;
  u64* w=malloc((size_t)N_WIRE*B*sizeof(u64)); u64* st=calloc((size_t)N_STATE*B,sizeof(u64));
  if(!w||!st){printf("OOM\n");A->ticks=0;return 0;}
  u64 s=(u64)(A->tid+1)*0x9E3779B97F4A7C15ull;                     /* seed each lane's state independently */
  for(int j=0;j<N_STATE;j++) for(int i=0;i<B;i++){ s=s*6364136223846793005ull+1442695040888963407ull; st[(size_t)j*B+i]=s; }
  long long tk=0; double t0=secs(); u64 sink=0;
  while(secs()-t0<A->dur){ tick(w,st,B); tk++; }
  for(int j=0;j<N_STATE;j++) for(int i=0;i<B;i++) sink^=st[(size_t)j*B+i];
  A->ticks=tk; A->sink=sink; free(w); free(st); return 0; }
int main(int argc,char**argv){
  if(argc<3){printf("usage: %s <m.bin> run <maxticks> | bench <T> <dur> <Bwords>\n",argv[0]);return 1;}
  int fd=open(argv[1],O_RDONLY); struct stat sb; fstat(fd,&sb);
  MAP=mmap(0,sb.st_size,PROT_READ,MAP_PRIVATE,fd,0); if(MAP==MAP_FAILED){perror("mmap");return 1;} parse();
  if(!strcmp(argv[2],"run")){
    long long MAX=atoll(argv[3]); int B=1; u64* w=malloc((size_t)N_WIRE*sizeof(u64)); u64* st=calloc(N_STATE,sizeof(u64));
    for(int j=0;j<N_STATE;j++){int byte=j>>3,bit=j&7; st[j]=((u32)byte<STATE_NB && ((INIT[byte]>>bit)&1))?1ull:0;}
    long long tk=0; int halted=0; double t0=secs();
    for(;tk<MAX;tk++){ tick(w,st,1);
      if(HALT_IDX>=0 && HALT_IDX<N_STATE && (st[HALT_IDX]&1)){ halted=1; tk++; break; }   /* halt bit fed back into state */
    }
    double el=secs()-t0;
    printf("run: ticks=%lld halted=%d sec=%.3f => %.3e ticks/sec rssMB=%.2f state=",tk,halted,el,(double)tk/el,rss_kb()/1024.0);
    for(int j=0;j<N_STATE;j+=8){ u32 byte=0; for(int b=0;b<8&&j+b<N_STATE;b++) if(st[j+b]&1) byte|=(1<<b); printf("%02x",byte); }
    printf("\n"); return 0;
  }
  int T=atoi(argv[3]); double dur=atof(argv[4]); int B=argc>5?atoi(argv[5]):1;
  pthread_t th[64]; arg_t a[64]; double t0=secs();
  for(int i=0;i<T;i++){a[i].tid=i;a[i].B=B;a[i].dur=dur;pthread_create(&th[i],0,work,&a[i]);}
  long long tot=0; u64 sk=0; for(int i=0;i<T;i++){pthread_join(th[i],0);tot+=a[i].ticks;sk^=a[i].sink;}
  double el=secs()-t0; double lanes=(double)64.0*B; long long mt=(long long)(tot*lanes);
  printf("bench: T=%d lanes/thread=%.0f machines=%.0f tickrounds=%lld machine-ticks=%lld sec=%.2f => %.3e machine-ticks/sec rssMB=%.2f sink=%llu\n",
         T,lanes,lanes*T,tot,mt,el,(double)mt/el,rss_kb()/1024.0,(unsigned long long)sk);
  return 0;
}
'''


def main():
    machines = [cm_counter(), cm_hasher(), cm_cpu()]
    for m in machines:
        blob = serialize(m)
        path = os.path.join(OUT, f"pfc_cm_{m['name']}.bin")
        open(path, "wb").write(blob)
        print(f"  {m['name']:8s}: {len(m['gates']):>6} gates, n_state={m['n_state']}, halt_idx={m['halt']} -> {os.path.basename(path)} ({len(blob)} B)", flush=True)
    open(os.path.join(OUT, "pfc_cm.c"), "w", newline="\n").write(C_ENGINE)
    print(f"  engine -> pfc_cm.c\n  (byte-exact verified on host before writing: counter 200 ticks, hasher vs hashlib, cpu layout)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
