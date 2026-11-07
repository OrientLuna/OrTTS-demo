"""Aggregate per-process CPU/RSS and CLI inference measurements; run at repo root."""
import json,re,hashlib
from pathlib import Path
import soundfile as sf
import numpy as np
out=Path('outputs/unified-2026-11-07');rows=[]
for p in sorted(out.glob('*-[12].json')):
 r=json.loads(p.read_text());tag=p.stem;log=(out/(tag+'.log')).read_text();r['metrics']=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M))
 if r['name']=='whisper':
  times=dict((k.strip(),float(v)) for k,v in re.findall(r'whisper_print_timings:\s+(.+?) time\s*=\s*([\d.]+) ms',log));r['whisper_timings_ms']=times;r['metrics'].update(wall_ms=str(times['total']-times['load']),rtf=str((times['total']-times['load'])/3692))
 wav=out/(tag+'.wav')
 if wav.exists():
  x,sr=sf.read(wav);r['audio']=dict(seconds=len(x)/sr,sample_rate=sr,finite=bool(np.isfinite(x).all()),peak=float(abs(x).max()),rms=float(np.sqrt(np.mean(x*x))),clipped_fraction=float(np.mean(abs(x)>=1)),sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
 r['cpu_total_s']=r['cpu_user_s']+r['cpu_system_s'];r['process_peak_rss_MiB']=r['process_peak_rss_bytes']/1048576
 if r['name']=='f5-native' and len(r['argv'])==3:r['argv'].append(str(out/(tag+'.f32')))
 r['argv']=[str(a).replace(str(Path.cwd())+'/', '') for a in r['argv']]
 rows.append(r)
report=dict(notes=['Kokoro PL-BERT candidate is not production source; short-text WAV SHA256 matches baseline.','F5 first run includes a 1-second stack sample; DiT F16/F32 dot products were hot.','F5 native and Whisper are independent executors, not integrated backends.'],date='2026-11-07',host='M5 MacBook Air 24GB',os='macOS 27.2 26B123',threads=4,backend='CPU; Metal/CUDA/OpenMP off; Accelerate available',text='At nine thirty, please check the train ticket and call the station.',input_audio_s=3.692,method='Serial separate processes, 2 repetitions, page cache not flushed. RUSAGE_CHILDREN from fresh worker: CPU includes load/inference/exit; macOS ru_maxrss bytes. CLI wall_ms excludes session construction; Whisper total-load includes setup overhead. No energy measurement.',source_revisions=dict(audio_cpp='e9303b76983993cc59576bf6d16d8a0635ae4d85',whisper_cpp='v1.7.6',crispasr='34a3f0007b949a0868fc99c3c43d8920ec3e5e64',crisp_ggml='1b972bb754aa5f83e2d872ccf37a335717f6658d'),results=rows)
report['quality']={}
for name in ['piper','kokoro-baseline','kitten','pocket','zipvoice','f5']:
 check=out/(name+'-check.txt')
 if check.exists():report['quality'][name]={'whisper_base_readback':check.read_text().strip(),'human_listening':'pending'}
if 'f5' in report['quality']:
 report['quality']['f5']['raw_repeat_sha256']=[hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('f5-native-[12].f32'))]
Path('benchmarks/unified-models-macos-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
for name in dict.fromkeys(r['name'] for r in rows):
 rs=[r for r in rows if r['name']==name and r['returncode']==0]
 if not rs:print(name,'FAILED');continue
 def rng(fn):
  vs=[fn(r) for r in rs];return f'{min(vs):.3f}–{max(vs):.3f}'
 print(name,'RTF',rng(lambda r:float(r['metrics']['rtf'])),'rssMiB',rng(lambda r:r['process_peak_rss_MiB']),'cpu',rng(lambda r:r['cpu_total_s']),'process',rng(lambda r:r['process_wall_s']))
