#!/usr/bin/env python3
"""Copy verified prepared sources and apply bounded speech fixes; no network."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
from source_identity import identity
ROOT=Path(__file__).resolve().parents[1]
def prepare(source,out):
 source=source.resolve();out=out.resolve()
 if out==source or out.is_relative_to(source):raise ValueError('Output must be outside input source tree')
 identity(source,(source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').exists())
 if out.exists():raise ValueError('Choose a fresh output directory')
 lock=json.loads((ROOT/'vendor/speech/lock.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if sha(ROOT/'vendor/speech/audio.patch')!=lock['patch_sha256']:raise ValueError('Speech patch modified')
 for f in lock['files']:
  if sha(source/f['path'])!=f['base_sha256']:raise ValueError('Speech base mismatch: '+f['path'])
 shutil.copytree(source,out)
 subprocess.run(['git','apply',str(ROOT/'vendor/speech/audio.patch')],cwd=out,env={**os.environ,'GIT_CEILING_DIRECTORIES':str(out.parent)},check=True)
 for f in lock['files']:
  if sha(out/f['path'])!=f['sha256']:raise ValueError('Speech patch output mismatch')
 (out/'ORTTS_SPEECH_SOURCE_RECEIPT.json').write_text(json.dumps(lock,indent=2)+'\n')
 return lock
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();print(json.dumps(prepare(a.source,a.out),indent=2))
