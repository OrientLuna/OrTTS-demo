#!/usr/bin/env python3
"""Official sherpa Chinese VITS baseline; a separate ONNX executor."""
import sys,json,time,subprocess,re,hashlib,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[2]
a=root/'local/compat/assets/vits-icefall-zh-aishell3';out=root/'outputs/voices-2026-11-07'
text='今天上午九点半，请检查车票和随身行李。'
if len(sys.argv)>1:
 import sherpa_onnx as so
 import soundfile as sf
 sid=int(sys.argv[1]);t=time.monotonic()
 config=so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(vits=so.OfflineTtsVitsModelConfig(model=str(a/'model.onnx'),lexicon=str(a/'lexicon.txt'),tokens=str(a/'tokens.txt')),num_threads=4,provider='cpu'),rule_fsts=','.join(str(a/f) for f in ['phone.fst','date.fst','number.fst']))
 tts=so.OfflineTts(config);load=time.monotonic()-t;t=time.monotonic();audio=tts.generate(text,sid=sid,speed=1.0);wall=time.monotonic()-t
 sf.write(out/f'vits-sid{sid}.wav',audio.samples,audio.sample_rate,subtype='PCM_16')
 print(f'metrics.load_ms={load*1000}\nmetrics.wall_ms={wall*1000}\nmetrics.rtf={wall/(len(audio.samples)/audio.sample_rate)}\nmetrics.num_speakers={tts.num_speakers}\nmetrics.sample_rate={audio.sample_rate}')
 sys.exit()
# Only extract named assets used by this test, excluding the optional 172MiB rule.far.
pack=a.with_suffix('.tar.bz2');meta=json.loads((root/'local/compat/sherpa-tts-release.json').read_text());asset=next(e for e in meta['assets'] if e['name']==pack.name);assert pack.stat().st_size==asset['size']
a.mkdir(exist_ok=True);selected=['model.onnx','lexicon.txt','tokens.txt','speakers.txt','phone.fst','date.fst','number.fst'];receipt={}
with tarfile.open(pack) as tar:
 for name in selected:
  data=tar.extractfile('vits-icefall-zh-aishell3/'+name).read();(a/name).write_bytes(data);receipt[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
results=[]
for sid in [0,21,100]:
 cmd=[sys.executable,str(Path(__file__).resolve()),str(sid)];p=subprocess.run([sys.executable,str(root/'tools/compatibility/compare_local.py'),'--worker',json.dumps(cmd)],capture_output=True,text=True,check=True)
 r=json.loads(p.stdout);log=r.pop('log');(out/f'vits-sid{sid}.log').write_text(log);r.update(sid=sid,metrics=dict(re.findall(r'^metrics\.([^=]+)=(.*)$',log,re.M)));results.append(r);print(sid,r,flush=True)
report=dict(text=text,executor='sherpa-onnx Python 1.13.8, ONNX CPU4; Python/import overhead included in process resources',source_asset={k:asset.get(k) for k in ['id','size','created_at','updated_at','browser_download_url']},archive_sha256_observed=hashlib.file_digest(pack.open('rb'),'sha256').hexdigest(),upstream_digest='not published in release metadata; local hash is a receipt, not independent upstream verification',selected_assets=receipt,results=results)
(root/'benchmarks/vits-zh-voices-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
