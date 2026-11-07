#!/usr/bin/env python3
"""Run a small multi-model CPU corpus; models must already be installed/verified."""
import argparse, hashlib, json, os, re, subprocess, time
from pathlib import Path
import numpy as np
import soundfile as sf
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
en='The northern wind crossed the quiet harbor. At nine thirty, please check the train ticket and call the station.'
zh='今天是十一月七日，上午九点三十分的列车即将出发。请检查身份证、车票和随身行李，确认手机电量充足。欢迎使用本地语音合成，祝你旅途愉快。'
k='Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf';v='Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf';s='sensevoice-small-q8-audiocpp-v1.gguf'
cases=[('piper-en','piper_tts',v,en,'en',None,[]),('kokoro-en','kokoro_tts',k,en,'en-us','af_heart',[]),('kokoro-en-male','kokoro_tts',k,en,'en-us','am_adam',[]),('kokoro-zh-stream','kokoro_tts',k,zh,'zh','zf_xiaobei',['--mode','streaming','--text-chunk-size','30']),('kokoro-zh-mixed','kokoro_tts',k,'今天是2026年11月7日，订单编号A123，价格是99.50元。请在下午3:30检查GPU和WiFi设置。','zh','zf_xiaobei',[])]
results=[]
def execute(name,cmd):
 start=time.monotonic();r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=300);wall=time.monotonic()-start;(a.out/(name+'.log')).write_text(r.stdout)
 metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',r.stdout,re.M));return {'name':name,'argv':cmd,'returncode':r.returncode,'process_wall_s':wall,'metrics':metrics}
for name,family,model,text,lang,voice,options in cases:
 output=a.out/(name+'.wav');cmd=[str(a.binary.resolve()),'--task','tts','--family',family,'--model',str((a.assets/model).resolve()),'--backend','cpu','--threads','4','--text',text,'--language',lang,'--seed','42','--out',str(output.resolve())]+options
 if voice:cmd+=['--voice-id',voice]
 cmd+=['--log'] if 'streaming' in options else ['--metrics','--log']
 result=execute(name,cmd);result['text']=text
 if result['returncode']==0:
  x,rate=sf.read(output,dtype='float32',always_2d=True);result['audio']={'sample_rate':rate,'channels':x.shape[1],'frames':len(x),'seconds':len(x)/rate,'finite':bool(np.isfinite(x).all()),'peak':float(np.max(np.abs(x))),'rms':float(np.sqrt(np.mean(x*x))),'clipped_fraction':float(np.mean(np.abs(x)>=1)),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
 results.append(result);print(name,result['returncode'],result.get('audio',{}).get('seconds'),flush=True)
# Silence is a negative ASR fixture, not a recognition accuracy benchmark.
silence=a.out/'silence.wav';sf.write(silence,np.zeros(16000*5,dtype='float32'),16000)
for name,input_path,lang in [('asr-silence',silence,'auto'),('asr-public-zh',a.out/'reference-zh.wav','zh'),('asr-kokoro-zh',a.out/'kokoro-zh-stream.wav','zh'),('asr-piper-en',a.out/'piper-en.wav','en')]:
 if not input_path.exists():continue
 text_path=a.out/(name+'.txt');cmd=[str(a.binary.resolve()),'--task','asr','--family','sense_asr','--model',str((a.assets/s).resolve()),'--backend','cpu','--threads','4','--audio',str(input_path.resolve()),'--language',lang,'--request-option','audio_chunk_mode=none','--text-out',str(text_path.resolve()),'--metrics','--log']
 result=execute(name,cmd);result['transcript']=text_path.read_text() if text_path.exists() else None;result['quality_checks']={'silence_empty':not bool((result['transcript'] or '').strip())} if name=='asr-silence' else {};results.append(result);print(name,result['returncode'],result['transcript'],flush=True)
# Unsupported voice must fail clearly, not silently choose another voice.
result=execute('invalid-voice',[str(a.binary.resolve()),'--task','tts','--family','kokoro_tts','--model',str((a.assets/k).resolve()),'--text','Hello','--voice-id','not_a_voice','--backend','cpu']);result['expected_failure']=True;results.append(result)
(a.out/'smoke-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
failed=[r['name'] for r in results if (r['returncode']==0)==r.get('expected_failure',False)]
failed += [r['name']+':quality' for r in results if any(v is False for v in r.get('quality_checks',{}).values())]
failed += [r['name']+':PCM' for r in results if r.get('audio') and (not r['audio']['finite'] or r['audio']['channels']!=1 or r['audio']['frames']<=0)]
if failed:raise SystemExit('Unexpected statuses: '+str(failed))
