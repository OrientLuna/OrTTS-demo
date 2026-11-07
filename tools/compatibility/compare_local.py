#!/usr/bin/env python3
"""Serial CPU4 comparison. Fresh worker per process keeps getrusage peak RSS independent."""
import json,os,re,resource,subprocess,sys,time
from pathlib import Path
if len(sys.argv)>1 and sys.argv[1]=='--worker':
 cmd=json.loads(sys.argv[2]); start=time.monotonic()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=900); status=p.returncode; log=p.stdout+p.stderr
 except subprocess.TimeoutExpired as e: status=124;log=str(e)
 u=resource.getrusage(resource.RUSAGE_CHILDREN)
 print(json.dumps(dict(returncode=status,process_wall_s=time.monotonic()-start,cpu_user_s=u.ru_utime,cpu_system_s=u.ru_stime,process_peak_rss_bytes=u.ru_maxrss,log=log)));sys.exit()
import soundfile as sf
import numpy as np
root=Path(__file__).resolve().parents[2];os.chdir(root)
out=root/'outputs/unified-2026-11-07';out.mkdir(parents=True,exist_ok=True)
assets=root/'local/compat/assets';binary=root/'build/compat-profile/bin/audiocpp_cli'
os.environ.update(AUDIOCPP_ESPEAK_LIBRARY='/opt/homebrew/lib/libespeak-ng.dylib',AUDIOCPP_ESPEAK_DATA='/opt/homebrew/share/espeak-ng-data')
text='At nine thirty, please check the train ticket and call the station.'
def base(family,model,task='tts'):
 return [str(binary),'--task',task,'--family',family,'--model',str(assets/model),'--backend','cpu','--threads','4','--metrics','--log'] + (['--seed','42'] if task!='asr' else [])
cases={
'piper':base('piper_tts','Piper-TTS-GGUF/piper-en-us-lessac-medium-orig.gguf'),
'kokoro-baseline':[str(root/'build/compat-cpu/bin/audiocpp_cli')]+base('kokoro_tts','Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf')[1:]+['--voice-id','af_heart','--language','en-us'],
'kokoro-plbert-patch':base('kokoro_tts','Kokoro-82M-GGUF/kokoro-82m-q8_0.gguf')+['--voice-id','af_heart','--language','en-us'],
'kitten':base('kitten_tts','KittenTTS-GGUF/kitten-tts-mini-0.8-orig.gguf'),
'pocket':base('pocket_tts','PocketTTS-GGUF/english/pocket-tts-english-q8_0.gguf')+['--voice-id','alba'],
'zipvoice':base('zipvoice','zipvoice-distill-q8_0.gguf','clon')+['--voice-ref',str(out/'reference.wav'),'--reference-text','The northern wind crossed the quiet harbor.','--session-option','zipvoice.espeak_library_path=/opt/homebrew/lib/libespeak-ng.dylib'],
'f5':base('f5_tts','f5-tts-v1-base-f16.gguf','clon')+['--voice-ref',str(out/'reference.wav'),'--reference-text','The northern wind crossed the quiet harbor.','--session-option','f5_tts.frame_budget=768'],
'moonshine':base('moonshine_asr','Moonshine-Streaming-GGUF/moonshine-streaming-tiny-q8_0.gguf','asr'),
'sensevoice':base('sense_asr','sensevoice-small-q8-audiocpp-v1.gguf','asr')+['--language','en','--request-option','audio_chunk_mode=none'],
'f5-native':[str(root/'build/crisp-f5-compat/f5-native-probe'),str(assets/'f5-tts-v1-base-f16.gguf'),str(out/'reference-24k.f32')],
'whisper':[str(root/'build/whisper-compat/bin/whisper-cli'),'-m',str(assets/'ggml-base.bin'),'-t','4','-l','en','-ng','-nt']}
names=sys.argv[1:] or list(cases)
for name in names:
 for repeat in range(2):
  tag=f'{name}-{repeat+1}';cmd=cases[name].copy()
  if name in ('moonshine','sensevoice'):cmd+=['--audio',str(out/'asr-input.wav'),'--text-out',str(out/(tag+'.txt'))]
  elif name=='whisper':cmd+=['-f',str(out/'asr-input.wav'),'-otxt','-of',str(out/tag)]
  elif name=='f5-native':cmd+=[str(out/(tag+'.f32'))]
  else:cmd+=['--text',text,'--out',str(out/(tag+'.wav'))]
  print('RUN',tag,flush=True)
  p=subprocess.run([sys.executable,__file__,'--worker',json.dumps(cmd)],capture_output=True,text=True,check=True)
  r=json.loads(p.stdout);log=r.pop('log');(out/(tag+'.log')).write_text(log);r.update(name=name,repeat=repeat+1,argv=cmd,metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M)))
  wav=out/(tag+'.wav');txt=out/(tag+'.txt')
  if name=='f5-native' and r['returncode']==0:
   raw=np.fromfile(out/(tag+'.f32'),dtype='float32');sf.write(wav,raw,int(r['metrics']['sample_rate']),subtype='PCM_16')
  if wav.exists():
   x,sr=sf.read(wav);r['audio']=dict(seconds=len(x)/sr,sample_rate=sr,finite=bool(np.isfinite(x).all()),peak=float(np.max(np.abs(x))),rms=float(np.sqrt(np.mean(x*x))))
  if txt.exists():r['transcript']=txt.read_text()
  (out/(tag+'.json')).write_text(json.dumps(r,indent=2)+'\n');print(tag,r['returncode'],r['metrics'],r.get('transcript',''),flush=True)
  if r['returncode']!=0:break
