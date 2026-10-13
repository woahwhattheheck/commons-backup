#!/usr/bin/env python3
"""host/pfc_phone_clock.py — bake the CLOCKED Muhlnickel into a substrate file for the phone, + emit a NATIVE self-clocked
engine (owner 07-19: "keep pushing · same way any computer would · ram = signal routing only, everything else pfc").

The PC ran the clocked machine in Python (16k ticks/s counter, 554 ticks/s CPU) — flat footprint, host = clock. This
emits the SAME clocked architecture as native C for the phone's fast cores: the gates are read OFF the substrate file,
the state lives in an mmap'd state file (the pfc's OWN storage), and the loop only advances the clock. Nothing wide in
host RAM → flat footprint; native C lifts the tick rate ~100×.

  python host/pfc_phone_clock.py     # write pfc_clock_sub.bin (the baked counter) + pfc_clockrun.c
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_clocked import build_counter, pack_ctr, ripple, get_word     # reuse the verified clocked counter

OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"
os.makedirs(OUT, exist_ok=True)
BIN = os.path.join(OUT, "pfc_clock_sub.bin"); CSRC = os.path.join(OUT, "pfc_clockrun.c")
OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
WORD = 32


def serialize_one(name, gates, outs, n_in, n_wire):     # PFCSUBS1, single circuit (same format as pfc_subrun)
    buf = bytearray(b"PFCSUBS1" + struct.pack("<I", 1))
    nm = name.encode(); buf += struct.pack("<H", len(nm)) + nm
    buf += struct.pack("<IIII", n_in, n_wire, len(gates), len(outs))
    buf += b"".join(struct.pack("<I", w) for w in outs)
    buf += b"".join(struct.pack("<III", (op if isinstance(op, int) else OPC[op]), a, b) for (op, a, b) in gates)
    return bytes(buf)


C_ENGINE = r'''/* pfc_clockrun.c — the CLOCKED pfc, native. Reads the state register + baked next-state OFF the substrate
   file; holds STATE in an mmap'd state file (the pfc's own storage); the loop is only the CLOCK. Emitted by
   host/pfc_phone_clock.py.   ./pfc_clockrun <sub.bin> <ticks> [state.bin] */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
typedef uint64_t u64; typedef uint32_t u32;
static const unsigned char* MAP;
static u32 rd32(size_t* p){ u32 v; memcpy(&v, MAP+*p, 4); *p+=4; return v; }
static double secs(){ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec*1e-9; }
static long rss_kb(){ FILE* f=fopen("/proc/self/status","r"); if(!f) return -1; char l[256]; long v=-1;
  while(fgets(l,sizeof l,f)) if(!strncmp(l,"VmHWM:",6)){ sscanf(l+6,"%ld",&v); break; } fclose(f); return v; }
int main(int argc,char**argv){
  if(argc<3){ printf("usage: %s <sub.bin> <ticks> [state.bin]\n",argv[0]); return 1; }
  long long TICKS=atoll(argv[2]); const char* sfp=argc>3?argv[3]:"clock_state.bin";
  int fd=open(argv[1],O_RDONLY); struct stat st; fstat(fd,&st);
  MAP=mmap(0,st.st_size,PROT_READ,MAP_PRIVATE,fd,0); if(MAP==MAP_FAILED){ perror("mmap"); return 1; }
  size_t p=0; if(memcmp(MAP,"PFCSUBS1",8)){ fprintf(stderr,"bad magic\n"); return 2; } p=8;
  rd32(&p); u32 nl; memcpy(&nl,MAP+p,2); p+=2; p+=nl;
  u32 n_in=rd32(&p), n_wire=rd32(&p), n_gate=rd32(&p), n_out=rd32(&p);
  const u32* outs=(const u32*)(MAP+p); p+=4*(size_t)n_out;
  const u32* g=(const u32*)(MAP+p);            /* gates: n_gate*(op,a,b) — the pfc, read off the file */
  /* STATE lives in the pfc's own storage: an mmap'd state file */
  int sfd=open(sfp,O_RDWR|O_CREAT,0600); if(sfd<0){ perror("open state"); return 1; }
  if(ftruncate(sfd,4)){} u32* STATE=mmap(0,4,PROT_READ|PROT_WRITE,MAP_SHARED,sfd,0);
  if(STATE==MAP_FAILED){ perror("mmap state"); return 1; } *STATE=0;
  u64* w=calloc(n_wire,sizeof(u64)); u32 base=2+n_in;
  double t0=secs();
  for(long long t=0;t<TICKS;t++){
    u32 s=*STATE;                              /* read state from the pfc's storage */
    memset(w,0,(size_t)n_wire*sizeof(u64)); w[1]=~(u64)0;
    for(u32 j=0;j<32;j++) w[2+j]= (s>>j)&1 ? ~(u64)0 : 0;   /* state -> input wires */
    w[2+32]=~(u64)0;                                         /* clk = 1 */
    for(u32 k=0;k<n_gate;k++){                 /* ONE clock tick: settle the baked next-state */
      u32 op=g[3*k],a=g[3*k+1],b=g[3*k+2]; u64 va=w[a],vb=w[b];
      w[base+k]= op==3? va^vb : op==1? va&vb : op==2? va|vb : op==4? ~va : ~(va&vb);
    }
    u32 ns=0; for(u32 j=0;j<n_out;j++){ u32 wi=outs[j]; u64 bit= wi==0?0: wi==1?1: (w[wi]&1); if(bit) ns|=(1u<<j); }
    *STATE=ns;                                 /* latch next state back to storage */
  }
  double el=secs()-t0;
  printf("gates=%u ticks=%lld sec=%.3f => %.3e ticks/sec  final_state=%u  rssMB=%.2f\n",
         n_gate,TICKS,el,(double)TICKS/el,*STATE,rss_kb()/1024.0);
  return 0;
}
'''


def main():
    g, outs = build_counter()
    gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    # sanity: byte-exact 200 ticks (host, pre-write)
    Gi = [(op if isinstance(op, int) else OPC[op], a, b) for (op, a, b) in gates]
    st = 0; ok = True
    for t in range(1, 201):
        st = get_word(ripple(Gi, n_wire, g.n_in, pack_ctr(st, 1)), o2)
        if st != t: ok = False; break
    print(f"  clocked counter: {len(gates)} gates, byte-exact 200 ticks: {ok}", flush=True)
    if not ok:
        print("  MISMATCH — writing nothing."); return 1
    open(BIN, "wb").write(serialize_one("clock_counter", gates, o2, g.n_in, n_wire))
    open(CSRC, "w", newline="\n").write(C_ENGINE)
    print(f"  wrote {BIN} ({os.path.getsize(BIN)} B) + {CSRC}", flush=True)
    print(f"  next: push both over the cable, clang -O3, run ./pfc_clockrun pfc_clock_sub.bin <ticks>.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
