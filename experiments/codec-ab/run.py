#!/usr/bin/env python3
"""Same-generator codec isolation using the existing unified probe; no downloads.

The probe enables timing traces. Three fresh sessions per codec, each one cold
and one warm call. Codes must be identical across all sessions and codecs.
"""
import argparse,hashlib,json,os,re,statistics,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--legacy-pack',type=Path,required=True);p.add_argument('--liquid-pack',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);root=out/'fixed-generation';root.mkdir(exist_ok=True)
 def digest(file):
  h=hashlib.sha256()
  with file.open('rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
  return h.hexdigest()
 for pack,expected in [(a.legacy_pack,'20e24b0bc7fd0e3b58e31dcb409c07102f9e0ddf33f8e70153f69073271b5f7f'),(a.liquid_pack,'2b23c30f658e88ce8b3215e4ea24dacf8898ffca159a7908f61a8942e9e93720')]:
  if digest(pack/'download-manifest.json')!=expected:raise ValueError('Unexpected manifest revision')
  if out.is_relative_to(pack.resolve()):raise ValueError('Output must be outside input pack')
  manifest=json.loads((pack/'download-manifest.json').read_text())
  for asset in manifest['files']:
   needed=(asset['path'].startswith(('native/','P3/predictor/')) or asset['path']=='voices/female.f32') if pack==a.legacy_pack else asset['path'].startswith('native/lc/')
   if needed:
    file=pack/asset['path']
    if file.stat().st_size!=asset['bytes'] or digest(file)!=asset['sha256']:raise ValueError('Asset identity mismatch: '+asset['path'])
 def link(src,dst):
  dst.parent.mkdir(parents=True,exist_ok=True)
  if not dst.exists():os.link(src,dst)
 for src in (a.legacy_pack/'native').rglob('*'):
  if src.is_file():link(src,root/src.relative_to(a.legacy_pack/'native'))
 for src in (a.legacy_pack/'voices').glob('*.f32'):link(src,root/'voices'/src.name)
 alias=root/'tokenizer-control.gguf'
 if not alias.exists():alias.symlink_to('tokenizer-b260k-MIXED_Q4_0.gguf')
 text='你好，欢迎使用 OrTTS。本地语音合成，让交流更加自然。';env=dict(os.environ,ORTTS_CONTROL_MANIFEST_SHA='a4202fc2d5ba0352cd847b02e83fd7382b0a2ba54e3e3aefdc4c82c7aa068228',ORTTS_LC_ASSETS=str((a.liquid_pack/'native/lc').resolve()))
 rows=[];code_hashes=set()
 for i,decoder in enumerate(['b260k','base100k','base100k','b260k','b260k','base100k']):
  directory=out/f'{i}-{decoder}';directory.mkdir(exist_ok=True)
  cmd=[str(a.probe.resolve()),str(root),'streaming',text,str(directory),'2',str((a.legacy_pack/'P3/predictor').resolve()),decoder,'female','control']
  with (directory/'stdout.jsonl').open('w') as stdout,(directory/'stderr.log').open('w') as stderr:subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr,check=True,timeout=180)
  calls=[json.loads(line) for line in (directory/'stdout.jsonl').read_text().splitlines() if line.startswith('{')]
  # The historical probe labels ru_maxrss KiB; Darwin actually returns bytes.
  for call in calls:call['peak_rss_bytes']=call.pop('peak_RSS_KiB')*(1 if sys.platform=='darwin' else 1024)
  trace=(directory/'trace.log').read_text();timing={key:[float(v) for v in re.findall(re.escape(key)+r' ([0-9.eE+-]+)',trace)] for key in ['qwen3_tts.prefill_build_ms','qwen3_tts.talker_ms','qwen3_tts.speech_decoder_ms']}
  codes={file.name:digest(file) for file in directory.glob('codes-*.i32')};code_hashes.update(codes.values())
  if len(calls)!=2 or len(codes)!=2:raise ValueError('Missing benchmark output')
  rows.append({'codec':decoder,'calls':calls,'timing_ms':timing,'codes_sha256':codes,'pcm_sha256':digest(directory/'pcm-1.f32')});print(i,decoder,'PASS',flush=True)
 if len(code_hashes)!=1:raise ValueError('Generated codes differ: not a codec isolation')
 summary={decoder:{'warm_rtf_median':statistics.median(r['calls'][1]['RTF'] for r in rows if r['codec']==decoder),'warm_decoder_ms_median':statistics.median(r['timing_ms']['qwen3_tts.speech_decoder_ms'][-1] for r in rows if r['codec']==decoder),'warm_talker_ms_median':statistics.median(r['timing_ms']['qwen3_tts.talker_ms'][-1] for r in rows if r['codec']==decoder)} for decoder in ['b260k','base100k']}
 report={'text':text,'seed':20261029,'threads':4,'generator':'same legacy talker, P3 safetensors and female embedding; only codec branch changes','same_codes_sha256':next(iter(code_hashes)),'trace_enabled':True,'summary':summary,'sessions':rows,'limits':['Mac CPU result, not phone','timing trace enabled; no pure-kernel or power claim','legacy generator and assets intentionally retained for isolation; not the current LiquidCodec distribution memory footprint','no perceptual quality certificate']};(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
