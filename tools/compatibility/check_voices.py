#!/usr/bin/env python3
"""Fixed representative voice/language samples, not an exhaustive voice benchmark."""
import os,json,re,subprocess,sys,hashlib
from pathlib import Path
import numpy as np
import soundfile as sf
root=Path(__file__).resolve().parents[2];os.chdir(root)
out=Path('outputs/voices-2026-11-07');out.mkdir(parents=True,exist_ok=True)
a=Path('local/compat/assets');b='build/compat-profile/bin/audiocpp_cli'
os.environ.update(AUDIOCPP_ESPEAK_LIBRARY='/opt/homebrew/lib/libespeak-ng.dylib',AUDIOCPP_ESPEAK_DATA='/opt/homebrew/share/espeak-ng-data')
zh='今天上午九点半，请检查车票和随身行李。';en='At nine thirty, please check the train ticket and call the station.'
rows=[]
def save():Path('benchmarks/voices-and-languages-20261107.json').write_text(json.dumps(dict(host='M5 MacBook Air 24GB CPU4',seed=42,scope='one run per representative voice; human listening pending',results=rows),ensure_ascii=False,indent=2)+'\n')
def run(name,cmd,task='tts',lang='en',text=None):
 print('RUN',name,flush=True);p=subprocess.run([sys.executable,'tools/compatibility/compare_local.py','--worker',json.dumps(cmd)],capture_output=True,text=True,check=True)
 d=json.loads(p.stdout);log=d.pop('log');(out/(name+'.log')).write_text(log);d.update(name=name,argv=cmd,language=lang,text=text,metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M)));rows.append(d);save();return d
cases=[]
for lang,vs in [('zh',['zf_xiaobei','zf_xiaoyi','zm_yunjian','zm_yunxi']),('en-us',['af_heart','am_adam']),('en-gb',['bf_emma'])]:
 for voice in vs:cases.append(('kokoro',voice,lang,'Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf'))
for v in ['Bella','Leo']:cases.append(('kitten',v,'en','KittenTTS-GGUF/kitten-tts-mini-0.8-orig.gguf'))
for v in ['alba','anna','george']:cases.append(('pocket',v,'en','PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf'))
# Generate all TTS first; ASR checks run serially after F5 too.
for family,voice,lang,model in cases:
 name=family+'-'+voice;wav=out/(name+'.wav');text=zh if lang=='zh' else en
 cmd=[b,'--task','tts','--family',family+'_tts','--model',str(a/model),'--backend','cpu','--threads','4','--seed','42','--voice-id',voice,'--text',text,'--out',str(wav),'--metrics','--log']
 if family!='kitten':cmd+=['--language',lang]
 d=run(name,cmd,lang=lang,text=text)
 if d['returncode']==0:
  x,sr=sf.read(wav);d['audio']=dict(seconds=len(x)/sr,sample_rate=sr,finite=bool(np.isfinite(x).all()),peak=float(abs(x).max()),rms=float(np.sqrt(np.mean(x*x))),sha256=hashlib.sha256(wav.read_bytes()).hexdigest());save()
# F5 Chinese: same known synthetic English reference as prior English baseline.
name='f5-zh';raw=out/(name+'.f32')
d=run(name,['build/crisp-f5-compat/f5-native-probe',str(a/'f5-tts-v1-base-f16.gguf'),'outputs/unified-2026-11-07/reference-24k.f32',str(raw),zh],lang='zh',text=zh)
if d['returncode']==0:
 x=np.fromfile(raw,dtype='float32');sr=int(d['metrics']['sample_rate']);sf.write(out/(name+'.wav'),x,sr,subtype='PCM_16');d['audio']=dict(seconds=len(x)/sr,sample_rate=sr,finite=bool(np.isfinite(x).all()),peak=float(abs(x).max()),rms=float(np.sqrt(np.mean(x*x))));save()
# Recognizer readback is a quality screen, not human voice/speaker verification.
for row in list(rows):
 wav=out/(row['name']+'.wav')
 if row['returncode'] or not wav.exists():continue
 temp=out/(row['name']+'-16k.wav');subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-ar','16000','-ac','1',str(temp)],check=True)
 dest=out/(row['name']+'-readback');lang='zh' if row['language']=='zh' else 'en'
 r=run(row['name']+'-asr',['build/whisper-compat/bin/whisper-cli','-m',str(a/'ggml-base.bin'),'-t','4','-ng','-nt','-l',lang,'-f',str(temp),'-otxt','-of',str(dest)],task='asr',lang=lang)
 r['transcript']=dest.with_suffix('.txt').read_text().strip() if dest.with_suffix('.txt').exists() else '';print(r['transcript'],flush=True);save()
