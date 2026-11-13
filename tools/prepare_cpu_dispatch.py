#!/usr/bin/env python3
"""Prepare checked Android CPU variants from local unified sources; no download."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path
from source_identity import identity
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(source,out):
 source=source.resolve();out=out.resolve()
 if out.exists() or out==source or out.is_relative_to(source):raise ValueError('Choose a fresh output outside the input tree')
 if (source/'ORTTS_CPU_DISPATCH_RECEIPT.json').exists():raise ValueError('CPU dispatch already applied')
 if (source/'ORTTS_CANCELLATION_RECEIPT.json').exists():raise ValueError('CPU auto-dispatch + cooperative cancellation is unsupported; use separate fixed-profile cancellation sources')
 speech=(source/'ORTTS_SPEECH_SOURCE_RECEIPT.json').exists()
 identity(source,True,speech)
 ur=json.loads((source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').read_text());ggml=Path(ur['ggml_source_dir'])
 if any(out.is_relative_to(p.resolve()) for p in [ggml,source.parent/'mtmd']):raise ValueError('Output must not be inside a copied dependency')
 vendor=ROOT/'vendor/cpu-dispatch';lock=json.loads((vendor/'lock.json').read_text())
 for name,digest in lock['patches'].items():
  if sha(vendor/name)!=digest:raise ValueError('CPU dispatch patch modified: '+name)
 for item in lock['files']:
  base=source if item['scope']=='audio' else ggml;p=base/item['path']
  if item['base_sha256'] is None:
   if p.exists():raise ValueError('CPU dispatch new file already exists: '+str(p))
  elif not p.is_file() or sha(p)!=item['base_sha256']:raise ValueError('CPU dispatch base mismatch: '+str(p))
 support=['mtmd','fullchain_probe.cpp','lc_fixture.cpp','compat_probe.cpp']
 for name in support:
  if not (source.parent/name).exists():raise ValueError('Missing unified support: '+name)
 out.mkdir(parents=True)
 for origin,target in [(source,out/'audio.cpp'),(ggml,out/'ggml')]+[(source.parent/n,out/n) for n in support]:
  if origin.is_dir():shutil.copytree(origin,target,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
  else:shutil.copyfile(origin,target)
 env={**os.environ,'GIT_CEILING_DIRECTORIES':str(out),'TMPDIR':'/tmp'}
 for scope,directory in [('audio',out/'audio.cpp'),('ggml',out/'ggml')]:
  patch=vendor/(scope+'.patch')
  subprocess.run(['git','apply','--check',str(patch)],cwd=directory,env=env,check=True)
  subprocess.run(['git','apply',str(patch)],cwd=directory,env=env,check=True)
 ur['llama_source_read_only']=str(Path(ur.get('llama_source_read_only',ggml.parent)).resolve())
 ur['ggml_source_dir']=str(out/'ggml');ur['out']=str(out)
 (out/'audio.cpp/ORTTS_UNIFIED_SOURCE_RECEIPT.json').write_text(json.dumps(ur,indent=2)+'\n')
 (out/'audio.cpp/ORTTS_CPU_DISPATCH_RECEIPT.json').write_text(json.dumps(lock,indent=2)+'\n')
 identity(out/'audio.cpp',True,speech)
 return {'source':str(out/'audio.cpp'),'ggml':str(out/'ggml'),'verified':True,'models_copied':False}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.source,a.out),indent=2))
