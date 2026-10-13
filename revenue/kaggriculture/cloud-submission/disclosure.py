"""Prepare a public associated Kaggle notebook from exact designated archive bytes.

Does not publish, execute candidate code, modify the existing v2 notebook, or
submit a competition entry. Source and upstream license/notice bytes are shown.
"""
import argparse,base64,hashlib,io,json,tarfile,zipfile
from pathlib import Path,PurePosixPath


def members(path):
    data=Path(path).read_bytes()
    if len(data)>64_000_000:raise ValueError('Archive exceeds bounded disclosure size')
    if path.suffix=='.py':return {'main.py':data}
    result={}
    def add(name,body):
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or name in result:raise ValueError('Invalid archive member')
        if sum(map(len,result.values()))+len(body)>64_000_000:raise ValueError('Expanded size exceeds bound')
        result[name]=body
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for m in archive.infolist():
                if not m.is_dir():
                    if m.file_size>64_000_000:raise ValueError('Oversized member')
                    add(m.filename,archive.read(m))
    else:
        with tarfile.open(path,'r:*') as archive:
            for m in archive:
                if m.isdir():continue
                if not m.isfile() or m.size>64_000_000:raise ValueError('Unsupported archive member')
                add(m.name,archive.extractfile(m).read())
    if 'main.py' not in result:raise ValueError('Archive must contain root main.py')
    return result


def prepare(artifact,expected_sha256,output,source_ref,slug='titan-kaggriculture-frontier-20260907'):
    artifact=Path(artifact);data=artifact.read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual!=expected_sha256:raise ValueError('Exact designated artifact hash required')
    files=members(artifact)
    if not any('LICENSE' in n.upper() for n in files) or not any('NOTICE' in n.upper() for n in files):
        raise ValueError('Supply archive carrying original LICENSE and NOTICE for this derivative')
    manifest={n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in files.items()}
    intro=f'''# TITAN Kaggriculture frontier source

Exact artifact SHA256: `{actual}`. Source/provenance: {source_ref}.

This is a derivative of the credited public Kaito/Igor sources. Original authorship, Apache-2.0 license and change notices are reproduced below. Commons modifications are described in those notices. This notebook shares the exact source for the artifact; development/validation evidence is separate from hosted competition scoring. No hosted win or leaderboard rank is claimed here.

The existing tokenjunkielabs-farm-manager notebook version347872961 is unchanged. This separate associated notebook provides public competition source disclosure; direct file submission does not require a notebook commit.
'''
    def md(text):return {'cell_type':'markdown','metadata':{},'source':text}
    cells=[md(intro)]
    for name,body in files.items():
        try:text=body.decode('utf-8')
        except UnicodeDecodeError:
            text='Binary member, included byte-exact in the artifact cell below. SHA256 '+manifest[name]['sha256']
        fence='`'*(max([len(x) for x in text.split() if x and set(x)=={'`'}] or [3])+1)
        cells.append(md('## '+name+'\n\nSHA256 `'+manifest[name]['sha256']+'`\n\n'+fence+'\n'+text+'\n'+fence+'\n'))
    materialize="import base64, hashlib\nfrom pathlib import Path\npayload = base64.b64decode("+repr(base64.b64encode(data).decode())+")\nassert hashlib.sha256(payload).hexdigest() == "+repr(actual)+"\nPath("+repr(artifact.name)+").write_bytes(payload)\nprint('Exact artifact written; SHA256', hashlib.sha256(payload).hexdigest())\n"
    cells.append({'cell_type':'code','metadata':{},'source':materialize,'execution_count':None,'outputs':[]})
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':cells}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'frontier-source.ipynb').write_text(json.dumps(notebook,indent=2)+'\n')
    metadata={'id':'tokenjunkielabs/'+slug,'title':'TITAN Kaggriculture Frontier Source','code_file':'frontier-source.ipynb','language':'python','kernel_type':'notebook','is_private':False,'enable_gpu':False,'enable_tpu':False,'enable_internet':False,'dataset_sources':[],'competition_sources':['kaggriculture'],'kernel_sources':[]}
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (output/'disclosure-manifest.json').write_text(json.dumps({'archive_sha256':actual,'source_ref':source_ref,'members':manifest,'status':'PREPARED_NOT_PUBLISHED'},indent=2)+'\n')
    return {'archive_sha256':actual,'notebook':str(output/'frontier-source.ipynb'),'status':'PREPARED_NOT_PUBLISHED'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--sha256',required=True);p.add_argument('--source-ref',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.artifact,a.sha256,a.output,a.source_ref)))
