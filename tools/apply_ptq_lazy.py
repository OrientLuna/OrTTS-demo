"""Apply opt-in PTQ/lazy support after unified public compatibility patches."""
from pathlib import Path
import hashlib,json,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
def apply(source):
 source=Path(source);lock=json.loads((ROOT/'vendor/ptq-lazy.lock.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();patch=ROOT/lock['patch']
 if sha(patch)!=lock['patch_sha256']:raise ValueError('PTQ patch SHA mismatch')
 for e in lock['files']:
  if sha(source/e['path'])!=e['base_sha256']:raise ValueError('PTQ base mismatch: '+e['path'])
 env={**os.environ,'GIT_CEILING_DIRECTORIES':str(source.parent),'TMPDIR':'/tmp'}
 for args in [['git','apply','--check',str(patch)],['git','apply',str(patch)]]:subprocess.run(args,cwd=source,env=env,check=True)
 for e in lock['files']:
  if sha(source/e['path'])!=e['sha256']:raise ValueError('PTQ output mismatch')
 (source/'ORTTS_PTQ_LAZY_RECEIPT.json').write_text(json.dumps(lock,indent=2)+'\n')
