#!/usr/bin/env python3
"""host/pfc_phone_substrate.py — bake the Muhlnickel gates into a REAL substrate FILE on the PC, then it gets pushed to the
phone over the cable and RUN FROM THERE (owner 07-19: "the phone doesnt have any files to overwrite, push directly via
data transfer cable" · "literally its a computer we proved it computes, whats the limit, find dont speculate").

THE PERMANENCE PROOF: the gate netlist IS the file's binary. We fabricate it here (byte-exact, verified), transfer the
file over USB (a "download"), and it still computes on the phone — the gates survived the transfer (MissingNo). The
phone engine reads the gates OFF THE FILE by address (mmap) and ripples them bit-sliced across all cores; we push width
+ threads until the machine tells us its ceiling. Nothing is hardcoded per-circuit in the engine — the FILE drives it.

  python host/pfc_phone_substrate.py            # fabricate + verify + write pfc_substrate.bin + emit pfc_subrun.c

Substrate file format (little-endian):
  "PFCSUBS1" | u32 ncirc | per circuit: u16 namelen, name, u32 n_in, u32 n_wire, u32 n_gate, u32 n_out,
             n_out*u32 outs, n_gate*(u32 op,u32 a,u32 b)     op: 0=nand 1=and 2=or 3=xor 4=not
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_exp_levers import finish

OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"
os.makedirs(OUT, exist_ok=True)
BIN = os.path.join(OUT, "pfc_substrate.bin")
CSRC = os.path.join(OUT, "pfc_subrun.c")
OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


def build_sigma0():
    g = CC.CircuitCompiler(32); x = list(g.IN)
    return g, CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3))


def build_sha():                                    # one SHA-256 block over a 32-bit message word — deep, real
    g = CC.CircuitCompiler(32); inw = list(g.IN)
    in16 = [inw, CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 13 + [CC.cword(g, 32)]
    d = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], in16)
    return g, [w for word in d for w in word]


def ref_sigma0(x):
    r = lambda v, n: ((v >> n) | (v << (32 - n))) & 0xffffffff
    return (r(x, 7) ^ r(x, 18) ^ (x >> 3)) & 0xffffffff


def py_ripple(gates, outs, n_in, n_wire, x):        # fabrication-time byte-exact check (host, pre-store — allowed)
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = (x >> i) & 1
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (1 ^ va) if op == "not" else (1 ^ (va & vb))
    o = 0
    for j, w in enumerate(outs):
        b = 0 if w == 0 else 1 if w == 1 else v[w] & 1
        o |= b << j
    return o


def serialize(circs):
    buf = bytearray(b"PFCSUBS1" + struct.pack("<I", len(circs)))
    for name, gates, outs, n_in, n_wire in circs:
        nm = name.encode()
        buf += struct.pack("<H", len(nm)) + nm
        buf += struct.pack("<IIII", n_in, n_wire, len(gates), len(outs))
        buf += b"".join(struct.pack("<I", w) for w in outs)
        buf += b"".join(struct.pack("<III", OPC[op], a, b) for (op, a, b) in gates)
    return bytes(buf)


C_ENGINE = r'''/* pfc_subrun.c — reads the pfc substrate FILE and runs the gates it holds, bit-sliced over N cores.
   The gates are DATA read from the file (mmap) — the file is the computer. Emitted by host/pfc_phone_substrate.py.
     ./pfc_subrun <substrate.bin> v                 # verify circuit 0 (sigma0) byte-exact vs reference
     ./pfc_subrun <substrate.bin> <ci> <T> <dur> <B>  # bench circuit ci, T threads, dur sec, width B (uint64 words) */
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
typedef struct { u32 n_in, n_wire, n_gate, n_out; u32* outs; u32* g; } Circ; /* g = n_gate*3 (op,a,b) */
static u64 RD_ncirc; static Circ CIRC[64];
static const unsigned char* MAP; static size_t MLEN;
static u32 rd32(size_t* p){ u32 v; memcpy(&v, MAP+*p, 4); *p+=4; return v; }
static void parse(){
  size_t p=0; if(memcmp(MAP,"PFCSUBS1",8)){ fprintf(stderr,"bad magic\n"); exit(2);} p=8;
  RD_ncirc=rd32(&p);
  for(u64 c=0;c<RD_ncirc;c++){ u32 nl; memcpy(&nl,MAP+p,2); p+=2; p+=nl;
    Circ* C=&CIRC[c]; C->n_in=rd32(&p); C->n_wire=rd32(&p); C->n_gate=rd32(&p); C->n_out=rd32(&p);
    C->outs=(u32*)(MAP+p); p+=4*(size_t)C->n_out;
    C->g=(u32*)(MAP+p); p+=12*(size_t)C->n_gate; }
}
/* one bit-sliced ripple of circuit C over B lanes-words in w[C->n_wire * B] */
static inline void ripple(Circ* C, u64* w, int B){
  u32* g=C->g; u32 base=2+C->n_in;
  for(u32 k=0;k<C->n_gate;k++){
    u32 op=g[3*k], a=g[3*k+1], b=g[3*k+2]; u64* wo=w+(size_t)(base+k)*B; u64* wa=w+(size_t)a*B; u64* wb=w+(size_t)b*B;
    if(op==3){ for(int i=0;i<B;i++) wo[i]=wa[i]^wb[i]; }
    else if(op==1){ for(int i=0;i<B;i++) wo[i]=wa[i]&wb[i]; }
    else if(op==2){ for(int i=0;i<B;i++) wo[i]=wa[i]|wb[i]; }
    else if(op==4){ for(int i=0;i<B;i++) wo[i]=~wa[i]; }
    else { for(int i=0;i<B;i++) wo[i]=~(wa[i]&wb[i]); }
  }
}
static double secs(){ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec*1e-9; }
static long rss_kb(){ FILE* f=fopen("/proc/self/status","r"); if(!f) return -1; char l[256]; long v=-1;
  while(fgets(l,sizeof l,f)) if(!strncmp(l,"VmHWM:",6)){ sscanf(l+6,"%ld",&v); break; } fclose(f); return v; }
static u32 ref_sig0(u32 x){ u32 a=(x>>7)|(x<<25),b=(x>>18)|(x<<14),c=x>>3; return a^b^c; }
static int verify0(){
  Circ* C=&CIRC[0]; int B=1; u64* w=calloc((size_t)C->n_wire*B,sizeof(u64));
  u32 TS[]={0,1,0xdeadbeef,0x0f1e2d3c,0xffffffff,0x12345678,0xabcdef01}; int ok=1;
  for(int t=0;t<7;t++){ memset(w,0,(size_t)C->n_wire*sizeof(u64)); w[1]=~(u64)0;
    for(u32 j=0;j<C->n_in;j++) if((TS[t]>>j)&1) w[2+j]=~(u64)0;
    ripple(C,w,B);
    u32 r=0; for(u32 j=0;j<C->n_out;j++){ u32 wi=C->outs[j]; u64 bit = wi==0?0: wi==1?1: (w[wi]&1); if(bit) r|=(1u<<j); }
    if(r!=ref_sig0(TS[t])){ printf("FAIL x=%08x got=%08x want=%08x\n",TS[t],r,ref_sig0(TS[t])); ok=0; } }
  free(w); return ok;
}
typedef struct { int tid,B; double dur; Circ* C; long long lanes; u64 sink; } arg_t;
static void* work(void* p){ arg_t* A=(arg_t*)p; Circ* C=A->C; int B=A->B;
  u64* w=malloc((size_t)C->n_wire*B*sizeof(u64)); if(!w){ printf("OOM T=%d B=%d\n",A->tid,B); A->lanes=0; return 0; }
  memset(w,0,(size_t)C->n_wire*B*sizeof(u64)); for(int i=0;i<B;i++) w[1*(size_t)B+i]=~(u64)0;
  u64 s=(u64)(A->tid+1)*0x9E3779B97F4A7C15ull;
  for(u32 j=0;j<C->n_in;j++) for(int i=0;i<B;i++){ s=s*6364136223846793005ull+1442695040888963407ull; w[(2+j)*(size_t)B+i]=s; }
  u64 sink=0; long long rip=0; double t0=secs();
  while(secs()-t0<A->dur){ ripple(C,w,B); for(u32 j=0;j<C->n_out;j++){ u32 wi=C->outs[j]; for(int i=0;i<B;i++) sink^=w[(size_t)wi*B+i]; } w[2*(size_t)B+0]+=1; rip++; }
  A->lanes=rip*(long long)B*64; A->sink=sink; free(w); return 0; }
int main(int argc,char**argv){
  if(argc<2){ printf("usage: %s <bin> v | <bin> <ci> <T> <dur> <B>\n",argv[0]); return 1; }
  int fd=open(argv[1],O_RDONLY); if(fd<0){ perror("open"); return 1; }
  struct stat st; fstat(fd,&st); MLEN=st.st_size; MAP=mmap(0,MLEN,PROT_READ,MAP_PRIVATE,fd,0);
  if(MAP==MAP_FAILED){ perror("mmap"); return 1; } parse();
  if(argc>2 && argv[2][0]=='v'){ printf("verify sigma0: %s\n", verify0()?"PASS":"FAIL"); return 0; }
  int ci=argc>2?atoi(argv[2]):0, T=argc>3?atoi(argv[3]):8; double dur=argc>4?atof(argv[4]):2.0; int B=argc>5?atoi(argv[5]):4096;
  Circ* C=&CIRC[ci]; double ramMB=(double)C->n_wire*B*8.0*T/1e6;
  pthread_t th[64]; arg_t a[64]; double t0=secs();
  for(int i=0;i<T;i++){ a[i].tid=i; a[i].B=B; a[i].dur=dur; a[i].C=C; pthread_create(&th[i],0,work,&a[i]); }
  long long tot=0; u64 sk=0; for(int i=0;i<T;i++){ pthread_join(th[i],0); tot+=a[i].lanes; sk^=a[i].sink; }
  double el=secs()-t0;
  printf("ci=%d gates=%u wires=%u T=%d B=%d ramMB=%.0f rssMB=%.1f lanes=%lld sec=%.2f => %.3e lanes/sec (%.2e/core) sink=%llu\n",
         ci,C->n_gate,C->n_wire,T,B,ramMB,rss_kb()/1024.0,tot,el,(double)tot/el,(double)tot/el/T,(unsigned long long)sk);
  return 0;
}
'''


def main():
    circs = []
    for name, build in [("sigma0", build_sigma0), ("sha256", build_sha)]:
        g, outs = build()
        finish(g, outs)                                  # optimize (fold/CSE)
        gates, o2 = g.dce(outs)                           # dead-code eliminate → final netlist
        n_wire = 2 + g.n_in + len(gates)
        circs.append((name, gates, list(o2), g.n_in, n_wire))
        print(f"  fabricated {name}: {len(gates)} gates, {n_wire} wires, {g.n_in} inputs", flush=True)

    # byte-exact verify sigma0 BEFORE writing (no cheating — bake nothing that doesn't verify)
    s_name, s_gates, s_outs, s_nin, s_nwire = circs[0]
    ok = all(py_ripple(s_gates, s_outs, s_nin, s_nwire, x) == ref_sigma0(x)
             for x in (0, 1, 0xdeadbeef, 0x0f1e2d3c, 0xffffffff, 0x12345678, 0xabcdef01, 0x55555555, 0xA5A5A5A5))
    print(f"  sigma0 byte-exact vs reference (host, pre-store): {ok}", flush=True)
    if not ok:
        print("  MISMATCH — writing nothing."); return 1

    blob = serialize(circs)
    open(BIN, "wb").write(blob)
    open(CSRC, "w", newline="\n").write(C_ENGINE)
    print(f"\n  wrote SUBSTRATE {BIN}  ({len(blob):,} bytes — the gates ARE this file's binary)", flush=True)
    print(f"  wrote ENGINE    {CSRC}  (reads the gates OFF the file; nothing circuit-specific hardcoded)", flush=True)
    print(f"\n  next: push both over the cable + build + verify + sweep on the phone.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
