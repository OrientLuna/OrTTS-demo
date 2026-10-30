#!/usr/bin/env python3
"""Run a user-supplied native P3/P5 asset manifest. No downloads, SSH, ADB or GPU."""
import argparse, hashlib, json, re, struct, math, subprocess, os
from pathlib import Path
FILES=('model','bridge_manifest','decoder','base_decoder','vocoder','speaker')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def resolve_assets(manifest,verify=False,allow_external=False,voice=None):
 manifest=manifest.resolve();doc=json.loads(manifest.read_text())
 if doc.get('schema')!='ortts-demo-assets-v1' or doc.get('variant') not in ('P3','P5'):raise ValueError('Unsupported model variant')
 root=manifest.parent;files={}
 voice=voice or doc.get("default_voice")
 items=dict(doc["files"])
 if "voices" in doc:
  if voice not in doc["voices"]:raise ValueError("Unknown standard voice")
  items["speaker"]=doc["voices"][voice]
 names=FILES+(("p3_weights","p3_config","p3_talker_config") if doc["variant"]=="P3" else ())
 for name in names:
  item=items[name];rel=Path(item['path'])
  if rel.is_absolute() or '..' in rel.parts:raise ValueError('Asset paths must be relative and inside the asset manifest root')
  p=(root/rel).resolve()
  if (not allow_external and not p.is_relative_to(root)) or not p.is_file():raise ValueError('Missing or escaping asset: '+name)
  digest=item['sha256']
  if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Fill a real SHA256 for '+name)
  if verify and sha(p)!=digest:raise ValueError('SHA mismatch: '+name)
  files[name]=p
 vector=files['speaker'].read_bytes()
 if len(vector)!=4096 or not all(math.isfinite(x) for x in struct.unpack('<1024f',vector)):raise ValueError('Speaker must be1024 finite F32 values from this 0.6B model')
 if sha(files['speaker'])!=items['speaker']['sha256']:raise ValueError('Speaker vector SHA mismatch')
 if sha(files['bridge_manifest'])!=doc['files']['bridge_manifest']['sha256']:raise ValueError('Bridge manifest identity mismatch')
 if doc["variant"]=="P3" and len({files[k].parent for k in ("p3_weights","p3_config","p3_talker_config")})!=1:raise ValueError("P3 files must share one source directory")
 return doc,files

def argv_for(binary,doc,files,args):
 cmd=[str(binary.resolve()),'--model',str(files['model']),'--bridge',str(files['bridge_manifest'].parent),'--decoder',str(files['decoder']),'--base-decoder',str(files['base_decoder']),'--vocoder',str(files['vocoder']),'--speaker',str(files['speaker']),'--manifest-sha',doc['files']['bridge_manifest']['sha256'],'--text',args.text,'--out',str(args.out.resolve()),'--threads',str(args.threads),'--seed',str(args.seed),'--repeats',str(args.repeats),'--max-tokens',str(args.max_tokens)]
 if doc['variant']=='P3':cmd+=['--p3-source',str(files['p3_weights'].parent)]
 return cmd
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets-manifest',required=True,type=Path);p.add_argument('--binary',required=True,type=Path);p.add_argument('--voice',choices=['female','male']);p.add_argument('--text',required=True);p.add_argument('--out',required=True,type=Path);p.add_argument('--threads',type=int,default=4);p.add_argument('--seed',type=int,default=20261029);p.add_argument('--repeats',type=int,default=1);p.add_argument('--max-tokens',type=int,default=513);p.add_argument('--verify-assets',action='store_true');p.add_argument('--allow-external-assets',action='store_true',help='Explicitly permit read-only symlinks to existing shared asset locations');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 if not(1<=a.threads<=8 and 1<=a.repeats<=3 and 1<=a.max_tokens<=513 and 0<=a.seed<=0xffffffff):p.error('Invalid threads/repeats/token budget/seed')
 doc,files=resolve_assets(a.assets_manifest,a.verify_assets,a.allow_external_assets,a.voice);cmd=argv_for(a.binary,doc,files,a);print(json.dumps({'argv':cmd,'mode':'offline_whole_sentence','first_pcm_ms':None},ensure_ascii=False,indent=2))
 if not a.dry_run:
  if a.out.exists():raise ValueError('Choose a fresh output directory')
  subprocess.run(cmd,check=True,env={k:v for k,v in os.environ.items() if not k.startswith("ORTTS_")})
