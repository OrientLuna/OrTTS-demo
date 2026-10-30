#!/usr/bin/env python3
"""Hash an existing model-only directory into a local manifest. Never copy or download assets."""
import argparse,json
from pathlib import Path
from run import sha
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-external-assets',action='store_true');p.add_argument('--variant',choices=['P3','P5'],default='P5');p.add_argument('--decoder',default='tokenizer-b260k-MIXED_Q4_0.gguf');p.add_argument('--p3-source',default='P3/predictor');p.add_argument('--standard-voices',action='store_true');p.add_argument('--speaker',default='voices/female.f32');a=p.parse_args();root=a.assets.resolve()
 paths={'model':'model.gguf','bridge_manifest':'bridge/MANIFEST.json','decoder':a.decoder,'base_decoder':'tokenizer-LFM2.5-Audio-1.5B-Q4_0.gguf','vocoder':'vocoder-LFM2.5-Audio-1.5B-Q4_0.gguf','speaker':a.speaker}
 if (root/'native/model.gguf').is_file():
  for name in ['model','bridge_manifest','decoder','base_decoder','vocoder']:paths[name]='native/'+paths[name]
 if a.standard_voices:paths['speaker']='voices/female.f32'
 if a.variant=='P3':paths.update(p3_weights=a.p3_source+'/predictor.safetensors',p3_config=a.p3_source+'/config.json',p3_talker_config=a.p3_source+'/talker_config.json')
 if a.out.exists():raise ValueError('Never overwrite a manifest')
 if a.out.resolve().parent!=root:raise ValueError('Write manifest directly inside the explicit assets root')
 files={}
 for k,n in paths.items():
  if Path(n).is_absolute() or '..' in Path(n).parts:raise ValueError('Asset aliases must be relative without parent traversal')
  v=(root/n).resolve()
  if (not a.allow_external_assets and not v.is_relative_to(root)) or not v.is_file():raise ValueError('Missing or escaping '+k)
  files[k]={'path':n,'bytes':v.stat().st_size,'sha256':sha(v)}
 doc={'schema':'ortts-demo-assets-v1','variant':a.variant,'files':files}
 if a.standard_voices:
  voices={}
  for name in ['female','male']:
   rel='voices/'+name+'.f32';v=(root/rel).resolve()
   if (not a.allow_external_assets and not v.is_relative_to(root)) or not v.is_file():raise ValueError('Missing/escaping voice '+name)
   voices[name]={'path':rel,'sha256':sha(v),'bytes':v.stat().st_size}
  doc.update(default_voice='female',voices=voices)
 a.out.write_text(json.dumps(doc,indent=2)+'\n');print(str(a.out))
