#!/usr/bin/env python3
"""Create a fresh private source tree; no download, weights, builds or source edits."""
from pathlib import Path
import argparse,hashlib,json,subprocess,shutil,os
ROOT=Path(__file__).resolve().parents[1]/"vendor/unified"
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release-compat',action='store_true');p.add_argument('--audio-source',type=Path,required=True);p.add_argument('--llama-source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();lock=json.loads((ROOT/'lock.json').read_text())
 if out.exists():raise ValueError('Output must not exist')
 if sha(ROOT/'audio.patch')!=lock['patch_sha256']:raise ValueError('Patch SHA mismatch')
 if sha(a.llama_source/'ggml/include/ggml.h')!=lock['ggml_header_sha256']:raise ValueError('Pinned ggml header identity mismatch')
 for item in lock['llama_sources']:
  if sha(a.llama_source/item['path'])!=item['sha256']:raise ValueError('Pinned llama source mismatch: '+item['path'])
 for item in lock['changed_files']:
  if item['base_sha256'] and sha(a.audio_source/item['path'])!=item['base_sha256']:raise ValueError('Base source mismatch: '+item['path'])

 if sha(ROOT/'mtmd.patch')!=lock['mtmd_patch_sha256']:raise ValueError('mtmd patch SHA mismatch')
 for name,digest in lock['support_files'].items():
  if sha(ROOT/'support'/name)!=digest:raise ValueError('Support source mismatch: '+name)
 out.mkdir(parents=True);audio=out/'audio.cpp';shutil.copytree(a.audio_source,audio,ignore=shutil.ignore_patterns('.git','ggml','__pycache__','*.pyc'),symlinks=True)
 for item in lock['changed_files']:
  f=audio/item['path']
  if item['base_sha256']:f.write_text(f.read_text()) # Normalize changed CRLF files before LF patch.
 env={**os.environ,'GIT_CEILING_DIRECTORIES':str(out),'TMPDIR':'/tmp'}
 subprocess.run(['git','apply','--check',str(ROOT/'audio.patch')],cwd=audio,env=env,check=True);subprocess.run(['git','apply',str(ROOT/'audio.patch')],cwd=audio,env=env,check=True)
 mt=out/'mtmd';shutil.copytree(a.llama_source/'tools/mtmd',mt)
 subprocess.run(['git','apply','--check',str(ROOT/'mtmd.patch')],cwd=mt,env=env,check=True);subprocess.run(['git','apply',str(ROOT/'mtmd.patch')],cwd=mt,env=env,check=True)
 for name in ['fullchain_probe.cpp','lc_fixture.cpp','compat_probe.cpp']:shutil.copy2(ROOT/'support'/name,out/name)
 for item in lock['changed_files']:
  if sha(audio/item['path'])!=item['sha256']:raise ValueError('Patched source differs: '+item['path'])
 receipt={'ggml_source_dir':str((a.llama_source/'ggml').resolve()),'unified_patch_sha256':lock['patch_sha256'],'files_verified':len(lock['changed_files']),'patch_SHA':lock['patch_sha256'],'llama_source_read_only':str(a.llama_source.resolve()),'base_untouched':True,'out':str(out),
          'mtmd_sources':{str(f.relative_to(mt)):sha(f) for f in mt.rglob('*') if f.is_file()}}
 (audio/'ORTTS_UNIFIED_SOURCE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');
 if a.release_compat:
  from apply_release_compat import apply
  apply(audio)
 print(json.dumps(receipt))
if __name__=='__main__':main()
