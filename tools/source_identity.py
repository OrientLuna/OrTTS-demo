"""Validate legacy sources, or an explicitly opted-in unified source tree."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def identity(source,liquidcodec=False):
 source=Path(source);lock=json.loads((ROOT/'vendor/runtime.lock.json').read_text())
 receipt=json.loads((source/'ORTTS_SOURCE_RECEIPT.json').read_text())
 for k in ('base_commit','patch_sha256'):
  if receipt[k]!=lock[k]:raise ValueError('Source identity mismatch: '+k)
 if receipt.get('additional_patches',[])!=lock.get('additional_patches',[]):raise ValueError('Source patch list mismatch')
 u=source/'ORTTS_UNIFIED_SOURCE_RECEIPT.json';changes={}
 if u.exists():
  if not liquidcodec:raise ValueError('Unified source requires --liquidcodec; legacy builds use their original source')
  ul=json.loads((ROOT/'vendor/unified/lock.json').read_text());ur=json.loads(u.read_text())
  if ur['unified_patch_sha256']!=ul['patch_sha256']:raise ValueError('Unified integration identity mismatch')
  if hashlib.sha256((Path(ur['ggml_source_dir'])/'include/ggml.h').read_bytes()).hexdigest()!=ul['ggml_header_sha256']:raise ValueError('Unified ggml identity mismatch')
  llama=Path(ur['ggml_source_dir']).parent
  for item in ul['llama_sources']:
   if hashlib.sha256((llama/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Pinned llama source modified: '+item['path'])
  changes={x['path']:x['sha256']for x in ul['changed_files']}
 elif liquidcodec:raise ValueError('Prepare unified sources before using --liquidcodec')
 expected={x['path']:x['sha256']for x in lock['selected_files']};expected.update(changes)
 for rel,digest in expected.items():
  if hashlib.sha256((source/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Prepared source modified: '+rel)
 return lock
