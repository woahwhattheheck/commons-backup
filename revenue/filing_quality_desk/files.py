from .core import FilingQualityError
from .render import outputs,verify_outputs
NAMES=('packet.json','observations.csv','comparisons.csv','findings.csv','report.html','manifest.json')
def compile_dir(source,policy,out):
    files=outputs(source.read_bytes(),policy.read_bytes())
    if out.exists():
        if out.is_symlink() or not out.is_dir():raise FilingQualityError('output path must be a real directory')
        if any(out.iterdir()):raise FilingQualityError('output directory must be empty; refusing overwrite')
    else:out.mkdir(parents=True,exist_ok=False)
    for k,v in files.items():
        try:
            with (out/k).open('xb') as f:f.write(v)
        except FileExistsError as e:raise FilingQualityError(f'refusing overwrite: {k}') from e
def verify_dir(source,policy,out):
    if out.is_symlink() or not out.is_dir():raise FilingQualityError('output path must be a real directory')
    entries=list(out.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in entries):raise FilingQualityError('output directory contains non-regular file')
    if {p.name for p in entries}!=set(NAMES):raise FilingQualityError('output file set mismatch')
    verify_outputs(source.read_bytes(),policy.read_bytes(),{k:(out/k).read_bytes() for k in NAMES})
