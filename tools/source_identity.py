"""Validate legacy sources, or an explicitly opted-in unified source tree."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def identity(source,liquidcodec=False,speech=False):
 source=Path(source);lock=json.loads((ROOT/'vendor/runtime.lock.json').read_text())
 receipt=json.loads((source/'ORTTS_SOURCE_RECEIPT.json').read_text())
 for k in ('base_commit','patch_sha256'):
  if receipt[k]!=lock[k]:raise ValueError('Source identity mismatch: '+k)
 if receipt.get('additional_patches',[])!=lock.get('additional_patches',[]):raise ValueError('Source patch list mismatch')
 dispatch=None
 if (source/'ORTTS_CPU_DISPATCH_RECEIPT.json').exists():
  dispatch=json.loads((ROOT/'vendor/cpu-dispatch/lock.json').read_text())
  if json.loads((source/'ORTTS_CPU_DISPATCH_RECEIPT.json').read_text())!=dispatch:raise ValueError('CPU dispatch receipt mismatch')
  for name,digest in dispatch['patches'].items():
   if hashlib.sha256((ROOT/'vendor/cpu-dispatch'/name).read_bytes()).hexdigest()!=digest:raise ValueError('CPU dispatch patch modified: '+name)
 u=source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json';changes={}
 if u.exists():
  if not liquidcodec:raise ValueError('Unified source requires --liquidcodec; legacy builds use their original source')
  ul=json.loads((ROOT/'vendor/unified/lock.json').read_text());ur=json.loads(u.read_text())
  if ur['unified_patch_sha256']!=ul['patch_sha256']:raise ValueError('Unified integration identity mismatch')
  if hashlib.sha256((Path(ur['ggml_source_dir'])/'include/ggml.h').read_bytes()).hexdigest()!=ul['ggml_header_sha256']:raise ValueError('Unified ggml identity mismatch')
  llama=Path(ur['llama_source_read_only']) if dispatch else Path(ur['ggml_source_dir']).parent
  for item in ul['llama_sources']:
   actual=llama/item['path'];digest=item['sha256']
   if dispatch and item['path'].startswith('ggml/'):
    relative=item['path'][len('ggml/'):]
    actual=Path(ur['ggml_source_dir'])/relative
    digest=next((x['sha256'] for x in dispatch['files'] if x['scope']=='ggml' and x['path']==relative),digest)
   if hashlib.sha256(actual.read_bytes()).hexdigest()!=digest:raise ValueError('Pinned llama source modified: '+item['path'])
  if ur.get('mtmd_sources'):
   for path,digest in ur['mtmd_sources'].items():
    if hashlib.sha256((source.parent/'mtmd'/path).read_bytes()).hexdigest()!=digest:raise ValueError('Patched mtmd source modified: '+path)
  for path,digest in ul['support_files'].items():
   if hashlib.sha256((source.parent/path).read_bytes()).hexdigest()!=digest:raise ValueError('Unified support source modified: '+path)
  changes={x['path']:x['sha256']for x in ul['changed_files']}
 elif liquidcodec:raise ValueError('Prepare unified sources before using --liquidcodec')
 expected={x['path']:x['sha256']for x in lock['selected_files']};expected.update(changes)
 release=source/'ORTTS_RELEASE_COMPAT_RECEIPT.json'
 if release.exists():
  rl=json.loads((ROOT/'vendor/release-compat/lock.json').read_text());rr=json.loads(release.read_text())
  if rr!=rl or hashlib.sha256((ROOT/'vendor/release-compat/audio.patch').read_bytes()).hexdigest()!=rl['patch_sha256']:raise ValueError('Release source receipt mismatch')
  expected.update({x['path']:x['sha256'] for x in rl['files']})
  lock={**lock,'release_compat':rl}
 sr=source/'ORTTS_SPEECH_SOURCE_RECEIPT.json'
 if sr.exists():
  if not speech:raise ValueError('Speech source requires --speech')
  sl=json.loads((ROOT/'vendor/speech/lock.json').read_text())
  if json.loads(sr.read_text())!=sl or hashlib.sha256((ROOT/'vendor/speech/audio.patch').read_bytes()).hexdigest()!=sl['patch_sha256']:raise ValueError('Speech source receipt mismatch')
  expected.update({x['path']:x['sha256'] for x in sl['files']})
  lock={**lock,'speech':sl}
 elif speech:raise ValueError('Prepare speech sources before using --speech')
 ptq=source/'ORTTS_PTQ_LAZY_RECEIPT.json'
 if ptq.exists():
  pl=json.loads((ROOT/'vendor/ptq-lazy.lock.json').read_text())
  if json.loads(ptq.read_text())!=pl or hashlib.sha256((ROOT/pl['patch']).read_bytes()).hexdigest()!=pl['patch_sha256']:raise ValueError('PTQ source receipt mismatch')
  expected.update({x['path']:x['sha256'] for x in pl['files']})
  lock={**lock,'ptq_lazy':pl}
 if dispatch:
  if not u.exists():raise ValueError('CPU dispatch requires unified sources')
  ggml=Path(json.loads(u.read_text())['ggml_source_dir'])
  for item in dispatch['files']:
   if item['scope']=='audio':expected[item['path']]=item['sha256']
   elif item['scope']=='ggml':
    if hashlib.sha256((ggml/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('CPU dispatch ggml modified: '+item['path'])
   else:raise ValueError('Unknown CPU dispatch source scope')
  lock={**lock,'cpu_dispatch':dispatch}
 for rel,digest in expected.items():
  if hashlib.sha256((source/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Prepared source modified: '+rel)
 return lock
