#!/usr/bin/env python3
"""Retry corrected Kitten options, screen VITS samples, test F5 Chinese reference."""
import json,os,re,subprocess,sys
from pathlib import Path
import numpy as np
import soundfile as sf
root=Path(__file__).resolve().parents[2];os.chdir(root);out=Path('outputs/voices-2026-11-07');a=Path('local/compat/assets');b='build/compat-profile/bin/audiocpp_cli';report=Path('benchmarks/voices-and-languages-20261107.json');doc=json.loads(report.read_text())
os.environ.update(AUDIOCPP_ESPEAK_LIBRARY='/opt/homebrew/lib/libespeak-ng.dylib',AUDIOCPP_ESPEAK_DATA='/opt/homebrew/share/espeak-ng-data')
def run(name,cmd,lang,text=''):
 print('RUN',name,flush=True);p=subprocess.run([sys.executable,'tools/compatibility/compare_local.py','--worker',json.dumps(cmd)],capture_output=True,text=True,check=True);r=json.loads(p.stdout);log=r.pop('log');(out/(name+'.log')).write_text(log);r.update(name=name,argv=cmd,language=lang,text=text,metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M)))
 doc['results']=[old for old in doc['results'] if old['name']!=name]+[r];report.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');return r
for voice in ['Bella','Leo']:
 name='kitten-'+voice;text='At nine thirty, please check the train ticket and call the station.'
 r=run(name,[b,'--task','tts','--family','kitten_tts','--model',str(a/'KittenTTS-GGUF/kitten-tts-mini-0.8-orig.gguf'),'--backend','cpu','--threads','4','--seed','42','--voice-id',voice,'--text',text,'--out',str(out/(name+'.wav')),'--metrics','--log'],'en',text)
 if r['returncode']==0:
  x,sr=sf.read(out/(name+'.wav'));r['audio']=dict(seconds=len(x)/sr,finite=bool(np.isfinite(x).all()),rms=float(np.sqrt(np.mean(x*x))));report.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
# No TTS overlap: VITS checks and Kitten checks before expensive F5.
def readback(name,lang):
 temp=out/(name+'-16k.wav');subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/(name+'.wav')),'-ar','16000','-ac','1',str(temp)],check=True);dest=out/(name+'-readback');r=run(name+'-asr',['build/whisper-compat/bin/whisper-cli','-m',str(a/'ggml-base.bin'),'-t','4','-ng','-nt','-l',lang,'-f',str(temp),'-otxt','-of',str(dest)],lang);r['transcript']=dest.with_suffix('.txt').read_text().strip() if dest.with_suffix('.txt').exists() else '';report.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');print(r['transcript'],flush=True)
for name in ['kitten-Bella','kitten-Leo']:readback(name,'en')
for sid in [0,21,100]:readback('vits-sid'+str(sid),'zh')
ref=out/'reference-zh.f32';subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'kokoro-zf_xiaoyi.wav'),'-ar','24000','-ac','1','-f','f32le',str(ref)],check=True)
name='f5-zh-zhref';target='欢迎使用本地语音合成。';r=run(name,['build/crisp-f5-compat/f5-native-probe',str(a/'f5-tts-v1-base-f16.gguf'),str(ref),str(out/(name+'.f32')),target,'今天上午九点半，请检查车票和随身行李。'],'zh',target)
if r['returncode']==0:
 x=np.fromfile(out/(name+'.f32'),dtype='float32');sr=int(r['metrics']['sample_rate']);sf.write(out/(name+'.wav'),x,sr,subtype='PCM_16');r['audio']=dict(seconds=len(x)/sr,finite=bool(np.isfinite(x).all()),rms=float(np.sqrt(np.mean(x*x))));report.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');readback(name,'zh')
# Cross-check ambiguous 8kHz/F5 readbacks with another recognizer.
for name in ['vits-sid0','vits-sid21','vits-sid100','f5-zh','f5-zh-zhref']:
 txt=out/(name+'-sensevoice.txt');temp=out/(name+'-16k.wav');r=run(name+'-sensevoice',[b,'--task','asr','--family','sense_asr','--model',str(a/'sensevoice-small-q8-audiocpp-v1.gguf'),'--backend','cpu','--threads','4','--language','zh','--audio',str(temp),'--request-option','audio_chunk_mode=none','--text-out',str(txt),'--metrics','--log'],'zh');r['transcript']=txt.read_text().strip() if txt.exists() else '';report.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');print(name,r['transcript'],flush=True)
