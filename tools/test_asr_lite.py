#!/usr/bin/env python3
"""Real OrTTS C-ABI bilingual smoke/recovery benchmark. Local assets only.
Desktop accelerated execution is NEVER a physical low-end acceptance report.
"""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import wave
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
 if platform.system()!='Darwin':p.error('This harness currently measures macOS native RSS, not mobile footprint')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);lib=a.build.resolve()/'install/lib';assets=a.assets.resolve();binary=out/'asr-lite-test'
 subprocess.run(['clang++','-std=c++17','-O2','-I'+str(ROOT/'runtime/include'),str(ROOT/'tests/asr_lite_integration.cpp'),'-L'+str(lib),'-lortts','-Wl,-rpath,'+str(lib),'-o',str(binary)],check=True)
 trials=[]
 for i in range(5):
  wav=assets/f'test_wavs/{i}.wav'
  with wave.open(str(wav),'rb') as f:
   if (f.getframerate(),f.getnchannels(),f.getsampwidth())!=(16000,1,2):raise ValueError('Expected 16kHz mono PCM16 fixture')
   samples=array.array('h',f.readframes(f.getnframes()))
   if sys.byteorder!='little':samples.byteswap()
   pcm=array.array('f',(v/32768. for v in samples))
  raw=out/f'{i}.f32';raw.write_bytes(pcm.tobytes())
  for repeat in range(3 if i==0 else 1):
   transcript=out/f'{i}-{repeat}.txt'
   r=subprocess.run([str(binary),str(assets),str(raw),str(transcript)],capture_output=True,text=True,timeout=120,env={**os.environ,'DYLD_LIBRARY_PATH':str(lib)})
   (out/f'{i}-{repeat}.log').write_text(r.stdout+r.stderr)
   if r.returncode:raise RuntimeError(f'Native acceptance failed: {out}/{i}-{repeat}.log')
   metrics=json.loads(r.stdout);metrics['peak_rss_mib']=metrics.pop('peak_rss_native_units')/1024/1024
   trials.append({'fixture':f'test_wavs/{i}.wav','input_sha256':sha(wav),'repeat':repeat,'hypothesis':transcript.read_text(),'reference':None,'human_reference_verified':False,**metrics})
   print('native fixture',i,'repeat',repeat,'passed',flush=True)
 cpu=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip();ram=int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True));hardware=subprocess.check_output(['sysctl','-n','hw.model'],text=True).strip()
 receipt=json.loads((a.build.resolve()/'ENGINE_BUILD_RECEIPT.json').read_text())
 report={'source_base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'runtime_sources_sha256':receipt['plugin_source_sha256'],'source_state':'uncommitted-ASR-prototype-on-base-commit','schema':'ortts-asr-desktop-smoke-v1','date':'2026-11-13','scope':'macos-accelerated-functional-and-recovery-only','physical_low_end_certified':False,'quality_scored':False,'host':{'os':platform.system(),'arch':platform.machine(),'os_version':platform.mac_ver()[0],'cpu':cpu,'ram_bytes':ram,'hardware':hardware},'runtime_sha256':sha(lib/'libortts.dylib'),'model_identity':json.loads((ROOT/'runtime/models/asr-recipes.json').read_text())['profiles'][0]['identity_sha256'],'test_source_sha256':sha(ROOT/'tests/asr_lite_integration.cpp'),'model_assets':[{'path':v['path'],'sha256':sha(assets/v['path'])} for v in json.loads((ROOT/'runtime/models/asr-recipes.json').read_text())['profiles'][0]['model']['assets']],'dependencies':[{'name':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(lib.glob('*.dylib'))],'cold_load_scope':'new-process-with-possibly-warm-OS-file-cache; includes asset hashes and recognizer load','trials':trials,'summary':{'process_cold_load_ms':[r['cold_load_ms'] for r in trials[:3]],'warm_rtf_median':statistics.median(r['warm_rtf'] for r in trials),'peak_rss_mib_max':max(r['peak_rss_mib'] for r in trials)},'limitations':['No A53/A55/old-iPhone physical evidence','No manually checked reference corpus; no accuracy claim','RSS of standalone macOS process is not Android PSS or iOS physical footprint','Accelerated input is not realtime microphone latency or thermal evidence','ORT compatibility is an additional tensor backend, not ggml unification']}
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
