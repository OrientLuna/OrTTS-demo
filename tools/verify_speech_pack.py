#!/usr/bin/env python3
"""Verify a host speech catalog entry without downloads or changing any files."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def verify(manifest,model_id,root):
 doc=json.loads(manifest.read_text())
 if doc.get('schema')!='ortts-speech-catalog-v1':raise ValueError('Unsupported speech catalog schema')
 entries=[m for m in doc['models'] if m['id']==model_id]
 if len(entries)!=1:raise ValueError('Missing/duplicate model id')
 model=entries[0];root=root.resolve();seen=set()
 for asset in model['assets']:
  rel=Path(asset['path'])
  if '\\' in asset['path'] or rel.is_absolute() or '..' in rel.parts or asset['path'] in seen:raise ValueError('Invalid/duplicate asset path')
  seen.add(asset['path']);p=(root/rel).resolve()
  if not p.is_relative_to(root) or not p.is_file():raise ValueError('Missing/escaping asset: '+asset['path'])
  if p.stat().st_size!=asset['bytes'] or hashlib.file_digest(p.open('rb'),'sha256').hexdigest()!=asset['sha256']:raise ValueError('Asset size/SHA mismatch: '+asset['path'])
 if model['model_path'] not in seen:raise ValueError('Model path not covered by assets')
 return dict(family=model['family'],model_path=str(root/model['model_path']),verified_assets=len(seen),validated_languages=model['validated_languages'],voice_sample=model['voice_sample'])
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,default=ROOT/'runtime/models/catalog.example.json');p.add_argument('--id',required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.manifest,a.id,a.root),ensure_ascii=False,indent=2))
