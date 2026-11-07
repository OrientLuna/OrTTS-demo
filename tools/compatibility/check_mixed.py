#!/usr/bin/env python3
"""Mixed Chinese/English acceptance slice; no English-only fallback."""
import json,os,re,subprocess,sys
from pathlib import Path
import numpy as np
import soundfile as sf
root=Path(__file__).resolve().parents[2];os.chdir(root)
out=Path('outputs/mixed-2026-11-07');out.mkdir(parents=True,exist_ok=True)
a=Path('local/compat/assets');b='build/compat-profile/bin/audiocpp_cli'
os.environ.update(AUDIOCPP_ESPEAK_LIBRARY='/opt/homebrew/lib/libespeak-ng.dylib',AUDIOCPP_ESPEAK_DATA='/opt/homebrew/share/espeak-ng-data')
text='请打开 WiFi，然后说 Hello world。今天的 meeting 在下午三点开始。';rows=[]
def run(name,cmd):
 print('RUN',name,flush=True)
 r=subprocess.run([sys.executable,'tools/compatibility/compare_local.py','--worker',json.dumps(cmd)],capture_output=True,text=True,check=True);d=json.loads(r.stdout);log=d.pop('log');(out/(name+'.log')).write_text(log);d.update(name=name,argv=cmd,metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M)));rows.append(d);return d
for name,family,model,extra in [
 ('kokoro','kokoro_tts','Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf',['--language','zh','--voice-id','zf_xiaobei']),
 ('zipvoice','zipvoice','zipvoice-distill-q8_0.gguf',['--voice-ref','outputs/unified-2026-11-07/reference.wav','--reference-text','The northern wind crossed the quiet harbor.','--session-option','zipvoice.espeak_library_path=/opt/homebrew/lib/libespeak-ng.dylib'])]:
 wav=out/(name+'.wav');cmd=[b,'--task','tts' if name=='kokoro' else 'clon','--family',family,'--model',str(a/model),'--backend','cpu','--threads','4','--seed','42','--text',text,'--out',str(wav),'--metrics','--log']+extra
 d=run(name,cmd)
 if d['returncode']!=0:continue
 x,sr=sf.read(wav);d['audio']=dict(seconds=len(x)/sr,finite=bool(np.isfinite(x).all()),peak=float(abs(x).max()))
 audio16=out/(name+'-16k.wav');subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-ar','16000','-ac','1',str(audio16)],check=True)
 for engine in ['whisper','sensevoice']:
  txt=out/(name+'-'+engine+'.txt')
  if engine=='whisper':cmd=['build/whisper-compat/bin/whisper-cli','-m',str(a/'ggml-base.bin'),'-t','4','-ng','-nt','-l','zh','-f',str(audio16),'-otxt','-of',str(txt.with_suffix(''))]
  else:cmd=[b,'--task','asr','--family','sense_asr','--model',str(a/'sensevoice-small-q8-audiocpp-v1.gguf'),'--backend','cpu','--threads','4','--language','auto','--audio',str(audio16),'--request-option','audio_chunk_mode=none','--text-out',str(txt),'--metrics','--log']
  d=run(name+'-'+engine,cmd);d['transcript']=txt.read_text().strip() if txt.exists() else '';print(d['transcript'],flush=True)
report=dict(text=text,host='M5 MacBook Air 24GB, CPU4',human_listening='pending',results=rows)
Path('benchmarks/mixed-zh-en-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
