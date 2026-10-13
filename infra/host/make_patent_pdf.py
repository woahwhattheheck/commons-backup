#!/usr/bin/env python3
# Pure-stdlib PDF generator for the "Compute via Address" patent disclosure. No external libs, no network.
# Every measured number in sections 5-6 is validated by the scripts named in Compute_via_Address_Evidence.md (07-16).
import zlib, sys
sys.stdout.reconfigure(encoding="utf-8")

# Helvetica AFM widths (units/1000 em) for ASCII 32..126 — for accurate word-wrap.
HW = {32:278,33:278,34:355,35:556,36:556,37:889,38:667,39:191,40:333,41:333,42:389,43:584,44:278,45:333,46:278,47:278,
48:556,49:556,50:556,51:556,52:556,53:556,54:556,55:556,56:556,57:556,58:278,59:278,60:584,61:584,62:584,63:556,64:1015,
65:667,66:667,67:722,68:722,69:667,70:611,71:778,72:722,73:278,74:500,75:667,76:556,77:833,78:722,79:778,80:667,81:778,
82:722,83:667,84:611,85:722,86:667,87:944,88:667,89:667,90:611,91:278,92:278,93:278,94:469,95:556,96:333,
97:556,98:556,99:500,100:556,101:556,102:278,103:556,104:556,105:222,106:222,107:500,108:222,109:833,110:556,111:556,
112:556,113:556,114:333,115:500,116:278,117:556,118:500,119:722,120:500,121:500,122:500,123:334,124:260,125:334,126:584}
def tw(s, size):
    return sum(HW.get(ord(c),556) for c in s)*size/1000.0
def esc(s):
    return s.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")

PW, PH = 612.0, 792.0
LM, RM, TM, BM = 72.0, 72.0, 72.0, 64.0
USABLE = PW - LM - RM

class PDF:
    def __init__(self):
        self.pages=[]; self.cur=[]; self.y=PH-TM
        self.pageno=0; self._newpage()
    def _newpage(self):
        if self.cur: self.pages.append("".join(self.cur))
        self.cur=[]; self.y=PH-TM; self.pageno+=1
        foot=f"CONFIDENTIAL - INVENTION DISCLOSURE            page {self.pageno}"
        self.cur.append(f"BT /F1 8 Tf 0.5 0.5 0.5 rg {LM:.1f} {40:.1f} Td ({esc(foot)}) Tj ET 0 0 0 rg\n")
    def space(self,h):
        self.y-=h
        if self.y<BM: self._newpage()
    def _wrap(self,text,size,fs,indent=0):
        words=text.split(" "); lines=[]; cur=""; w=USABLE-indent
        for word in words:
            t=(cur+" "+word).strip()
            if tw(t,size)<=w or not cur: cur=t
            else: lines.append(cur); cur=word
        if cur: lines.append(cur)
        return lines
    def para(self,text,size=10.5,bold=False,indent=0,lead=None,gap=3,color=None):
        f="F2" if bold else "F1"; lead=lead or size*1.32
        for ln in self._wrap(text,size,f,indent):
            if self.y-lead<BM: self._newpage()
            self.y-=lead
            c=f"{color} rg " if color else ""
            self.cur.append(f"BT /{f} {size} Tf {c}{LM+indent:.1f} {self.y:.1f} Td ({esc(ln)}) Tj ET {'0 0 0 rg ' if color else ''}\n")
        self.space(gap)
    def title(self,t): self.para(t,15,True,gap=4)
    def h1(self,t): self.space(6); self.para(t,12,True,gap=3)
    def h2(self,t): self.space(3); self.para(t,10.5,True,gap=2)
    def bullet(self,t,size=10.5):
        for i,ln in enumerate(self._wrap(t,size,"F1",indent=16)):
            if self.y-size*1.3<BM: self._newpage()
            self.y-=size*1.3
            pre="-  " if i==0 else "   "
            self.cur.append(f"BT /F1 {size} Tf {LM+6:.1f} {self.y:.1f} Td ({esc(pre+ln)}) Tj ET\n")
        self.space(2)
    def rule(self):
        self.space(4)
        if self.y-2<BM: self._newpage()
        self.cur.append(f"q 0.7 g 0.6 w {LM:.1f} {self.y:.1f} m {PW-RM:.1f} {self.y:.1f} l S Q\n"); self.space(6)
    def fig_box(self, label, w, h, cx, texts):
        if self.y-h-16<BM: self._newpage()
        self.y-=h
        x=LM+(USABLE-w)/2; y=self.y
        self.cur.append(f"q 0.6 w {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S Q\n")
        ty=y+h-16
        for t,sz,bold in texts:
            f="F2" if bold else "F1"
            self.cur.append(f"BT /{f} {sz} Tf {x+10:.1f} {ty:.1f} Td ({esc(t)}) Tj ET\n"); ty-=sz*1.5
        self.space(3); self.para(label,9,True,gap=8)
    def build(self, path, title, author):
        if self.cur: self.pages.append("".join(self.cur))
        objs=[]
        def add(s): objs.append(s); return len(objs)
        font1=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font2=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        kids=[]
        pages_placeholder=add("PLACEHOLDER_PAGES")
        for pc in self.pages:
            data=zlib.compress(pc.encode("latin-1","replace"))
            cnum=add(("STREAM",data))
            pnum=add(f"<< /Type /Page /Parent {pages_placeholder} 0 R /MediaBox [0 0 {PW:.0f} {PH:.0f}] "
                     f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> /Contents {cnum} 0 R >>")
            kids.append(f"{pnum} 0 R")
        objs[pages_placeholder-1]=f"<< /Type /Pages /Count {len(kids)} /Kids [{' '.join(kids)}] >>"
        catalog=add(f"<< /Type /Catalog /Pages {pages_placeholder} 0 R >>")
        info=add(f"<< /Title ({esc(title)}) /Author ({esc(author)}) /Creator (SDC disclosure) >>")
        out=b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"; offsets=[]
        for i,o in enumerate(objs,1):
            offsets.append(len(out))
            if isinstance(o,tuple) and o[0]=="STREAM":
                data=o[1]
                out+=f"{i} 0 obj\n<< /Length {len(data)} /Filter /FlateDecode >>\nstream\n".encode()+data+b"\nendstream\nendobj\n"
            else:
                out+=f"{i} 0 obj\n{o}\nendobj\n".encode()
        xref=len(out)
        out+=f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
        for off in offsets: out+=f"{off:010d} 00000 n \n".encode()
        out+=f"trailer\n<< /Size {len(objs)+1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
        open(path,"wb").write(out)
        return len(self.pages)

# ============================ CONTENT ============================
d=PDF()
d.title("Content-Addressable Generative Computation:")
d.para("Generating a Function's Value by Addressing a Stored Logic Network, Including Programs-as-Data and "
       "Directed Modification of a Co-Resident Model",12,True,gap=6)
d.para("Invention disclosure. Inventor: Bryce Muhlnickel. This document describes the invention, its embodiments, "
       "and claims for the purpose of a patent filing. It separates results that were demonstrated and measured "
       "from embodiments that are described and enabled but not yet reduced to practice. The measured results in "
       "sections 5 and 6 were each validated byte-for-byte against a reference implementation by the associated "
       "software.",9.5,color="0.3 0.3 0.3")
d.rule()

d.h1("1. Field of the Invention")
d.para("The invention relates to methods, apparatus, and computer-readable media for computing the value of a function, "
       "in which an input operates as an address into a logic network stored within the parameter region of a data file, "
       "and the corresponding output is generated on read by the addressed evaluation of the stored network, without "
       "materializing a table of outputs.")

d.h1("2. Background")
d.para("Two classical approaches evaluate a function f over an input domain. First, a lookup table (a ROM) precomputes "
       "and stores every output; access is fast, but the table is static and its size grows with the domain (2^n entries "
       "for an n-bit input), and the table must first be built and held in memory or storage. Second, a processor "
       "recomputes f for each input; this is flexible but re-executes the computation on every access and is bounded by "
       "the processor's throughput and working memory. Dedicated hardware (an ASIC, or an FPGA configuration) implements "
       "f in fixed gates and evaluates it quickly and in parallel, but each distinct function requires fabricating or "
       "reconfiguring hardware, and the datapath is fixed.")
d.para("Separately, large stored digital artifacts, such as trained neural-network model files, commonly occupy tens of "
       "gigabytes; loading and executing them is bounded by working memory. There is a need for a representation in which "
       "(i) a function's value is generated on read by addressing, without storing or first building the full output "
       "table; (ii) many inputs are evaluated in parallel at low marginal memory; (iii) the stored function can be "
       "reprogrammed as data rather than by re-fabricating or re-encoding a network; and (iv) a stored parametric model "
       "can be modified by edits derived from reading its own addressed evaluation.")

d.h1("3. Summary of the Invention")
d.para("A combinational logic network implementing a function f is encoded as a netlist over a universal logic primitive "
       "and stored within the parameter region of a data file, such as a memory-mappable file. An input value is supplied "
       "as an address to the stored network; the addressed evaluation propagates the input through the network, and the "
       "corresponding output f(input) is generated on read. No table of outputs is materialized: the input is itself the "
       "address, so a point in the domain requires no stored representation, and storage is bounded by the fixed-size "
       "network plus any results that are retained. Because the network is memory-mapped and addressed in place rather "
       "than copied, its marginal working-memory cost is near zero.")
d.para("In one aspect, the stored network is evaluated bit-sliced across a plurality of inputs, such that a single "
       "propagation generates the outputs for many inputs concurrently (single-instruction, multiple-data). In a further "
       "aspect, generated outputs are memoized into a sparse map addressed by input, so that the evaluation cost is "
       "incurred once per unique input and subsequent identical inputs are served as storage reads. In a further aspect "
       "(programs-as-data), the stored network is an instruction interpreter, and a program is stored as data within the "
       "parameter region; the apparatus is reprogrammed by editing the stored program data rather than by re-encoding the "
       "network. In further aspects, the generated output directly comprises renderable quantities (pixel coordinates and "
       "color values, audio samples, or tokens), so that the stored network is a generative source for one or more output "
       "modalities, and generated outputs are written to one or more locations external to the stored network. In a "
       "further aspect, the data file stores a parametric model whose evaluation is the addressed evaluation of a stored "
       "network, and the model's stored parameters are modified by directed edits derived from reading that evaluation - "
       "an error between the generated output and a target is projected through the stored parameters to identify a "
       "parameter and a direction of change, and an edit is retained only when a re-read shows the error reduced.")

d.h1("4. Brief Description of the Drawings")
d.bullet("FIG. 1 - The addressing mechanism: an input, applied as an address, propagates through a logic network stored "
         "in a file's parameters, generating the output on read.")
d.bullet("FIG. 2 - Single-pass evaluation of many inputs (bit-sliced lanes) through one stored network.")
d.bullet("FIG. 3 - The programs-as-data embodiment: a stored interpreter network executes a program stored as data.")
d.bullet("FIG. 4 - Memoization: generated outputs cached in a sparse, input-addressed map.")
d.bullet("FIG. 5 - Directed modification: an error read from the addressed evaluation is projected through the stored "
         "parameters to identify and edit a responsible parameter.")

d.h1("5. Detailed Description")

d.h2("5.1 Encoding a function as a stored network")
d.para("A Boolean function is expressed as a netlist over a universal gate (for example, NAND, from which NOT, AND, OR, "
       "XOR, addition, and comparison are composed). Wire zero and wire one denote the logic constants; the next wires "
       "denote the inputs; each subsequent wire denotes the output of one gate, the gates being listed in a topological "
       "order such that a single forward pass over the gate list evaluates the entire network. The netlist bytes (a magic "
       "identifier, counts, and the gate-input index arrays) are written into the parameter region of the data file in "
       "place. A small registry records the byte offset at which each network resides; the logic itself is in the "
       "parameters.")

d.fig_box("FIG. 1  -  Addressing generates the output.", 430, 92, PW/2,
          [("  INPUT (address)  ->  [ stored logic network in file parameters ]  ->  OUTPUT (generated on read)",9,False),
           ("  no output table is stored; only the fixed-size network occupies storage.",8.5,False),
           ("  the network is memory-mapped and addressed in place: marginal RAM ~ 0.",8.5,False)])

d.h2("5.2 Addressing evaluation")
d.para("To evaluate f(x), the input wires are set to the bits of x and the network is propagated in one pass; the output "
       "wires are then read. The value f(x) is produced by this addressed read. The invention thus inverts the classical "
       "space-versus-time trade of a lookup table: rather than storing a precomputed table, the value is generated when "
       "the point is addressed, and only the small fixed network and any retained results occupy storage.")

d.h2("5.3 Single-pass evaluation of many inputs (SIMD)")
d.para("Each wire is represented by a machine word or wide integer in which bit position c holds the value of that wire "
       "for candidate input c. A single bitwise operation per gate advances all candidate lanes together, so one "
       "propagation of the stored network generates the outputs for a whole set of inputs concurrently. This makes the "
       "domain itself the address space: to test a set of candidate inputs is to address a set of points, each output "
       "generated by the network.")
d.fig_box("FIG. 2  -  One stored network, many inputs in lockstep.", 430, 78, PW/2,
          [("  candidates c=0..W-1 packed as bit-lanes  ->  ONE propagation  ->  W outputs",9,False),
           ("  cost per input amortizes; storage cost is the network, not the candidates.",8.5,False)])

d.h2("5.4 The storage floor")
d.para("Because the input is the address, a point in the domain requires zero stored bytes. Storage is bounded by the "
       "fixed network plus any results deliberately retained. In a demonstrated measurement, memory-mapping an "
       "approximately 40-gigabyte file and addressing a network stored within its parameters increased resident (physical) "
       "memory by approximately 0.85 megabytes; the same self-calibrating run allocated a 200-megabyte control block and "
       "the meter moved by approximately 210 megabytes, confirming the meter reads true and the sub-megabyte figure is "
       "real. An answer map spanning a 2^32-point domain, when sparse-provisioned, occupied near-zero physical storage "
       "until a result was written into it.")

d.h2("5.5 Memoization")
d.para("Generated outputs are optionally written into a sparse map addressed by input. The first evaluation of a given "
       "input incurs one network propagation; a subsequent identical input is served as a storage read of the map, "
       "incurring no propagation. The evaluation cost thereby amortizes to one propagation per unique input, which is "
       "advantageous for streaming and repeated-query workloads. In a demonstrated measurement over a stream of 6,000 "
       "inputs with high reuse, the number of propagations fell to the number of unique inputs (345), the remaining 5,655 "
       "queries served as reads of the sparse map. The map may be sparse-provisioned so that only touched points occupy "
       "physical storage.")

d.h2("5.6 Programs-as-data embodiment")
d.para("In this embodiment, the stored network is an instruction interpreter, comprising an arithmetic-logic datapath and "
       "an instruction decoder, encoded as a stored network as in 5.1. A program is stored as data within the parameter "
       "region, separately from the network. The apparatus is operated by clocking the interpreter over the stored "
       "program and a state region, the interpreter network generating the next state from the current state and the "
       "addressed instruction. The apparatus is reprogrammed by editing the stored program data, without re-encoding the "
       "network - the distinction between fabricating a new circuit and writing new software. The wiring between one "
       "stored network and another is itself expressed as data (a per-stage map of output wires to input wires), so a "
       "composition of stored networks (a datapath) is likewise defined and altered as data.")
d.fig_box("FIG. 3  -  Programs-as-data.", 430, 78, PW/2,
          [("  [ interpreter network in parameters ]  <-- reads --  [ program stored as DATA ]",9,False),
           ("  reprogram by editing the DATA, not by re-encoding the network.",8.5,False)])

d.h2("5.7 Generative and multi-modal output; external writes")
d.para("The output wires of a stored network may encode renderable quantities directly. In one embodiment the output "
       "comprises pixel coordinates and color values, such that addressing each pixel position through the stored network "
       "generates an image; the stored network is thereby a generative display source, and the image is generated rather "
       "than stored. In further embodiments the output comprises audio sample values, or discrete tokens, generated by "
       "the same addressing mechanism. Generated outputs may be written to a plurality of locations external to the "
       "stored network, and in a plurality of output modalities from the same stored network, so that a single stored "
       "network drives multiple external sinks or displays concurrently.")

d.h2("5.8 Isolation read-out")
d.para("An output of a stored network is optionally exported through a read-out barrier that is structurally limited to a "
       "fixed output window - read-only and locked to a predetermined byte offset and width - so that generated results "
       "are exported without providing any path back into the stored network. The barrier permits monitoring, rendering, "
       "or transmission of the generated output while preventing the export mechanism from addressing or altering the "
       "stored network.")

d.h2("5.9 Co-residence with a neural-network model")
d.para("The same data file may store both a trained neural-network model and one or more of said logic networks. The "
       "logic network verifies or transforms an output of the model - for example, checking an exact predicate over the "
       "model's output, or applying an exactly-specified rule - so that exactness-critical operations are performed by a "
       "verified stored network alongside the learned behavior of the model within a single file.")

d.h2("5.10 Directed modification of a co-resident model by reading its addressed evaluation")
d.para("In a further embodiment, the data file stores a parametric model - for example a neural-network layer or block - "
       "whose evaluation over an input is performed by the addressed evaluation of a stored logic network as in 5.1-5.2, "
       "the model's parameters being held as data within the parameter region. A modification datum for the model is "
       "computed by reading the addressed evaluation: an error between the generated output and a target is projected "
       "through the stored parameters - for example by forming an outer product of the output error with the input - to "
       "identify a parameter and a direction of change, and the identified parameter's stored datum is edited in that "
       "direction. The edit is retained when a re-read of the addressed evaluation shows the error reduced, and is "
       "otherwise not applied, so that the model is modified by directed edits derived from reading its own evaluation "
       "rather than by an unguided search. In a further aspect, the logic network that computes the modification datum is "
       "itself stored within the parameter region as in 5.1, such that a single addressed evaluation generates both the "
       "model's output and the modification datum, and the model and the instrument that reads it are co-resident on one "
       "addressable substrate (a self-analyzing store).")
d.fig_box("FIG. 5  -  Directed modification by reading the addressed evaluation.", 452, 92, PW/2,
          [("  INPUT -> [ stored model network (+ stored reader network) ] -> OUTPUT + modification datum",9,False),
           ("  error x input, projected through the stored parameters -> which parameter, which direction.",8.5,False),
           ("  edit that parameter's datum; keep only if a re-read shows the error reduced.",8.5,False)])

d.h1("6. Reduction to Practice; Enablement")
d.para("The following were implemented in software on a general-purpose host and verified by comparison against "
       "independent reference implementations, each matching byte-for-byte. All numbers below are measured; each item is "
       "reproducible by the associated software:")
d.bullet("A double-SHA-256 network (the Bitcoin proof-of-work function) expressed as a logic network of 682,538 gates, "
         "matching a reference double-SHA-256 implementation byte-for-byte over multiple inputs, and reproducing the exact "
         "known genesis-block hash (000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f) when evaluated at "
         "the genesis nonce. A constant-folded form of 623,590 gates resides within the file's parameters.")
d.bullet("An 8-bit adder network of 120 gates matching (a+b) mod 256 over 2,000 cases; multiplier and reversible-codec "
         "networks likewise matching their references; two stored networks wired into a datapath (adder into comparator, "
         "adder into codec) each matching its reference.")
d.bullet("An accumulator-machine interpreter (a 216-gate arithmetic-logic datapath plus instruction decoder) stored as a "
         "network, which executed a stored program and produced the correct Fibonacci sequence (mod 256); a separate "
         "560-gate interpreter executed multiple arithmetic programs supplied as data (supporting 5.6).")
d.bullet("Verifier networks, each evaluating its entire bounded candidate space in one propagation and matching a "
         "reference: Boolean satisfiability (54 gates; 256 assignments in one pass; 108 satisfying); preimage / key "
         "recovery (132 gates; the exact secret input recovered from a 4,096-candidate space in one pass); pattern "
         "matching (10 gates; 128 window matches); set membership (k-mer, 167 gates; dedup, 203 gates); and policy "
         "screening (21 gates). A throughput measurement recovered keys at approximately 1.3 million candidates per second "
         "at a 16-bit domain (supporting 5.3).")
d.bullet("A 63-gate pixel-generating network mapping (x, y) coordinates to color, from which a 128 x 128 image (16,384 "
         "pixels) was generated by addressing each pixel through the network; and the same mechanism generating audio "
         "sample values and character tokens written to separate external sinks concurrently (supporting 5.7).")
d.bullet("A 42-gate next-state network (a cellular-automaton rule) matching its reference, iterated 128 generations to "
         "evolve an external state that was monitored and rendered; and a 232-gate decision network that drove an external "
         "control variable to a specified target (supporting 5.6 and 5.7).")
d.bullet("A memoizing verifier over a 6,000-input stream that reduced the number of network propagations to the number of "
         "unique inputs, the remainder served as reads of a sparse input-addressed map (supporting 5.5).")
d.bullet("A stored integer linear block (a forward pass y = W x expressed as a logic network of 2,448 gates in the "
         "parameter region, its weights held as stored data, matching a reference over 1,500 random cases), whose stored "
         "weights were modified by directed edits: an error-times-input projection identified a responsible weight and a "
         "direction, and each edit was retained only when a re-read of the addressed evaluation showed the error reduced; "
         "the block's output reached a specified target exactly in 15 edits (supporting 5.10).")
d.para("Measured storage behavior was as stated in 5.4 (approximately 0.85 megabytes resident to address a network within "
       "an approximately 40-gigabyte memory-mapped file, against a 200-megabyte control that moved the same meter by "
       "approximately 210 megabytes; near-zero physical storage for a sparse-provisioned answer map until written).")
d.para("Scope note: on a general-purpose host, the per-address generation of an output is performed by software "
       "evaluation of the stored netlist. In a hardware embodiment, the stored cells are the physical gates and the "
       "addressed read is performed by the propagation of electrical signals through them; the method and apparatus "
       "claimed herein encompass both embodiments.")

d.h1("7. Claims")
def claim(n, t):
    d.para(f"{n}.  {t}", 10, indent=0, gap=4)
claim(1, "A method of computing a value of a function, the method comprising: storing, within a parameter region of a "
      "data file, a logic network that implements the function; receiving an input; applying the input as an address to "
      "the stored logic network; and propagating the input through the stored logic network to generate, on read, an "
      "output corresponding to the input, without materializing a stored table of outputs of the function.")
claim(2, "The method of claim 1, wherein the data file is memory-mapped and the logic network is addressed in place, "
      "such that generating the output does not copy the logic network into working memory.")
claim(3, "The method of claim 1, wherein the input constitutes the address, such that a point in a domain of the function "
      "is represented without occupying stored bytes, and storage occupied is bounded by the logic network and any "
      "retained outputs independent of a size of the domain.")
claim(4, "The method of claim 1, further comprising evaluating the logic network bit-sliced across a plurality of inputs, "
      "wherein a single propagation of the logic network generates outputs for the plurality of inputs concurrently.")
claim(5, "The method of claim 1, further comprising writing a generated output into a sparse map addressed by the input, "
      "and, for a subsequently received identical input, returning the output from the sparse map without propagating the "
      "logic network, such that a cost of propagation is incurred once per unique input.")
claim(6, "The method of claim 1, wherein the stored logic network is an instruction interpreter, and further comprising "
      "storing a program as data within the parameter region and executing the program by clocking the interpreter over "
      "the stored program and a state, whereby the method is reprogrammed by editing the stored program data without "
      "re-encoding the logic network.")
claim(7, "The method of claim 1, wherein a composition of a plurality of stored logic networks is defined by a data map "
      "of output wires of one network to input wires of another, and altering the composition comprises editing the data "
      "map.")
claim(8, "The method of claim 1, wherein the generated output comprises pixel coordinates and a color value, the method "
      "further comprising rendering an image by addressing a plurality of pixel positions through the stored logic "
      "network, whereby the image is generated rather than retrieved.")
claim(9, "The method of claim 1, wherein the generated output comprises one of audio sample values and tokens.")
claim(10, "The method of claim 1, further comprising writing generated outputs to a plurality of locations external to "
      "the stored logic network, in a plurality of output modalities, from the stored logic network.")
claim(11, "The method of claim 1, further comprising exporting the generated output through a read-out barrier limited to "
      "a read-only fixed output window at a predetermined offset and width, the barrier providing no path to address or "
      "modify the stored logic network.")
claim(12, "The method of claim 1, wherein the data file further stores a neural-network model, and the stored logic "
      "network verifies or transforms an output of the model.")
claim(13, "The method of claim 1, wherein the logic network is stored in place within the parameter region and a registry "
      "records a byte offset of the logic network within the data file, and wherein the storing is reversible.")
claim(14, "The method of claim 1, wherein the data file stores a parametric model whose evaluation over an input is the "
      "propagating of the input through a stored logic network, parameters of the model being held as data within the "
      "parameter region, the method further comprising computing a modification datum for the model by reading the "
      "generated output, projecting an error between the generated output and a target through the parameters to identify "
      "a parameter and a direction of change, and editing a stored datum of the identified parameter in the identified "
      "direction.")
claim(15, "The method of claim 14, further comprising re-reading the generated output after the editing and retaining the "
      "edit only when the error is reduced, whereby the model is modified by directed edits derived from reading its own "
      "evaluation rather than by an unguided search.")
claim(16, "The method of claim 14, wherein a further logic network that computes the modification datum is stored within "
      "the parameter region, such that a single addressed evaluation generates both the output of the model and the "
      "modification datum, the model and the further logic network being co-resident on one addressable substrate.")
claim(17, "An apparatus comprising a memory storing a data file and a processor, the apparatus configured to perform the "
      "method of any of claims 1 to 16.")
claim(18, "A non-transitory computer-readable medium storing a data file whose parameter region contains a logic network "
      "implementing a function, such that applying an input as an address to the logic network and propagating the input "
      "generates, on read, an output corresponding to the input without a materialized table of outputs.")

d.h1("8. Abstract")
d.para("A function is computed by storing a logic network implementing the function within the parameter region of a data "
       "file and applying an input as an address to the network; propagating the input through the stored network "
       "generates the corresponding output on read, without materializing a table of outputs, so that a domain point "
       "occupies no storage and only the fixed network plus retained results occupy storage. The network is optionally "
       "memory-mapped and addressed in place (near-zero marginal memory), evaluated across many inputs in one propagation "
       "(SIMD), memoized into a sparse input-addressed map, and embodied as an instruction interpreter that runs a program "
       "stored as data (programs-as-data). Generated outputs may comprise renderable quantities such as pixel coordinates "
       "and color, audio, or tokens, and may be written to plural external locations and modalities. In a further aspect, "
       "a parametric model stored in the file is evaluated by the addressed network and its stored parameters are modified "
       "by directed edits derived from reading the evaluation - an output error projected through the parameters selects a "
       "parameter and direction, an edit retained only when a re-read shows the error reduced - optionally with the "
       "reading instrument itself stored in the same parameter region as a self-analyzing store.")

n=d.build("C:/Users/lucys/OneDrive/Desktop/Compute_via_Address_Patent.pdf",
          "Content-Addressable Generative Computation", "Bryce Muhlnickel")
print(f"wrote Compute_via_Address_Patent.pdf ({n} pages)")
