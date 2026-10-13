#!/usr/bin/env python3
"""host/pfc_billions.py — MAKE THE BILLIONS (owner 07-19/20: "make the billions, thats always been my endgame — the
perfect pfc small as possible then go as wide as possible").

The smallest real pfc: an 8-bit counter (1 BYTE of state; the gates are shared off one file; wire-state is transient).
Instantiate BILLIONS of them, advance every one by the clock (bit-sliced, 64 machines/word), byte-exact spot-checked.
RAM-backed (fast, bounded by free RAM) or storage-backed (mmap a file → bounded by disk = tens of billions, flat
resident). This realizes avail ÷ resident = billions of connected pfc, for real.

  python host/pfc_billions.py     # verify + write pfc_billions_sub.bin (8-bit counter) + pfc_billions.c
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"
os.makedirs(OUT, exist_ok=True)
OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
SW = 8   # state width — the smallest meaningful pfc: an 8-bit counter = 1 byte resident


def build_counter8():
    g = CC.CircuitCompiler(SW + 1); IN = g.IN
    state = IN[0:SW]; clk = IN[SW]
    c = g.C1; inc = []
    for i in range(SW): inc.append(g.XOR(state[i], c)); c = g.AND(state[i], c)
    nxt = [g.OR(g.AND(clk, inc[i]), g.AND(g.NOT(clk), state[i])) for i in range(SW)]
    return g, nxt


def norm(gates): return [(op if isinstance(op, int) else OPC[op], a, b) for (op, a, b) in gates]


def py_ripple(gates, n_wire, n_in, state, clk):
    v = [0] * n_wire; v[1] = 1
    for i in range(SW): v[2 + i] = (state >> i) & 1
    v[2 + SW] = clk
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == 3 else (va & vb) if op == 1 else (va | vb) if op == 2 \
            else (1 ^ va) if op == 4 else (1 ^ (va & vb))
    return v


def serialize(name, gates, outs, n_in, n_wire, n_state, consts):
    buf = bytearray(b"PFCCM01\x00")
    buf += struct.pack("<IIII", n_in, n_wire, len(gates), len(outs))
    buf += struct.pack("<iiI", n_state, -1, len(consts))
    for idx, val in consts: buf += struct.pack("<Ii", idx, val)
    buf += b"".join(struct.pack("<i", w) for w in outs)
    buf += struct.pack("<I", 0)                              # no init blob (billions start at 0)
    buf += b"".join(struct.pack("<III", op, a, b) for (op, a, b) in gates)
    return bytes(buf)


C_ENGINE = r'''/* pfc_billions.c — MAKE THE BILLIONS. The smallest pfc (state read off the substrate), instantiated N times
   (N/64 words x n_state bitplanes), every one advanced by the clock (bit-sliced 64/word), batched so the wire buffer
   stays bounded. RAM-backed or storage-backed (mmap). Emitted by host/pfc_billions.py.
     ./pfc_billions <sub.bin> ram|store <N> <Bbatch> <sweeps> [statefile] */
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
static u32 N_IN,N_WIRE,N_GATE,N_OUT,SW; static int N_STATE; static const int* OUTS; static const u32* G; static u32 CLKIDX;
static u32 rd(size_t*p){u32 v;memcpy(&v,MAP+*p,4);*p+=4;return v;}
static double secs(){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static double rss_mb(){FILE*f=fopen("/proc/self/status","r");if(!f)return -1;char l[256];long v=-1;
  while(fgets(l,sizeof l,f))if(!strncmp(l,"VmHWM:",6)){sscanf(l+6,"%ld",&v);break;}fclose(f);return v/1024.0;}
static void parse(){size_t p=0;if(memcmp(MAP,"PFCCM01",7)){fprintf(stderr,"magic\n");exit(2);}p=8;
  N_IN=rd(&p);N_WIRE=rd(&p);N_GATE=rd(&p);N_OUT=rd(&p);N_STATE=(int)rd(&p);(void)rd(&p);u32 nc=rd(&p);
  CLKIDX=0xffffffff; for(u32 c=0;c<nc;c++){u32 idx=rd(&p);(void)rd(&p);CLKIDX=idx;}
  OUTS=(const int*)(MAP+p);p+=4*(size_t)N_OUT; (void)rd(&p); G=(const u32*)(MAP+p); SW=(u32)N_STATE;}
int main(int argc,char**argv){
  if(argc<6){printf("usage: %s <sub.bin> ram|store <N> <Bbatch> <sweeps> [statefile]\n",argv[0]);return 1;}
  int fd=open(argv[1],O_RDONLY);struct stat sb;fstat(fd,&sb);MAP=mmap(0,sb.st_size,PROT_READ,MAP_PRIVATE,fd,0);parse();
  int store=!strcmp(argv[2],"store"); long long N=atoll(argv[3]); int B=atoi(argv[4]); int sweeps=atoi(argv[5]);
  const char* sfp=argc>6?argv[6]:"pfc_billions_state.bin";
  long long W=(N+63)/64; N=W*64;                              /* round N up to a whole word */
  size_t stbytes=(size_t)N_STATE*(size_t)W*sizeof(u64);       /* n_state planes x W words = N bytes */
  u64* st;
  if(store){ int s=open(sfp,O_RDWR|O_CREAT,0600); if(ftruncate(s,stbytes)){perror("ftruncate");return 1;}
    st=mmap(0,stbytes,PROT_READ|PROT_WRITE,MAP_SHARED,s,0); if(st==MAP_FAILED){perror("mmap st");return 1;} }
  else { st=calloc(1,stbytes); if(!st){printf("OOM: need %.2f GB in RAM\n",stbytes/1e9);return 1;} }
  u64* w=malloc((size_t)N_WIRE*B*sizeof(u64)); if(!w){printf("OOM wire\n");return 1;} u32 base=2+N_IN;
  double t0=secs();
  for(int s=0;s<sweeps;s++){
    for(long long chunk=0;chunk<W;chunk+=B){ int bb=(int)((W-chunk<B)?(W-chunk):B);
      for(int j=0;j<N_STATE;j++){u64* wj=w+(size_t)(2+j)*B; u64* sj=st+(size_t)j*W+chunk; for(int i=0;i<bb;i++) wj[i]=sj[i];}
      for(int i=0;i<bb;i++){ w[0*B+i]=0; w[1*B+i]=~(u64)0; }
      if(CLKIDX!=0xffffffff){u64* wc=w+(size_t)(2+CLKIDX)*B; for(int i=0;i<bb;i++) wc[i]=~(u64)0;}   /* clk=1 */
      for(u32 k=0;k<N_GATE;k++){u32 op=G[3*k],a=G[3*k+1],b=G[3*k+2];u64* wo=w+(size_t)(base+k)*B;u64* wa=w+(size_t)a*B;u64* wb=w+(size_t)b*B;
        if(op==3){for(int i=0;i<bb;i++)wo[i]=wa[i]^wb[i];}else if(op==1){for(int i=0;i<bb;i++)wo[i]=wa[i]&wb[i];}
        else if(op==2){for(int i=0;i<bb;i++)wo[i]=wa[i]|wb[i];}else if(op==4){for(int i=0;i<bb;i++)wo[i]=~wa[i];}
        else{for(int i=0;i<bb;i++)wo[i]=~(wa[i]&wb[i]);}}
      for(int j=0;j<N_STATE;j++){int wi=OUTS[j];u64* sj=st+(size_t)j*W+chunk;
        if(wi==0){for(int i=0;i<bb;i++)sj[i]=0;}else if(wi==1){for(int i=0;i<bb;i++)sj[i]=~(u64)0;}
        else{u64* wv=w+(size_t)wi*B;for(int i=0;i<bb;i++)sj[i]=wv[i];}}
    }
  }
  double el=secs()-t0;
  /* spot-check: machine k's counter must == sweeps (started 0), extracted from the bitplanes */
  long long ks[3]={0,123456789LL%N,N-1}; int ok=1;
  for(int q=0;q<3;q++){long long k=ks[q]; long long word=k/64; int lane=k%64; u32 val=0;
    for(int j=0;j<N_STATE;j++) if((st[(size_t)j*W+word]>>lane)&1) val|=(1u<<j);
    if(val!=(u32)(sweeps & ((1u<<N_STATE)-1))) ok=0; }
  printf("MADE %.3e Muhlnickel (%lld exactly), each %d-bit=%d byte. %d sweeps in %.2fs => %.3e machine-advances/sec. "
         "resident=%.1f MB. spot-check(3 machines == %d): %s. backing=%s\n",
         (double)N,N,N_STATE,(N_STATE+7)/8,sweeps,el,(double)N*sweeps/el,rss_mb(),sweeps,ok?"PASS":"FAIL",store?"storage(mmap)":"RAM");
  return ok?0:1;
}
'''


def main():
    g, outs = build_counter8()
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    st = 0; ok = True
    for t in range(1, 300):
        st = 0
        v = py_ripple(norm(gates), nw, g.n_in, (t - 1) & 0xff, 1)
        bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
        st = sum(bit(o2[i]) << i for i in range(SW))
        if st != (t & 0xff): ok = False; break
    print(f"  8-bit counter (smallest Muhlnickel = 1 byte): {len(gates)} gates, byte-exact wrap 0..255: {ok}", flush=True)
    if not ok:
        print("  MISMATCH — writing nothing."); return 1
    blob = serialize("counter8", norm(gates), o2, g.n_in, nw, SW, [(SW, 1)])
    open(os.path.join(OUT, "pfc_billions_sub.bin"), "wb").write(blob)
    open(os.path.join(OUT, "pfc_billions.c"), "w", newline="\n").write(C_ENGINE)
    print(f"  wrote pfc_billions_sub.bin ({len(blob)} B) + pfc_billions.c", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
