#!/usr/bin/env python3
"""Real-model native C/Rust acceptance on the current host. No downloads."""
import argparse,hashlib,json,os,platform,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True,type=Path);p.add_argument('--source',required=True,type=Path);p.add_argument('--assets',required=True,type=Path);p.add_argument('--espeak-library',required=True,type=Path);p.add_argument('--espeak-data',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 from verify_speech_pack import verify
 catalog=ROOT/'runtime/models/catalog.example.json'
 for model in json.loads(catalog.read_text())['models']:verify(catalog,model['id'],a.assets)
 build=a.build.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);lib=build/'install/lib';env={**os.environ,'AUDIOCPP_ESPEAK_LIBRARY':str(a.espeak_library.resolve()),'AUDIOCPP_ESPEAK_DATA':str(a.espeak_data.resolve()),'ORTTS_TEST_VAD_MODEL':str((a.source/'assets/framework/models/silero_vad/silero_vad_16k.safetensors').resolve()),'ORTTS_LIB_DIR':str(lib)}
 if platform.system()=='Darwin':env['DYLD_LIBRARY_PATH']=str(lib)
 else:env['LD_LIBRARY_PATH']=str(lib)
 commands=[['c++','-std=c++17','-I'+str(ROOT/'runtime/include'),str(ROOT/'tests/speech_integration.cpp'),'-L'+str(lib),'-lortts','-Wl,-rpath,'+str(lib),'-o',str(out/'integration')],[str(out/'integration'),str(a.assets.resolve()),str(out)],['cargo','run','--offline','--manifest-path',str(ROOT/'runtime/rust/Cargo.toml'),'--example','speech','--',str(a.assets.resolve())]]
 rows=[]
 for i,cmd in enumerate(commands):
  r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=600);(out/f'check-{i}.log').write_text(r.stdout);rows.append({'step':i,'returncode':r.returncode});print('step',i,r.returncode,flush=True)
  if r.returncode:raise RuntimeError('Acceptance failed: '+str(out/f'check-{i}.log'))
 artifact=lib/('libortts.dylib' if platform.system()=='Darwin' else 'libortts.so');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 report={'schema':1,'host':platform.system()+' '+platform.machine(),'model_execution':'current host only; cross-builds are not device certification','checks':rows,'artifact_sha256':sha(artifact),'artifact_bytes':artifact.stat().st_size,'public_headers':{p.name:sha(p) for p in (ROOT/'runtime/include').glob('*.h')},'assertions':['five native-format TTS families','Kokoro/Pocket/ZipVoice callback/pull stream cancellation and reuse','Piper/Kitten reject streaming','English model rejects zh and Han text, invalid UTF-8 and missing voice','SenseVoice/Moonshine offline equals buffered-final','ASR bounds/reset/digital silence/nonfinite input','SenseVoice explicit Silero NoSpeech does not re-transcribe whole input','legacy and speech share BUSY gate','Rust native-rate copy + ASR + Pocket stream reuse'],'subjective_quality':'not certified'}
 (out/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
