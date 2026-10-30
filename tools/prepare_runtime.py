#!/usr/bin/env python3
"""Materialize a pinned upstream tree and local patch without network or source mutation."""
import argparse, hashlib, json, subprocess, tarfile, tempfile, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def prepare(source, destination):
    lock=json.loads((ROOT/'vendor/runtime.lock.json').read_text())
    patch=ROOT/lock['patch']
    if digest(patch)!=lock['patch_sha256']:raise ValueError('Runtime patch SHA mismatch')
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('Destination already exists; choose a fresh directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','-C',str(source),'cat-file','-e',lock['base_commit']+'^{commit}'],check=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'source.tar'
        subprocess.run(['git','-C',str(source),'archive','--format=tar','-o',str(archive),lock['base_commit']],check=True)
        destination.mkdir()
        with tarfile.open(archive) as tar:tar.extractall(destination,filter='data')
    subprocess.run(['git','apply','--check',str(patch)],cwd=destination,env={**os.environ,'GIT_CEILING_DIRECTORIES':str(destination.parent)},check=True)
    subprocess.run(['git','apply',str(patch)],cwd=destination,env={**os.environ,'GIT_CEILING_DIRECTORIES':str(destination.parent)},check=True)
    for item in lock.get('additional_patches',[]):
        extra=ROOT/item['path']
        if digest(extra)!=item['sha256']:raise ValueError('Additional runtime patch SHA mismatch')
        subprocess.run(['git','apply','--check',str(extra)],cwd=destination,env={**os.environ,'GIT_CEILING_DIRECTORIES':str(destination.parent)},check=True)
        subprocess.run(['git','apply',str(extra)],cwd=destination,env={**os.environ,'GIT_CEILING_DIRECTORIES':str(destination.parent)},check=True)
    for item in lock['selected_files']:
        if digest(destination/item['path'])!=item['sha256']:raise ValueError('Materialized source mismatch: '+item['path'])
    receipt={'schema':1,'base_commit':lock['base_commit'],'patch_sha256':lock['patch_sha256'],'verified_changed_files':len(lock['selected_files']),'additional_patches':lock.get('additional_patches',[]),'network_used':False,'upstream_checkout_modified':False}
    (destination/'ORTTS_SOURCE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-repo',required=True,type=Path);p.add_argument('--out',type=Path,default=ROOT/'_work/audio.cpp');a=p.parse_args();print(json.dumps(prepare(a.source_repo,a.out),indent=2))
