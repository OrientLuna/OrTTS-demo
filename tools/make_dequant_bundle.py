#!/usr/bin/env python3
"""Extract the unchanged official Qwen dequant subset from a trusted local bundle."""
from pathlib import Path
import argparse,json,hashlib,shutil,struct
TOKENIZER='836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(source,expected,out):
 source=Path(source).resolve();out=Path(out).resolve();mf=source/'MANIFEST.json'
 if sha(mf)!=expected:raise ValueError('Source manifest SHA mismatch')
 if out.exists():raise ValueError('Output must be fresh')
 m=json.loads(mf.read_text());catalog=json.loads((Path(__file__).resolve().parents[1]/'vendor/release-compat/dequant_catalog.json').read_text());items=m['tensors'];keys=['codebook.'+str(i)for i in range(16)]+['semantic.projection.weight','acoustic.projection.weight'];selected={}
 # Match all 18 unchanged payload identities against the reviewed official-table catalog.
 # Older manifests lack an explicit tokenizer SHA; their source description alone is insufficient.
 for key in keys:
  row=items[key];
  if any(row[k]!=catalog['tensors'][key][k] for k in ['shape','dtype','bytes','sha256']):raise ValueError('Canonical official table identity mismatch: '+key)
  rel=Path(row['path']);file=(source/rel).resolve();shape=[2048,256]if key.startswith('codebook.')else[512,256]
  if rel.is_absolute()or'..'in rel.parts or not file.is_relative_to(source)or row['dtype']!='F32'or row['shape']!=shape or row['bytes']!=shape[0]*shape[1]*4 or file.stat().st_size!=row['bytes']or sha(file)!=row['sha256']:raise ValueError('Dequant tensor mismatch: '+key)
  selected[key]={**row,'path':key+'.f32'}
 out.mkdir(parents=True)
 for key,row in selected.items():shutil.copyfile(source/items[key]['path'],out/row['path'])
 doc={'schema':'ortts-qwen-dequant-v1','checkpoint_kind':'QWEN_DEQUANT_ONLY','endianness':'little','qwen_tokenizer_sha256':TOKENIZER,'source_manifest_sha256':expected,'source_RVQ_groups':16,'codebook_size':2048,'output_dim':512,'tensors':selected}
 (out/'MANIFEST.json').write_text(json.dumps(doc,indent=2)+'\n');return {'manifest_sha256':sha(out/'MANIFEST.json'),'tensor_count':18,'mathematics_changed':False}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--trusted-source-sha',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args();print(json.dumps(prepare(a.source,a.trusted_source_sha,a.out),indent=2))
