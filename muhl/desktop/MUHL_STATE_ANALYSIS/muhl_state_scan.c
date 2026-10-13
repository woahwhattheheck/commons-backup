/* muhl_state_scan.c — self-hosted state analysis. C89. No libraries. No allocation.
 *
 * Owner's brief: "Everything I need reduces to four primitive operations:
 *                 shift, XOR, popcount, accumulate. Nothing else."
 *
 * This is the SEMANTICS the fabricated MUHLNICKEL circuit must match byte-exact.
 * It is NOT meant to run on the host against real state — the host never walks the
 * machine. Owner: "claude tried to suggest host walking the machine. DO NOT DO THAT."
 * It exists so the fabricator can verify gates against a reference BEFORE storing,
 * which is manufacturing, not runtime.
 *
 * SINGLE PASS. Never seeks backward. Never buffers the data. Counter state is fixed
 * at compile time: identical for 4 MiB of state or 100 GiB.
 *
 * FIXED FOOTPRINT
 *   lag       4096 * 4 =    16,384 B
 *   col      32637 * 4 =   130,548 B     (sum of widths 3..255, one counter per
 *                                          position per width)
 *   spans  3 * 4096 * 4 =    49,152 B
 *   hist            512 =       512 B
 *                        ------------
 *                          196,596 B  ~192 KiB, constant.
 */

#define MAXLAG   4096
#define MINW        3
#define MAXW      256
#define COLTOT  32637              /* sum_{w=3}^{255} w */
#define NSPAN    4096
#define HISTB     512              /* rolling byte history, power of two */

typedef unsigned long u32;
typedef unsigned char u8;

/* the only primitives used: shift, XOR, popcount, accumulate */
#define SHR(x, n) ((x) >> (n))
#define XOR(a, b) ((a) ^ (b))

static u32 popcount8(u8 v)
{
    static const u8 t[16] = {0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4};
    return (u32)t[v & 15] + (u32)t[SHR(v, 4) & 15];
}

struct scan {
    u32 lag[MAXLAG];
    u32 col[COLTOT];
    u32 colbase[MAXW];
    u32 span_pop[NSPAN];
    u32 span_zero[NSPAN];
    u32 span_ones[NSPAN];
    u8  hist[HISTB];
    u32 head;
    u32 bits_lo;
    u32 bits_hi;
    u32 span_bits;
};

void scan_init(struct scan *s, u32 total_bits_hi, u32 total_bits_lo)
{
    u32 i, base;
    for (i = 0; i < MAXLAG; i++) s->lag[i] = 0;
    for (i = 0; i < COLTOT; i++) s->col[i] = 0;
    for (i = 0; i < NSPAN;  i++) { s->span_pop[i]=0; s->span_zero[i]=0; s->span_ones[i]=0; }
    for (i = 0; i < HISTB;  i++) s->hist[i] = 0;
    base = 0;
    for (i = 0; i < MAXW; i++) {
        s->colbase[i] = base;
        if (i >= MINW) base += i;
    }
    s->head = 0;
    s->bits_lo = 0;
    s->bits_hi = 0;
    if (total_bits_hi) {
        s->span_bits = 0xFFFFFFFFul / NSPAN;      /* huge state: coarse fixed stride */
    } else {
        s->span_bits = total_bits_lo / NSPAN;
    }
    if (!s->span_bits) s->span_bits = 1;
}

/* feed exactly one byte. EVERY bit is examined. no sampling, no striding. */
void scan_byte(struct scan *s, u8 b)
{
    u32 i, w, bit, p, span;
    u8  old;

    /* --- self-correlation: XOR against history at each byte lag, popcount --- */
    for (i = 1; i <= MAXLAG / 8; i++) {
        old = s->hist[(s->head + HISTB - i) & (HISTB - 1)];
        s->lag[i - 1] += popcount8((u8)XOR(b, old));
    }

    /* --- column bias: one counter per position per candidate width --------- */
    for (w = MINW; w < MAXW; w++) {
        for (bit = 0; bit < 8; bit++) {
            if (SHR(b, bit) & 1ul) {
                p = (s->bits_lo + bit) % w;
                s->col[s->colbase[w] + p] += 1;
            }
        }
    }

    /* --- region occupancy -------------------------------------------------- */
    span = s->bits_lo / s->span_bits;
    if (span >= NSPAN) span = NSPAN - 1;
    s->span_pop[span] += popcount8(b);
    if (b == 0x00) s->span_zero[span] += 1;
    if (b == 0xFF) s->span_ones[span] += 1;

    /* --- advance ----------------------------------------------------------- */
    s->hist[s->head] = b;
    s->head = (s->head + 1) & (HISTB - 1);
    if (s->bits_lo + 8 < s->bits_lo) s->bits_hi += 1;
    s->bits_lo += 8;
}

/* the single output callback. nothing else leaves this routine. */
typedef void (*emit_fn)(const char *tag, const u32 *v, u32 n);

void scan_emit(const struct scan *s, emit_fn emit)
{
    emit("lag",       s->lag,       MAXLAG);
    emit("colbase",   s->colbase,   MAXW);
    emit("col",       s->col,       COLTOT);
    emit("span_pop",  s->span_pop,  NSPAN);
    emit("span_zero", s->span_zero, NSPAN);
    emit("span_ones", s->span_ones, NSPAN);
    emit("bits_lo",   &s->bits_lo,  1);
    emit("bits_hi",   &s->bits_hi,  1);
}
