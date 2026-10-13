#!/usr/bin/env python3
"""Extract exact original/candidate contributor methods for a native fixture."""
from pathlib import Path
import argparse, hashlib, json
from apply_prefix import apply, EDITS

FIELDS = '''    int h;
    std::vector<Demand> demands;
    std::vector<Sparse> routed;
'''
START = '    static double coefficient('
END = '    // This score orders the neighborhood only.'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    text=args.source.read_text()
    # This fixture needs genuinely different source versions. An idempotent
    # transform is useful for publication but must not create a self-comparison.
    if any(text.count(before) != 1 or text.count(after) != 0 for before, after in EDITS):
        raise ValueError("native preparation requires the unapplied contributor source")
    fixed=apply(text)
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) >= text.index(END):
        raise ValueError("ambiguous or reversed native extraction boundaries")
    args.output.mkdir(parents=True,exist_ok=False)
    for name,source in [('Original',text),('Candidate',fixed)]:
        methods=source[source.index(START):source.index(END)]
        (args.output/(name.lower()+'.hpp')).write_text('struct '+name+' {\n'+FIELDS+methods+'};\n')
    (args.output/'native_prefix.cpp').write_bytes(Path(__file__).with_name('native_prefix.cpp').read_bytes())
    (args.output/'source.json').write_text(json.dumps({'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'candidate_sha256':hashlib.sha256(fixed.encode()).hexdigest()},indent=2)+'\n')

if __name__=='__main__':main()
