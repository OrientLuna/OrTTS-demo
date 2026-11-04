#!/usr/bin/env python3
"""Apply the reviewed public loader changes to a fresh unified source tree."""
from pathlib import Path
import argparse,hashlib,json,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
def apply(source):
 source=Path(source).resolve();assets=ROOT/'vendor/release-compat';lock=json.loads((assets/'lock.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 if (source/'ORTTS_RELEASE_COMPAT_RECEIPT.json').exists():raise ValueError('Release compatibility already applied')
 if not (source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').is_file():raise ValueError('Release candidate requires the pinned unified backend')
 if sha(assets/'audio.patch')!=lock['patch_sha256']:raise ValueError('Release patch SHA mismatch')
 for e in lock['files']:
  p=source/e['path']
  if (e['base_sha256'] is None and p.exists()) or (e['base_sha256'] is not None and (not p.is_file() or sha(p)!=e['base_sha256'])):raise ValueError('Release base mismatch: '+e['path'])
 env={**os.environ,'TMPDIR':'/tmp','GIT_CEILING_DIRECTORIES':str(source.parent)}
 subprocess.run(['git','apply','--check',str(assets/'audio.patch')],cwd=source,env=env,check=True)
 subprocess.run(['git','apply',str(assets/'audio.patch')],cwd=source,env=env,check=True)
 for e in lock['files']:
  if sha(source/e['path'])!=e['sha256']:raise ValueError('Release output mismatch: '+e['path'])
 (source/'ORTTS_RELEASE_COMPAT_RECEIPT.json').write_text(json.dumps(lock,indent=2)+'\n');return lock
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);a=p.parse_args();print(json.dumps(apply(a.source),indent=2))
